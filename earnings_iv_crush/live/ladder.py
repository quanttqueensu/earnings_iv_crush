"""
ladder.py
Clock-driven limit-order ladder that trades every entry and exit leg of a session together.

The forward-test specification (section 2.1) trades the straddle leg by leg with limits
that start at the mid and walk to the touch, finishing before the 15:59 ET mark the
backtest uses:

==========  ===========================================================
15:45:00    rung 0, every leg at mid
15:47:30    rung 1, 25% of the way from mid to the touch
15:50:00    rung 2, 50%
15:52:30    rung 3, 75%
15:55:00    rung 4, the touch (bid for a sell, ask for a buy)
15:56:30    sweep: every unfilled exit leg is re-priced through the displayed ask
15:58:00    cancel every working order; re-read status after the settle time
15:59:00    NBBO of every leg, filled or not (the counterfactual basis)
==========  ===========================================================

Entry legs sell and walk down toward the bid; exit legs buy and walk up toward the ask.
Each rung re-quotes the open legs. A failed re-quote holds the resting order rather
than walking a stale book, and a leg whose book is unusable is not priced. Every limit
is rounded to a legal tick away from the far touch (``ib_orders.round_to_tick``).

**Sweep.** The touch rung bids the displayed ask, which on a delayed feed is minutes
old and can sit under the real offer. An exit left there is a short the rule no longer
wants, and one leg of it is a naked short. So at ``exit_sweep_at`` every unfilled exit
leg is re-priced once to the displayed ask plus a bounded allowance
(:meth:`LegQuote.sweep_limit`), on a tick legal in every option class, and a leg whose
order was rejected or cancelled with nothing filled gets one fresh order. IB's price
protection cancels a limit it judges too far through the market and states the cap; such
a sweep or flatten is re-placed once, one coarse tick under that cap. Entry legs never
sweep: an unfilled sale costs nothing.

**Legging.** An entry is complete only when both legs fill in full. If one leg (or
part of one) fills and the other does not by the cancel time, the filled quantity is
bought back at the sweep price before 15:59 and the event is reported
``legged_flattened``. An exit still incomplete after the sweep has its working orders
cancelled and the caller raises an alarm; the next session's ladder buys back what is
left (``session.plan_exit``).

**Switches.** ``halted()`` is checked before every rung and before the flatten. When it
returns ``True`` every working order is cancelled and nothing further is sent on any
path, flatten included.

**Dry run.** With ``transmit=False`` the ladder runs the same clock and prices, writes
every intended order to the log with ``transmit=False``, and places nothing.

Every state change is written to the order-event log before the ladder acts on it.
The clock and the quote source are injected, so the whole schedule runs offline in
tests against a fake gateway.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from ..config import LIVE
from .ib_orders import round_to_tick
from .order_events import OrderEventLog

EXCHANGE_TZ = "America/New_York"
# US equity options tick in 0.01 / 0.05 (penny programme) or 0.05 / 0.10 (the rest),
# switching at 3.00. A multiple of the coarse pair is legal under both schedules.
_TICK_BREAK = 3.0
_COARSE_TICK_LOW = 0.05
_COARSE_TICK_HIGH = 0.10
# IB's price protection cancels a limit too far through the market (error 202) and states
# the cap: "We cannot accept an order at a limit price at or more aggressive than 3.7."
# The band is not published, so the sweep learns it from the cancel.
_PRICE_CAP_RE = re.compile(r"more aggressive than\s+\$?(\d+(?:\.\d+)?)")


# ── quotes ───────────────────────────────────────────────────────────────────


def _tick(price: float) -> float:
    """Penny-programme tick for an option price (0.01 below 3.00, 0.05 at or above)."""
    return 0.01 if price < 3.0 else 0.05


@dataclass(frozen=True)
class LegQuote:
    """Touch of one option leg at one instant."""

    bid: float
    ask: float
    bid_size: float = float("nan")
    ask_size: float = float("nan")
    ts: pd.Timestamp | None = None

    def usable_for(self, side: str) -> bool:
        """Whether this book can price an order on ``side``.

        A sell needs a positive bid and an ask at or above it. A buy needs a positive
        ask; a missing or zero bid is allowed, because after a large gap the far
        out-of-the-money leg often shows no bid and must still be closable (ticket
        T11). A crossed book is never usable.
        """
        bid_ok = np.isfinite(self.bid) and self.bid > 0
        ask_ok = np.isfinite(self.ask) and self.ask > 0
        if side == "SELL":
            return bool(bid_ok and ask_ok and self.ask >= self.bid)
        if side == "BUY":
            return bool(ask_ok and (not bid_ok or self.bid <= self.ask))
        raise ValueError(f"side must be BUY or SELL, got {side!r}")

    def limit(self, side: str, frac: float) -> float:
        """Rounded limit ``frac`` of the way from mid to the touch on ``side``.

        For a buy with no bid, the walk runs from one tick to the ask instead of from
        the mid, so rung 0 sits half-way between them and the final rung is the ask.
        """
        frac = float(np.clip(frac, 0.0, 1.0))
        if side == "SELL":
            mid = 0.5 * (self.bid + self.ask)
            raw = mid - frac * 0.5 * (self.ask - self.bid)
            return round_to_tick(raw, "SELL", self.bid, self.ask)
        bid = self.bid if (np.isfinite(self.bid) and self.bid > 0) else _tick(self.ask)
        bid = min(bid, self.ask)
        mid = 0.5 * (bid + self.ask)
        raw = mid + frac * 0.5 * (self.ask - bid)
        return round_to_tick(raw, "BUY", None, self.ask)

    def sweep_limit(self, frac: float, floor: float) -> float:
        """Buy limit through the displayed ask by ``max(floor, frac * ask)`` per share.

        Rounded up to 0.05 below 3.00 and to 0.10 at or above, the coarser of the two
        listed tick schedules, so the order is legal whether or not the class is in
        the penny programme and cannot be rejected for its tick.

        Raises
        ------
        ValueError
            If the book has no positive ask: a sweep is never priced off a hole.
        """
        if not self.usable_for("BUY"):
            raise ValueError(f"Cannot price a sweep from bid {self.bid!r} ask {self.ask!r}.")
        raw = self.ask + max(float(floor), float(frac) * self.ask)
        tick = _COARSE_TICK_LOW if raw < _TICK_BREAK else _COARSE_TICK_HIGH
        return float(round(np.ceil(raw / tick - 1e-9) * tick, 2))


def under_price_cap(cap: float) -> float:
    """Highest coarse-tick price strictly below a broker price cap (``nan`` if none).

    The cap is exclusive ("at or more aggressive than"), so a price on the cap itself
    is refused again.
    """
    tick = _COARSE_TICK_LOW if cap <= _TICK_BREAK else _COARSE_TICK_HIGH
    px = float(round((np.ceil(cap / tick - 1e-9) - 1) * tick, 2))
    return px if px > 0 else float("nan")


def price_cap_from(trade: Any) -> float | None:
    """The price cap stated in a trade's log by an IB price-protection cancel, if any."""
    for entry in reversed(list(getattr(trade, "log", []) or [])):
        m = _PRICE_CAP_RE.search(str(getattr(entry, "message", "") or ""))
        if m:
            return float(m.group(1))
    return None


