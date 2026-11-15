"""vxlib.py: shared trade construction for the N09 VIX-complex pilot.

Builds event and matched-control windows on the CFE VX daily settlement panel and scores them
with the project's date-clustered bootstrap. Prices are daily settlements (VWAP or mid at 15:00
Chicago), so every net figure subtracts an explicit touch cost; see ``diagnosis.log``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
)

LANE = Path(__file__).resolve().parents[1]


# ── constants (rationale in diagnosis.log entry 1) ──
@dataclass(frozen=True)
class CostModel:
    primary_rt: float = 0.055  # one-tick market crossed both sides (2 x 0.025) + ~$5 fees / $1,000
    stress_rt: float = 0.105  # a full tick paid each side + fees
    primary_entry_only: float = 0.0275  # cash-settled trades pay one side only
    stress_entry_only: float = 0.0525


COST = CostModel()
CONTROL_HALF_WINDOW_DAYS = 35  # same weekday within +-5 weeks: about 10 controls per event


@dataclass(frozen=True)
class Split:
    start: str
    end: str


DISC_FOMC = Split("2008-01-01", "2016-12-31")
HELD_FOMC = Split("2017-01-01", "2026-11-12")
DISC_MACRO = Split("2016-01-01", "2020-12-31")
HELD_MACRO = Split("2021-01-01", "2026-11-12")


# ── data ──
def load() -> tuple[pd.DataFrame, pd.Series, pd.DatetimeIndex, pd.DataFrame, pd.DataFrame]:
    vx = pd.read_parquet(LANE / "data/vx_panel.parquet")
    settle = vx.pivot(index="trade_date", columns="contract", values="settle")
    expiry = vx.groupby("contract")["expiry"].first()
    days = pd.DatetimeIndex(sorted(vx["trade_date"].unique()))
    ev = pd.read_csv(LANE / "data/events.csv", parse_dates=["date"])
    idx = pd.read_parquet(LANE / "data/indices.parquet")
    return settle, expiry, days, ev, idx


def prev_day(days: pd.DatetimeIndex, d: pd.Timestamp) -> pd.Timestamp | None:
    i = days.searchsorted(d) - 1
    return days[i] if i >= 0 else None


def nth_contract(expiry: pd.Series, after: pd.Timestamp, n: int) -> int | None:
    live = expiry[expiry > after].sort_values()
    return int(live.index[n - 1]) if len(live) >= n else None


def short_window(
    settle: pd.DataFrame, expiry: pd.Series, days: pd.DatetimeIndex, d: pd.Timestamp, n: int,
    entry_lag: int = 1,
) -> tuple[float, float] | None:
    """Short the n-th contract from the settle ``entry_lag`` sessions before d to the settle on d.

    Returns (gross points, entry price) or None when a leg is missing.
    """
    if d not in days:
        return None
    i = days.get_loc(d)
    if i - entry_lag < 0:
        return None
    e = days[i - entry_lag]
    k = nth_contract(expiry, d, n)
    if k is None:
        return None
    s0, s1 = settle.at[e, k] if k in settle.columns else np.nan, settle.at[d, k]
    if not (np.isfinite(s0) and np.isfinite(s1)) or s0 <= 0:
        return None
    return float(s0 - s1), float(s0)


def event_table(
    kind: str, split: Split, n: int, cost_rt: float, entry_lag: int = 1
) -> tuple[pd.DataFrame, dict]:
    settle, expiry, days, ev, _ = load()
    all_events = set(ev["date"])
    evd = ev[(ev["kind"] == kind) & ev["date"].between(split.start, split.end)]["date"]
    funnel = {"events_in_split": len(evd), "not_trading_day": 0, "missing_leg": 0,
              "no_controls": 0, "kept": 0}
    rows = []
    for d in evd:
        if d not in days:
            funnel["not_trading_day"] += 1
            continue
        w = short_window(settle, expiry, days, d, n, entry_lag)
        if w is None:
            funnel["missing_leg"] += 1
            continue
        lo, hi = d - pd.Timedelta(days=CONTROL_HALF_WINDOW_DAYS), d + pd.Timedelta(
            days=CONTROL_HALF_WINDOW_DAYS)
        cands = [c for c in days[(days >= lo) & (days <= hi)]
                 if c.weekday() == d.weekday() and c not in all_events and c != d]
        crs = []
        for c in cands:
            wc = short_window(settle, expiry, days, c, n, entry_lag)
            if wc is not None:
                crs.append(wc[0] / wc[1])
        if not crs:
            funnel["no_controls"] += 1
            continue
        g, s0 = w
        rows.append({
            "date": d, "entry_price": s0, "gross_pts": g, "gross_ret": g / s0,
            "net_ret": (g - cost_rt) / s0, "control_gross_ret": float(np.mean(crs)),
            "n_controls": len(crs),
        })
        funnel["kept"] += 1
    t = pd.DataFrame(rows)
    if t.empty:
        raise ValueError(f"no events kept for {kind} {split}: {funnel}")
    t["surplus"] = t["gross_ret"] - t["control_gross_ret"]
    return t, funnel


def ci(values: pd.Series, dates: pd.Series, stat=np.mean) -> dict:
    iv = date_clustered_ci(values.to_numpy(), dates.to_numpy(), stat=stat)
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n, "clusters": iv.clusters}


def summarise(t: pd.DataFrame, cost_rt: float, cost_stress: float) -> dict:
    net_stress = (t["gross_pts"] - cost_stress) / t["entry_price"]
    return {
        "n": len(t),
        "gross_ret": ci(t["gross_ret"], t["date"]),
        "net_ret": ci(t["net_ret"], t["date"]),
        "net_ret_stress": ci(net_stress, t["date"]),
        "net_sharpe": ci(t["net_ret"], t["date"], stat=per_trade_sharpe),
        "control_gross_ret": ci(t["control_gross_ret"], t["date"]),
        "surplus": ci(t["surplus"], t["date"]),
        "gross_pts_mean": float(t["gross_pts"].mean()),
        "hit_rate_net": float((t["net_ret"] > 0).mean()),
        "worst_net_ret": float(t["net_ret"].min()),
    }


def passes(s: dict) -> bool:
    return s["net_ret"]["low"] > 0 and s["surplus"]["low"] > 0


def soq_table(split: Split) -> tuple[pd.DataFrame, dict]:
    """Long the expiring contract from the prior session's settle to the final settlement (SOQ)."""
    vx = pd.read_parquet(LANE / "data/vx_panel.parquet")
    settle, expiry, days, _, _ = load()
    funnel = {"contracts": 0, "missing": 0, "kept": 0}
    rows = []
    for k, x in expiry.items():
        if not (pd.Timestamp(split.start) <= x <= pd.Timestamp(split.end)):
            continue
        funnel["contracts"] += 1
        e = prev_day(days, x)
        last = vx[(vx["contract"] == k) & (vx["trade_date"] == x)]
        if e is None or last.empty or not np.isfinite(settle.at[e, k]):
            funnel["missing"] += 1
            continue
        soq = float(last["settle"].iloc[0])
        close_x = float(last["close"].iloc[0])
        s0 = float(settle.at[e, k])
        k2 = nth_contract(expiry, x, 1)
        f2 = np.nan
        if k2 is not None and np.isfinite(settle.at[e, k2]) and np.isfinite(settle.at[x, k2]):
            f2 = (settle.at[x, k2] - settle.at[e, k2]) / settle.at[e, k2]
        rows.append({
            "date": x, "contract": k, "entry_price": s0, "soq": soq,
            "gross_pts": soq - s0, "gross_ret": (soq - s0) / s0,
            "last_trade": close_x if close_x > 0 else np.nan,
            "next_contract_ret": f2,
        })
        funnel["kept"] += 1
    return pd.DataFrame(rows), funnel


