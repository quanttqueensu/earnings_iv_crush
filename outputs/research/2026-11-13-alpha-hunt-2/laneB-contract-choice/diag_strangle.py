"""
diag_strangle.py
Descriptive, discovery block only (entry 2013-18): where the vega-matched IM/2 strangle with
vol-tight wings (trial 1,821) loses, per event. Not a trial; nothing here is scored as a rule.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/diag_strangle.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import score as sc  # noqa: E402


def main() -> None:
    d = sc.load()
    d = d[d["year"].between(2013, 2018) & d["status_b"].eq("ok")]
    w = pd.read_parquet(HERE / "wings.parquet")
    w["entry_date"] = pd.to_datetime(w["entry_date"])
    e = d.merge(w, on=["ticker", "entry_date"], suffixes=("", "_w"))
    e = e[e["wstatus"].eq("ok") & e["tw_status"].eq("ok")].copy()
    vh = sc._h_vega(e)
    vt = sc._pair_vega(e, "tc", "tp")
    sc_ = vh / vt / e["m0"].to_numpy()
    e["S"] = e["tw_usd"].to_numpy() * sc_
    e["S_mid"] = e["tw_usd_mid"].to_numpy() * sc_
    e["S_spread"] = (
        (e["tc_ask"] - e["tc_bid"] + e["tp_ask"] - e["tp_bid"]) / 2 * sc_
    )
    e["H_spread"] = (e["mid0"] - e["s0"]) / e["m0"]
    e["mr"] = e["abs_move"] / e["im"]
    print(f"N {len(e)}; mean S {e['S'].mean():+.4%}, S_mid {e['S_mid'].mean():+.4%}, "
          f"entry half-spread S {e['S_spread'].mean():.4%} vs H {e['H_spread'].mean():.4%}")
    print("other costs (mid - touch - entry half-spread):",
          f"{(e['S_mid'] - e['S'] - e['S_spread']).mean():+.4%}")
    for col, bins in (("mr", [0, 0.5, 1, 1.5, 2, 3, np.inf]),):
        g = e.groupby(pd.cut(e[col], bins), observed=True)
        t = g.agg(n=("S", "size"), S=("S", "mean"), H=("H", "mean"), S_mid=("S_mid", "mean"))
        t["S_sum_share"] = g["S"].sum() / e["S"].sum()
        print(f"\nby {col}:\n{t.round(4).to_string()}")
    e["spr_q"] = pd.qcut(e["S_spread"], 3, labels=["tight", "mid", "wide"])
    print("\nby strangle entry half-spread tercile:")
    print(e.groupby("spr_q", observed=True)[["S", "S_mid", "H", "S_spread"]].mean().round(4))
    print("\nby year:")
    print(e.groupby("year")[["S", "S_mid", "H"]].mean().round(4))
    print("\nworst 10 events (S, unit m0):")
    print(e.nsmallest(10, "S")[["ticker", "entry_date", "S", "H", "mr", "im"]].to_string())
    k = max(1, len(e) // 100)
    print(f"\nshare of total S from worst 1% ({k} events): "
          f"{e.nsmallest(k, 'S')['S'].sum() / e['S'].sum():.2f}")
    print(f"mean S excluding worst 1%: {e.drop(e.nsmallest(k, 'S').index)['S'].mean():+.4%}")


if __name__ == "__main__":
    main()
