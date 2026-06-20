"""Tests for greeks.implied_vol: round-trip inversion and degenerate inputs."""

from __future__ import annotations

import math

import pytest

from earnings_iv_crush.engine.greeks import bs_price, implied_vol


@pytest.mark.parametrize("sigma", [0.1, 0.25, 0.5, 1.0])
@pytest.mark.parametrize("right", ["C", "P"])
def test_round_trips_to_input_sigma(sigma, right):
    spot, strike, t, r = 100.0, 100.0, 0.10, 0.0
    price = bs_price(spot, strike, t, r, sigma, right)
    assert implied_vol(price, spot, strike, t, r, right) == pytest.approx(sigma, abs=1e-4)


def test_round_trips_off_the_money():
    spot, strike, t, r, sigma = 100.0, 110.0, 0.25, 0.01, 0.40
    price = bs_price(spot, strike, t, r, sigma, "C")
    assert implied_vol(price, spot, strike, t, r, "C") == pytest.approx(sigma, abs=1e-4)


@pytest.mark.parametrize(
    "price,spot,strike,t",
    [
        (-1.0, 100, 100, 0.1),  # negative price
        (5.0, 100, 100, 0.0),  # zero tenor
        (5.0, 0.0, 100, 0.1),  # zero spot
    ],
)
def test_degenerate_inputs_return_nan(price, spot, strike, t):
    assert math.isnan(implied_vol(price, spot, strike, t, 0.0, "C"))


def test_price_above_bracket_returns_nan():
    # A price richer than any sigma<=5 can produce is not bracketed -> NaN.
    assert math.isnan(implied_vol(1e6, 100, 100, 0.1, 0.0, "C"))
