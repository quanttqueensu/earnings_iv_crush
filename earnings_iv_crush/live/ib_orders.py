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

from collections.abc import Callable
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
    strike = nearest_strike(chain, front_expiry, underlying.spot)
    if not np.isfinite(strike):
        raise ValueError("No ATM strike available on the front expiry.")
    call, put = qualify_straddle_legs(ib, underlying.contract.symbol, float(strike), front_expiry)

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


def qualify_straddle_legs(
    ib: IB, symbol: str, strike: float, expiry: pd.Timestamp
) -> tuple[Contract, Contract]:
    """Qualify the call and put at an explicit strike and expiry.

    Exits must close the contracts that were sold, so they pass the stored strike and
    expiry here rather than re-picking the strike nearest today's spot, which after an
    earnings move is a different contract.

    Raises
    ------
    ValueError
        If either leg fails to qualify.
    """
    from ib_async import Option

    expiry_code = pd.Timestamp(expiry).strftime("%Y%m%d")
    legs = [Option(symbol, expiry_code, float(strike), right, "SMART") for right in ("C", "P")]
    qualified = ib.qualifyContracts(*legs)
    if len(qualified) != 2 or not all(getattr(c, "conId", 0) for c in qualified):
        raise ValueError(f"Could not qualify both straddle legs at strike {strike}.")
    return qualified[0], qualified[1]


def round_to_tick(
    price: float, side: str, bid: float | None = None, ask: float | None = None
) -> float:
    """Round a limit to a legal option tick, never through the far touch.

    Penny-program schedule: 0.01 below 3.00, 0.05 at or above. A buy rounds up (it may
    not exceed the ask), a sell rounds down (it may not go below the bid), so rounding
    never makes an order less likely to fill than the unrounded price, and never
    crosses the spread. Non-penny classes (0.05 / 0.10) can still reject; the order
    log records the rejection rather than resubmitting blindly.

    Raises
    ------
    ValueError
        If ``price`` is not finite or the rounded limit is not positive: an order
        priced off a missing quote must fail here, not reach the broker.
    """
    if not np.isfinite(price):
        raise ValueError(f"Cannot build a limit from a non-finite price ({price!r}).")
    tick = 0.01 if price < 3.0 else 0.05
    steps = price / tick
    n = np.ceil(steps - 1e-9) if side == "BUY" else np.floor(steps + 1e-9)
    out = float(round(n * tick, 2))
    if side == "BUY" and ask is not None and np.isfinite(ask):
        out = min(out, float(ask))
    if side == "SELL" and bid is not None and np.isfinite(bid):
        out = max(out, float(bid))
    if out <= 0:
        raise ValueError(f"Limit {out!r} from price {price!r} is not a legal option price.")
    return out


