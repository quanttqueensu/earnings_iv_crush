"""
round3.py
Lane I (entry day), round 3: use the extra days for a resting sale instead of a taker sale.

Round 2 showed the early sale is fair at the mid and loses only its larger touch cost. An early
entry's real asset is time: a sell order can rest for k sessions. T2031 rests a straddle offer at
the D-k DoltHub mid on the k7-10 entry day's strike and expiry; it is deemed filled, at the limit,
on the first later DoltHub end-of-day snapshot (or the D0 15:59 Databento quote) whose straddle
bid reaches the limit; unfilled offers are cancelled and the event is sold at the standard S0
15:59 bid. T2032 rests at the D-k ask instead (fills only after a run-up). A filled sale is hedged
from its fill close on, like every other arm. Quote-through on end-of-day snapshots is a
conservative fill rule (intraday crossings between snapshots are missed), and a fill that is
picked off by a vol rise shows up as a sale below the later bid, inside the P&L.

Nearest prior work: the resting-entry studies at D0 (maker F1 in docs/RESEARCH_STATE.md, and
research/execution/2026-11-13-maker-entry-confirmation), which rest for minutes before the 15:59
sale; this rests for days and changes the entry session.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/round3.py --set discovery
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from analyse import pick_bin  # noqa: E402
from build import FEATURES, databento_chain, hold, simulate  # noqa: E402
from pull import cached, shift  # noqa: E402
from score import ci, log_trial, signflip_pct  # noqa: E402

from earnings_iv_crush.research.hedged_hold import straddle_iv, year_frac  # noqa: E402


def straddle_touch(ch: pd.DataFrame | None, expiry: pd.Timestamp, k: float) -> tuple[float, float]:
    """(bid, mid) of the straddle at strike k, NaN unless both legs are two-sided."""
    if ch is None or ch.empty:
        return float("nan"), float("nan")
    s = ch[(ch["expiry"] == expiry) & np.isclose(ch["strike"], k)]
    if set(s["right"]) != {"C", "P"} or len(s) != 2:
        return float("nan"), float("nan")
    if (s["bid"] <= 0).any() or (s["ask"] < s["bid"]).any():
        return float("nan"), float("nan")
    return float(s["bid"].sum()), float((s["bid"] + s["ask"]).sum() / 2)


def resting(r: pd.Series, s0: pd.Series, lam: float, crsp: dict, permno: float) -> dict:
    d0, exp, k = pd.Timestamp(r["entry_date"]), pd.Timestamp(r["expiry"]), float(r["strike"])
    limit = r["mid"] + lam * (r["ask"] - r["mid"])
    kk = int(r["k"])
    fill_day, fill_mid, src = None, np.nan, "none"
    for j in range(kk - 1, -1, -1):
        day = shift(d0, -j)
        if j == 0:
            bid, mid = straddle_touch(databento_chain(r["ticker"], d0), exp, k)
            source = "databento_d0"
        else:
            p = cached(r["ticker"], day)
            bid, mid = straddle_touch(pd.read_parquet(p) if p else None, exp, k)
            source = "dolthub"
        if np.isfinite(bid) and bid >= limit:
            fill_day, fill_mid, src = day, mid, source
            break
    if fill_day is None:
        return {"filled": False, "net_rest": s0["net_m0"], "src": src, "limit": limit}
    st, g = hold.stock_path(crsp, permno, fill_day, exp)
    if st != "ok" or g is None:
        return {"filled": True, "net_rest": np.nan, "src": f"path_{st}", "limit": limit}
    sig_pre = straddle_iv(fill_mid, r["fwd"], k, year_frac(fill_day, exp))
    if not np.isfinite(sig_pre):
        sig_pre = r["iv_entry"]
    res = simulate(
        g=g,
        entry=fill_day,
        hedge_from=fill_day,
        d0=d0,
        t1=pd.Timestamp(r["exit_date"]),
        expiry_last=g.index[-1],
        expiry=exp,
        k=k,
        fwd=r["fwd"],
        bid=limit,
        mid=fill_mid,
        sig_pre=sig_pre,
        sig_post=r["sig_post"],
    )
    return {
        "filled": True,
        "net_rest": res["net"] / r["m0"],
        "src": src,
        "limit": limit,
        "fill_k": (pd.Index(hold.nyse_sessions(fill_day, d0)).size - 1),
        "below_bid_m0": (limit - fill_mid) / r["m0"],
    }


def run(which: str, ids: dict[float, int]) -> None:
    d = pd.read_parquet(HERE / f"arms_{which}.parquet")
    ok = d[d["status"] == "ok"]
    s0 = ok[ok["arm"] == "S0"].set_index(["ticker", "entry_date"])
    e = pick_bin(ok, 7, 10).reset_index(drop=True)
    feats = pd.read_parquet(FEATURES)
    feats["entry_date"] = pd.to_datetime(feats["entry_date"])
    permno = feats.drop_duplicates(["ticker", "entry_date"]).set_index(["ticker", "entry_date"])[
        "permno"
    ]
    crsp = hold.load_crsp()
    block = f"{which} (k7-10 bin, 2019-24)"
    for lam, tid in ids.items():
        rows = []
        for _, r in e.iterrows():
            key = (r["ticker"], r["entry_date"])
            rows.append(resting(r, s0.loc[key], lam, crsp, permno[key]))
        x = pd.concat([e, pd.DataFrame(rows)], axis=1)
        x["net_s0"] = [s0.loc[(a, b), "net_m0"] for a, b in zip(x["ticker"], x["entry_date"])]
        print(f"  lambda {lam}: fill sources {x['src'].value_counts().to_dict()}")
        x = x.dropna(subset=["net_rest"])
        dd = x["net_rest"] - x["net_s0"]
        c = ci(dd, x["exit_date"])
        pct = signflip_pct(dd, x["exit_date"])
        lvl = ci(x["net_rest"], x["exit_date"])
        f = x[x["filled"].astype(bool)]
        cf = ci(f["net_rest"] - f["net_s0"], f["exit_date"]) if len(f) > 30 else None
        print(
            f"T{tid} resting at mid+{lam}*half-spread: N={c['n']} fill rate "
            f"{x['filled'].mean():.3f}; book minus S0 {c['point']:+.4f} [{c['low']:+.4f}, "
            f"{c['high']:+.4f}] t={c['t']:+.2f} flip {pct:.1f}; book level {lvl['point']:+.4f} "
            f"[{lvl['low']:+.4f}, {lvl['high']:+.4f}] vs S0 {x['net_s0'].mean():+.4f}"
        )
        if cf:
            print(
                f"    filled only: N={cf['n']} diff {cf['point']:+.4f} [{cf['low']:+.4f}, "
                f"{cf['high']:+.4f}]; sale below fill-day mid {f['below_bid_m0'].mean():+.4f} m0; "
                f"filled S0 mean {f['net_s0'].mean():+.4f} vs unfilled "
                f"{x.loc[~x['filled'].astype(bool), 'net_s0'].mean():+.4f}"
            )
        log_trial(
            {
                "trial_id": tid,
                "hypothesis": f"Rest a straddle offer at the D-k mid + {lam} x half-spread from "
                "the k7-10 entry day, fill on EOD quote-through, else sell at S0; beats S0",
                "mechanism": "the early day's value is time to rest a passive sale and collect "
                "the half-spread a taker pays",
                "block": block,
                "n": c["n"],
                "effect": round(c["point"], 5),
                "ci_low": round(c["low"], 5),
                "ci_high": round(c["high"], 5),
                "t": round(c["t"], 2),
                "null_pct": round(pct, 1),
                "basis": "per trade, standard m0, net (fill at the limit, else 15:59 bid), paired "
                "minus S0; modelled quote-through fills",
                "verdict": f"exploratory, modelled fills; fill rate {x['filled'].mean():.3f}; "
                f"book level {lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}]",
            }
        )
        x.to_parquet(HERE / f"round3_{which}_lam{lam}.parquet")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lane I round 3")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    run(a.set, {0.0: 2031, 1.0: 2032})


if __name__ == "__main__":
    main()
