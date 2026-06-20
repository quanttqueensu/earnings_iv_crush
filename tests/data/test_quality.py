"""Tests for the data-quality gates (quotes and events)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from earnings_iv_crush.data import quality


def _chain(**overrides):
    base = {
        "expiry": [pd.Timestamp("2026-07-17")] * 4,
        "strike": [100.0, 100.0, 100.0, 100.0],
        "right": ["C", "P", "C", "P"],
        "bid": [3.0, 3.0, 3.0, 3.0],
        "ask": [3.2, 3.2, 3.2, 3.2],
        "iv": [0.4] * 4,
        "open_interest": [500] * 4,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_clean_chain_passes():
    chain, rep = quality.filter_chain(_chain(), spot=100.0)
    assert rep.n_out == 4 and rep.n_in == 4


def test_bad_price_dropped():
    chain, rep = quality.filter_chain(
        _chain(bid=[0, 3, np.nan, 3], ask=[0, 3.2, np.nan, 3.2]), 100.0
    )
    assert rep.n_bad_price == 2
    assert rep.n_out == 2


def test_low_oi_dropped_but_nan_oi_passes():
    chain, rep = quality.filter_chain(_chain(open_interest=[5, np.nan, 500, 500]), 100.0)
    assert rep.n_low_oi == 1
    assert rep.n_out == 3  # NaN OI is absence of evidence, kept


def test_wide_spread_dropped():
    chain, rep = quality.filter_chain(
        _chain(bid=[2.0, 3.0, 3.0, 3.0], ask=[4.0, 3.2, 3.2, 3.2]), 100.0
    )
    assert rep.n_wide_spread == 1
    assert rep.n_out == 3


def test_far_strike_dropped():
    chain, rep = quality.filter_chain(_chain(strike=[100, 100, 140, 60]), 100.0)
    assert rep.n_far_strike == 2
    assert rep.n_out == 2


def test_empty_chain():
    chain, rep = quality.filter_chain(pd.DataFrame(), 100.0)
    assert rep.n_in == 0 and rep.n_out == 0


def _event(**overrides):
    base = {
        "spot_entry": 100.0,
        "iv_entry": 0.5,
        "spot_exit": 99.0,
        "iv_term_spread": 0.1,
        "implied_move": 0.06,
        "cohort": "megacap",
    }
    base.update(overrides)
    return pd.Series(base)


def test_event_quality_ok():
    assert quality.event_quality(_event()) is None


def test_event_quality_reasons_in_order():
    assert quality.event_quality(_event(spot_entry=np.nan)) == "missing_entry"
    assert quality.event_quality(_event(iv_entry=np.nan)) == "missing_entry"
    assert quality.event_quality(_event(spot_exit=np.nan)) == "missing_exit"
    assert quality.event_quality(_event(iv_term_spread=np.nan)) == "no_term_spread"
    assert quality.event_quality(_event(implied_move=np.nan)) == "no_implied_move"


def test_exclusion_table_by_cohort():
    events = pd.DataFrame(
        [_event(), _event(spot_exit=np.nan), _event(cohort="broad-only", iv_entry=np.nan)]
    )
    table = quality.exclusion_table(events)
    assert set(table.columns) == {"reason", "cohort", "n"}
    assert table["n"].sum() == 3
    assert "ok" in set(table["reason"])
