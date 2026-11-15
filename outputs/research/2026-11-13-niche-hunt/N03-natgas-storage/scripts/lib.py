"""lib.py: event calendar, same-contract returns and statistics for the N03 pilot.

Builds a per-week panel of NYMEX Henry Hub settlement-to-settlement log returns around the EIA
Weekly Natural Gas Storage Report (Thursday 10:30 ET) from the free EIA futures file, and the
statistics pre-registered in ../diagnosis.log (trials 2142-2144).

References
----------
Linn, S. C. and Zhu, Z. (2004). Natural gas prices and the gas storage report. Journal of
    Futures Markets 24(3), 283-313.
Prokopczuk, M., Wese Simen, C. and Wichmann, R. (2021). The natural gas announcement day
    puzzle. Energy Journal 42(2), 91-112.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

# ── constants (rationale in ../diagnosis.log) ──
FIRST_EIA_RELEASE = pd.Timestamp("2002-05-09")
DISCOVERY = (pd.Timestamp("2002-05-09"), pd.Timestamp("2018-12-31"))
HELDOUT = (pd.Timestamp("2019-01-01"), pd.Timestamp("2024-04-05"))
TICK = 0.001  # $/MMBtu, NYMEX NG minimum fluctuation on Globex
CONTRACT_MMBTU = 10_000.0
FEES_PER_SIDE_USD = 2.50  # IB commission + NYMEX non-member fee + pennies, see diagnosis.log
TICKS_PER_SIDE = 1.0  # conservative: a full tick per side (half-spread is about half a tick)
N_BOOT = 10_000
SEED = 0  # earnings_iv_crush.research.protocol.SEED
RHO_PASS = 0.25


@dataclass(frozen=True)
class Funnel:
    """Counts at each filter of the weekly panel."""

    steps: tuple[tuple[str, int], ...]

    def __str__(self) -> str:
        return "\n".join(f"  {k:<58s}{v:>6d}" for k, v in self.steps)


# ── data ──
def load_futures(lane: Path) -> pd.DataFrame:
    f = pd.read_csv(lane / "data" / "futures_daily.csv", parse_dates=["date"]).set_index("date")
    f = f.dropna(subset=["c1", "c2", "c3"])
    if f.empty:
        raise ValueError("futures file empty after dropping rows without settlements")
    return f


def last_trade_days(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """C1 last trade day: third-last trading day of each calendar month in the file."""
    s = pd.Series(idx, index=idx)
    ltd = s.groupby([idx.year, idx.month]).apply(lambda x: x.iloc[-3] if len(x) >= 3 else pd.NaT)
    return pd.DatetimeIndex(ltd.dropna().values)


def same_contract_returns(f: pd.DataFrame) -> pd.DataFrame:
    """Log returns of C1 and C2 that never mix two delivery months."""
    idx = f.index
    ltd = set(last_trade_days(idx))
    prev_is_ltd = pd.Series([False] + [d in ltd for d in idx[:-1]], index=idx)
    out = pd.DataFrame(index=idx)
    out["is_ltd"] = [d in ltd for d in idx]
    out["is_roll"] = prev_is_ltd.values
    for k, nxt in (("c1", "c2"), ("c2", "c3")):
        base = np.where(out["is_roll"], f[nxt].shift(1), f[k].shift(1))
        out[f"r_{k}"] = np.log(f[k].to_numpy() / base)
    out["c1"] = f["c1"]
    out["c2"] = f["c2"]
    out["gap_days"] = pd.Series(idx, index=idx).diff().dt.days
    return out.iloc[1:]


def weekly_panel(r: pd.DataFrame) -> tuple[pd.DataFrame, Funnel]:
    """One row per report week with Tue, Wed, Thu returns, and the funnel of drops."""
    hol = set(USFederalHolidayCalendar().holidays(r.index.min(), r.index.max() + pd.Timedelta(7, "D")))
    thursdays = pd.date_range(FIRST_EIA_RELEASE, r.index.max(), freq="W-THU")
    steps: list[tuple[str, int]] = [("report Thursdays in range", len(thursdays))]
    rows = []
    n_hol = n_missing = n_roll = 0
    for thu in thursdays:
        mon = thu - pd.Timedelta(3, "D")
        week = pd.date_range(mon, mon + pd.Timedelta(4, "D"))
        if any(d in hol for d in week):
            n_hol += 1
            continue
        tue, wed = thu - pd.Timedelta(2, "D"), thu - pd.Timedelta(1, "D")
        if not all(d in r.index for d in (tue, wed, thu)) or r.loc[tue, "gap_days"] != 1:
            n_missing += 1
            continue
        sub = r.loc[[tue, wed, thu]]
        if sub["is_roll"].any() or sub["is_ltd"].any():
            n_roll += 1
            continue
        rows.append(
            {
                "week": thu,
                "r1_tue": sub.loc[tue, "r_c1"],
                "r1_wed": sub.loc[wed, "r_c1"],
                "r1_thu": sub.loc[thu, "r_c1"],
                "r2_tue": sub.loc[tue, "r_c2"],
                "r2_wed": sub.loc[wed, "r_c2"],
                "r2_thu": sub.loc[thu, "r_c2"],
                "f1_mon": r.loc[mon, "c1"] if mon in r.index else np.nan,
                "f1_tue": r.loc[tue, "c1"],
                "f1_wed": r.loc[wed, "c1"],
            }
        )
    steps += [
        ("dropped: federal holiday Mon-Fri (release may move)", n_hol),
        ("dropped: Tue/Wed/Thu settlement missing or Tue spans >1 day", n_missing),
        ("dropped: Tue/Wed/Thu is a C1 last trade day or roll day", n_roll),
    ]
    p = pd.DataFrame(rows)
    steps.append(("weeks kept", len(p)))
    if p.empty:
        raise ValueError("weekly panel is empty")
    bad = p[["r1_tue", "r1_wed", "r1_thu"]].isna().any(axis=1).sum()
    if bad:
        raise ValueError(f"{bad} kept weeks carry NaN returns")
    return p, Funnel(tuple(steps))


def block(p: pd.DataFrame, span: tuple[pd.Timestamp, pd.Timestamp]) -> pd.DataFrame:
    b = p[(p["week"] >= span[0]) & (p["week"] <= span[1])].reset_index(drop=True)
    if b.empty:
        raise ValueError(f"block {span} is empty")
    return b


# ── statistics ──
def _boot_weeks(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n, size=(N_BOOT, n))


def rho_stats(b: pd.DataFrame, k: str) -> dict[str, float]:
    """Excess event variance rho and straddle break-even ratio B with week-clustered CIs."""
    thu2 = b[f"r{k}_thu"].to_numpy() ** 2
    ctl2 = 0.5 * (b[f"r{k}_tue"].to_numpy() ** 2 + b[f"r{k}_wed"].to_numpy() ** 2)
    thua = np.abs(b[f"r{k}_thu"].to_numpy())
    ctla = 0.5 * (np.abs(b[f"r{k}_tue"].to_numpy()) + np.abs(b[f"r{k}_wed"].to_numpy()))
    rng = np.random.default_rng(SEED)
    ix = _boot_weeks(len(b), rng)
    rho_b = thu2[ix].sum(1) / ctl2[ix].sum(1) - 1
    b_b = thua[ix].mean(1) / ctla[ix].mean(1)
    return {
        "n_weeks": float(len(b)),
        "rho": float(thu2.sum() / ctl2.sum() - 1),
        "rho_lo": float(np.quantile(rho_b, 0.025)),
        "rho_hi": float(np.quantile(rho_b, 0.975)),
        "B": float(thua.mean() / ctla.mean()),
        "B_lo": float(np.quantile(b_b, 0.025)),
        "B_hi": float(np.quantile(b_b, 0.975)),
        "sd_thu_daily": float(np.sqrt(thu2.mean())),
        "sd_ctl_daily": float(np.sqrt(ctl2.mean())),
    }


def cost_per_side(f: np.ndarray) -> np.ndarray:
    return (TICKS_PER_SIDE * TICK + FEES_PER_SIDE_USD / CONTRACT_MMBTU) / f


def short_stats(b: pd.DataFrame) -> dict[str, float]:
    """Short C1 Wed settle -> Thu settle, net of costs, against the Tue/Wed matched control."""
    ev = -b["r1_thu"].to_numpy() - 2 * cost_per_side(b["f1_wed"].to_numpy())
    c_tue = -b["r1_tue"].to_numpy() - 2 * cost_per_side(b["f1_mon"].fillna(b["f1_tue"]).to_numpy())
    c_wed = -b["r1_wed"].to_numpy() - 2 * cost_per_side(b["f1_tue"].to_numpy())
    ctl = 0.5 * (c_tue + c_wed)
    diff = ev - ctl
    rng = np.random.default_rng(SEED)
    ix = _boot_weeks(len(b), rng)
    ev_b, d_b = ev[ix].mean(1), diff[ix].mean(1)
    sd = ev.std(ddof=1)
    years = (b["week"].max() - b["week"].min()).days / 365.0
    tpy = len(b) / years if years > 0 else float("nan")
    return {
        "n_weeks": float(len(b)),
        "ev_mean": float(ev.mean()),
        "ev_lo": float(np.quantile(ev_b, 0.025)),
        "ev_hi": float(np.quantile(ev_b, 0.975)),
        "ev_gross_mean": float((-b["r1_thu"]).mean()),
        "diff_mean": float(diff.mean()),
        "diff_lo": float(np.quantile(d_b, 0.025)),
        "diff_hi": float(np.quantile(d_b, 0.975)),
        "ctl_mean": float(ctl.mean()),
        "sharpe_per_trade": float(ev.mean() / sd) if sd > 0 else float("nan"),
        "trades_per_year": float(tpy),
        "sharpe_ann_sqrt_tpy": float(ev.mean() / sd * np.sqrt(tpy)) if sd > 0 else float("nan"),
        "cost_rt_mean": float((2 * cost_per_side(b["f1_wed"].to_numpy())).mean()),
    }