def broker_short_qty(ib: IB, contract: Contract) -> int:
    """Signed position the broker holds in ``contract`` (negative when short)."""
    con_id = getattr(contract, "conId", None)
    total = 0
    for p in ib.positions():
        if getattr(p.contract, "conId", None) == con_id:
            total += int(p.position)
    return total


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
            order = LimitOrder("SELL", contracts, round_to_tick(price, "SELL"))
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
        fills summed). NaN when the ladder did not complete: an unfilled order is
        never booked as if it had filled.
    filled_at_limit : bool
        ``True`` if the close filled at a mid-seeking rung; ``False`` if it had to
        cross fully to the touch or did not complete.
    complete : bool
        ``True`` only when both legs reported a complete fill.
    legs_filled : int
        Number of legs fully filled (0, 1 or 2). One means the position is legged
        and needs operator attention.
    filled_qty : tuple of int
        Contracts the broker reports filled on the call and the put. A leg can be
        partly filled without being complete, so this, not ``legs_filled``, is what
        the operator needs to square the position.
    """

    fill_price_ps: float
    filled_at_limit: bool
    complete: bool = True
    legs_filled: int = 2
    filled_qty: tuple[int, int] = (0, 0)


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
    requote: Callable[[], StraddleQuote | None] | None = None,
    cancel_settle_s: float = LIVE.exit_cancel_settle_s,
) -> ManagedExitFill:
    """Place the mid-seeking straddle buy-back and read the realised broker fill.

    Both legs are bought to close with a limit priced ``cross_frac`` of the way
    from mid toward the touch, then walked toward the touch over ``reprice_steps``
    rungs, resting ``step_wait_s`` seconds at each. Each rung re-reads the quote
    through ``requote`` when supplied; when the re-read fails the resting orders
    are held at their last price rather than walked along the stale book. Only a
    leg that is not yet filled is repriced, and a leg whose own book is crossed,
    unpriced or has no offer is never priced at all. If both legs are not filled
    by the final rung, every working order is cancelled, the statuses are re-read
    after ``cancel_settle_s`` (a fill can beat the cancel), and an unfinished
    ladder is marked incomplete with a NaN price: the caller must not book it as
    a close. Any exception inside the ladder cancels the working orders before it
    propagates, so nothing is left resting at the broker unobserved.

    Reading a fill requires ``transmit=True`` (and a connected gateway); with
    ``transmit=False`` the legs are staged in TWS but never fill. ``contracts`` is
    the per-leg quantity (matching the opened lot).

    Raises
    ------
    ValueError
        If ``contracts <= 0``.
    """
    from ib_async import LimitOrder

    if contracts <= 0:
        raise ValueError("contracts must be positive to close a straddle.")

    steps = max(0, int(reprice_steps))
    orders = {"C": LimitOrder("BUY", contracts, 0.0), "P": LimitOrder("BUY", contracts, 0.0)}
    for o in orders.values():
        o.transmit = bool(transmit)
    contracts_by_right = {"C": call, "P": put}
    trades: dict[str, Trade | None] = {"C": None, "P": None}
    q = quote
    last_frac = cross_frac

    def _cancel_working() -> None:
        for right, order in orders.items():
            if trades[right] is not None and not _is_filled(trades[right]):
                ib.cancelOrder(order)

    def _result(frac: float) -> ManagedExitFill:
        qty = (_filled_qty(trades["C"], contracts), _filled_qty(trades["P"], contracts))
        if all(_is_filled(t) for t in trades.values()):
            return ManagedExitFill(
                fill_price_ps=sum(_avg_fill(t) for t in trades.values()),
                filled_at_limit=frac < 1.0,
                filled_qty=qty,
            )
        return ManagedExitFill(
            fill_price_ps=float("nan"),
            filled_at_limit=False,
            complete=False,
            legs_filled=sum(_is_filled(t) for t in trades.values()),
            filled_qty=qty,
        )

    try:
        for i in range(steps + 1):
            frac = cross_frac if steps == 0 else cross_frac + (1.0 - cross_frac) * (i / steps)
            if requote is not None and i > 0:
                fresh = requote()
                if fresh is None:
                    ib.sleep(step_wait_s)
                    if all(_is_filled(t) for t in trades.values()):
                        return _result(last_frac)
                    continue
                q = fresh
            last_frac = frac
            books = {"C": (q.call_bid, q.call_ask), "P": (q.put_bid, q.put_ask)}
            for right, order in orders.items():
                if _is_filled(trades[right]):
                    continue
                bid, ask = books[right]
                if not _leg_book_usable(bid, ask):
                    continue
                order.lmtPrice = round_to_tick(_leg_buy_limit(bid, ask, frac), "BUY", bid, ask)
                trades[right] = ib.placeOrder(contracts_by_right[right], order)
            ib.sleep(step_wait_s)
            if all(_is_filled(t) for t in trades.values()):
                return _result(last_frac)
    except BaseException:
        _cancel_working()
        raise

    _cancel_working()
    ib.sleep(cancel_settle_s)
    return _result(last_frac)


# ── helpers ──────────────────────────────────────────────────────────────────


def _leg_buy_limit(bid: float, ask: float, frac: float) -> float:
    """Buy-to-close limit for one leg, ``frac`` of the way from mid to the ask."""
    mid = 0.5 * (bid + ask)
    half = 0.5 * (ask - bid)
    return float(mid + max(0.0, frac) * half)


def _leg_book_usable(bid: float, ask: float) -> bool:
    """Whether one leg's touch can price a buy-to-close.

    The package check upstream sums the legs, so a crossed or empty leg can hide
    inside a sane straddle spread; each leg needs a finite non-negative bid, a
    positive offer, and no cross. A locked book (bid equal to ask) is usable.
    """
    return bool(np.isfinite(bid) and np.isfinite(ask) and bid >= 0 and ask > 0 and ask >= bid)


def _filled_qty(trade: Trade | None, contracts: int) -> int:
    """Contracts the broker reports filled on one leg."""
    if _is_filled(trade):
        return int(contracts)
    filled = getattr(getattr(trade, "orderStatus", None), "filled", 0.0)
    return int(filled) if filled is not None and np.isfinite(filled) else 0


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