# ── legs ─────────────────────────────────────────────────────────────────────


@dataclass
class LadderLeg:
    """One option leg the ladder works, with its live order state.

    Attributes
    ----------
    group : str
        Legs that must complete together (one straddle entry or one exit).
    purpose : str
        ``"entry"`` or ``"exit"``.
    side : str
        ``"SELL"`` (entries) or ``"BUY"`` (exits).
    right : str
        ``"C"`` or ``"P"``.
    contract : ib_async.Contract
        The qualified option contract.
    quantity : int
        Contracts to trade on this leg.
    """

    group: str
    ticker: str
    position_key: str
    purpose: str
    side: str
    right: str
    contract: Any
    quantity: int
    strike: float
    expiry: pd.Timestamp
    order: Any = None
    trade: Any = None
    limit_price: float = float("nan")
    rung: int | None = None
    last_status: str = ""
    seen_exec: set[str] = field(default_factory=set)
    last_quote: LegQuote | None = None

    @property
    def key(self) -> str:
        return f"{self.group}:{self.right}"

    @property
    def filled_qty(self) -> int:
        """Contracts the broker reports filled on this leg's order."""
        status = getattr(self.trade, "orderStatus", None)
        filled = getattr(status, "filled", 0.0) if status is not None else 0.0
        if filled is None or not np.isfinite(filled):
            return 0
        return int(round(float(filled)))

    @property
    def avg_fill(self) -> float:
        status = getattr(self.trade, "orderStatus", None)
        px = getattr(status, "avgFillPrice", float("nan")) if status is not None else float("nan")
        return float(px) if px is not None and self.filled_qty > 0 else float("nan")

    @property
    def done(self) -> bool:
        return self.filled_qty >= self.quantity

    def working(self) -> bool:
        status = getattr(getattr(self.trade, "orderStatus", None), "status", "")
        return self.trade is not None and status not in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive",
        )

    def base_fields(self) -> dict[str, Any]:
        order_id = getattr(self.order, "orderId", None) if self.order is not None else None
        perm_id = getattr(self.order, "permId", None) if self.order is not None else None
        return {
            "ticker": self.ticker,
            "position_key": self.position_key,
            "leg": self.right,
            "con_id": getattr(self.contract, "conId", None),
            "strike": float(self.strike),
            "expiry": str(pd.Timestamp(self.expiry).date()),
            "purpose": self.purpose,
            "side": self.side,
            "order_id": order_id or None,
            "perm_id": perm_id or None,
            "order_qty": int(self.quantity),
        }


