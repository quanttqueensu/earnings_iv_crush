"""s02_score.py: event surplus of gold and silver implied variance over realised, by block.

Reads events.parquet (s01_build.py) and scores the pre-registered statistic in diagnosis.log:
S = (eQ - eP) / u per event session, its mean with a date-clustered 95% interval and a
calendar-month-clustered interval beside it, for each trial (2,412 GLD pooled, 2,413 SLV pooled,
2,414 to 2,416 GLD by release type). The held-out block runs only when the freeze note exists and
records this file's SHA-256; it appends one line to trials.csv per trial.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s02_score.py discovery
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s02_score.py heldout
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

EVENTS = HERE / "events.parquet"
FREEZE = HERE / "freeze_heldout.md"
TRIALS = HERE / "trials.csv"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def score(ev: pd.DataFrame) -> dict[str, object]:
    eq = -(ev["dW"] - ev["ctrl_dW_mean"])
    ep = ev["r2"] - ev["ctrl_r2_mean"]
    s = (eq - ep) / ev["u"]
    d = pd.to_datetime(ev["date"])
    ci = date_clustered_ci(s.to_numpy(), d.to_numpy(), stat=_mean)
    month = d.dt.to_period("M").dt.to_timestamp()
    ci_m = date_clustered_ci(s.to_numpy(), month.to_numpy(), stat=_mean)
    eq_u = (eq / ev["u"]).to_numpy()
    ep_u = (ep / ev["u"]).to_numpy()
    ci_eq = date_clustered_ci(eq_u, d.to_numpy(), stat=_mean)
    ci_ep = date_clustered_ci(ep_u, d.to_numpy(), stat=_mean)
    su = (eq - ep).to_numpy()
    u = ev["u"].to_numpy()
    eqv = eq.to_numpy()
    pi1 = float(su.mean() / (2 * (u.mean() + eqv.mean())))
    pi3 = float(su.mean() / (2 * (3 * u.mean() + eqv.mean())))
    return {
        "n": int(len(ev)),
        "S_mean": ci.point,
        "S_lo": ci.low,
        "S_hi": ci.high,
        "S_month_lo": ci_m.low,
        "S_month_hi": ci_m.high,
        "S_median": float(np.median(s)),
        "share_S_pos": float((s > 0).mean()),
        "eQ_u_mean": ci_eq.point,
        "eQ_u_lo": ci_eq.low,
        "eQ_u_hi": ci_eq.high,
        "eP_u_mean": ci_ep.point,
        "eP_u_lo": ci_ep.low,
        "eP_u_hi": ci_ep.high,
        "pi_1": pi1,
        "pi_3": pi3,
        "u_mean": float(u.mean()),
        "eQ_mean": float(eqv.mean()),
    }


TRIAL_SETS = {
    2412: ("GLD", lambda k: k != "", "GLD all CPI, payrolls, FOMC sessions"),
    2413: ("SLV", lambda k: k != "", "SLV all CPI, payrolls, FOMC sessions"),
    2414: ("GLD", lambda k: "fomc" in k, "GLD FOMC sessions"),
    2415: ("GLD", lambda k: k == "cpi", "GLD CPI sessions"),
    2416: ("GLD", lambda k: k == "nfp", "GLD payrolls sessions"),
}


def main(block: str) -> None:
    if block not in ("discovery", "heldout"):
        raise SystemExit("block must be discovery or heldout")
    me = Path(__file__).resolve()
    if block == "heldout":
        if not FREEZE.exists():
            raise SystemExit("held-out read refused: no freeze note")
        if _sha(me) not in FREEZE.read_text(encoding="utf-8"):
            raise SystemExit("held-out read refused: scorer hash not recorded in the freeze note")
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev["block"] == block]
    results = {}
    for tid, (sym, sel, label) in TRIAL_SETS.items():
        sub = ev[(ev["sym"] == sym) & ev["kind"].map(sel)]
        if len(sub) < 10:
            print(f"trial {tid} {label}: N={len(sub)} too small, not scored")
            continue
        r = score(sub)
        results[tid] = {"label": label, "block": block, **r}
        print(
            f"trial {tid} {label} [{block}] N={r['n']}: mean S {r['S_mean']:+.3f} "
            f"[{r['S_lo']:+.3f}, {r['S_hi']:+.3f}] (month-clustered [{r['S_month_lo']:+.3f}, "
            f"{r['S_month_hi']:+.3f}]), median {r['S_median']:+.3f}, share>0 {r['share_S_pos']:.2f}; "
            f"eQ/u {r['eQ_u_mean']:+.3f} [{r['eQ_u_lo']:+.3f}, {r['eQ_u_hi']:+.3f}], "
            f"eP/u {r['eP_u_mean']:+.3f} [{r['eP_u_lo']:+.3f}, {r['eP_u_hi']:+.3f}]; "
            f"pi_1 {r['pi_1']:+.4f}, pi_3 {r['pi_3']:+.4f} of premium (mid, gross)"
        )
    out = HERE / f"results_{block}.json"
    out.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    if block == "heldout":
        rows = []
        for tid, r in results.items():
            passed = r["S_mean"] > 0 and r["S_lo"] > 0
            rows.append(
                {
                    "trial": tid,
                    "label": r["label"],
                    "block": "heldout 2022-01-03 to 2026-10-30",
                    "n": r["n"],
                    "statistic": "mean S, ordinary-day equivalents, gross at mid (index)",
                    "point": round(r["S_mean"], 4),
                    "ci_low": round(r["S_lo"], 4),
                    "ci_high": round(r["S_hi"], 4),
                    "pass": passed if tid in (2412, 2413) else "descriptive",
                }
            )
        pd.DataFrame(rows).to_csv(HERE / "trials_heldout_rows.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "discovery")
