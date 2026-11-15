"""
score.py
Lane I (entry day): descriptive tables and scoring helpers for the earlier-entry hedged hold.

Reads ``arms_<set>.parquet`` from ``build.py``. Every interval is date-clustered on the reaction
session (``protocol.date_clustered_ci``); the null percentile of a paired change is the share of
date-cluster sign-flip draws below the observed mean (the no-effect null for a change to the
trade); the null percentile of a conditional rule is ``protocol.matched_random_null``.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/score.py --set discovery
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

TRIALS = HERE / "trials.csv"
COLS = [
    "trial_id",
    "hypothesis",
    "mechanism",
    "block",
    "n",
    "effect",
    "ci_low",
    "ci_high",
    "t",
    "null_pct",
    "basis",
    "verdict",
]
N_FLIP = 5000
SEED = 0
FWD_TOL = 0.05  # DoltHub parity forward vs CRSP close; beyond 5% the snapshot is not that day's


def mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def ci(x: pd.Series, dates: pd.Series) -> dict:
    iv = date_clustered_ci(x.to_numpy(float), dates, mean)
    se = (iv.high - iv.low) / (2 * 1.96)
    return {
        "point": iv.point,
        "low": iv.low,
        "high": iv.high,
        "n": iv.n,
        "clusters": iv.clusters,
        "t": iv.point / se if se > 0 else float("nan"),
    }


def signflip_pct(x: pd.Series, dates: pd.Series) -> float:
    """Percentile of the observed mean among date-cluster sign-flip draws (no-effect null)."""
    d = pd.DataFrame({"x": x.to_numpy(float), "d": pd.to_datetime(dates).dt.normalize()})
    d = d[np.isfinite(d["x"])]
    s = d.groupby("d")["x"].sum().to_numpy()
    n = len(d)
    obs = s.sum() / n
    rng = np.random.default_rng(SEED)
    draws = (rng.choice([-1.0, 1.0], size=(N_FLIP, s.size)) * s).sum(axis=1) / n
    return float(100.0 * (draws < obs).mean())


def log_trial(row: dict) -> None:
    """Append one scored trial to trials.csv (never rewrites earlier rows)."""
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in COLS})


def load(which: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All arm rows, and the ok rows with the forward sanity filter applied (funnel printed)."""
    d = pd.read_parquet(HERE / f"arms_{which}.parquet")
    ok = d[d["status"] == "ok"].copy()
    return d, ok


def wide(ok: pd.DataFrame, col: str) -> pd.DataFrame:
    w = ok[ok["arm"] != "REP"].pivot_table(
        index=["ticker", "entry_date", "exit_date"], columns="arm", values=col, aggfunc="first"
    )
    return w.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser(description="Lane I descriptive tables")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    d, ok = load(a.set)
    print(d.groupby(["arm", "status"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