# ── schedule and clock ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class LadderSchedule:
    """Absolute times (exchange time zone) for one session's ladder."""

    rungs: tuple[tuple[pd.Timestamp, float], ...]
    cancel_at: pd.Timestamp
    nbbo_at: pd.Timestamp
    latest_start: pd.Timestamp
    sweep_at: pd.Timestamp | None = None

    @classmethod
    def for_session(cls, session_date: pd.Timestamp, config: Any = LIVE) -> LadderSchedule:
        """Build the schedule from ``LiveConfig`` for an exchange date."""
        day = pd.Timestamp(session_date).date()

        def at(hhmmss: str) -> pd.Timestamp:
            return pd.Timestamp(f"{day} {hhmmss}", tz=EXCHANGE_TZ)

        rungs = tuple((at(t), float(f)) for t, f in config.ladder_rungs)
        sweep_at = at(config.exit_sweep_at)
        sched = cls(
            rungs=rungs,
            cancel_at=at(config.ladder_cancel_at),
            nbbo_at=at(config.ladder_nbbo_at),
            latest_start=at(config.ladder_latest_start),
            sweep_at=sweep_at,
        )
        times = [t for t, _ in rungs] + [sweep_at, sched.cancel_at, sched.nbbo_at]
        if any(b <= a for a, b in zip(times, times[1:], strict=False)):
            raise ValueError("Ladder times must be strictly increasing.")
        return sched


class Clock(Protocol):
    def now(self) -> pd.Timestamp: ...

    def wait_until(self, when: pd.Timestamp) -> None: ...


class IBClock:
    """Wall clock that waits through ``ib.sleep`` so order events keep arriving."""

    def __init__(self, ib: Any, step_s: float = 2.0) -> None:
        self.ib = ib
        self.step_s = step_s

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=EXCHANGE_TZ)

    def wait_until(self, when: pd.Timestamp) -> None:
        while True:
            remaining = (when - self.now()).total_seconds()
            if remaining <= 0:
                return
            self.ib.sleep(min(remaining, self.step_s))


class LadderTooLate(RuntimeError):
    """Raised when a pass reaches the ladder after its latest permitted start."""


