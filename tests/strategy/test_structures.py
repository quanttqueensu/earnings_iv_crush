"""Tests for strategy.structures (iron fly, calendar) and strategy.regime."""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_iv_crush.engine.greeks import bs_vega, straddle_price
from earnings_iv_crush.strategy import regime, structures

# --- iron fly ----------------------------------------------------------------


def test_iron_fly_wings_straddle_the_spot():
    lower, upper = structures.iron_fly_wings(100.0, implied_move=0.06, wing_mult=1.5)
    assert lower < 100.0 < upper
    assert upper - 100.0 == pytest.approx(1.5 * 0.06 * 100.0)


def test_iron_fly_credit_below_naked_straddle():
    # Long wings cost a debit, so the iron fly collects less than the straddle.
    naked = straddle_price(100, 100, 0.05, 0.0, 0.5) * 100
    fly = structures.iron_fly_pnl(
        spot_entry=100,
        strike=100,
        t_entry=0.05,
        t_exit=0.02,
        iv_entry=0.5,
        iv_exit=0.3,
        spot_exit=100.0,
        implied_move=0.06,
    )
    assert 0 < fly["entry_credit"] < naked


def test_iron_fly_loss_is_capped_at_expiry():
    # Huge move to expiry: loss cannot exceed the defined max_loss.
    fly = structures.iron_fly_pnl(
        spot_entry=100,
        strike=100,
        t_entry=0.05,
        t_exit=0.0,
        iv_entry=0.5,
        iv_exit=0.5,
        spot_exit=200.0,
        implied_move=0.06,
    )
    assert fly["pnl"] == pytest.approx(-fly["max_loss"], abs=1e-6)


# --- calendar ----------------------------------------------------------------


def test_calendar_ratio_is_vega_balanced():
    ratio = structures.calendar_ratio(
        100, 100, t_front=0.02, t_back=0.12, iv_front=0.5, iv_back=0.4
    )
    front_v = bs_vega(100, 100, 0.02, 0.0, 0.5)
    back_v = bs_vega(100, 100, 0.12, 0.0, 0.4)
    assert ratio * back_v == pytest.approx(front_v, rel=1e-9)


def test_calendar_profits_when_front_crushes_more():
    cal = structures.calendar_pnl(
        spot_entry=100,
        strike=100,
        t_front_entry=0.02,
        t_front_exit=0.005,
        t_back_entry=0.12,
        t_back_exit=0.105,
        iv_front_entry=0.60,
        iv_front_exit=0.25,
        iv_back_entry=0.40,
        iv_back_exit=0.38,
        spot_exit=100.0,
    )
    assert cal["pnl"] > 0


# --- regime ------------------------------------------------------------------


def test_high_vix_forces_iron_fly():
    assert regime.select_structure(vix=30.0, term_spread=0.0, level_richness=0.5) == regime.IRON_FLY


def test_term_dominance_picks_calendar():
    out = regime.select_structure(vix=15.0, term_spread=0.25, level_richness=0.10)
    assert out == regime.CALENDAR


def test_rich_level_low_term_picks_straddle():
    out = regime.select_structure(vix=15.0, term_spread=0.02, level_richness=0.40)
    assert out == regime.STRADDLE


def test_assign_structures_uses_event_vix_column():
    events = pd.DataFrame(
        {
            "implied_move": [0.06, 0.06, 0.06],
            "iv_term_spread": [0.02, 0.25, 0.02],
            "vix": [30.0, 15.0, 15.0],
        }
    )
    fair = [0.04, 0.05, 0.04]  # richness ~ +0.5, +0.2, +0.5
    labels = regime.assign_structures(events, fair)
    assert list(labels) == [regime.IRON_FLY, regime.CALENDAR, regime.STRADDLE]
