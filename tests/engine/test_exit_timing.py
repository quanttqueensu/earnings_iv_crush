"""Regression tests for the exit-timing fix that captures the vega crush.

The strategy earns from the post-earnings implied-vol collapse (vega), not from
time decay (theta). That only shows up in the P&L when the trade is exited while
the option still has time value (``t_exit > 0``); holding past the front expiry
settles the straddle at intrinsic and the crush never marks, leaving the
attribution theta/gamma-dominated. These tests lock in the corrected behaviour
so the bug cannot silently return.
"""

from __future__ import annotations

from earnings_iv_crush.data.real_events import build_execution_events, entry_exit_dates
from earnings_iv_crush.engine.attribution import attribute_straddle_pnl

# A clean earnings crush: rich front-week IV at entry, normal IV one day later,
# a small realised move, and a still-live expiry (~1 week out) at exit.
CRUSH = dict(
    spot_entry=100.0,
    strike=100.0,
    t_entry=8 / 365,
    t_exit=7 / 365,
    iv_entry=0.80,
    iv_exit=0.40,
    spot_exit=100.5,
)


def test_crush_attribution_is_vega_dominated_when_time_value_remains():
    attr = attribute_straddle_pnl(**CRUSH)
    # The crush is profitable and the vega leg carries it.
    assert attr["vega_pnl"] > 0
    assert abs(attr["vega_pnl"]) > abs(attr["theta_pnl"])
    assert abs(attr["vega_pnl"]) > abs(attr["gamma_pnl"])


def test_holding_past_expiry_loses_the_vega_signal():
    # The original bug: exit AT/after the front expiry (t_exit <= 0). The mark
    # is then pure intrinsic and the first-order theta term is inflated, so vega
    # no longer dominates - exactly the pathology the fix removes.
    lapsed = {**CRUSH, "t_exit": 0.0}
    attr = attribute_straddle_pnl(**lapsed)
    assert abs(attr["theta_pnl"]) >= abs(attr["vega_pnl"])


def test_entry_exit_dates_are_a_single_overnight_hold():
    for session in ("amc", "bmo", "dmh"):
        entry, exit_ = entry_exit_dates("2024-06-10", session)
        assert exit_ > entry
        # One business day apart: the overnight spanning the crush.
        assert len(__import__("pandas").bdate_range(entry, exit_)) == 2


def test_assembler_guarantees_positive_time_to_exit():
    import numpy as np
    import pandas as pd

    from earnings_iv_crush.engine.greeks import bs_price

    def fetch_chain(_t, d):
        asof = pd.Timestamp(d)
        rows = []
        for exp in (pd.Timestamp("2024-06-21"), pd.Timestamp("2024-07-19")):
            t = max((exp - asof).days, 1) / 365.0
            for k in np.arange(90.0, 111.0, 5.0):
                for right in ("C", "P"):
                    rows.append(
                        {
                            "expiry": exp,
                            "strike": float(k),
                            "right": right,
                            "bid": bs_price(100.0, k, t, 0.0, 0.4, right),
                            "ask": bs_price(100.0, k, t, 0.0, 0.4, right),
                            "iv": 0.4,
                            "open_interest": 100,
                        }
                    )
        return pd.DataFrame(rows)

    cal = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-12"]})
    df = build_execution_events(
        cal,
        fetch_chain=fetch_chain,
        fetch_prices=lambda _t, s, e: pd.DataFrame({"date": pd.bdate_range(s, e), "close": 100.0}),
    )
    assert (df["t_exit"] > 0).all()
