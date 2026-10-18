"""
session.py
The daily paper-book pass: confirm the calendar, plan exits and entries, run one ladder, book fills.

This is the forward-test specification's daily rule (sections 2 to 7) in one place:

1. **Calendar.** A name is a candidate only when at least two of three independent
   sources (Finnhub, Nasdaq, Yahoo) agree on its announcement date and session, and
   that bracket puts the entry on today's session. Fewer than two is skipped with
   reason ``calendar_unconfirmed``; an unknown session is never guessed.
2. **Exits.** Every open position due today is closed on the stored strike and
   expiry. A transmitting exit first checks the broker holds the short legs.
3. **Entries.** Candidates are admitted in ascending SHA-256 of ``ticker|entry_date``,
   an order that depends on nothing about the trade, up to ``max_names_per_day``. Each
   is priced on the first expiry strictly after the exit date, skipped if an
   ex-dividend date falls inside the hold or cannot be read, and sized with the
   backtest's ``size_contracts`` capped at ``max_contracts_per_leg``.
4. **Ladder.** Every entry and exit leg runs through one ``ladder.run_ladder``.
5. **Booking.** A transmitted entry is booked from its fills, never from the model
   price; a dry pass books its intent at the 15:59 mid into the dry stores only, so a
   dry run can never mark a broker-held short as closed.

Every admitted event and every due exit gets a row in the intended-trades log, filled
or not, because the paired-improvement measure counts unfilled entries at zero. Every
alarm is printed with the ``ALARM:`` prefix the drivers look for, and the pass returns
the alarm count so the driver can exit non-zero.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from ..config import GLOBAL, LIVE, LiveConfig
from ..data.features import atm_iv, nearest_strike
from ..engine.greeks import implied_vol
from ..engine.pnl import ACCOUNT_SIZE, _straddle_value, regt_straddle_margin, size_contracts
from . import ib_market, ib_orders, paper_book
from .forward_test import FORWARD, StraddleQuote
from .ib_connection import kill_switch_active
from .ladder import (
    Clock,
    GroupOutcome,
    IBClock,
    LadderLeg,
    LadderSchedule,
    LadderTooLate,
    LegQuote,
    run_ladder,
)
from .order_events import OrderEventLog, position_key

R = GLOBAL.risk_free_rate
MULT = GLOBAL.contract_multiplier
SESSIONS = ("bmo", "amc")
# Strikes snapshotted around spot per name: enough for the ATM pair after a gap in the
# listed grid, small enough to stay far inside IB's market-data line limit.
STRIKES_AROUND_SPOT = 8


# ── stores ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stores:
    """Every path one pass reads or writes. Dry passes get their own copies."""

    open_positions: str
    nostop: str
    stop: str
    reconciliation: str
    heartbeat: str
    intended: str
    order_events: str

    @classmethod
    def for_mode(
        cls, transmit: bool, config: LiveConfig = LIVE, root: str | Path | None = None
    ) -> Stores:
        """The stores for a transmitting or a dry pass.

        ``root`` relocates every store (tests use a temporary directory); a dry pass
        always lives one level down, in its own ``dry`` folder.
        """
        if root is not None:
            base = Path(root)
            names = cls.for_mode(True, config)
            live_root = cls(**{k: str(base / Path(v).name) for k, v in names.__dict__.items()})
            if transmit:
                return live_root
            return cls(**{k: str(base / "dry" / Path(v).name) for k, v in names.__dict__.items()})
        live = cls(
            open_positions=config.open_positions_path,
            nostop=FORWARD.nostop_ledger_path,
            stop=FORWARD.stop_ledger_path,
            reconciliation=FORWARD.reconciliation_path,
            heartbeat=config.heartbeat_path,
            intended=config.intended_path,
            order_events=config.order_events_path,
        )
        if transmit:
            return live
        dry = Path(config.dry_dir)
        return cls(**{k: str(dry / Path(v).name) for k, v in live.__dict__.items()})


INTENDED_COLUMNS = [
    "run_id",
    "session_date",
    "ticker",
    "purpose",
    "announce_date",
    "session",
    "entry_date",
    "exit_date",
    "position_key",
    "strike",
    "expiry",
    "contracts",
    "decision",
    "reason",
    "outcome",
    "fill_ps",
    "nbbo_mid_1559_ps",
    "transmit",
    "calendar_detail",
]


def _append_intended(path: str, row: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists() or p.stat().st_size == 0
    with p.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(INTENDED_COLUMNS)
        w.writerow(["" if row.get(c) is None else row.get(c) for c in INTENDED_COLUMNS])


# ── universe and calendar confirmation ───────────────────────────────────────


def load_universe(path: str | Path) -> set[str]:
    """Tickers of the tradable universe; raises when the file is missing or empty.

    The calendar is the whole US tape, so trading without the universe would put
    micro-caps into a book specified and costed on 346 liquid names.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Universe file {p} not found; the session pass will not trade the whole tape."
        )
    frame = pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p, columns=["ticker"])
    tickers = set(frame["ticker"].dropna().astype(str))
    if not tickers:
        raise ValueError(f"Universe file {p} lists no tickers.")
    return tickers


