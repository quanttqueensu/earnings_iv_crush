"""structures.py
Defined-risk and term-structure trade variants around the short straddle.

The naked short ATM straddle is the primary structure, with two variants the
regime selector switches to:

* **Iron fly** — short ATM straddle plus long out-of-the-money call and put
  wings at ``wing_mult`` times the implied event move. The wings cap the loss,
  required when VIX is elevated (defined-risk regime).
* **Calendar** — short the front-week straddle, long a vega-balanced back-month
  straddle. Harvests the term-structure premium when the front-vs-back IV slope
  dominates the absolute level mispricing.

Each variant exposes a ``*_pnl`` function returning the entry credit, exit value
and net short P&L per ``contracts`` lot, priced with the Black-Scholes engine.
Wing and back-month legs are priced at the ATM implied vol for simplicity (the
skew refinement is deferred to the historical-data phase).

This module implements:

* ``iron_fly_wings``  — wing strikes from the implied event move.
* ``iron_fly_pnl``    — short iron-fly economics (loss is capped).
* ``calendar_ratio``  — vega-balancing front/back contract ratio.
* ``calendar_pnl``    — short-front / long-back calendar economics.
"""

from __future__ import annotations

from ..engine.greeks import bs_price, bs_vega, straddle_price

# ─────────────────────────────────────────────────────────────────────────────
# Iron fly
# ─────────────────────────────────────────────────────────────────────────────


def iron_fly_wings(spot: float, implied_move: float, wing_mult: float = 1.5) -> tuple[float, float]:
    """
    Lower and upper wing strikes for an iron fly.

    Parameters
    ----------
    spot : float
        Underlying price (USD); the ATM body sits here.
    implied_move : float
        Implied event move as a fraction of spot (the straddle's ~1-sigma move).
    wing_mult : float
        Wing distance in multiples of the implied move. Defaults to ``1.5``.

    Returns
    -------
    tuple of float
        ``(lower_strike, upper_strike)`` in USD, floored at zero on the downside.
    """
    offset = wing_mult * implied_move * spot
    return max(spot - offset, 0.0), spot + offset


def iron_fly_pnl(
    spot_entry: float,
    strike: float,
    t_entry: float,
    t_exit: float,
    iv_entry: float,
    iv_exit: float,
    spot_exit: float,
    implied_move: float,
    r: float = 0.0,
    contracts: int = 1,
    wing_mult: float = 1.5,
    multiplier: int = 100,
) -> dict:
    """
    Net P&L of a short iron fly held across the event.

    Short the ATM call and put (the body), long the wing call and put. The
    short body collects the straddle credit; the long wings cost a debit but
    cap the worst-case loss. P&L is the net entry credit minus the net cost to
    close at exit.

    Returns
    -------
    dict
        ``entry_credit``, ``exit_value``, ``pnl`` and ``max_loss`` (USD), where
        ``max_loss`` is the defined worst case (wing width minus net credit).
    """
    lower, upper = iron_fly_wings(spot_entry, implied_move, wing_mult)
    scale = multiplier * contracts

    body_entry = straddle_price(spot_entry, strike, t_entry, r, iv_entry)
    wings_entry = bs_price(spot_entry, upper, t_entry, r, iv_entry, "C") + bs_price(
        spot_entry, lower, t_entry, r, iv_entry, "P"
    )
    net_credit_ps = body_entry - wings_entry

    def _val(s, k, t, sig, right):
        if t <= 0 or sig <= 0:
            return max(s - k, 0.0) if right == "C" else max(k - s, 0.0)
        return bs_price(s, k, t, r, sig, right)

    body_exit = _val(spot_exit, strike, t_exit, iv_exit, "C") + _val(
        spot_exit, strike, t_exit, iv_exit, "P"
    )
    wings_exit = _val(spot_exit, upper, t_exit, iv_exit, "C") + _val(
        spot_exit, lower, t_exit, iv_exit, "P"
    )
    net_close_ps = body_exit - wings_exit

    entry_credit = net_credit_ps * scale
    exit_value = net_close_ps * scale
    wing_width = upper - strike  # symmetric ATM body
    max_loss = (wing_width - net_credit_ps) * scale
    return {
        "entry_credit": float(entry_credit),
        "exit_value": float(exit_value),
        "pnl": float(entry_credit - exit_value),
        "max_loss": float(max_loss),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Calendar
# ─────────────────────────────────────────────────────────────────────────────


def calendar_ratio(
    spot: float,
    strike: float,
    t_front: float,
    t_back: float,
    iv_front: float,
    iv_back: float,
    r: float = 0.0,
) -> float:
    """
    Back-month contract ratio that vega-neutralises a short-front calendar.

    Returns ``vega_front / vega_back`` so that going long this many back-month
    straddles per short front-month straddle leaves the position vega-flat at
    entry; the trade then earns the *differential* crush (front IV falls faster
    than back IV). Returns ``0.0`` if the back-month vega is degenerate.
    """
    vega_front = bs_vega(spot, strike, t_front, r, iv_front)
    vega_back = bs_vega(spot, strike, t_back, r, iv_back)
    if vega_back <= 0:
        return 0.0
    return float(vega_front / vega_back)


def calendar_pnl(
    spot_entry: float,
    strike: float,
    t_front_entry: float,
    t_front_exit: float,
    t_back_entry: float,
    t_back_exit: float,
    iv_front_entry: float,
    iv_front_exit: float,
    iv_back_entry: float,
    iv_back_exit: float,
    spot_exit: float,
    r: float = 0.0,
    contracts: int = 1,
    multiplier: int = 100,
) -> dict:
    """
    Net P&L of a vega-balanced short-front / long-back calendar.

    Short one front-month straddle, long ``calendar_ratio`` back-month straddles
    (vega-flat at entry). The book profits when the front IV collapses by more
    than the back IV after the event.

    Returns
    -------
    dict
        ``ratio`` (back-month straddles held per front straddle), ``entry_credit``
        (net credit collected), ``exit_value`` (net cost to close) and ``pnl``.
    """
    ratio = calendar_ratio(
        spot_entry, strike, t_front_entry, t_back_entry, iv_front_entry, iv_back_entry, r
    )
    scale = multiplier * contracts

    def _straddle(s, k, t, sig):
        if t <= 0 or sig <= 0:
            return abs(s - k)
        return straddle_price(s, k, t, r, sig)

    front_entry = _straddle(spot_entry, strike, t_front_entry, iv_front_entry)
    back_entry = _straddle(spot_entry, strike, t_back_entry, iv_back_entry)
    front_exit = _straddle(spot_exit, strike, t_front_exit, iv_front_exit)
    back_exit = _straddle(spot_exit, strike, t_back_exit, iv_back_exit)

    # Short front, long ratio*back. Net credit = short premium - long premium.
    entry_credit = (front_entry - ratio * back_entry) * scale
    exit_value = (front_exit - ratio * back_exit) * scale
    return {
        "ratio": float(ratio),
        "entry_credit": float(entry_credit),
        "exit_value": float(exit_value),
        "pnl": float(entry_credit - exit_value),
    }
