"""
ib_orders.py
Build and (optionally) transmit the short-straddle legs.

The strategy sells the front-expiry ATM call and put. This module qualifies
those two legs, sizes nothing itself (the caller passes the contract count from
``pnl.size_contracts`` so live and backtest sizing are identical), and submits
them as two single-leg SELL orders. Two safety properties:

* nothing is sent unless ``transmit=True`` is passed explicitly *and* both legs
  qualify - a half-qualified straddle is never sent one-legged; and
* a limit order is priced to be marketable by giving up a configurable fraction
  of the bid-ask spread (``LiveConfig.limit_cross_frac``), rather than a naked
  market order into a wide single-name option book.

``ib_async`` is imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..config import LIVE
from ..data.features import nearest_strike

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ib_async import IB, Contract, Trade

    from .forward_test import StraddleQuote
    from .ib_market import UnderlyingQuote


@dataclass(frozen=True)
class StraddleLegs:
    """The two qualified ATM legs and the price each would sell at.

    Attributes
    ----------
    call, put : ib_async.Contract
        Qualified front-expiry ATM call and put.
    strike : float
        The shared ATM strike.
    expiry : pd.Timestamp
        The front expiry.
    call_price, put_price : float
        Marketable sell prices (NaN when a side has no quote).
    """

    call: Contract
    put: Contract
    strike: float
    expiry: pd.Timestamp
    call_price: float
    put_price: float


def build_straddle_legs(
    ib: IB,
    underlying: UnderlyingQuote,
    chain: pd.DataFrame,
    front_expiry: pd.Timestamp,
) -> StraddleLegs:
    """Qualify the front-expiry ATM call and put and price them to sell.

    The ATM strike is the listed strike of ``front_expiry`` closest to spot
    (``features.nearest_strike``), so the traded instrument matches the strike
    the signal was measured on.

    Parameters
    ----------
    ib : ib_async.IB
        A connected client.
    underlying : UnderlyingQuote
        Qualified underlying and spot.
    chain : pd.DataFrame
        The snapshot chain (canonical schema) used to read the touches.
    front_expiry : pd.Timestamp
        The expiry to trade (from ``features.nearest_expiries``).

    Returns
    -------
    StraddleLegs
        The qualified legs and their marketable sell prices.

    Raises
    ------
    ValueError
        If either leg fails to qualify.
    """
    from ib_async import Option

    strike = nearest_strike(chain, front_expiry, underlying.spot)
    if not np.isfinite(strike):
        raise ValueError("No ATM strike available on the front expiry.")

    expiry_code = pd.Timestamp(front_expiry).strftime("%Y%m%d")
    legs = [
        Option(underlying.contract.symbol, expiry_code, float(strike), right, "SMART")
        for right in ("C", "P")
    ]
    qualified = ib.qualifyContracts(*legs)
    if len(qualified) != 2 or not all(getattr(c, "conId", 0) for c in qualified):
        raise ValueError(f"Could not qualify both straddle legs at strike {strike}.")
    call, put = qualified

    rows = chain[(chain["expiry"] == front_expiry) & np.isclose(chain["strike"], strike)]
    call_px = _sell_price(rows, "C")
    put_px = _sell_price(rows, "P")
    return StraddleLegs(
        call=call,
        put=put,
        strike=float(strike),
        expiry=pd.Timestamp(front_expiry),
        call_price=call_px,
        put_price=put_px,
    )


def place_short_straddle(
    ib: IB,
    legs: StraddleLegs,
    contracts: int,
    *,
    transmit: bool,
    order_type: str = LIVE.order_type,
) -> list[Trade]:
    """Submit the two SELL legs of the straddle.

    With ``transmit=False`` the orders are staged in TWS but not sent (you can
    inspect them in the order window); with ``transmit=True`` they go live to the
    paper account. ``contracts`` is the per-leg quantity from
    ``pnl.size_contracts``.

    Parameters
    ----------
    ib : ib_async.IB
        A connected client.
    legs : StraddleLegs
        The qualified legs from :func:`build_straddle_legs`.
    contracts : int
        Per-leg contract count (> 0).
    transmit : bool
        Whether to actually transmit. Keyword-only by design.
    order_type : str, optional
        ``"LMT"`` or ``"MKT"``. Defaults to ``LiveConfig.order_type``.

    Returns
    -------
    list of ib_async.Trade
        One trade per leg.

    Raises
    ------
    ValueError
        If ``contracts <= 0`` or a limit order lacks a usable price.
    """
    from ib_async import LimitOrder, MarketOrder, Order

    if contracts <= 0:
        raise ValueError("contracts must be positive to place a straddle.")

    trades = []
    for contract, price in ((legs.call, legs.call_price), (legs.put, legs.put_price)):
        order: Order
        if order_type == "MKT":
            order = MarketOrder("SELL", contracts)
        else:
            if not np.isfinite(price):
                raise ValueError(
                    f"No quote to price the {contract.right} leg as a limit order; "
                    "pass order_type='MKT' or skip this name."
                )
            order = LimitOrder("SELL", contracts, round(price, 2))
        order.transmit = bool(transmit)
        trades.append(ib.placeOrder(contract, order))
    return trades


# ── managed buy-back (transmitting exit) ─────────────────────────────────────


@dataclass(frozen=True)
class ManagedExitFill:
    """Realised outcome of a transmitted managed buy-back.

    Attributes
    ----------
    fill_price_ps : float
        Per-share straddle buy-back price actually paid (the two leg average
        fills summed), or the modelled touch when the ladder never filled.
    filled_at_limit : bool
        ``True`` if the close rested inside the touch (filled at a mid-seeking
        rung); ``False`` if it had to cross fully to the touch (or never filled).
    """

    fill_price_ps: float
    filled_at_limit: bool


def place_managed_buyback(
    ib: IB,
    call: Contract,
    put: Contract,
    contracts: int,
    quote: StraddleQuote,
    *,
    transmit: bool,
    cross_frac: float = LIVE.limit_cross_frac,
    reprice_steps: int = LIVE.exit_reprice_steps,
    step_wait_s: float = LIVE.exit_step_wait_s,
) -> ManagedExitFill:
    """Place the mid-seeking straddle buy-back and read the realised broker fill.

    Both legs are bought to close with a limit priced ``cross_frac`` of the way
    from mid toward the touch, then the limit is walked toward the touch over
    ``reprice_steps`` rungs (resting ``step_wait_s`` seconds at each). The first
    rung that fills is taken; if nothing fills before the final full-cross rung
    the modelled touch is booked as the conservative fill. The returned price and
    ``filled_at_limit`` come from the broker, not from an assumed mid mark.

    Reading a fill requires ``transmit=True`` (and a connected gateway); with
    ``transmit=False`` the legs are staged in TWS but never fill, so the touch is
    booked. ``contracts`` is the per-leg quantity (matching the opened lot).

    Raises
    ------
    ValueError
        If ``contracts <= 0``.
    """
    from ib_async import LimitOrder

    if contracts <= 0:
        raise ValueError("contracts must be positive to close a straddle.")

    steps = max(0, int(reprice_steps))
    call_order = LimitOrder("BUY", contracts, 0.0)
    put_order = LimitOrder("BUY", contracts, 0.0)
    call_order.transmit = bool(transmit)
    put_order.transmit = bool(transmit)
    call_trade = put_trade = None

    for i in range(steps + 1):
        frac = cross_frac if steps == 0 else cross_frac + (1.0 - cross_frac) * (i / steps)
        call_order.lmtPrice = round(_leg_buy_limit(quote.call_bid, quote.call_ask, frac), 2)
        put_order.lmtPrice = round(_leg_buy_limit(quote.put_bid, quote.put_ask, frac), 2)
        call_trade = ib.placeOrder(call, call_order)
        put_trade = ib.placeOrder(put, put_order)
        ib.sleep(step_wait_s)
        if _is_filled(call_trade) and _is_filled(put_trade):
            return ManagedExitFill(
                fill_price_ps=_avg_fill(call_trade) + _avg_fill(put_trade),
                filled_at_limit=frac < 1.0,
            )

    # Never filled across the ladder: book the touch as the conservative close.
    return ManagedExitFill(fill_price_ps=float(quote.touch_buy), filled_at_limit=False)


# ── helpers ──────────────────────────────────────────────────────────────────


def _leg_buy_limit(bid: float, ask: float, frac: float) -> float:
    """Buy-to-close limit for one leg, ``frac`` of the way from mid to the ask."""
    mid = 0.5 * (bid + ask)
    half = 0.5 * (ask - bid)
    return float(mid + max(0.0, frac) * half)


def _is_filled(trade: Trade | None) -> bool:
    """Whether a placed trade has reported a complete fill."""
    status = getattr(getattr(trade, "orderStatus", None), "status", "")
    return status == "Filled"


def _avg_fill(trade: Trade | None) -> float:
    """Average fill price reported on a trade (0.0 when none yet)."""
    px = getattr(getattr(trade, "orderStatus", None), "avgFillPrice", 0.0)
    return float(px) if px is not None else 0.0


def _sell_price(rows: pd.DataFrame, right: str) -> float:
    """Marketable sell price for one leg: step from the bid toward the ask.

    Selling, so we start at the bid and give up ``limit_cross_frac`` of the
    spread to lift our fill probability. Falls back to whichever touch exists.
    """
    side = rows[rows["right"] == right]
    if side.empty:
        return float("nan")
    bid = pd.to_numeric(side["bid"], errors="coerce").iloc[0]
    ask = pd.to_numeric(side["ask"], errors="coerce").iloc[0]
    if np.isfinite(bid) and np.isfinite(ask):
        return float(bid + (ask - bid) * (1.0 - LIVE.limit_cross_frac))
    return float(bid if np.isfinite(bid) else ask)