def _norm_session(value: Any) -> str | None:
    """``bmo``/``amc``; ``dmh`` shares the ``bmo`` bracket; anything else is unknown."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    key = str(value).strip().lower()
    if key == "dmh":
        return "bmo"
    return key if key in SESSIONS else None


def confirm_events(votes: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Apply the 2-of-3 rule to calendar votes and bracket each confirmed event.

    Parameters
    ----------
    votes : pandas.DataFrame
        One row per (source, ticker) with ``source``, ``ticker``, ``announce_date``
        and ``session``.
    asof : pandas.Timestamp
        Today's exchange date.

    Returns
    -------
    pandas.DataFrame
        One row per ticker: ``ticker``, ``announce_date``, ``session``, ``n_agree``,
        ``confirmed``, ``entry_date``, ``exit_date``, ``is_today`` and ``detail``
        (each source's answer, so disagreements are visible in the log).
    """
    from ..data.earnings import trade_dates_for_session

    cols = [
        "ticker",
        "announce_date",
        "session",
        "n_agree",
        "confirmed",
        "entry_date",
        "exit_date",
        "is_today",
        "detail",
    ]
    if votes.empty:
        return pd.DataFrame(columns=cols)
    v = votes.copy()
    v["announce_date"] = pd.to_datetime(v["announce_date"]).dt.normalize()
    v["session_n"] = v["session"].map(_norm_session)
    rows = []
    for ticker, g in v.groupby("ticker", sort=True):
        detail = "; ".join(
            f"{s}={pd.Timestamp(d).date()} {sess or 'unknown'}"
            for s, d, sess in zip(g["source"], g["announce_date"], g["session_n"], strict=True)
        )
        known = g[g["session_n"].notna()]
        counts = known.groupby(["announce_date", "session_n"])["source"].nunique()
        best = counts[counts >= 2]
        row: dict[str, Any] = {"ticker": ticker, "detail": detail, "confirmed": False}
        if len(best) == 1:
            pair, n = next(iter(best.items()))
            day, sess = pd.Timestamp(pair[0]), str(pair[1])  # type: ignore[index]
            bracket = trade_dates_for_session(day, sess)
            if bracket is not None:
                row.update(
                    announce_date=day,
                    session=sess,
                    n_agree=int(n),
                    confirmed=True,
                    entry_date=bracket[0],
                    exit_date=bracket[1],
                )
        if not row["confirmed"]:
            row["n_agree"] = int(counts.max()) if len(counts) else 0
        row["is_today"] = bool(row["confirmed"] and row["entry_date"] == asof.normalize())
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


VoteFn = Callable[[pd.Timestamp, set[str]], pd.DataFrame]