# ── outcome ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GroupOutcome:
    """How one straddle entry or exit finished.

    ``status`` is one of ``filled``, ``unfilled``, ``legged_flattened``,
    ``legged_open`` (entry legged and the flatten failed: an alarm) or
    ``incomplete`` (exit not fully closed: an alarm).
    """

    group: str
    purpose: str
    status: str
    fill_ps: float
    legs: tuple[LadderLeg, ...]
    nbbo_1559: dict[str, LegQuote | None]

    @property
    def alarm(self) -> bool:
        return self.status in ("legged_open", "incomplete")


QuoteFn = Callable[[list[LadderLeg]], dict[str, LegQuote | None]]


# ── engine ───────────────────────────────────────────────────────────────────


def _observe(leg: LadderLeg, log: OrderEventLog) -> None:
    """Log any new status and any new execution on one leg's order."""
    trade = leg.trade
    if trade is None:
        return
    status = getattr(trade.orderStatus, "status", "")
    for fill in list(getattr(trade, "fills", []) or []):
        execution = getattr(fill, "execution", None)
        exec_id = str(getattr(execution, "execId", id(fill)))
        if exec_id in leg.seen_exec:
            continue
        leg.seen_exec.add(exec_id)
        report = getattr(fill, "commissionReport", None)
        commission = getattr(report, "commission", None)
        when = getattr(fill, "time", None)
        log.record(
            "fill",
            **leg.base_fields(),
            ts_broker=pd.Timestamp(when).isoformat() if when is not None else None,
            fill_qty=int(getattr(execution, "shares", 0)),
            fill_price=float(getattr(execution, "price", float("nan"))),
            cum_filled=leg.filled_qty,
            avg_fill_price=leg.avg_fill,
            commission=float(commission) if commission else None,
            status=status,
            rung=leg.rung,
        )
    if status != leg.last_status:
        leg.last_status = status
        if status == "Inactive":
            messages = [getattr(e, "message", "") for e in getattr(trade, "log", []) or []]
            log.record(
                "reject",
                **leg.base_fields(),
                status=status,
                reason=next((m for m in reversed(messages) if m), "rejected"),
            )
        else:
            remaining = getattr(trade.orderStatus, "remaining", None)
            log.record(
                "status",
                **leg.base_fields(),
                status=status,
                cum_filled=leg.filled_qty,
                avg_fill_price=leg.avg_fill,
                remaining=int(remaining) if remaining is not None else None,
                limit_price=leg.limit_price,
            )


def _place(
    ib: Any,
    leg: LadderLeg,
    limit: float,
    rung: int,
    frac: float,
    log: OrderEventLog,
    *,
    transmit: bool,
    quote: LegQuote,
    reason: str | None = None,
) -> None:
    """Submit or modify one leg's limit, logging the intent before sending it.

    A rung whose rounded limit equals the resting one sends nothing: re-placing an
    unchanged order costs a message and gains no queue priority.
    """
    posted = bool(np.isfinite(leg.limit_price))
    if posted and np.isclose(limit, leg.limit_price):
        return
    event = "modify" if posted else "submit"
    qty = int(leg.quantity)
    fields = leg.base_fields()
    leg.rung = rung
    leg.limit_price = float(limit)
    if transmit:
        from ib_async import LimitOrder

        if leg.order is None:
            leg.order = LimitOrder(leg.side, qty, float(limit))
            leg.order.transmit = True
            # Stated, not left to the account preset: when the preset fills it in,
            # the gateway answers with notice 10349 and ib_async marks the live
            # order Cancelled locally, which would stop the ladder working it and,
            # at the cancel time, stop it being cancelled.
            leg.order.tif = "DAY"
            # Reserve the id now so the submit row, written before sending, carries
            # it; ib_async's placeOrder keeps an id that is already set.
            leg.order.orderId = ib.client.getReqId()
            fields["order_id"] = leg.order.orderId
        else:
            leg.order.lmtPrice = float(limit)
    log.record(
        event,
        **fields,
        rung=rung,
        cross_frac=frac,
        limit_price=float(limit),
        nbbo_bid=quote.bid,
        nbbo_ask=quote.ask,
        nbbo_bid_size=quote.bid_size,
        nbbo_ask_size=quote.ask_size,
        nbbo_ts_utc=quote.ts.isoformat() if quote.ts is not None else None,
        status="intent" if not transmit else None,
        reason=reason,
    )
    if transmit:
        leg.trade = ib.placeOrder(leg.contract, leg.order)
        # The broker assigns the order id on first placement; later rows carry it.
        _observe(leg, log)


