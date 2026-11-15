"""
lanec_lib.py
Shared scoring for lane C: causal terciles, the hold-or-close rule against always holding, the
add-on sale, and a trials.csv logger.

Bases (fixed for every trial): outcomes per trade, unit m0 = 0.20 x entry forward + entry bid
premium, net at the touch unless named D_mid (gross at the reaction-close mid, before equity
costs). Intervals: protocol.date_clustered_ci, clusters on the reaction session, 5,000 draws.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
)

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
COLS = ["trial_id", "hypothesis", "mechanism", "block", "n", "effect", "ci_low", "ci_high", "t",
        "null_pct", "basis", "verdict", "secondary"]
BLOCKS = {"discovery": (2013, 2018), "heldout": (2019, 2024)}
MIN_PRIOR = HEDGED.tercile_min_prior  # 200 strictly earlier events before a tercile is issued


def mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def ci(x: pd.Series | np.ndarray, dates: pd.Series) -> dict:
    iv = date_clustered_ci(np.asarray(x, float), dates, mean)
    se = (iv.high - iv.low) / 3.92
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n,
            "t": iv.point / se if se > 0 else np.nan}


def load(path: Path = HERE / "panel.parquet") -> pd.DataFrame:
    p = pd.read_parquet(path)
    p = p[p["lc_status"] == "ok"].copy()
    p["iv_pts"] = 100 * p["iv_post"]
    p["vp_real"] = p["iv_pts"] - 100 * np.sqrt(p["rv_rem"])  # realised vol premium, vol points
    p["block"] = "other"
    for name, (a, b) in BLOCKS.items():
        p.loc[(p["year"] >= a) & (p["year"] <= b), "block"] = name
    return p.sort_values("exit_date").reset_index(drop=True)


def bins(p: pd.DataFrame, signal: pd.Series, n: int = 3) -> np.ndarray:
    """Causal bins over the whole chronological panel (breakpoints from earlier events only)."""
    return hh.causal_bins(signal.to_numpy(float), p["exit_date"], n, MIN_PRIOR)


def hold_or_close(blk: pd.DataFrame, close: np.ndarray) -> dict:
    """Rule book R = B where closed else H; effect R - H (always hold) per event over the block."""
    close = np.asarray(close, bool)
    r = np.where(close, blk["B"], blk["H"])
    eff = ci(r - blk["H"].to_numpy(), blk["exit_date"])
    lvl = ci(r, blk["exit_date"])
    hold_lvl = ci(blk["H"], blk["exit_date"])
    nul = matched_random_null((blk["B"] - blk["H"]).to_numpy(float), close, mean)
    return {"effect": eff, "level_rule": lvl, "level_hold": hold_lvl,
            "null_pct": nul.percentile, "n_closed": int(close.sum()),
            "G_closed": float((blk["H"] - blk["B"])[close].mean()),
            "G_kept": float((blk["H"] - blk["B"])[~close].mean())}


def tmb(blk: pd.DataFrame, col: str, b: np.ndarray) -> tuple[float, float, float]:
    return hh.top_minus_bottom_ci(blk[col].to_numpy(float), b == 2, b == 0, blk["exit_date"])


def log_trial(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLS})


def fmt(x: dict, scale: float = 100.0) -> str:
    return (f"{scale * x['point']:+.3f} [{scale * x['low']:+.3f}, {scale * x['high']:+.3f}] "
            f"N={x['n']} t={x['t']:+.2f}")