def gather_votes(
    asof: pd.Timestamp,
    universe: set[str],
    *,
    finnhub: Callable[[str, str], pd.DataFrame] | None = None,
    nasdaq: Callable[[str], pd.DataFrame] | None = None,
    yahoo: Callable[[list[str], str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Collect each source's (date, session) for universe names that could enter today.

    An entry today means an announcement today after the close or on the next session
    before the open, so only those two dates are read. A source that fails contributes
    no votes and is reported, never silently treated as agreement.
    """
    from ..data import earnings as cal

    finnhub = finnhub or cal.fetch_earnings_calendar
    nasdaq = nasdaq or cal.fetch_nasdaq_calendar
    yahoo = yahoo or cal.fetch_earnings_dates
    days = [asof.normalize(), (asof + BDay(1)).normalize()]
    lo, hi = str(days[0].date()), str(days[1].date())
    frames: list[pd.DataFrame] = []

    try:
        fh = finnhub(lo, hi)
        if not fh.empty:
            fh = fh.rename(columns={"hour": "session"})
            fh["source"] = "finnhub"
            frames.append(fh[["source", "ticker", "announce_date", "session"]])
    except Exception as exc:  # noqa: BLE001 - a dead source is reported and outvoted
        print(f"  warning: Finnhub calendar unavailable ({type(exc).__name__}: {exc}).")
    for day in days:
        try:
            nq = nasdaq(str(day.date()))
            nq["source"] = "nasdaq"
            frames.append(nq[["source", "ticker", "announce_date", "session"]])
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: Nasdaq calendar unavailable for {day.date()} ({exc}).")
    seen = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if seen.empty:
        return pd.DataFrame(columns=["source", "ticker", "announce_date", "session"])
    seen["announce_date"] = pd.to_datetime(seen["announce_date"]).dt.normalize()
    seen = seen[seen["ticker"].isin(universe) & seen["announce_date"].isin(days)]
    names = sorted(seen["ticker"].unique())
    if names:
        try:
            yh = yahoo(names, lo, hi)
            yh["source"] = "yahoo"
            seen = pd.concat([seen, yh[["source", "ticker", "announce_date", "session"]]])
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: Yahoo earnings dates unavailable ({exc}).")
    return seen.reset_index(drop=True)


# ── ex-dividend ──────────────────────────────────────────────────────────────


def exdiv_decision(
    dates: dict[str, Any], entry: pd.Timestamp, exit_: pd.Timestamp
) -> tuple[bool, str]:
    """Whether a hold from ``entry`` to ``exit_`` is clear of an ex-dividend date.

    ``dates`` maps each source to a ``Timestamp``, ``None`` (the source reports no
    upcoming dividend) or ``"unreadable"``. Any readable date inside the hold blocks
    the trade, because a short call in the money before an ex-date can be assigned
    early. If no source could be read the answer is unknown and the trade is skipped.
    """
    readable = {s: d for s, d in dates.items() if not (isinstance(d, str) and d == "unreadable")}
    if not readable:
        return False, "exdiv_unknown"
    for d in readable.values():
        if d is not None and entry.normalize() <= pd.Timestamp(d).normalize() <= exit_.normalize():
            return False, "exdiv_in_window"
    return True, ""


def _yahoo_exdiv(ticker: str) -> Any:
    """Ex-dividend date from Yahoo's calendar, ``None`` when it lists none."""
    try:
        import yfinance as yf

        cal = yf.Ticker(ticker).calendar or {}
    except Exception:  # noqa: BLE001 - reported to the caller as unreadable
        return "unreadable"
    d = cal.get("Ex-Dividend Date") if isinstance(cal, dict) else None
    return pd.Timestamp(d) if d else None


# ── plans ────────────────────────────────────────────────────────────────────


def admission_order(tickers: list[str], entry_date: pd.Timestamp) -> list[str]:
    """Deterministic admission order, independent of any signal or outcome."""
    day = str(pd.Timestamp(entry_date).date())
    return sorted(tickers, key=lambda t: hashlib.sha256(f"{t}|{day}".encode()).hexdigest())


@dataclass
class EntryPlan:
    ticker: str
    announce_date: pd.Timestamp
    session: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    expiry: pd.Timestamp
    strike: float
    spot: float
    iv: float
    t_entry: float
    contracts: int
    call: Any
    put: Any
    implied_move: float
    calendar_detail: str = ""

    @property
    def key(self) -> str:
        return position_key(self.ticker, self.entry_date, self.strike, self.expiry)


@dataclass
class ExitPlan:
    position: pd.Series
    call: Any
    put: Any
    spot: float
    iv_exit: float
    t_exit: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        p = self.position
        return str(
            p.get("position_key")
            or position_key(p["ticker"], p["entry_date"], float(p["strike"]), p["front_expiry"])
        )


def _leg_mid(chain: pd.DataFrame, expiry: pd.Timestamp, strike: float, right: str) -> float:
    rows = chain[
        (pd.to_datetime(chain["expiry"]) == expiry)
        & np.isclose(chain["strike"].astype(float), strike)
        & (chain["right"] == right)
    ]
    if rows.empty:
        return float("nan")
    bid, ask = float(rows["bid"].iloc[0]), float(rows["ask"].iloc[0])
    if not (np.isfinite(bid) and np.isfinite(ask) and ask >= bid > 0):
        return float("nan")
    return 0.5 * (bid + ask)


def plan_entry(
    ib: Any,
    cand: pd.Series,
    asof: pd.Timestamp,
    config: LiveConfig = LIVE,
    exdiv_sources: Callable[[Any, Any, str], dict[str, Any]] | None = None,
) -> EntryPlan | str:
    """Price one confirmed candidate, or return the reason it is skipped."""
    ticker = str(cand["ticker"])
    exit_date = pd.Timestamp(cand["exit_date"])
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        expiries, strikes = ib_market.option_grid(ib, underlying)
    except (ValueError, RuntimeError):
        return "unpriced"
    later = [e for e in expiries if e > exit_date]
    if not later:
        return "expiry_le_exit"
    expiry = later[0]
    spot = float(underlying.spot)
    near = sorted(sorted(strikes, key=lambda k: abs(k - spot))[:STRIKES_AROUND_SPOT])
    chain = ib_market.snapshot_strikes(ib, underlying, expiry, near)
    if chain.empty:
        return "unpriced"
    strike = float(nearest_strike(chain, expiry, spot))
    if not np.isfinite(strike):
        return "unpriced"
    call_mid, put_mid = (_leg_mid(chain, expiry, strike, r) for r in ("C", "P"))
    if not (np.isfinite(call_mid) and np.isfinite(put_mid)):
        return "unpriced"
    t_entry = max((expiry - asof).days, 1) / 365.0
    iv = float(atm_iv(chain, expiry, strike))
    if not np.isfinite(iv):
        ivs = [
            implied_vol(call_mid, spot, strike, t_entry, R, "C"),
            implied_vol(put_mid, spot, strike, t_entry, R, "P"),
        ]
        iv = float(np.nanmean([x for x in ivs if x is not None]))
    if not np.isfinite(iv):
        return "unpriced"

    sources = (exdiv_sources or _exdiv_sources)(ib, underlying, ticker)
    ok, reason = exdiv_decision(sources, asof, exit_date)
    if not ok:
        return reason

    credit_ps = _straddle_value(spot, strike, t_entry, R, iv)
    contracts = min(
        int(size_contracts(ACCOUNT_SIZE, spot, strike, credit_ps)), config.max_contracts_per_leg
    )
    if contracts <= 0:
        return "sized_zero"
    try:
        call, put = ib_orders.qualify_straddle_legs(ib, underlying.contract.symbol, strike, expiry)
    except ValueError:
        return "unpriced"
    return EntryPlan(
        ticker=ticker,
        announce_date=pd.Timestamp(cand["announce_date"]),
        session=str(cand["session"]),
        entry_date=asof.normalize(),
        exit_date=exit_date,
        expiry=expiry,
        strike=strike,
        spot=spot,
        iv=iv,
        t_entry=t_entry,
        contracts=contracts,
        call=call,
        put=put,
        implied_move=(call_mid + put_mid) / spot,
        calendar_detail=str(cand.get("detail", "")),
    )


def _exdiv_sources(ib: Any, underlying: Any, ticker: str) -> dict[str, Any]:
    try:
        ib_date = ib_market.next_ex_dividend(ib, underlying)
    except Exception:  # noqa: BLE001 - an unreadable tick is "unknown", never "none"
        ib_date = "unreadable"
    return {"ib": ib_date, "yahoo": _yahoo_exdiv(ticker)}


def plan_exit(ib: Any, pos: pd.Series, asof: pd.Timestamp, *, transmit: bool) -> ExitPlan | str:
    """Qualify the stored contracts of one due position, or return why it cannot exit."""
    ticker = str(pos["ticker"])
    strike = float(pos["strike"])
    expiry = pd.Timestamp(pos["front_expiry"])
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        call, put = ib_orders.qualify_straddle_legs(ib, underlying.contract.symbol, strike, expiry)
    except (ValueError, RuntimeError) as exc:
        return f"unqualified: {exc}"
    if transmit:
        need = int(pos["contracts"])
        held = {c.right: ib_orders.broker_short_qty(ib, c) for c in (call, put)}
        if any(q > -need for q in held.values()):
            return f"broker_mismatch: broker holds {held}, ledger expects -{need} per leg"
    chain = ib_market.snapshot_strikes(ib, underlying, expiry, [strike])
    iv_exit = float(atm_iv(chain, expiry, strike)) if not chain.empty else float("nan")
    return ExitPlan(
        position=pos,
        call=call,
        put=put,
        spot=float(underlying.spot),
        iv_exit=iv_exit,
        t_exit=max((expiry - asof).days, 0) / 365.0,
    )


def _legs_for_entry(plan: EntryPlan) -> list[LadderLeg]:
    return [
        LadderLeg(
            group=f"{plan.key}:entry",
            ticker=plan.ticker,
            position_key=plan.key,
            purpose="entry",
            side="SELL",
            right=right,
            contract=contract,
            quantity=plan.contracts,
            strike=plan.strike,
            expiry=plan.expiry,
        )
        for right, contract in (("C", plan.call), ("P", plan.put))
    ]


def _legs_for_exit(plan: ExitPlan) -> list[LadderLeg]:
    pos = plan.position
    return [
        LadderLeg(
            group=f"{plan.key}:exit",
            ticker=str(pos["ticker"]),
            position_key=plan.key,
            purpose="exit",
            side="BUY",
            right=right,
            contract=contract,
            quantity=int(pos["contracts"]),
            strike=float(pos["strike"]),
            expiry=pd.Timestamp(pos["front_expiry"]),
        )
        for right, contract in (("C", plan.call), ("P", plan.put))
    ]


# ── booking ──────────────────────────────────────────────────────────────────


def _mid_1559(outcome: GroupOutcome) -> float:
    mids = []
    for q in outcome.nbbo_1559.values():
        if q is None or not q.usable_for("SELL"):
            return float("nan")
        mids.append(0.5 * (q.bid + q.ask))
    return float(sum(mids))


def _straddle_quote(outcome: GroupOutcome) -> StraddleQuote | None:
    legs = {leg.right: (outcome.nbbo_1559.get(leg.right) or leg.last_quote) for leg in outcome.legs}
    c, p = legs.get("C"), legs.get("P")
    if c is None or p is None:
        return None
    return StraddleQuote(call_bid=c.bid, call_ask=c.ask, put_bid=p.bid, put_ask=p.ask)


def _book_entry(plan: EntryPlan, outcome: GroupOutcome, stores: Stores, transmit: bool) -> str:
    """Write the open position from fills (transmit) or the 15:59 mid (dry).

    A transmitted entry that did not fill in full books nothing. A dry entry never
    fills, so its intent is booked at the 15:59 mid into the dry store, which lets the
    next day's dry exit exercise the whole path without touching the live book.
    """
    if transmit:
        if outcome.status != "filled":
            return outcome.status
        credit_ps = outcome.fill_ps
    else:
        credit_ps = _mid_1559(outcome)
    if not np.isfinite(credit_ps) or credit_ps <= 0:
        return "booking_error" if transmit else "unquoted"
    paper_book.record_entry(
        {
            "ticker": plan.ticker,
            "announce_date": plan.announce_date,
            "entry_date": plan.entry_date,
            "exit_date": plan.exit_date,
            "front_expiry": plan.expiry,
            "strike": plan.strike,
            "contracts": int(plan.contracts),
            "spot_entry": plan.spot,
            "iv_entry": plan.iv,
            "t_entry": plan.t_entry,
            "entry_credit": float(credit_ps * MULT * plan.contracts),
            "margin": float(
                regt_straddle_margin(plan.spot, plan.strike, credit_ps, plan.contracts)
            ),
            "selection_rule": "unconditional",
            "implied_move": plan.implied_move,
            "entry_mid_ps": _mid_1559(outcome),
            "entry_fill_ps": float(credit_ps),
            "transmitted": bool(transmit),
            "position_key": plan.key,
        },
        path=stores.open_positions,
    )
    return "filled" if transmit else "dry_booked_at_mid"


def _book_exit(
    plan: ExitPlan, outcome: GroupOutcome, stores: Stores, transmit: bool, asof: pd.Timestamp
) -> str:
    if transmit and outcome.status != "filled":
        return outcome.status
    quote = _straddle_quote(outcome)
    if quote is None:
        if not transmit:
            return "unquoted"
        fills = {leg.right: leg.avg_fill for leg in outcome.legs}
        quote = StraddleQuote(fills["C"], fills["C"], fills["P"], fills["P"])
    max_rung = max((leg.rung or 0) for leg in outcome.legs)
    paper_book.forward_exit_from_quote(
        plan.position,
        quote,
        spot_exit=plan.spot,
        iv_exit=plan.iv_exit,
        exit_date=asof,
        t_exit=plan.t_exit,
        filled_at_limit=max_rung < len(LIVE.ladder_rungs) - 1,
        transmitted_fill_ps=outcome.fill_ps if transmit else None,
        nostop_path=stores.nostop,
        stop_path=stores.stop,
        reconciliation_path=stores.reconciliation,
        open_path=stores.open_positions,
    )
    return "filled" if transmit else "dry_booked_at_mid"


# ── the pass ─────────────────────────────────────────────────────────────────


@dataclass
class SessionResult:
    run_id: str
    funnel: dict[str, int]
    alarms: list[str]
    outcomes: list[GroupOutcome]


def _alarm(alarms: list[str], text: str) -> None:
    alarms.append(text)
    print(f"  ALARM: {text}")


def run_session(
    asof: pd.Timestamp,
    *,
    transmit: bool,
    ib: Any = None,
    clock: Clock | None = None,
    quote_fn: Callable[[list[LadderLeg]], dict[str, LegQuote | None]] | None = None,
    votes: pd.DataFrame | None = None,
    config: LiveConfig = LIVE,
    exdiv_sources: Callable[[Any, Any, str], dict[str, Any]] | None = None,
    stores: Stores | None = None,
) -> SessionResult:
    """Run one session of the paper book end to end.

    Parameters
    ----------
    asof : pandas.Timestamp
        Exchange date of the session.
    transmit : bool
        Whether orders are sent to the paper account. The driver passes this only
        when ``_private/TRANSMIT_OK`` exists.
    ib : ib_async.IB, optional
        A connected client; one is opened (and closed) when omitted.
    clock, quote_fn : optional
        Injected for tests; default to the wall clock and live leg quotes.
    votes : pandas.DataFrame, optional
        Calendar votes (``source, ticker, announce_date, session``); gathered from
        the three sources when omitted. A manual run passes its own.
    config : LiveConfig, optional
        Settings; defaults to ``LIVE``.

    Returns
    -------
    SessionResult
        Run id, the funnel counts, every alarm raised, and each group's outcome.
    """
    asof = pd.Timestamp(asof).normalize()
    stores = stores or Stores.for_mode(transmit, config)
    alarms: list[str] = []
    funnel = dict.fromkeys(
        ("seen", "confirmed", "today", "admitted", "priced", "entered", "exits_due", "exited"), 0
    )

    def halted() -> bool:
        return Path(config.halt_file).exists()

    log = OrderEventLog(
        stores.order_events, asof, transmit=transmit, market_data_type=config.ib_market_data_type
    )
    print(
        f"Session {asof.date()} run {log.run_id[:8]}: "
        f"{'TRANSMIT to PAPER' if transmit else 'DRY RUN (nothing sent)'}; "
        f"cap {config.max_names_per_day} names, {config.max_contracts_per_leg} contracts/leg."
    )
    if halted():
        _alarm(alarms, f"HALT present ({config.halt_file}); nothing runs on any path.")
        log.record("halt", reason="HALT present at start")
        return SessionResult(log.run_id, funnel, alarms, [])

    universe = load_universe(config.universe_path)
    if votes is None:
        votes = gather_votes(asof, universe)
    confirmed = confirm_events(votes, asof)
    funnel["seen"] = int(confirmed["ticker"].nunique())
    funnel["confirmed"] = int(confirmed["confirmed"].sum())
    today = confirmed[confirmed["is_today"]]
    funnel["today"] = len(today)
    for _, row in confirmed[~confirmed["confirmed"]].iterrows():
        _append_intended(
            stores.intended,
            {
                "run_id": log.run_id,
                "session_date": asof.date(),
                "ticker": row["ticker"],
                "purpose": "entry",
                "decision": "skip",
                "reason": "calendar_unconfirmed",
                "transmit": transmit,
                "calendar_detail": row["detail"],
            },
        )

    own_ib = ib is None
    if own_ib:
        from .ib_connection import connect_paper

        ib = connect_paper()
    try:
        clock = clock or IBClock(ib)
        quote_fn = quote_fn or (lambda legs: ib_market.quote_legs(ib, legs))

        # Exits first: they are planned even when STOP blocks entries.
        book = paper_book.load_open_positions(stores.open_positions)
        due = (
            book[pd.to_datetime(book["exit_date"]).dt.normalize() <= asof]
            if not book.empty
            else book
        )
        funnel["exits_due"] = len(due)
        exit_plans: list[ExitPlan] = []
        for _, pos in due.iterrows():
            plan = plan_exit(ib, pos, asof, transmit=transmit)
            if isinstance(plan, str):
                _alarm(alarms, f"{pos['ticker']} exit not placed ({plan}); position left open.")
                continue
            exit_plans.append(plan)

        entry_plans: list[EntryPlan] = []
        if kill_switch_active(config.kill_switch_file):
            _alarm(alarms, f"STOP present ({config.kill_switch_file}); no entries today.")
        else:
            by_ticker = {str(r["ticker"]): r for _, r in today.iterrows()}
            for ticker in admission_order(list(by_ticker), asof):
                cand = by_ticker[ticker]
                if len(entry_plans) >= config.max_names_per_day:
                    decision, reason, plan_e = "skip", "cap_names", None
                else:
                    res = plan_entry(ib, cand, asof, config, exdiv_sources)
                    plan_e = res if isinstance(res, EntryPlan) else None
                    decision = "admit" if plan_e else "skip"
                    reason = "" if plan_e else str(res)
                if plan_e is not None:
                    entry_plans.append(plan_e)
                    continue
                _append_intended(
                    stores.intended,
                    {
                        "run_id": log.run_id,
                        "session_date": asof.date(),
                        "ticker": ticker,
                        "purpose": "entry",
                        "announce_date": pd.Timestamp(cand["announce_date"]).date(),
                        "session": cand["session"],
                        "entry_date": asof.date(),
                        "exit_date": pd.Timestamp(cand["exit_date"]).date(),
                        "decision": decision,
                        "reason": reason,
                        "transmit": transmit,
                        "calendar_detail": cand["detail"],
                    },
                )
        funnel["admitted"] = len(entry_plans)
        funnel["priced"] = len(entry_plans)
        if funnel["today"] and not entry_plans and not kill_switch_active(config.kill_switch_file):
            _alarm(alarms, f"{funnel['today']} candidates today and none admitted; read the log.")

        legs = [leg for p in exit_plans for leg in _legs_for_exit(p)] + [
            leg for p in entry_plans for leg in _legs_for_entry(p)
        ]
        _print_funnel(funnel, entry_plans, exit_plans)
        if not legs:
            paper_book.record_heartbeat(asof, funnel["today"], 0, 0, 0, path=stores.heartbeat)
            return SessionResult(log.run_id, funnel, alarms, [])

        try:
            outcomes = run_ladder(
                ib,
                legs,
                quote_fn=quote_fn,
                clock=clock,
                schedule=LadderSchedule.for_session(asof, config),
                log=log,
                transmit=transmit,
                halted=halted,
            )
        except LadderTooLate as exc:
            _alarm(alarms, str(exc))
            return SessionResult(log.run_id, funnel, alarms, [])
    finally:
        if own_ib and ib is not None and ib.isConnected():
            ib.disconnect()

    by_group = {o.group: o for o in outcomes}
    for p in exit_plans:
        o = by_group[f"{p.key}:exit"]
        status = _book_exit(p, o, stores, transmit, asof)
        if o.alarm:
            _alarm(alarms, f"{p.position['ticker']} exit {o.status}; working orders cancelled.")
        funnel["exited"] += status in ("filled", "dry_booked_at_mid")
        _append_intended(stores.intended, _intended_row(log.run_id, asof, p, o, status, transmit))
    for e in entry_plans:
        o = by_group[f"{e.key}:entry"]
        status = _book_entry(e, o, stores, transmit)
        if o.alarm:
            _alarm(alarms, f"{e.ticker} entry {o.status}: a naked leg may be held at the broker.")
        funnel["entered"] += status in ("filled", "dry_booked_at_mid")
        _append_intended(stores.intended, _intended_row(log.run_id, asof, e, o, status, transmit))

    paper_book.record_heartbeat(
        asof,
        funnel["today"],
        funnel["priced"],
        funnel["admitted"],
        funnel["entered"],
        path=stores.heartbeat,
    )
    print(
        f"  done: {funnel['entered']} entered of {funnel['admitted']} admitted; "
        f"{funnel['exited']} exited of {funnel['exits_due']} due; {len(alarms)} alarm(s)."
    )
    return SessionResult(log.run_id, funnel, alarms, outcomes)


def _intended_row(
    run_id: str, asof: pd.Timestamp, plan: Any, o: GroupOutcome, status: str, transmit: bool
) -> dict[str, Any]:
    if isinstance(plan, EntryPlan):
        base = {
            "ticker": plan.ticker,
            "purpose": "entry",
            "announce_date": plan.announce_date.date(),
            "session": plan.session,
            "entry_date": plan.entry_date.date(),
            "exit_date": plan.exit_date.date(),
            "strike": plan.strike,
            "expiry": plan.expiry.date(),
            "contracts": plan.contracts,
            "calendar_detail": plan.calendar_detail,
        }
    else:
        pos = plan.position
        base = {
            "ticker": pos["ticker"],
            "purpose": "exit",
            "entry_date": pd.Timestamp(pos["entry_date"]).date(),
            "exit_date": asof.date(),
            "strike": float(pos["strike"]),
            "expiry": pd.Timestamp(pos["front_expiry"]).date(),
            "contracts": int(pos["contracts"]),
        }
    return {
        **base,
        "run_id": run_id,
        "session_date": asof.date(),
        "position_key": plan.key,
        "decision": "admit",
        "outcome": status,
        "fill_ps": o.fill_ps,
        "nbbo_mid_1559_ps": _mid_1559(o),
        "transmit": transmit,
    }


def _print_funnel(funnel: dict[str, int], entries: list[EntryPlan], exits: list[ExitPlan]) -> None:
    print(
        "  funnel: "
        + ", ".join(f"{k} {v}" for k, v in funnel.items() if k not in ("entered", "exited"))
    )
    for p in exits:
        pos = p.position
        print(
            f"    exit  {pos['ticker']}: {int(pos['contracts'])}x {float(pos['strike']):g} "
            f"exp {pd.Timestamp(pos['front_expiry']).date()}"
        )
    for e in entries:
        print(
            f"    entry {e.ticker}: {e.contracts}x {e.strike:g} exp {e.expiry.date()} "
            f"({e.session} {e.announce_date.date()}, exit {e.exit_date.date()}, "
            f"iv {e.iv:.2f}, implied move {e.implied_move:.1%})"
        )