def _cancel_working(ib: Any, legs: Iterable[LadderLeg], log: OrderEventLog) -> None:
    # An order already PendingCancel is not cancelled twice: the broker answers a
    # second cancel with an error, and ib_async marks any order error Cancelled,
    # which would let the ladder act on an order the broker has not yet confirmed.
    for leg in legs:
        if leg.working() and not _pending_cancel(leg):
            log.record("cancel_req", **leg.base_fields(), limit_price=leg.limit_price)
            ib.cancelOrder(leg.order)


def _pending_cancel(leg: LadderLeg) -> bool:
    status = getattr(getattr(leg.trade, "orderStatus", None), "status", "")
    return leg.trade is not None and status == "PendingCancel"


def _await_status(
    ib: Any,
    legs: list[LadderLeg],
    log: OrderEventLog,
    pending: Callable[[LadderLeg], bool],
    *,
    timeout_s: float,
    poll_s: float,
) -> list[LadderLeg]:
    """Re-read status until no leg is ``pending`` or ``timeout_s`` has passed.

    A cancel is not final until the broker confirms it, and on the paper account that
    took over a minute near the close. Acting on an order still being cancelled
    either skips it (the price-cap re-price) or crosses it (a flatten on the same
    contract, which IB reprices so as not to trade against the resting order).

    Returns
    -------
    list of LadderLeg
        The legs still pending when the wait ended.
    """
    if poll_s <= 0:
        raise ValueError(f"poll_s must be positive, got {poll_s!r}")
    waited = 0.0
    while True:
        for leg in legs:
            _observe(leg, log)
        left = [leg for leg in legs if pending(leg)]
        if not left or waited >= timeout_s:
            return left
        ib.sleep(poll_s)
        waited += poll_s


