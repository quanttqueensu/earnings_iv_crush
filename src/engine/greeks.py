"""Black-Scholes pricing and Greeks for ATM straddles.

Used to price entries/exits and to translate quoted prices into implied vols
when the data feed does not supply them.
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