def index_event_change(kind: str, split: Split, col: str) -> tuple[pd.DataFrame, dict]:
    """Log change of a Cboe index close on the event day minus matched controls (gross, mid)."""
    _, _, days, ev, idx = load()
    s = idx[col].dropna()
    sd = s.index
    all_events = set(ev["date"])
    evd = ev[(ev["kind"] == kind) & ev["date"].between(split.start, split.end)]["date"]
    lr = np.log(s).diff()
    rows = []
    funnel = {"events": len(evd), "missing": 0, "kept": 0}
    for d in evd:
        if d not in sd or not np.isfinite(lr.get(d, np.nan)):
            funnel["missing"] += 1
            continue
        lo, hi = d - pd.Timedelta(days=CONTROL_HALF_WINDOW_DAYS), d + pd.Timedelta(
            days=CONTROL_HALF_WINDOW_DAYS)
        cs = [c for c in sd[(sd >= lo) & (sd <= hi)]
              if c.weekday() == d.weekday() and c not in all_events and c != d]
        cv = lr.reindex(cs).dropna()
        if cv.empty:
            funnel["missing"] += 1
            continue
        rows.append({"date": d, "chg": lr[d], "ctrl": cv.mean(), "surplus": lr[d] - cv.mean()})
        funnel["kept"] += 1
    return pd.DataFrame(rows), funnel
