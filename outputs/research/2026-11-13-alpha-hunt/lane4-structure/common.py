"""common.py: shared loaders, arm construction and inference for the lane-4 structure studies."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

COMM = 0.0065  # USD 0.65 per contract per leg per side, per share
MARGIN_SPOT = 0.20  # the book's Reg-T approximation: 0.20 x forward + premium sold


def ci(x: pd.Series, dates: pd.Series, stat=None) -> tuple[float, float, float, int]:
    ok = np.isfinite(x.to_numpy(dtype=float))
    x, dates = x[ok], dates[ok]
    if len(x) < 5:
        return (np.nan, np.nan, np.nan, int(len(x)))
    c = date_clustered_ci(x, dates, stat or (lambda a: float(np.mean(a))))
    return (c.point, c.low, c.high, int(len(x)))


def tstat(x: pd.Series, dates: pd.Series) -> float:
    """Date-clustered t: mean over the standard error of date-cluster sums (CR0)."""
    ok = np.isfinite(x.to_numpy(dtype=float))
    x, dates = x[ok], dates[ok]
    n = len(x)
    if n < 5:
        return np.nan
    m = x.mean()
    s = (x - m).groupby(dates.to_numpy()).sum()
    se = np.sqrt((s**2).sum()) / n
    return float(m / se) if se > 0 else np.nan


def fmt(c: tuple[float, float, float, int], scale: float = 100.0) -> str:
    return f"{scale*c[0]:+.2f} [{scale*c[1]:+.2f}, {scale*c[2]:+.2f}] N={c[3]}"


def load_ticks() -> pd.DataFrame:
    """Tick panel with summed straddle quotes at each clock, forward and margin."""
    r = pd.read_parquet(OUT / "tick_panel.parquet")
    r["entry_date"] = pd.to_datetime(r["entry_date"])
    r["exit_date"] = pd.to_datetime(r["exit_date"])
    for tag, clocks in (("en", ("15:00", "15:30", "15:35", "15:40", "15:45", "15:50", "15:55", "15:59")),
                        ("ex", ("15:01", "15:15", "15:30", "15:45", "15:55", "15:59"))):
        for t in clocks:
            cb, pb = r[f"{tag}_C_{t}_bid"], r[f"{tag}_P_{t}_bid"]
            ca, pa = r[f"{tag}_C_{t}_ask"], r[f"{tag}_P_{t}_ask"]
            two = (cb > 0) & (pb > 0) & (ca > cb) & (pa > pb)
            askok = (ca > 0) & (pa > 0)
            r[f"{tag}_bid_{t}"] = np.where(two, cb + pb, np.nan)  # two-sided on both legs
            r[f"{tag}_ask_{t}"] = np.where(askok, ca + pa, np.nan)
            r[f"{tag}_bid0_{t}"] = np.where(askok, cb.clip(lower=0).fillna(0) + pb.clip(lower=0).fillna(0), np.nan)
            r[f"{tag}_two_{t}"] = two
            r[f"{tag}_minsz_bid_{t}"] = np.minimum(r[f"{tag}_C_{t}_bsz"], r[f"{tag}_P_{t}_bsz"])
            r[f"{tag}_minsz_ask_{t}"] = np.minimum(r[f"{tag}_C_{t}_asz"], r[f"{tag}_P_{t}_asz"])
    cm = (r["en_C_15:59_bid"] + r["en_C_15:59_ask"]) / 2
    pm = (r["en_P_15:59_bid"] + r["en_P_15:59_ask"]) / 2
    r["fwd"] = r["strike"] + cm - pm
    r["m0"] = MARGIN_SPOT * r["fwd"] + r["en_bid_15:59"]
    r["mid0"] = (r["en_bid_15:59"] + r["en_ask_15:59"]) / 2
    r["hs0"] = (r["en_ask_15:59"] - r["en_bid_15:59"]) / (2 * r["mid0"])
    r["dte"] = (pd.to_datetime(r["expiry"]) - r["entry_date"]).dt.days
    return r


TRIALS = OUT / "trials.csv"
_COLS = ["trial_id", "hypothesis", "mechanism", "block", "n", "effect", "ci_low", "ci_high", "t",
         "null_pct", "basis", "verdict"]


def log_trial(trial_id: int, hypothesis: str, mechanism: str, block: str, x: pd.Series | None,
              dates: pd.Series | None, basis: str, verdict: str, null_pct: float = np.nan,
              override: tuple | None = None) -> None:
    """Append one scored variant to trials.csv (replacing an earlier row with the same id and block)."""
    if override is None:
        c = ci(x, dates)
        t = tstat(x, dates)
    else:
        c, t = override[:4], override[4]
    row = dict(zip(_COLS, [trial_id, hypothesis, mechanism, block, c[3], c[0], c[1], c[2], t, null_pct,
                           basis, verdict]))
    old = pd.read_csv(TRIALS) if TRIALS.exists() else pd.DataFrame(columns=_COLS)
    old = old[~((old["trial_id"] == trial_id) & (old["block"] == block))]
    new = pd.DataFrame([row]) if old.empty else pd.concat([old, pd.DataFrame([row])], ignore_index=True)
    new.sort_values(["trial_id", "block"]).to_csv(TRIALS, index=False)
    print(f"  [trial {trial_id} | {block}] {hypothesis}: {fmt(c)} t={t:+.2f} null={null_pct} -> {verdict}")


def split_ticks(r: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Discovery: broad events entered in 2025. Held out: broad events entered in 2026. Megacap apart."""
    b = r[r["block"] == "broad_2025_2026"]
    return {"disc_broad_2025": b[b["entry_date"] < "2026-01-01"],
            "held_broad_2026H1": b[b["entry_date"] >= "2026-01-01"],
            "megacap_2023_24": r[r["block"] == "megacap_2023_2024"]}
