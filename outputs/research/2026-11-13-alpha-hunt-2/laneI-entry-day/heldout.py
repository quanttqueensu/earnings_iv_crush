"""
heldout.py
Lane I (entry day): the single held-out read frozen in freeze_2026-11-13_early-entry-heldout.md.

Refuses to run if the freeze note's SHA-256 differs from the value recorded at freeze time.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/heldout.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from analyse import describe, paired, pick_bin  # noqa: E402
from score import ci, load, log_trial, signflip_pct  # noqa: E402

FREEZE = HERE / "freeze_2026-11-13_early-entry-heldout.md"
FREEZE_SHA = (HERE / "freeze_sha256.txt").read_text().split()[0]
BLOCK = "held-out (names after CHD, seeded sample, 2019-24)"
SPEC = [
    (2034, (2, 3), "S0", "greater", "Selling 2-3 sessions earlier beats the standard S0 sale"),
    (2035, (2, 3), "D0", "greater", "At a matched DoltHub source, 2-3 sessions earlier beats D0"),
    (2036, (7, 10), "S0", "less", "Cost check: selling 7-10 sessions earlier loses to S0"),
]


def main() -> None:
    sha = hashlib.sha256(FREEZE.read_bytes()).hexdigest()
    if sha != FREEZE_SHA:
        raise SystemExit(f"freeze note changed: {sha} != {FREEZE_SHA}")
    print(f"freeze verified {sha[:12]}")
    d, ok = load("heldout")
    describe(d, ok)
    s0 = ok[ok["arm"] == "S0"]
    d0 = ok[ok["arm"] == "D0"]
    for tid, (lo, hi), ref_name, side, hyp in SPEC:
        ref = s0 if ref_name == "S0" else d0
        m = paired(pick_bin(ok, lo, hi), ref)
        c = ci(m["diff"], m["exit_date"])
        pct = signflip_pct(m["diff"], m["exit_date"])
        lvl = ci(m["net_m0"], m["exit_date"])
        g = paired(pick_bin(ok, lo, hi), ref, "gross_mid_m0")
        cg = ci(g["diff"], g["exit_date"])
        if side == "greater":
            ok_pass = c["point"] > 0 and c["t"] >= 3 and pct >= 95
        else:
            ok_pass = c["high"] < 0
        verdict = "PASS" if ok_pass else "FAIL"
        print(
            f"T{tid} k{lo}-{hi} minus {ref_name}: N={c['n']} ({c['clusters']} dates) diff "
            f"{c['point']:+.4f} [{c['low']:+.4f}, {c['high']:+.4f}] t={c['t']:+.2f} flip-pct "
            f"{pct:.1f}; gross-at-mid diff {cg['point']:+.4f} [{cg['low']:+.4f}, "
            f"{cg['high']:+.4f}]; early level {lvl['point']:+.4f} [{lvl['low']:+.4f}, "
            f"{lvl['high']:+.4f}], ref level {m['net_m0_ref'].mean():+.4f} -> {verdict}"
        )
        log_trial(
            {
                "trial_id": tid,
                "hypothesis": hyp,
                "mechanism": "frozen in freeze_2026-11-13_early-entry-heldout.md (sha "
                f"{sha[:12]})",
                "block": BLOCK,
                "n": c["n"],
                "effect": round(c["point"], 5),
                "ci_low": round(c["low"], 5),
                "ci_high": round(c["high"], 5),
                "t": round(c["t"], 2),
                "null_pct": round(pct, 1),
                "basis": f"per trade, standard m0, net at the touch, paired minus {ref_name}",
                "verdict": f"{verdict} (held-out, discovery-derived, exploratory); gross-at-mid "
                f"diff {cg['point']:+.4f} [{cg['low']:+.4f}, {cg['high']:+.4f}]; early level "
                f"{lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}]",
            }
        )
    m = d0.merge(s0, on=["ticker", "entry_date"], suffixes=("", "_s"))
    m = m[np.isclose(m["strike"], m["strike_s"])]
    print(
        f"same-day calibration: N={len(m)}; DoltHub/Databento mid gap median "
        f"{(m['mid'] / m['mid_s'] - 1).median():+.4f}; half-spread of premium DoltHub "
        f"{m['half_spread_prem'].mean():.4f} vs Databento {m['half_spread_prem_s'].mean():.4f}"
    )
    emp = d[d["status"] == "empty_snapshot"][["ticker", "entry_date"]].drop_duplicates()
    a = s0.merge(emp.assign(e=1), on=["ticker", "entry_date"], how="left")
    a["e"] = a["e"].fillna(0)
    dd = a.groupby("e")["net_m0"].agg(["size", "mean"])
    print(f"S0 net by any-empty-snapshot flag:\n{dd.round(4).to_string()}")
    pd.DataFrame({"sha": [sha]}).to_csv(HERE / "heldout_read_done.csv", index=False)


if __name__ == "__main__":
    if (HERE / "heldout_read_done.csv").exists():
        raise SystemExit("held-out read already run once")
    main()
