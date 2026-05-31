"""Black-Scholes pricing and Greeks for ATM straddles.

Used to price entries/exits, to translate quoted prices into implied vols when
the data feed does not supply them, and to attribute realised straddle P&L to
its vega / gamma / theta / delta sources (see ``engine.attribution``).

This module implements:

* ``bs_price`` / ``straddle_price`` — Black-Scholes value of an option / straddle.
* ``bs_delta`` / ``bs_gamma`` / ``bs_vega`` / ``bs_theta`` / ``bs_rho`` — Greeks.
* ``straddle_greeks`` — aggregate Greeks of an ATM straddle.
* ``implied_vol`` — invert the price to recover implied volatility.

Conventions: ``t`` is time-to-expiry in years; ``r`` and ``sigma`` are annualised
and continuously compounded. ``bs_theta`` is the derivative with respect to
**time-to-expiry** (positive for long vanilla options), not calendar theta, so
that a P&L attribution can multiply it by the change in time-to-expiry directly.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def bs_price(spot, strike, t, r, sigma, right="C"):
    """Black-Scholes price of a European option. right is 'C' or 'P'."""
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    if right == "C":
        return spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return strike * np.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def bs_delta(spot, strike, t, r, sigma, right="C"):
    """Black-Scholes delta. Call delta in (0, 1); put delta in (-1, 0).

    Used to locate the 25-delta strikes when computing the IV skew feature.
    """
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    if right == "C":
        return norm.cdf(d1)
    return norm.cdf(d1) - 1.0


def straddle_price(spot, strike, t, r, sigma):
    """Price of an ATM straddle (call + put at the same strike)."""
    return bs_price(spot, strike, t, r, sigma, "C") + bs_price(spot, strike, t, r, sigma, "P")


def implied_vol(price, spot, strike, t, r, right="C", lo=1e-6, hi=5.0):
    """Back out implied volatility from a quoted option price.

    Inverts `bs_price` with Brent's method over sigma in [lo, hi]. Returns NaN
    when the inputs are degenerate or the price is outside the no-arbitrage
    range that the bracket can solve (so a bad quote never raises).
    """
    if not (price > 0 and spot > 0 and strike > 0 and t > 0):
        return float("nan")

    def f(sigma):
        return bs_price(spot, strike, t, r, sigma, right) - price

    try:
        if f(lo) * f(hi) > 0:   # price not bracketed -> no solution in range
            return float("nan")
        return float(brentq(f, lo, hi, xtol=1e-8, maxiter=200))
    except (ValueError, RuntimeError):
        return float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Greeks
# ─────────────────────────────────────────────────────────────────────────────


def _d1_d2(spot, strike, t, r, sigma):
    """Return the Black-Scholes ``d1`` and ``d2`` terms."""
    d1 = (np.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return d1, d1 - sigma * np.sqrt(t)


def bs_gamma(spot, strike, t, r, sigma):
    """Black-Scholes gamma (d2V/dS2), identical for a call and a put (per share)."""
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, t, r, sigma)
    return float(norm.pdf(d1) / (spot * sigma * np.sqrt(t)))


def bs_vega(spot, strike, t, r, sigma):
    """Black-Scholes vega (dV/dsigma) per unit of volatility; same for call/put."""
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, t, r, sigma)
    return float(spot * norm.pdf(d1) * np.sqrt(t))


def bs_theta(spot, strike, t, r, sigma, right="C"):
    """Derivative of option value with respect to time-to-expiry (per year).

    Positive for long vanilla options (more time to expiry is worth more). This
    is the negative of the conventional calendar theta, chosen so a P&L
    attribution can multiply it by the change in time-to-expiry directly.
    """
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    d1, d2 = _d1_d2(spot, strike, t, r, sigma)
    decay = spot * norm.pdf(d1) * sigma / (2 * np.sqrt(t))
    if right == "C":
        return float(decay + r * strike * np.exp(-r * t) * norm.cdf(d2))
    return float(decay - r * strike * np.exp(-r * t) * norm.cdf(-d2))


def bs_rho(spot, strike, t, r, sigma, right="C"):
    """Black-Scholes rho (dV/dr) per unit rate; positive for calls, negative for puts."""
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    _, d2 = _d1_d2(spot, strike, t, r, sigma)
    if right == "C":
        return float(strike * t * np.exp(-r * t) * norm.cdf(d2))
    return float(-strike * t * np.exp(-r * t) * norm.cdf(-d2))


def straddle_greeks(spot, strike, t, r, sigma) -> dict:
    """Aggregate Greeks of a long ATM straddle (call + put), per share.

    Returns a dict with ``delta``, ``gamma``, ``vega``, ``theta`` (time-to-expiry
    convention) and ``rho``. Near the money the straddle delta is close to zero,
    gamma and vega are large and positive, and theta is positive (long optionality
    decays in the holder's favour only through realised movement).
    """
    return {
        "delta": bs_delta(spot, strike, t, r, sigma, "C") + bs_delta(spot, strike, t, r, sigma, "P"),
        "gamma": 2.0 * bs_gamma(spot, strike, t, r, sigma),
        "vega": 2.0 * bs_vega(spot, strike, t, r, sigma),
        "theta": bs_theta(spot, strike, t, r, sigma, "C") + bs_theta(spot, strike, t, r, sigma, "P"),
        "rho": bs_rho(spot, strike, t, r, sigma, "C") + bs_rho(spot, strike, t, r, sigma, "P"),
    }
