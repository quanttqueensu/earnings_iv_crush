"""attribution.py
Greek decomposition of realised short-straddle P&L.

A short straddle held across an earnings event earns its money from the
post-event implied-volatility collapse (the vega leg) and loses it to large
realised moves (the short-gamma leg). This module attributes the realised P&L
to those sources via a first-order Greek (Taylor) expansion evaluated at entry,
plus a once-at-close delta hedge — the desk-level view that makes explicit that
the edge is the vega (crush) component, consistent with the Dubinsky-Johannes
(2006) event-variance framing in the literature review.

This module implements:

* ``attribute_straddle_pnl`` — split realised short-straddle P&L into delta,
  gamma, vega and theta components plus a higher-order residual.
* ``delta_hedge_pnl``        — P&L of the spec's once-at-entry-close delta hedge.

References
----------
Dubinsky, A., & Johannes, M. (2006). Earnings announcements and equity options.
*Working paper, Columbia Business School*.
"""

from __future__ import annotations

from .greeks import straddle_greeks, straddle_price


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _straddle_value(spot: float, strike: float, t: float, r: float,
                    sigma: float) -> float:
    """Straddle price per share, falling back to intrinsic at/after expiry."""
    if t <= 0 or sigma <= 0:
        return abs(spot - strike)
    return straddle_price(spot, strike, t, r, sigma)


# ─────────────────────────────────────────────────────────────────────────────
# Attribution
# ─────────────────────────────────────────────────────────────────────────────


def attribute_straddle_pnl(spot_entry: float, strike: float, t_entry: float,
                           t_exit: float, iv_entry: float, iv_exit: float,
                           spot_exit: float, r: float = 0.0, contracts: int = 1,
                           multiplier: int = 100) -> dict:
    """
    Decompose realised short-straddle P&L into Greek components.

    Greeks are evaluated for the long straddle at entry; the short position
    earns the negative of each long-value change. On a clean earnings crush the
    ``vega_pnl`` term dominates and is positive (volatility fell), the
    ``gamma_pnl`` term is negative (any realised move hurts a short-gamma book),
    and ``theta_pnl`` is positive (time passed).

    Parameters
    ----------
    spot_entry, strike : float
        Underlying price at entry and the (ATM) strike (USD).
    t_entry, t_exit : float
        Time-to-expiry in years at entry and exit (``t_exit < t_entry``).
    iv_entry, iv_exit : float
        Straddle implied volatility at entry and exit (annualised).
    spot_exit : float
        Underlying price at exit (USD).
    r : float
        Risk-free rate (annualised, continuously compounded). Defaults to ``0``.
    contracts : int
        Number of straddles.
    multiplier : int
        Shares per contract. Defaults to ``100``.

    Returns
    -------
    dict
        ``delta_pnl``, ``gamma_pnl``, ``vega_pnl``, ``theta_pnl``, ``residual``
        and ``total_pnl`` (USD). The four components plus the residual sum to
        ``total_pnl`` by construction; the residual captures higher-order and
        cross Greek effects the first-order expansion omits.
    """
    g = straddle_greeks(spot_entry, strike, t_entry, r, iv_entry)
    d_spot = spot_exit - spot_entry
    d_sigma = iv_exit - iv_entry
    d_t = t_exit - t_entry  # negative: time-to-expiry shrinks
    scale = multiplier * contracts

    delta_pnl = -g["delta"] * d_spot * scale
    gamma_pnl = -0.5 * g["gamma"] * d_spot ** 2 * scale
    vega_pnl = -g["vega"] * d_sigma * scale
    theta_pnl = -g["theta"] * d_t * scale

    v_entry = _straddle_value(spot_entry, strike, t_entry, r, iv_entry)
    v_exit = _straddle_value(spot_exit, strike, t_exit, r, iv_exit)
    total_pnl = (v_entry - v_exit) * scale
    residual = total_pnl - (delta_pnl + gamma_pnl + vega_pnl + theta_pnl)

    return {
        "delta_pnl": float(delta_pnl),
        "gamma_pnl": float(gamma_pnl),
        "vega_pnl": float(vega_pnl),
        "theta_pnl": float(theta_pnl),
        "residual": float(residual),
        "total_pnl": float(total_pnl),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Delta hedge
# ─────────────────────────────────────────────────────────────────────────────


def delta_hedge_pnl(spot_entry: float, strike: float, t_entry: float,
                    iv_entry: float, spot_exit: float, r: float = 0.0,
                    contracts: int = 1, multiplier: int = 100) -> dict:
    """
    P&L of the spec's once-at-entry-close delta hedge of a short straddle.

    The short straddle has position delta ``-straddle_delta`` per share. The
    hedge takes an offsetting underlying position of ``+straddle_delta`` shares
    (scaled), held to exit. To first order this cancels the option delta P&L,
    leaving the gamma / vega / theta exposure that carries the edge.

    Parameters
    ----------
    spot_entry, strike, t_entry, iv_entry : float
        Straddle state at entry (see ``attribute_straddle_pnl``).
    spot_exit : float
        Underlying price at exit (USD).
    r : float
        Risk-free rate (annualised). Defaults to ``0``.
    contracts : int
        Number of straddles.
    multiplier : int
        Shares per contract. Defaults to ``100``.

    Returns
    -------
    dict
        ``hedge_shares`` (signed share count of the underlying hedge) and
        ``hedge_pnl`` (USD P&L of that hedge over the move to ``spot_exit``).
    """
    g = straddle_greeks(spot_entry, strike, t_entry, r, iv_entry)
    hedge_shares = g["delta"] * multiplier * contracts
    hedge_pnl = hedge_shares * (spot_exit - spot_entry)
    return {"hedge_shares": float(hedge_shares), "hedge_pnl": float(hedge_pnl)}