def run_ladder(
    ib: Any,
    legs: list[LadderLeg],
    *,
    quote_fn: QuoteFn,
    clock: Clock,
    schedule: LadderSchedule,
    log: OrderEventLog,
    transmit: bool,
    halted: Callable[[], bool] = lambda: False,
    settle_s: float = LIVE.exit_cancel_settle_s,
    sweep_frac: float = LIVE.exit_sweep_frac,
    sweep_min: float = LIVE.exit_sweep_min,
    confirm_s: float = LIVE.cancel_confirm_s,
    confirm_poll_s: float = LIVE.cancel_confirm_poll_s,
) -> list[GroupOutcome]:
    """Work every leg through the rung schedule and report each group's outcome.

    Parameters
    ----------
    ib : ib_async.IB or a fake with ``placeOrder``, ``cancelOrder`` and ``sleep``
        The gateway. Never called when ``transmit`` is ``False``.
    legs : list of LadderLeg
        Every entry and exit leg of the session.
    quote_fn : callable
        Returns the current :class:`LegQuote` per leg key, or ``None`` for a leg it
        could not quote.
    clock : Clock
        Supplies ``now`` and ``wait_until``.
    schedule : LadderSchedule
        The session's rung times.
    log : OrderEventLog
        Destination for every event.
    transmit : bool
        Whether orders are actually placed.
    halted : callable, optional
        The ``HALT`` switch; checked before each rung and before the flatten.
    settle_s : float, optional
        Seconds to wait after cancelling before re-reading status, because a fill can
        reach the exchange ahead of the cancel.
    sweep_frac, sweep_min : float, optional
        Allowance of the exit sweep and the flatten above the displayed ask
        (:meth:`LegQuote.sweep_limit`).
    confirm_s, confirm_poll_s : float, optional
        Longest wait, and poll interval, for the broker to confirm a cancel before
        the ladder acts on that order (:func:`_await_status`).

    Returns
    -------
    list of GroupOutcome
        One per group, in first-seen order.

    Raises
    ------
    LadderTooLate
        If the pass reaches the ladder after ``schedule.latest_start``. Nothing is sent.
    """
    if not legs:
        return []
    if clock.now() > schedule.latest_start:
        raise LadderTooLate(
            f"ladder reached at {clock.now():%H:%M:%S} ET, after the latest start "
            f"{schedule.latest_start:%H:%M:%S}; no orders sent"
        )
    was_halted = False
    try:
        for rung, (when, frac) in enumerate(schedule.rungs):
            clock.wait_until(when)
            for leg in legs:
                _observe(leg, log)
            if halted():
                was_halted = True
                log.record("halt", reason=f"HALT present before rung {rung}; cancelling all")
                _cancel_working(ib, legs, log)
                break
            # A leg whose order ended without filling (a reject) is not re-placed:
            # modifying a finished order raises inside ib_async, and resending blindly
            # loops on the same reject (ticket T13 adds a single fresh retry).
            open_legs = [
                leg for leg in legs if not leg.done and (leg.trade is None or leg.working())
            ]
            if not open_legs:
                break
            quotes = quote_fn(open_legs)
            for leg in open_legs:
                q = quotes.get(leg.key)
                if q is None:
                    log.record("hold_stale_quote", **leg.base_fields(), rung=rung)
                    continue
                leg.last_quote = q
                if not q.usable_for(leg.side):
                    log.record(
                        "skip_bad_book",
                        **leg.base_fields(),
                        rung=rung,
                        nbbo_bid=q.bid,
                        nbbo_ask=q.ask,
                    )
                    continue
                _place(
                    ib, leg, q.limit(leg.side, frac), rung, frac, log, transmit=transmit, quote=q
                )

        if not was_halted and schedule.sweep_at is not None:
            clock.wait_until(schedule.sweep_at)
            for leg in legs:
                _observe(leg, log)
            if halted():
                was_halted = True
                log.record("halt", reason="HALT present before the sweep; cancelling all")
                _cancel_working(ib, legs, log)
            else:
                # Entries stop resting here, not at the cancel time, so that the
                # broker has confirmed every entry cancel before a legged entry is
                # flattened at 15:58. No entry fill in the book has come after 15:55.
                _cancel_working(ib, [leg for leg in legs if leg.purpose == "entry"], log)
                _sweep(
                    ib,
                    legs,
                    quote_fn,
                    log,
                    rung=len(schedule.rungs),
                    transmit=transmit,
                    frac=sweep_frac,
                    floor=sweep_min,
                    settle_s=settle_s,
                    confirm_s=confirm_s,
                    confirm_poll_s=confirm_poll_s,
                )

        if not was_halted:
            clock.wait_until(schedule.cancel_at)
        for leg in legs:
            _observe(leg, log)
        _cancel_working(ib, legs, log)
        if transmit:
            ib.sleep(settle_s)
            entries = [leg for leg in legs if leg.purpose == "entry"]
            for leg in _await_status(
                ib,
                entries,
                log,
                LadderLeg.working,
                timeout_s=confirm_s,
                poll_s=confirm_poll_s,
            ):
                log.record(
                    "alarm",
                    **leg.base_fields(),
                    reason=f"entry cancel not confirmed after {confirm_s:g} s; "
                    "a flatten on this contract may be repriced by the broker",
                )
        for leg in legs:
            _observe(leg, log)

        flatten_legs = _flatten(
            ib,
            legs,
            quote_fn,
            clock,
            schedule,
            log,
            transmit=transmit,
            halted=was_halted or halted(),
            settle_s=settle_s,
            sweep_frac=sweep_frac,
            sweep_min=sweep_min,
            confirm_s=confirm_s,
            confirm_poll_s=confirm_poll_s,
        )

        clock.wait_until(schedule.nbbo_at)
        final = quote_fn(legs)
        for leg in legs:
            q = final.get(leg.key)
            log.record(
                "nbbo_1559",
                **leg.base_fields(),
                nbbo_bid=q.bid if q else None,
                nbbo_ask=q.ask if q else None,
                nbbo_bid_size=q.bid_size if q else None,
                nbbo_ask_size=q.ask_size if q else None,
                nbbo_ts_utc=q.ts.isoformat() if q is not None and q.ts is not None else None,
                cum_filled=leg.filled_qty,
                reason=None if q else "no quote at 15:59",
            )
    except BaseException:
        _cancel_working(ib, legs, log)
        raise

    return _outcomes(legs, flatten_legs, final)


