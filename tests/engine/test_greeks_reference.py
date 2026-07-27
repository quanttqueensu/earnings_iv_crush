"""Validate the pricing engine against an independent implementation.

``engine.greeks`` is hand-rolled Black-Scholes with a Brent inversion. Every number
this project reports passes through it, so it is checked here against ``py_vollib``,
a third-party library implementing Jaeckel's "Let's Be Rational" algorithm. Checking
maths against a separate implementation rather than against its own output is the
repo's stated convention for maths-bearing modules, and it is the only way an error in
the formula itself would ever surface: a self-consistent round-trip test passes
happily on a wrong formula.

Skipped rather than failed when ``py_vollib`` is absent, so the default suite stays
runnable on a bare environment.

References
----------
Jaeckel, P. (2015). Let's be rational. *Wilmott*, 2015(75), 40-53.
"""

from __future__ import annotations

import numpy as np
import pytest

from earnings_iv_crush.engine.greeks import bs_price, implied_vol, straddle_price

pytest.importorskip("py_vollib", reason="independent reference not installed")

from py_vollib.black_scholes import black_scholes  # noqa: E402
from py_vollib.black_scholes.implied_volatility import implied_volatility  # noqa: E402

# Tenors bracket the strategy's own range: it enters ~8 calendar days out and exits
# ~7, so the short end is where accuracy actually matters here.
TENORS = [2 / 365, 7 / 365, 30 / 365, 0.5]
VOLS = [0.15, 0.35, 0.60, 1.20]
RATES = [0.0, 0.05]


@pytest.mark.parametrize("t", TENORS)
@pytest.mark.parametrize("sigma", VOLS)
@pytest.mark.parametrize("r", RATES)
@pytest.mark.parametrize("right", ["C", "P"])
def test_bs_price_matches_reference(t: float, sigma: float, r: float, right: str) -> None:
    ours = bs_price(100.0, 100.0, t, r, sigma, right)
    theirs = black_scholes(right.lower(), 100.0, 100.0, t, r, sigma)
    assert ours == pytest.approx(theirs, abs=1e-10)


@pytest.mark.parametrize("moneyness", [0.85, 0.95, 1.0, 1.05, 1.15])
@pytest.mark.parametrize("right", ["C", "P"])
def test_bs_price_matches_reference_across_moneyness(moneyness: float, right: str) -> None:
    strike = 100.0 * moneyness
    ours = bs_price(100.0, strike, 7 / 365, 0.05, 0.45, right)
    theirs = black_scholes(right.lower(), 100.0, strike, 7 / 365, 0.05, 0.45)
    assert ours == pytest.approx(theirs, abs=1e-10)


@pytest.mark.parametrize("sigma", VOLS)
@pytest.mark.parametrize("right", ["C", "P"])
def test_implied_vol_matches_reference(sigma: float, right: str) -> None:
    """Invert a reference-generated price and recover the vol both libraries agree on."""
    t, r = 7 / 365, 0.05
    price = black_scholes(right.lower(), 100.0, 100.0, t, r, sigma)
    ours = implied_vol(price, 100.0, 100.0, t, r, right)
    theirs = implied_volatility(price, 100.0, 100.0, t, r, right.lower())
    assert ours == pytest.approx(theirs, abs=1e-6)
    assert ours == pytest.approx(sigma, abs=1e-6)


def test_straddle_equals_the_two_reference_legs() -> None:
    t, r, sigma = 7 / 365, 0.05, 0.45
    expected = black_scholes("c", 100.0, 100.0, t, r, sigma) + black_scholes(
        "p", 100.0, 100.0, t, r, sigma
    )
    assert straddle_price(100.0, 100.0, t, r, sigma) == pytest.approx(expected, abs=1e-10)


def test_put_call_parity_holds_in_our_engine() -> None:
    """C - P = S - K*exp(-rT). An identity the engine must satisfy exactly."""
    s, k, t, r, sigma = 100.0, 95.0, 7 / 365, 0.05, 0.45
    lhs = bs_price(s, k, t, r, sigma, "C") - bs_price(s, k, t, r, sigma, "P")
    assert lhs == pytest.approx(s - k * np.exp(-r * t), abs=1e-10)


def test_deep_itm_price_is_at_least_discounted_intrinsic() -> None:
    """The no-arbitrage floor the mark repair exists to enforce, checked in the engine."""
    s, k, t, r, sigma = 100.0, 60.0, 7 / 365, 0.05, 0.45
    assert bs_price(s, k, t, r, sigma, "C") >= s - k * np.exp(-r * t) - 1e-9
