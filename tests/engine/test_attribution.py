"""Tests for the Greek additions and the short-straddle P&L attribution."""
from __future__ import annotations

import pytest

from src.engine import greeks
from src.engine.attribution import attribute_straddle_pnl, delta_hedge_pnl


# --- greeks ------------------------------------------------------------------

def test_vega_matches_finite_difference():
    s, k, t, r, sig, h = 100, 100, 0.05, 0.0, 0.4, 1e-4
    fd = (greeks.bs_price(s, k, t, r, sig + h, "C")
          - greeks.bs_price(s, k, t, r, sig - h, "C")) / (2 * h)
    assert greeks.bs_vega(s, k, t, r, sig) == pytest.approx(fd, rel=1e-3)


def test_gamma_matches_delta_finite_difference():
    s, k, t, r, sig, h = 100, 100, 0.05, 0.0, 0.4, 1e-3
    fd = (greeks.bs_delta(s + h, k, t, r, sig, "C")
          - greeks.bs_delta(s - h, k, t, r, sig, "C")) / (2 * h)
    assert greeks.bs_gamma(s, k, t, r, sig) == pytest.approx(fd, rel=1e-3)


def test_straddle_greeks_atm_shape():
    g = greeks.straddle_greeks(100, 100, 0.05, 0.0, 0.4)
    assert abs(g["delta"]) < 0.1          # near delta-neutral ATM
    assert g["gamma"] > 0 and g["vega"] > 0
    assert g["vega"] == pytest.approx(2 * greeks.bs_vega(100, 100, 0.05, 0.0, 0.4))


def test_greeks_degenerate_inputs_are_zero():
    assert greeks.bs_vega(100, 100, 0.0, 0.0, 0.4) == 0.0
    assert greeks.bs_gamma(100, 100, 0.05, 0.0, 0.0) == 0.0


# --- attribution -------------------------------------------------------------

def test_pure_crush_is_vega_dominated_and_profitable():
    # Spot unchanged, IV collapses 0.6 -> 0.25: short straddle profits via vega.
    a = attribute_straddle_pnl(
        spot_entry=100, strike=100, t_entry=0.05, t_exit=0.02,
        iv_entry=0.60, iv_exit=0.25, spot_exit=100.0, contracts=1,
    )
    assert a["total_pnl"] > 0
    assert a["vega_pnl"] > 0
    assert a["vega_pnl"] > abs(a["gamma_pnl"])     # vega is the dominant leg
    assert a["gamma_pnl"] == pytest.approx(0.0, abs=1e-9)  # no realised move


def test_components_plus_residual_reconstruct_total():
    a = attribute_straddle_pnl(
        spot_entry=100, strike=100, t_entry=0.05, t_exit=0.02,
        iv_entry=0.55, iv_exit=0.30, spot_exit=103.0, contracts=2,
    )
    recon = (a["delta_pnl"] + a["gamma_pnl"] + a["vega_pnl"]
             + a["theta_pnl"] + a["residual"])
    assert recon == pytest.approx(a["total_pnl"])


def test_large_move_hurts_short_gamma():
    a = attribute_straddle_pnl(
        spot_entry=100, strike=100, t_entry=0.05, t_exit=0.02,
        iv_entry=0.40, iv_exit=0.38, spot_exit=120.0, contracts=1,
    )
    assert a["gamma_pnl"] < 0
    assert a["total_pnl"] < 0          # big move overwhelms the small crush


def test_delta_hedge_cancels_delta_pnl_to_first_order():
    # Use an off-ATM strike so the straddle carries non-trivial delta.
    kw = dict(spot_entry=100, strike=110, t_entry=0.05, iv_entry=0.40, contracts=3)
    a = attribute_straddle_pnl(t_exit=0.02, iv_exit=0.30, spot_exit=104.0, strike=110,
                               spot_entry=100, t_entry=0.05, iv_entry=0.40, contracts=3)
    h = delta_hedge_pnl(spot_exit=104.0, **kw)
    # Hedge offsets the first-order directional leg.
    assert a["delta_pnl"] + h["hedge_pnl"] == pytest.approx(0.0, abs=1e-6)
