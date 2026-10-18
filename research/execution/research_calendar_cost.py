"""
research_calendar_cost.py
What a front-over-back calendar costs to trade, per unit of event premium it keeps.

The naked short straddle carries two exposures at once: the announcement jump it is paid
to sell, and the level of diffusive volatility, which it neither wants nor is paid for. A
calendar (short the front straddle, long a later straddle at the same strike) hedges the
second. The question before any P&L study is whether the hedge is affordable when cost
already binds (round-trip break-even about 11.6% of premium on the naked book).

Comparing raw spread cost would flatter the calendar's burden twice over: it adds legs, and
it also gives back part of the premium, because the back expiry contains the same
announcement and loses value when it resolves. So cost is reported per unit of event
premium retained, using the two-expiry split on entry-date prices only:

    V_x = (straddle_x / (k S))^2              total implied variance to expiry x, k = sqrt(2/pi)
    s^2 = (V_b - V_f) / (t_b - t_f)           diffusive variance, flat between expiries
    harvest_x = straddle_x - k S sqrt(s^2 t_x)   premium above the diffusive value
    h = (t_f / sqrt V_f) / (t_b / sqrt V_b)   back straddles per front straddle that
                                              neutralise a parallel shift in s

Every quantity is an at-entry price or a quoted spread. No exit value is read, so the
2025-26 block's outcomes stay unviewed for any later selector. Spreads are the quoted
15:59 ET touch, half of bid-ask per leg per session; the measured effective cost on the
megacap book (1.7871% per side, ``fills_rescore.csv``) is smaller, so these are the
conservative arm.

The ATM straddle approximation ``k S sigma sqrt(t)`` ignores rates, dividends and the
strike's distance from spot. It is used identically on both expiries, so the ratio
comparisons it feeds are less affected than the levels.

Usage:
    python research/execution/research_calendar_cost.py

References
----------
Brenner, M. and Subrahmanyam, M. G. (1988). A Simple Formula to Compute the Implied
Standard Deviation. *Financial Analysts Journal* 44(5), 80-83.
Dubinsky, A. and Johannes, M. (2006). Fundamental Uncertainty, Earnings Announcements and
Equity Options. Working paper, Columbia University.
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.config import GLOBAL  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

LEDGER = Path("outputs/research/oos_2026_ledger.csv")
CHAINS = Path("data/cache/backfill_chains")
OUT = Path("outputs/research/calendar_cost")

# Identifying and at-entry columns only. Exit values and returns in the ledger are never
# loaded, so nothing here can inform a selector later confirmed on this block.
KEEP = ["ticker", "announce_date", "entry_date", "exit_date", "strike", "expiry", "spot_entry"]

K_ATM = np.sqrt(2.0 / np.pi)  # ATM straddle ~ k S sigma sqrt(t) (Brenner-Subrahmanyam)
BACK_GAP_DAYS = GLOBAL.back_month_min_gap_days  # same back-expiry rule as the feature build
BREAK_EVEN = 0.116  # naked round-trip break-even, fraction of entry premium


# ── chain access ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=4096)
def _chain(ticker: str, day: str) -> pd.DataFrame | None:
    p = CHAINS / f"{ticker}_{day}.parquet"
    if not p.exists():
        return None
    try:
        return _parse_chain(pd.read_parquet(p))
    except Exception:
        return None


def _quote(ch: pd.DataFrame, strike: float, expiry: pd.Timestamp) -> tuple[float, float] | None:
    """(mid, half-spread) of the straddle at one strike and expiry, both legs quoted."""
    leg = ch[(ch["strike"] == strike) & (ch["expiry"] == expiry)]
    c, p = leg[leg["right"] == "C"], leg[leg["right"] == "P"]
    if c.empty or p.empty:
        return None
    bid = float(c["bid_px_00"].iloc[0] + p["bid_px_00"].iloc[0])
    ask = float(c["ask_px_00"].iloc[0] + p["ask_px_00"].iloc[0])
    if not (ask > bid > 0):
        return None
    return (bid + ask) / 2, (ask - bid) / 2


# ── per-event measurement ────────────────────────────────────────────────────


def measure(ev: pd.DataFrame) -> pd.DataFrame:
    """Quote both straddles at entry and exit and derive the cost and harvest ratios."""
    reasons: dict[str, int] = {}

    def drop(why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    rows = []
    for _, e in ev.iterrows():
        tkr = str(e["ticker"])
        d_in, d_out = e["entry_date"], e["exit_date"]
        k, front, spot = float(e["strike"]), e["expiry"], float(e["spot_entry"])

        ch_in = _chain(tkr, str(d_in.date()))
        ch_out = _chain(tkr, str(d_out.date()))
        if ch_in is None or ch_out is None:
            drop("chain missing")
            continue
        later = np.sort(ch_in["expiry"].unique())
        later = later[later >= front + pd.Timedelta(days=BACK_GAP_DAYS)]
        if not len(later):
            drop("no back expiry")
            continue
        back = pd.Timestamp(later[0])

        q = {
            "f_in": _quote(ch_in, k, front),
            "b_in": _quote(ch_in, k, back),
            "f_out": _quote(ch_out, k, front),
            "b_out": _quote(ch_out, k, back),
        }
        missing = [name for name, v in q.items() if v is None]
        if missing:
            drop(f"unquoted {missing[0]}")
            continue
        f_in, b_in, f_out, b_out = (q[n] or (np.nan, np.nan) for n in q)

        t_f = (front - d_in).days / 365.0
        t_b = (back - d_in).days / 365.0
        p_f, p_b = f_in[0], b_in[0]
        v_f = (p_f / (K_ATM * spot)) ** 2
        v_b = (p_b / (K_ATM * spot)) ** 2
        s2 = (v_b - v_f) / (t_b - t_f)
        if s2 <= 0 or v_f <= s2 * t_f:
            drop("no positive event/diffusive split")
            continue
        harvest_f = p_f - K_ATM * spot * np.sqrt(s2 * t_f)
        harvest_b = p_b - K_ATM * spot * np.sqrt(s2 * t_b)
        h = (t_f / np.sqrt(v_f)) / (t_b / np.sqrt(v_b))

        cost_f = f_in[1] + f_out[1]
        cost_b = b_in[1] + b_out[1]
        rows.append(
            {
                "ticker": tkr,
                "entry_date": d_in,
                "dte_front": (front - d_in).days,
                "dte_back": (back - d_in).days,
                "hedge_ratio": h,
                "event_share_front": harvest_f / p_f,
                "harvest_retained_hedged": (harvest_f - h * harvest_b) / harvest_f,
                "harvest_retained_1to1": (harvest_f - harvest_b) / harvest_f,
                "naked_rt_pct_premium": cost_f / p_f,
                "cal_hedged_rt_pct_premium": (cost_f + h * cost_b) / p_f,
                "cal_1to1_rt_pct_premium": (cost_f + cost_b) / p_f,
                "naked_cost_per_harvest": cost_f / harvest_f,
                "cal_hedged_cost_per_harvest": (cost_f + h * cost_b) / (harvest_f - h * harvest_b),
                "cal_1to1_cost_per_harvest": (cost_f + cost_b) / (harvest_f - harvest_b),
                "front_half_spread_entry": f_in[1] / p_f,
                "front_half_spread_exit": f_out[1] / f_out[0],
                "back_half_spread_entry": b_in[1] / p_b,
                "back_half_spread_exit": b_out[1] / b_out[0],
            }
        )

    print("\n  measurement funnel:")
    print(f"    events considered               {len(ev)}")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    dropped, {why:<36} {n}")
    print(f"    measured                        {len(rows)}")
    if not rows:
        raise SystemExit("no event could be quoted on both expiries - refusing to summarise")
    return pd.DataFrame(rows)


def summarise(m: pd.DataFrame) -> pd.DataFrame:
    """Median, interquartile range and mean of every ratio."""
    cols = [c for c in m.columns if c not in ("ticker", "entry_date")]
    out = m[cols].describe(percentiles=[0.25, 0.5, 0.75]).T
    return out[["count", "mean", "25%", "50%", "75%"]]


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n")[2]).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    ev = pd.read_csv(
        LEDGER, usecols=KEEP, parse_dates=["announce_date", "entry_date", "exit_date", "expiry"]
    )
    m = measure(ev)
    m.to_csv(OUT / "calendar_cost_events.csv", index=False)
    s = summarise(m)
    s.to_csv(OUT / "calendar_cost_summary.csv")
    print(s.to_string(float_format=lambda v: f"{v:.4f}"))

    # Positive-harvest subsample: a calendar whose back leg carries more event premium than
    # the front has no event exposure left to sell, and its cost-per-harvest is undefined.
    pos = m[m["harvest_retained_hedged"] > 0]
    print(f"\n  hedged calendar keeps a positive event harvest on {len(pos)}/{len(m)} events")
    for col in ("naked_cost_per_harvest", "cal_hedged_cost_per_harvest"):
        print(f"    median {col:<30} {pos[col].median():.4f}")
    print(
        f"  naked median round trip vs break-even {m['naked_rt_pct_premium'].median():.4f} "
        f"vs {BREAK_EVEN:.3f}"
    )
    print(f"\n  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