def _sweep(
    ib: Any,
    legs: list[LadderLeg],
    quote_fn: QuoteFn,
    log: OrderEventLog,
    *,
    rung: int,
    transmit: bool,
    frac: float,
    floor: float,
    settle_s: float = 0.0,
    confirm_s: float = 0.0,
    confirm_poll_s: float = 1.0,
) -> None:
    """Re-price every unfilled exit leg once through the displayed ask.

    A leg that cannot be re-quoted is priced from the last book this ladder read for
    it, because holding at a stale touch is what leaves the short open; a leg that
    was never quoted is not priced and is logged as an alarm. A leg whose order ended
    with nothing filled (a reject, or a cancel the ladder did not ask for) gets one
    fresh order. One that ended partly filled is left alone: its remainder is the next
    session's to buy, from the fills in the log. A sweep the broker then cancels for
    price protection is re-placed once under the cap it states (``_retry_under_cap``).
    """
    targets = [leg for leg in legs if leg.purpose == "exit" and not leg.done]
    if not targets:
        return
    quotes = quote_fn(targets)
    for leg in targets:
        q = quotes.get(leg.key)
        stale = q is None or not q.usable_for("BUY")
        if stale:
            q = leg.last_quote
        if q is None or not q.usable_for("BUY"):
            log.record("alarm", **leg.base_fields(), rung=rung, reason="exit sweep: no book")
            continue
        leg.last_quote = q
        if leg.trade is not None and not leg.working():
            if leg.filled_qty > 0:
                log.record(
                    "alarm",
                    **leg.base_fields(),
                    rung=rung,
                    reason="exit sweep: order ended partly filled; remainder left open",
                )
                continue
            leg.order, leg.trade = None, None
            leg.limit_price, leg.last_status = float("nan"), ""
        _place(
            ib,
            leg,
            q.sweep_limit(frac, floor),
            rung,
            1.0,
            log,
            transmit=transmit,
            quote=q,
            reason="sweep through the ask" + (" (last book read)" if stale else ""),
        )
    if transmit:
        ib.sleep(settle_s)
        # A price-protection cancel shows PendingCancel before the broker's message
        # arrives; re-pricing is decided only once it has.
        _await_status(ib, targets, log, _pending_cancel, timeout_s=confirm_s, poll_s=confirm_poll_s)
        _retry_under_cap(ib, targets, log, rung=rung, reason="sweep")


def _retry_under_cap(
    ib: Any, legs: list[LadderLeg], log: OrderEventLog, *, rung: int, reason: str
) -> None:
    """Re-place, once, a buy the broker cancelled for being too far through the market.

    Only an order that ended with nothing filled is re-placed, one coarse tick under the
    cap the broker stated; a partly filled one is left to the next session, as in the
    sweep, because a fresh order for the full quantity would over-buy.
    """
    for leg in legs:
        _observe(leg, log)
        if leg.trade is None or leg.working() or leg.done:
            continue
        cap = price_cap_from(leg.trade)
        if cap is None:
            continue
        px = under_price_cap(cap)
        if leg.filled_qty > 0 or not np.isfinite(px) or leg.last_quote is None:
            log.record(
                "alarm",
                **leg.base_fields(),
                rung=rung,
                reason=f"{reason}: cancelled at the broker price cap {cap}; not re-placed",
            )
            continue
        leg.order, leg.trade = None, None
        leg.limit_price, leg.last_status = float("nan"), ""
        _place(
            ib,
            leg,
            px,
            rung,
            1.0,
            log,
            transmit=True,
            quote=leg.last_quote,
            reason=f"{reason} re-priced under the broker price cap {cap}",
        )


