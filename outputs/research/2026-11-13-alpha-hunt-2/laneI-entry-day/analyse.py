"""
analyse.py
Lane I (entry day): coverage, spreads, segment decomposition and the round-1 paired trials.

Round 1 trials (mechanism stated before scoring): selling the same expiry k sessions earlier and
hedging daily collects diffusive premium on the way in (pre-event implied above pre-event
realised) and may pay a narrower relative spread, against the event-variance run-up it sells too
cheaply. The paired difference Dk - S0 (and Dk - D0, same source) in standard m0 tests which wins.
For each event the bin uses its smallest available k in the bin, a rule that does not look at
the outcome.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/analyse.py --set discovery
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score import ci, load, log_trial, signflip_pct  # noqa: E402

BINS = {"k2-3": (2, 3), "k4-6": (4, 6), "k7-10": (7, 10)}
BASIS = "per trade, standard m0, net at the touch, paired Dk minus reference"


def pick_bin(ok: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    """Smallest available k in [lo, hi] per event, among DoltHub early arms."""
    e = ok[ok["arm"].str.match(r"^D\d+$") & ok["k"].between(lo, hi)]
    return e.sort_values("k").drop_duplicates(["ticker", "entry_date"], keep="first")


def paired(early: pd.DataFrame, ref: pd.DataFrame, col: str = "net_m0") -> pd.DataFrame:
    m = early.merge(
        ref[["ticker", "entry_date", col]], on=["ticker", "entry_date"], suffixes=("", "_ref")
    )
    m["diff"] = m[col] - m[f"{col}_ref"]
    return m


def describe(d: pd.DataFrame, ok: pd.DataFrame) -> None:
    s0 = ok[ok["arm"] == "S0"]
    n_ev = s0[["ticker", "entry_date"]].drop_duplicates().shape[0]
    print(f"\n== coverage by arm (events with S0 ok: {n_ev}) ==")
    rows = []
    for k in range(11):
        arm = f"D{k}"
        a = d[d["arm"] == arm]
        st = a["status"].value_counts().to_dict()
        cov = ok[ok["arm"] == arm][["ticker", "entry_date"]].assign(cov=True)
        m = s0.merge(cov, on=["ticker", "entry_date"], how="left")
        m["cov"] = m["cov"].fillna(False).astype(bool)
        rows.append(
            {
                "arm": arm,
                "ok": int(m["cov"].sum()),
                "S0_net_covered": m.loc[m["cov"], "net_m0"].mean(),
                "S0_net_uncovered": m.loc[~m["cov"], "net_m0"].mean(),
                **{s: st.get(s, 0) for s in sorted(st) if s != "ok"},
            }
        )
    print(pd.DataFrame(rows).fillna(0).round(4).to_string(index=False))

    print("\n== entry spread and premium by arm (each arm on its own covered events) ==")
    g = ok[ok["arm"] != "REP"].groupby("arm")
    tab = g.agg(
        n=("net_m0", "size"),
        half_spread_prem=("half_spread_prem", "mean"),
        half_spread_m0=("half_spread_m0", "mean"),
        prem_m0=("prem_m0", "mean"),
        iv_entry=("iv_entry", "mean"),
        net_m0=("net_m0", "mean"),
        gross_mid_m0=("gross_mid_m0", "mean"),
    )
    print(tab.round(4).to_string())

    print("\n== paired with S0 on the same events: spread and net, by arm ==")
    s0c = s0[["ticker", "entry_date", "half_spread_m0", "half_spread_prem", "net_m0", "iv_entry"]]
    out = []
    for k in range(11):
        e = ok[ok["arm"] == f"D{k}"]
        m = e.merge(s0c, on=["ticker", "entry_date"], suffixes=("", "_s0"))
        if len(m) < 20:
            continue
        out.append(
            {
                "arm": f"D{k}",
                "n": len(m),
                "hs_m0": m["half_spread_m0"].mean(),
                "hs_m0_S0": m["half_spread_m0_s0"].mean(),
                "hs_prem": m["half_spread_prem"].mean(),
                "hs_prem_S0": m["half_spread_prem_s0"].mean(),
                "iv": m["iv_entry"].mean(),
                "iv_S0": m["iv_entry_s0"].mean(),
                "net": m["net_m0"].mean(),
                "net_S0": m["net_m0_s0"].mean(),
                "diff": (m["net_m0"] - m["net_m0_s0"]).mean(),
            }
        )
    print(pd.DataFrame(out).round(4).to_string(index=False))

    print("\n== segment decomposition (per m0; rows with both Databento marks) ==")
    segs = [
        "entry_spread_m0",
        "seg_runup_m0",
        "runup_hedge_m0",
        "runup_cost_m0",
        "seg_event_m0",
        "seg_post_m0",
        "fees_m0",
        "net_m0",
    ]
    full = ok[ok["arm"] != "REP"].dropna(subset=["seg_event_m0", "seg_post_m0"])
    print(full.groupby("arm")[segs].mean().assign(n=full.groupby("arm").size()).round(4).to_string())


def round1(ok: pd.DataFrame, block: str, first_id: int) -> None:
    s0 = ok[ok["arm"] == "S0"]
    d0 = ok[ok["arm"] == "D0"]
    tid = first_id
    for ref_name, ref in (("S0", s0), ("D0", d0)):
        for name, (lo, hi) in BINS.items():
            m = paired(pick_bin(ok, lo, hi), ref)
            c = ci(m["diff"], m["exit_date"])
            lvl = ci(m["net_m0"], m["exit_date"])
            pct = signflip_pct(m["diff"], m["exit_date"])
            print(
                f"T{tid} {name} minus {ref_name}: N={c['n']} diff {c['point']:+.4f} "
                f"[{c['low']:+.4f}, {c['high']:+.4f}] t={c['t']:+.2f} flip-pct {pct:.1f}; "
                f"early level {lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}]; "
                f"ref level {m['net_m0_ref'].mean():+.4f}"
            )
            log_trial(
                {
                    "trial_id": tid,
                    "hypothesis": f"Sell the front straddle {lo}-{hi} sessions before D0 "
                    f"(DoltHub EOD bid), hedge daily, beats {ref_name} on the same events",
                    "mechanism": "hedged pre-event diffusive premium plus narrower relative "
                    "spread outweigh the event-variance run-up sold early",
                    "block": block,
                    "n": c["n"],
                    "effect": round(c["point"], 5),
                    "ci_low": round(c["low"], 5),
                    "ci_high": round(c["high"], 5),
                    "t": round(c["t"], 2),
                    "null_pct": round(pct, 1),
                    "basis": BASIS.replace("reference", ref_name),
                    "verdict": f"exploratory; early level {lvl['point']:+.4f} "
                    f"[{lvl['low']:+.4f}, {lvl['high']:+.4f}], ref level "
                    f"{m['net_m0_ref'].mean():+.4f}",
                }
            )
            tid += 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Lane I round 1")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--trials", action="store_true", help="score and log the round-1 trials")
    a = ap.parse_args()
    d, ok = load(a.set)
    describe(d, ok)
    if a.trials:
        round1(ok, f"{a.set} (names A-CHD, 2019-24)", 2021)


if __name__ == "__main__":
    main()