def _flatten(
    ib: Any,
    legs: list[LadderLeg],
    quote_fn: QuoteFn,
    clock: Clock,
    schedule: LadderSchedule,
    log: OrderEventLog,
    *,
    transmit: bool,
    halted: bool,
    settle_s: float,
    sweep_frac: float,
    sweep_min: float,
    confirm_s: float = 0.0,
    confirm_poll_s: float = 1.0,
) -> dict[str, LadderLeg]:
    """Buy back the filled quantity of every legged entry at the sweep price.

    Returns the flatten legs by group so the outcome can tell a repaired legging from
    an open one. With ``halted`` set nothing is sent, and the legging is reported open.
    """
    by_group: dict[str, list[LadderLeg]] = {}
    for leg in legs:
        if leg.purpose == "entry":
            by_group.setdefault(leg.group, []).append(leg)
    legged = {
        g: [leg for leg in group if leg.filled_qty > 0]
        for g, group in by_group.items()
        if not all(leg.done for leg in group) and any(leg.filled_qty > 0 for leg in group)
    }
    flat: dict[str, LadderLeg] = {}
    if not legged or halted or not transmit:
        return flat
    to_close = [leg for group in legged.values() for leg in group]
    probes = [
        LadderLeg(
            group=f"{leg.group}:flatten",
            ticker=leg.ticker,
            position_key=leg.position_key,
            purpose="flatten",
            side="BUY",
            right=leg.right,
            contract=leg.contract,
            quantity=leg.filled_qty,
            strike=leg.strike,
            expiry=leg.expiry,
        )
        for leg in to_close
    ]
    quotes = quote_fn(probes)
    for probe in probes:
        q = quotes.get(probe.key)
        if q is None or not q.usable_for("BUY"):
            log.record("alarm", **probe.base_fields(), reason="legged entry: no book to flatten")
            continue
        # The same stale-ask problem as an exit, with one attempt and under a minute
        # left: priced through the ask so the naked leg is actually closed.
        _place(
            ib,
            probe,
            q.sweep_limit(sweep_frac, sweep_min),
            len(schedule.rungs) + 1,
            1.0,
            log,
            transmit=True,
            quote=q,
            reason="flatten through the ask",
        )
        probe.last_quote = q
    ib.sleep(settle_s)
    _await_status(ib, probes, log, _pending_cancel, timeout_s=confirm_s, poll_s=confirm_poll_s)
    _retry_under_cap(ib, probes, log, rung=len(schedule.rungs) + 1, reason="flatten")
    clock.wait_until(schedule.nbbo_at - pd.Timedelta(seconds=10))
    for probe in probes:
        _observe(probe, log)
    _cancel_working(ib, probes, log)
    ib.sleep(settle_s)
    for probe in probes:
        _observe(probe, log)
        flat[f"{probe.group.rsplit(':flatten', 1)[0]}:{probe.right}"] = probe
    return flat


def _outcomes(
    legs: list[LadderLeg],
    flat: dict[str, LadderLeg],
    final: dict[str, LegQuote | None],
) -> list[GroupOutcome]:
    groups: dict[str, list[LadderLeg]] = {}
    for leg in legs:
        groups.setdefault(leg.group, []).append(leg)
    out: list[GroupOutcome] = []
    for group, members in groups.items():
        purpose = members[0].purpose
        nbbo = {leg.right: final.get(leg.key) for leg in members}
        if all(leg.done for leg in members):
            status = "filled"
            fill_ps = float(sum(leg.avg_fill for leg in members))
        elif not any(leg.filled_qty > 0 for leg in members):
            status = "unfilled"
            fill_ps = float("nan")
        elif purpose == "entry":
            repaired = [flat.get(leg.key) for leg in members if leg.filled_qty > 0]
            ok = all(p is not None and p.done for p in repaired)
            status = "legged_flattened" if ok else "legged_open"
            fill_ps = float("nan")
        else:
            status = "incomplete"
            fill_ps = float("nan")
        out.append(
            GroupOutcome(
                group=group,
                purpose=purpose,
                status=status,
                fill_ps=fill_ps,
                legs=tuple(members),
                nbbo_1559=nbbo,
            )
        )
    return out
