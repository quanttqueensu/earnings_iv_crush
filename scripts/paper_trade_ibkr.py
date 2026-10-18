"""
paper_trade_ibkr.py
Forward paper-trading loop for the earnings IV-crush book on an IB **paper** account.

``session`` is the daily pass and the only path that transmits entries. It runs the
forward-test specification end to end (``earnings_iv_crush.live.session``): 2-of-3
calendar confirmation, exits on the stored contracts, entries admitted in hash order
under the name and contract caps, one mid-to-touch ladder for every leg from 15:45 to
15:55 ET, a hard cancel at 15:58, the 15:59 NBBO record, and booking from broker fills.
Every order event goes to ``outputs/live/order_events.csv`` before it is acted on.

The other sub-commands are manual tools:

* ``enter`` - preview today's entry decisions with the legacy single-pass logic
  (Finnhub calendar, or ``--names`` for a manual test). It never transmits: entries
  reach the broker only through the ``session`` ladder;
* ``exit`` - re-snapshot the chain for each open position due to close, read the
  post-event spot and front ATM implied vol (the crush), and mark the trade into
  the paper ledger via the backtest's ``build_trade``; and
* ``forward-exit`` - the execution study: exit with a managed mid-seeking
  marketable limit (``exit_limit_cross_frac`` toward the touch, full-cross
  fallback) and run a PARALLEL hard-stop book alongside the no-stop book, logging
  both in the ledger schema plus a fill/spread reconciliation keyed to the
  canonical break-even (see ``earnings_iv_crush.live.forward_test``). By default it
  marks on the live quote and assumes the managed limit fills; ``--transmit``
  actually places the managed buy-back and books the realised broker fill, and
  ``--offline`` runs the booking from an injected quote with no gateway.

Safety: nothing transmits without ``--transmit`` (the daily drivers pass it only when
``_private/TRANSMIT_OK`` exists), and ``--dry-run`` always wins; the connection
refuses any live-account port; ``outputs/live/STOP`` blocks new entries while exits
still run; ``outputs/live/HALT`` stops every transmission on every path. A dry pass
writes only to ``outputs/live/dry/``. Intended to run daily from 15:20 ET against a
gateway logged into the paper account, from Windows Task Scheduler
(``scripts/run_paper_daily.ps1``) or the cloud compose stack in ``deploy/``.

Usage
-----
    python -m scripts.paper_trade_ibkr session
    python -m scripts.paper_trade_ibkr session --transmit
    python -m scripts.paper_trade_ibkr session --names NVDA --announce 2026-10-21 --hour amc
    python scripts/paper_trade_ibkr.py enter --dry-run
    python scripts/paper_trade_ibkr.py enter --rule term_q80 --dry-run
    python scripts/paper_trade_ibkr.py enter --names NVDA --announce 2026-06-22 --transmit
    python scripts/paper_trade_ibkr.py exit --dry-run
    python scripts/paper_trade_ibkr.py forward-exit
    python scripts/paper_trade_ibkr.py forward-exit --transmit
    python scripts/paper_trade_ibkr.py forward-exit --offline \
        --call-bid 1.0 --call-ask 1.2 --put-bid 0.9 --put-ask 1.1 \
        --spot-exit 101 --iv-exit 0.30
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.tseries.offsets import BDay

from earnings_iv_crush.config import GLOBAL, LIVE, SELECTION_RULES, STRATEGY
from earnings_iv_crush.data.earnings import fetch_earnings_calendar, trade_dates_for_session
from earnings_iv_crush.data.features import (
    atm_iv,
    implied_move,
    nearest_expiries,
    nearest_strike,
    skew_25d,
)
from earnings_iv_crush.engine.costs import CostModel
from earnings_iv_crush.engine.pnl import (
    ACCOUNT_SIZE,
    _straddle_value,
    regt_straddle_margin,
    size_contracts,
)
from earnings_iv_crush.live import ib_market, ib_orders, paper_book
from earnings_iv_crush.live.forward_test import FORWARD, StraddleQuote
from earnings_iv_crush.live.ib_connection import (
    connect_paper,
    kill_switch_active,
)
from earnings_iv_crush.live.session import Stores, run_session

R = GLOBAL.risk_free_rate
EXCHANGE_TZ = "America/New_York"


@dataclass(frozen=True)
class EntrySignal:
    """Chain-derived entry signal and execution coordinates for one event."""

    front_expiry: pd.Timestamp
    strike: float
    t_entry: float
    front_atm_iv: float
    iv_term_spread: float
    iv_term_spread_nearest: float
    skew_25d: float
    implied_move: float


def exchange_today(now: pd.Timestamp | None = None) -> pd.Timestamp:
    """The session date in exchange time, as a tz-naive midnight timestamp.

    The run date decides which announcements are due and which positions exit, so it
    must be the New York date whatever clock the host keeps; a laptop on another
    time zone would otherwise enter or exit a day early or late.
    """
    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return pd.Timestamp(stamp.tz_convert(EXCHANGE_TZ).date())


# ── signal ───────────────────────────────────────────────────────────────────


def compute_entry_signal(
    chain: pd.DataFrame, spot: float, announce_date: pd.Timestamp, asof: pd.Timestamp
) -> EntrySignal | None:
    """Derive the gate inputs and execution coordinates from a snapshot chain.

    Returns ``None`` when the chain does not bracket the announcement or the ATM
    front IV is missing, so the caller skips the name cleanly.
    """
    front, back = nearest_expiries(chain, announce_date)
    if front is None:
        return None
    strike = nearest_strike(chain, front, spot)
    if not (strike == strike):  # NaN
        return None
    t_entry = (pd.Timestamp(front) - pd.Timestamp(asof)).days / 365.0
    front_iv = atm_iv(chain, front, strike)
    back_iv = (
        atm_iv(chain, back, nearest_strike(chain, back, spot)) if back is not None else float("nan")
    )
    if not (front_iv == front_iv):
        return None
    spread = front_iv - back_iv if back_iv == back_iv else float("nan")

    # Panel-definition spread: nearest expiries as-of the entry day, the same rule
    # `historical_surfaces.build_surface_panel` applies to every trailing day and
    # that `sweep_term_panel.py` applies live. The executed-expiry spread above is
    # what the trade actually carries, but the two definitions sit ~0.22 vol pts
    # apart (see `real_events.py`), so gating one against a distribution built
    # from the other compares different quantities. The gate must use this column.
    n_front, n_back = nearest_expiries(chain, asof)
    spread_nearest = float("nan")
    if n_front is not None and n_back is not None:
        n_front_iv = atm_iv(chain, n_front, nearest_strike(chain, n_front, spot))
        n_back_iv = atm_iv(chain, n_back, nearest_strike(chain, n_back, spot))
        if n_front_iv == n_front_iv and n_back_iv == n_back_iv:
            spread_nearest = float(n_front_iv - n_back_iv)

    return EntrySignal(
        front_expiry=pd.Timestamp(front),
        strike=float(strike),
        t_entry=float(t_entry),
        front_atm_iv=float(front_iv),
        iv_term_spread=float(spread),
        iv_term_spread_nearest=spread_nearest,
        skew_25d=float(skew_25d(chain, front, spot, t_entry, R)),
        implied_move=float(implied_move(chain, spot, front, strike)),
    )


# ── candidate discovery ──────────────────────────────────────────────────────


def candidate_events(
    asof: pd.Timestamp, names: list[str] | None, announce: pd.Timestamp | None
) -> pd.DataFrame:
    """Names to enter today, with the exit date their announcement implies.

    With ``--names`` the calendar is bypassed for a manual test (an explicit
    ``--announce`` date is required). Otherwise the Finnhub calendar is queried
    and restricted to the validated universe.

    Which announcements are due depends on ``LiveConfig.session_aware_timing``.
    When set, each row's reporting session decides its bracket via
    ``trade_dates_for_session`` and a name is a candidate when that entry date is
    today, which is the one-session hold the backtest measures. When unset, the
    legacy fixed offset applies: announcements ``entry_offset_days`` business
    days ahead, exiting one business day after the print. The two agree only for
    ``bmo`` names on the entry leg and ``amc`` names on the exit leg, so the
    legacy path holds two sessions in every case.

    The universe restriction is not a convenience filter. The Finnhub calendar is
    the whole US tape, so an unrestricted pass evaluates micro-caps and OTC names
    (AEHR, ANGO, BRLL) whose option microstructure has nothing in common with the
    mega-cap cross-section the gate was fitted and costed on. A forward book built
    from those names measures a different strategy than the one under test.

    Returns
    -------
    pandas.DataFrame
        Columns ``ticker``, ``announce_date`` and ``exit_date``.
    """
    if names:
        if announce is None:
            raise SystemExit("--names requires --announce YYYY-MM-DD")
        day = pd.Timestamp(announce).normalize()
        return pd.DataFrame(
            {
                "ticker": names,
                "announce_date": [day] * len(names),
                "exit_date": [(day + BDay(1)).normalize()] * len(names),
            }
        )
    cal = fetch_earnings_calendar(asof.strftime("%Y-%m-%d"), (asof + BDay(5)).strftime("%Y-%m-%d"))
    if cal.empty:
        return cal
    cal["announce_date"] = pd.to_datetime(cal["announce_date"]).dt.normalize()
    universe = validated_universe()
    if universe:
        cal = cal[cal["ticker"].isin(universe)]

    if not LIVE.session_aware_timing:
        target = (asof + BDay(LIVE.entry_offset_days)).normalize()
        cal = cal[cal["announce_date"] == target][["ticker", "announce_date"]].copy()
        cal["exit_date"] = (cal["announce_date"] + BDay(1)).map(lambda d: d.normalize())
        return cal.reset_index(drop=True)

    sessions = cal["hour"] if "hour" in cal.columns else pd.Series(index=cal.index, dtype=object)
    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    for ticker, announce_day, session in zip(
        cal["ticker"], cal["announce_date"], sessions, strict=True
    ):
        day = pd.Timestamp(announce_day)
        bracket = trade_dates_for_session(day, session)
        if bracket is None:
            skipped.append(str(ticker))
            continue
        entry_date, exit_date = bracket
        if entry_date == asof.normalize():
            rows.append({"ticker": ticker, "announce_date": day, "exit_date": exit_date})
    # A universe name with no session is a candidate the pass silently dropped.
    # Guessing the bracket can open the position after the print or close it
    # before, so the name is skipped, but never quietly.
    if skipped:
        print(
            f"  warning: no reporting session for {sorted(set(skipped))}; "
            f"skipped (cannot bracket the print without it)."
        )
    return pd.DataFrame(rows, columns=["ticker", "announce_date", "exit_date"])


def validated_universe() -> set[str]:
    """Tickers the backtest actually validated, read from ``LiveConfig.universe_path``.

    Returns an empty set if the file is missing, in which case the caller does not
    filter - a missing seed should not silently halt the loop, but the unfiltered
    pass is then off-spec and the log says so.
    """
    seed = Path(LIVE.universe_path)
    if not seed.exists():
        print(f"  warning: universe seed {seed} not found; entry pass is UNFILTERED (off-spec).")
        return set()
    return set(pd.read_parquet(seed, columns=["ticker"])["ticker"].unique())


# ── transmission rule ────────────────────────────────────────────────────────

# Entries transmit only through the session ladder (order-event log, HALT switch,
# booking from fills, separate dry stores; forward-test spec T1 to T5).
# `tests/live/test_w0_safety.py` fails if this is True while any of those is missing.
# The legacy `enter` command never transmits whatever this says.
ENTRY_TRANSMIT_READY = True


def halt_active() -> bool:
    """Whether the ``HALT`` switch is present (stops every transmission)."""
    return Path(LIVE.halt_file).exists()


def transmit_requested(args: argparse.Namespace) -> bool:
    """One rule for every sub-command: ``--transmit`` sends unless ``--dry-run`` is set.

    The outer gate is the ``TRANSMIT_OK`` file checked by the daily drivers, which
    decide whether ``--transmit`` is passed at all.
    """
    return bool(getattr(args, "transmit", False)) and not bool(getattr(args, "dry_run", False))


# ── enter ────────────────────────────────────────────────────────────────────


def run_enter(args: argparse.Namespace) -> None:
    """Preview the day's entry decisions. Never transmits; use ``session`` to trade."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else exchange_today()
    transmit = False
    if transmit_requested(args):
        print(
            "  WARNING: `enter` is a preview and never transmits. Entries reach the broker "
            "only through `session`, which runs the order ladder; continuing as a preview."
        )
    rule = args.rule or LIVE.selection_rule
    if transmit and kill_switch_active():
        print(f"Kill-switch present ({LIVE.kill_switch_file}); no new entries. Exiting.")
        return

    events = candidate_events(asof, args.names, args.announce)
    if events.empty:
        print(
            f"No earnings candidates for entry on {asof.date()} "
            f"({'session-aware' if LIVE.session_aware_timing else 'fixed-offset'} timing)."
        )
        # Still recorded: a zero-candidate day and a day the task never fired are
        # otherwise the same absence of evidence in the heartbeat log.
        paper_book.record_heartbeat(asof, 0, 0, 0, 0)
        return

    costs = CostModel()
    prior_skews = paper_book.load_skew_history()
    ib = connect_paper()
    print(
        f"Connected to paper IB on {LIVE.ib_host}:{LIVE.ib_paper_port}. "
        f"Rule: {rule}. Mode: {'TRANSMIT' if transmit else 'DRY-RUN (no orders)'}"
    )
    outcomes: list[str] = []
    try:
        for ticker, announce_day, exit_day in zip(
            events["ticker"], events["announce_date"], events["exit_date"], strict=True
        ):
            outcomes.append(
                _process_entry(
                    ib,
                    ticker,
                    pd.Timestamp(announce_day),
                    pd.Timestamp(exit_day),
                    asof,
                    prior_skews,
                    costs,
                    transmit,
                    rule,
                )
            )
    finally:
        if ib.isConnected():
            ib.disconnect()

    n_priced = sum(o != "unpriced" for o in outcomes)
    n_gated = sum(o in ("sized_zero", "entered") for o in outcomes)
    n_entered = sum(o == "entered" for o in outcomes)
    paper_book.record_heartbeat(asof, len(outcomes), n_priced, n_gated, n_entered)
    print(
        f"  pass summary: {len(outcomes)} candidates, {n_priced} priced, "
        f"{n_gated} gated, {n_entered} entered."
    )
    if outcomes and n_priced == 0:
        print(
            "  ALARM: every candidate failed to price. This is a data or connection "
            "fault, not a quiet market. Check the IB market-data entitlement "
            "(LiveConfig.ib_market_data_type) before trusting the next report."
        )


def passes_rule(
    rule: str, ticker: str, announce_date: pd.Timestamp, sig: EntrySignal, prior_skews
) -> tuple[bool, str]:
    """Apply the selection rule to one priced candidate.

    Returns whether the event is traded and a short reason for the log.
    ``unconditional`` admits every priced event: the gate-free book is the
    population whose net premium any selector has to improve on.
    """
    if rule == "unconditional":
        return True, "unconditional"
    if rule == "term_q80":
        # Gated on the nearest-expiry (panel-definition) spread, not the executed
        # one: the panel it is quantiled against is built that way.
        term_ok = paper_book.passes_term_gate(ticker, announce_date, sig.iv_term_spread_nearest)
        skew_ok = (
            paper_book.passes_skew_gate(sig.skew_25d, prior_skews)
            if FORWARD.use_skew_gate
            else True
        )
        return term_ok and skew_ok, f"term={term_ok}, skew={skew_ok}"
    raise ValueError(f"unknown selection rule {rule!r}; expected one of {SELECTION_RULES}")


def _process_entry(
    ib, ticker, announce_date, exit_date, asof, prior_skews, costs, transmit, rule
) -> str:
    """Evaluate and (optionally) place one candidate; log every decision.

    Returns the outcome as one of ``"unpriced"``, ``"gated_out"``,
    ``"sized_zero"`` or ``"entered"``, which ``run_enter`` tallies into the
    heartbeat. The distinction that matters is ``"unpriced"``: a pass where every
    candidate lands there is a broken harness, not a quiet market.
    """
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: skipped ({exc}).")
        return "unpriced"
    if chain.empty:
        print(f"  {ticker}: skipped (no chain).")
        return "unpriced"

    sig = compute_entry_signal(chain, underlying.spot, announce_date, asof)
    if sig is None:
        print(f"  {ticker}: skipped (no front IV / strike).")
        return "unpriced"

    # Record the skew observation *before* gating, so the history accumulates
    # even on names that do not pass.
    #
    # The term panel is deliberately NOT written here. It is owned by
    # sweep_term_panel.py, which measures every universe name daily on an
    # asof-relative nearest-expiry basis. Writing this event's spread would both
    # double-count the day and mix bases: `sig.iv_term_spread` is measured
    # announcement-relative on the eve of the print, when the term spread is at
    # its cyclical peak, so it lands in the upper tail of the distribution the
    # gate quantiles over and pushes the threshold against the strategy.
    paper_book.record_skew_observation(ticker, announce_date, sig.skew_25d)

    traded, reason = passes_rule(rule, ticker, announce_date, sig, prior_skews)
    if not traded:
        print(
            f"  {ticker}: no trade ({reason}; "
            f"term_spread_nearest={sig.iv_term_spread_nearest:+.3f} [gated], "
            f"term_spread_executed={sig.iv_term_spread:+.3f}, skew={sig.skew_25d:+.3f})."
        )
        return "gated_out"

    credit_ps = _straddle_value(underlying.spot, sig.strike, sig.t_entry, R, sig.front_atm_iv)
    contracts = size_contracts(ACCOUNT_SIZE, underlying.spot, sig.strike, credit_ps)
    if contracts <= 0:
        print(f"  {ticker}: no trade (sizes to zero contracts).")
        return "sized_zero"

    # The quoted touch at entry, recorded so the cost-aware candidate (a causal
    # per-name spread cut) can later be scored on these same trades. A missing
    # quote is recorded as NaN rather than blocking the entry.
    entry_quote = _atm_quote(chain, sig.front_expiry, sig.strike)
    entry_mid_ps = entry_quote.mid if entry_quote is not None else float("nan")
    entry_rel_spread = entry_quote.relative_spread if entry_quote is not None else float("nan")

    mult = GLOBAL.contract_multiplier
    entry_credit = credit_ps * mult * contracts
    margin = regt_straddle_margin(underlying.spot, sig.strike, credit_ps, contracts)
    print(
        f"  {ticker}: TRADE {contracts}x straddle @ {sig.strike} exp {sig.front_expiry.date()} "
        f"credit~${entry_credit:,.0f} margin~${margin:,.0f} "
        f"(term_spread={sig.iv_term_spread:+.3f}, skew={sig.skew_25d:+.3f})."
    )

    if transmit:  # unreachable from the CLI; kept so a caller cannot book a model fill
        raise RuntimeError("entries transmit only through the session ladder")

    # A preview books into the dry store only, never the store a transmitting exit reads.
    paper_book.record_entry(
        {
            "ticker": ticker,
            "announce_date": announce_date,
            "entry_date": asof,
            "exit_date": exit_date,
            "front_expiry": sig.front_expiry,
            "strike": sig.strike,
            "contracts": int(contracts),
            "spot_entry": float(underlying.spot),
            "iv_entry": sig.front_atm_iv,
            "t_entry": sig.t_entry,
            "entry_credit": float(entry_credit),
            "margin": float(margin),
            "skew_25d": sig.skew_25d,
            "iv_term_spread": sig.iv_term_spread,
            "selection_rule": rule,
            "iv_term_spread_nearest": sig.iv_term_spread_nearest,
            "implied_move": sig.implied_move,
            "entry_mid_ps": float(entry_mid_ps),
            "entry_rel_spread": float(entry_rel_spread),
            "transmitted": False,
        },
        path=Stores.for_mode(transmit=False).open_positions,
    )
    return "entered"


# ── exit ─────────────────────────────────────────────────────────────────────


def run_exit(args: argparse.Namespace) -> None:
    """Mark every open position due to close into the paper ledger."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else exchange_today()
    book = paper_book.load_open_positions()
    if book.empty:
        print("No open positions.")
        return
    due = book[pd.to_datetime(book["exit_date"]).dt.normalize() <= asof]
    if due.empty:
        print(f"No positions due to exit on {asof.date()}.")
        return

    costs = CostModel()
    ib = connect_paper()
    print(f"Connected to paper IB. Marking {len(due)} position(s).")
    try:
        for _, pos in due.iterrows():
            _process_exit(ib, pos, asof, costs)
    finally:
        if ib.isConnected():
            ib.disconnect()


def _process_exit(ib, pos: pd.Series, asof: pd.Timestamp, costs: CostModel) -> None:
    """Re-snapshot one name, read the crush, and book the completed trade."""
    ticker = pos["ticker"]
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: cannot mark ({exc}).")
        return

    front = pd.Timestamp(pos["front_expiry"])
    iv_exit = atm_iv(chain, front, nearest_strike(chain, front, underlying.spot))
    if not (iv_exit == iv_exit):
        print(f"  {ticker}: cannot mark (no post-event IV on {front.date()}).")
        return
    t_exit = max((front - asof).days / 365.0, 0.0)
    trade = paper_book.mark_exit(
        pos,
        spot_exit=underlying.spot,
        iv_exit=float(iv_exit),
        exit_date=asof,
        t_exit=t_exit,
        costs=costs,
    )
    print(
        f"  {ticker}: closed, P&L ${trade['pnl']:,.0f} "
        f"(RoM {trade['return_on_margin']:+.2%}); iv {pos['iv_entry']:.3f}->{iv_exit:.3f}."
    )


# ── forward exit (managed mid-seeking exit + parallel hard-stop book) ─────────


def _atm_quote(
    chain: pd.DataFrame, front_expiry: pd.Timestamp, strike: float, *, exact: bool = False
) -> StraddleQuote | None:
    """Build the two-leg straddle quote from a snapshot chain, or ``None``.

    With ``exact=True`` (exits) only the given strike is accepted: marking or closing a
    neighbouring strike after an earnings move is a different contract, so the caller
    defers instead.
    """
    rows = chain[(chain["expiry"] == front_expiry) & (chain["strike"].sub(strike).abs() < 1e-6)]
    if rows.empty and exact:
        return None
    if rows.empty:
        rows = chain[chain["expiry"] == front_expiry]
        if rows.empty:
            return None
        strike = float(rows.iloc[(rows["strike"] - strike).abs().argmin()]["strike"])
        rows = chain[(chain["expiry"] == front_expiry) & (chain["strike"].sub(strike).abs() < 1e-6)]
    call = rows[rows["right"] == "C"]
    put = rows[rows["right"] == "P"]
    if call.empty or put.empty:
        return None

    def _f(series: pd.Series) -> float:
        return float(pd.to_numeric(series, errors="coerce").iloc[0])

    q = StraddleQuote(
        call_bid=_f(call["bid"]),
        call_ask=_f(call["ask"]),
        put_bid=_f(put["bid"]),
        put_ask=_f(put["ask"]),
    )
    if not (q.mid > 0 and q.half_spread >= 0):
        return None
    # The package test sums the legs, so a crossed or empty leg can pass it; an exit
    # books and trades each leg on its own touch.
    legs_ok = ib_orders._leg_book_usable(q.call_bid, q.call_ask) and (
        ib_orders._leg_book_usable(q.put_bid, q.put_ask)
    )
    if exact and not legs_ok:
        return None
    return q


def run_forward_exit(args: argparse.Namespace) -> None:
    """Mark open positions out under the managed exit, logging the no-stop and
    parallel hard-stop books plus the cost reconciliation.

    Default (no flags): marks on the live quote and assumes the managed limit
    fills ``exit_limit_cross_frac`` of the way to the touch. ``--transmit`` instead
    places the managed buy-back and books the realised broker fill. ``--offline``
    runs the booking from an injected quote with no gateway. The stop book crosses
    fully to the touch when the post-print-open mark has breached ``stop_loss_rom``
    - the conservative slippage upper bound the live book replaces with its
    realised gapped fill.
    """
    asof = pd.Timestamp(args.asof).normalize() if args.asof else exchange_today()
    book = paper_book.load_open_positions()
    if book.empty:
        print("No open positions.")
        return
    due = book[pd.to_datetime(book["exit_date"]).dt.normalize() <= asof]
    if due.empty:
        print(f"No positions due to exit on {asof.date()}.")
        return

    if args.offline:
        _run_forward_exit_offline(args, asof, due)
        return

    transmit = transmit_requested(args)
    if transmit and halt_active():
        print(f"  ALARM: HALT present ({LIVE.halt_file}); forward-exit sends nothing.")
        raise SystemExit(1)
    ib = connect_paper()
    print(
        f"Connected to paper IB. Forward-marking {len(due)} position(s); "
        f"exit_limit_cross_frac={FORWARD.exit_limit_cross_frac}, stop_rom={FORWARD.stop_loss_rom}. "
        f"Mode: {'TRANSMIT (managed buy-back)' if transmit else 'DRY-MARK (assume fill)'}"
    )
    failed: list[str] = []
    try:
        for _, pos in due.iterrows():
            # One bad position (an expired or unqualifiable leg, a dropped re-quote)
            # must not leave every later position unexited; it is named and the pass
            # exits non-zero so the driver reports it.
            try:
                _process_forward_exit(ib, pos, asof, transmit)
            except Exception as exc:  # noqa: BLE001 - isolate and report each position
                failed.append(str(pos["ticker"]))
                print(f"  ALARM: {pos['ticker']} exit raised {type(exc).__name__}: {exc}")
    finally:
        if ib.isConnected():
            ib.disconnect()
    if failed:
        raise SystemExit(f"forward-exit: {len(failed)} position(s) raised: {sorted(failed)}")


def _run_forward_exit_offline(
    args: argparse.Namespace, asof: pd.Timestamp, due: pd.DataFrame
) -> None:
    """Book each due position from an injected quote, with no gateway.

    The four touch prices (and the post-event spot / IV) are supplied on the
    command line, so the whole forward-exit decision and persistence path runs
    without IB. Intended as a single-name manual test of the booking logic.
    """
    if None in (args.call_bid, args.call_ask, args.put_bid, args.put_ask):
        raise SystemExit("--offline requires --call-bid/--call-ask/--put-bid/--put-ask.")
    quote = StraddleQuote(
        call_bid=float(args.call_bid),
        call_ask=float(args.call_ask),
        put_bid=float(args.put_bid),
        put_ask=float(args.put_ask),
    )
    print(
        f"Offline forward-mark of {len(due)} position(s) from injected quote "
        f"(mid {quote.mid:.2f}, spread {quote.relative_spread:.1%}); no gateway."
    )
    for _, pos in due.iterrows():
        spot_exit = (
            float(args.spot_exit) if args.spot_exit is not None else float(pos["spot_entry"])
        )
        iv_exit = float(args.iv_exit) if args.iv_exit is not None else float(pos["iv_entry"])
        t_exit = max((pd.Timestamp(pos["front_expiry"]) - asof).days / 365.0, 0.0)
        nostop_row, stop_row, recon = paper_book.forward_exit_from_quote(
            pos,
            quote,
            spot_exit=spot_exit,
            iv_exit=iv_exit,
            exit_date=asof,
            t_exit=t_exit,
        )
        _print_forward_exit(pos["ticker"], nostop_row, stop_row, recon)


def _process_forward_exit(ib, pos: pd.Series, asof: pd.Timestamp, transmit: bool) -> None:
    """Re-snapshot one name at the post-print open and book both parallel exits.

    With ``transmit`` set, the managed mid-seeking buy-back is actually placed and
    the realised broker fill (price and ``filled_at_limit`` flag) is booked;
    otherwise the managed limit is assumed to fill at its posted price.
    """
    ticker = pos["ticker"]
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: cannot mark ({exc}).")
        return

    front = pd.Timestamp(pos["front_expiry"])
    strike = float(pos["strike"])
    quote = _atm_quote(chain, front, strike, exact=True)
    if quote is None:
        print(f"  {ticker}: deferred (no quote at the held strike {strike} on {front.date()}).")
        return
    iv_exit = atm_iv(chain, front, nearest_strike(chain, front, underlying.spot))
    t_exit = max((front - asof).days / 365.0, 0.0)

    filled_at_limit = True
    transmitted_fill_ps: float | None = None
    if transmit:
        call, put = ib_orders.qualify_straddle_legs(ib, underlying.contract.symbol, strike, front)
        need = int(pos["contracts"])
        held = {c.right: ib_orders.broker_short_qty(ib, c) for c in (call, put)}
        if any(q > -need for q in held.values()):
            print(
                f"  ALARM: {ticker} broker holds {held} at strike {strike}, ledger expects "
                f"-{need} per leg; exit NOT transmitted, position left open for review."
            )
            return

        def _requote() -> StraddleQuote | None:
            return _atm_quote(ib_market.snapshot_chain(ib, underlying), front, strike, exact=True)

        fill = ib_orders.place_managed_buyback(
            ib,
            call,
            put,
            need,
            quote,
            transmit=True,
            cross_frac=FORWARD.exit_limit_cross_frac,
            requote=_requote,
        )
        if not fill.complete:
            call_qty, put_qty = fill.filled_qty
            print(
                f"  ALARM: {ticker} buy-back incomplete ({fill.legs_filled}/2 legs filled; "
                f"call {call_qty}/{need}, put {put_qty}/{need} contracts bought); "
                "working orders cancelled, nothing booked, position left open for review."
            )
            return
        transmitted_fill_ps = fill.fill_price_ps
        filled_at_limit = fill.filled_at_limit
        print(
            f"    {ticker}: managed buy-back filled {transmitted_fill_ps:.2f}/sh "
            f"({'at limit' if filled_at_limit else 'crossed to touch'})."
        )

    nostop_row, stop_row, recon = paper_book.forward_exit_from_quote(
        pos,
        quote,
        spot_exit=float(underlying.spot),
        iv_exit=float(iv_exit) if iv_exit == iv_exit else float("nan"),
        exit_date=asof,
        t_exit=t_exit,
        filled_at_limit=filled_at_limit,
        transmitted_fill_ps=transmitted_fill_ps,
        nostop_path=FORWARD.nostop_ledger_path,
        stop_path=FORWARD.stop_ledger_path,
        reconciliation_path=FORWARD.reconciliation_path,
    )
    _print_forward_exit(ticker, nostop_row, stop_row, recon)


def _print_forward_exit(ticker: str, nostop_row: dict, stop_row: dict, recon: dict) -> None:
    """One-line summary of a booked forward exit."""
    flag = "STOP-HIT" if recon["stop_was_triggered"] else "held"
    print(
        f"  {ticker}: no-stop P&L ${nostop_row['pnl']:,.0f} "
        f"(RoM {nostop_row['return_on_margin']:+.2%}); stop-book {flag} "
        f"P&L ${stop_row['pnl']:,.0f}; exit spread {recon['realised_exit_spread']:.1%} "
        f"(assumed {recon['assumed_exit_spread']:.1%}), "
        f"round-trip {recon['realised_round_trip_cost']:.1%} vs breakeven "
        f"{recon['breakeven_round_trip']:.1%}"
        f"{' OVER' if recon['over_breakeven'] else ''}."
    )


# ── session (the daily transmitting pass) ────────────────────────────────────


def run_session_cmd(args: argparse.Namespace) -> None:
    """Run the daily session pass; exit non-zero when any alarm was raised."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else exchange_today()
    votes = None
    if args.names:
        if not (args.announce and args.hour):
            raise SystemExit("--names requires --announce YYYY-MM-DD and --hour bmo|amc")
        # A manual run is the operator's own confirmation, recorded as two votes so the
        # 2-of-3 rule is satisfied explicitly rather than bypassed.
        votes = pd.DataFrame(
            [
                {"source": src, "ticker": t, "announce_date": args.announce, "session": args.hour}
                for t in args.names
                for src in ("manual", "manual_check")
            ]
        )
    result = run_session(asof, transmit=transmit_requested(args), votes=votes)
    if result.alarms:
        raise SystemExit(f"session: {len(result.alarms)} alarm(s); see the log above.")


# ── cli ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Construct the sub-command argument parser."""
    p = argparse.ArgumentParser(description="Earnings IV-crush paper trading via IB.")
    sub = p.add_subparsers(dest="command", required=True)

    ses = sub.add_parser(
        "session", help="the daily pass: confirm, plan, ladder every leg, book from fills"
    )
    ses.add_argument("--asof", default=None, help="session date YYYY-MM-DD (default today, ET)")
    ses.add_argument("--transmit", action="store_true", help="send orders to the PAPER account")
    ses.add_argument("--dry-run", action="store_true", default=False, help="never transmit")
    ses.add_argument("--names", nargs="*", default=None, help="manual tickers (skip the calendar)")
    ses.add_argument("--announce", default=None, help="announcement date for --names")
    ses.add_argument("--hour", choices=("bmo", "amc"), default=None, help="session for --names")
    ses.set_defaults(func=run_session_cmd)

    enter = sub.add_parser("enter", help="snapshot, gate, size and optionally transmit entries")
    enter.add_argument("--asof", default=None, help="entry date YYYY-MM-DD (default today)")
    enter.add_argument(
        "--names", nargs="*", default=None, help="manual ticker list (bypass calendar)"
    )
    enter.add_argument("--announce", default=None, help="announcement date for --names")
    enter.add_argument(
        "--rule",
        choices=SELECTION_RULES,
        default=None,
        help="selection rule (default LiveConfig.selection_rule, env SELECTION_RULE)",
    )
    enter.add_argument("--transmit", action="store_true", help="actually send orders to paper")
    enter.add_argument("--dry-run", action="store_true", default=False, help="never transmit")
    enter.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    enter.set_defaults(func=run_enter)

    ex = sub.add_parser("exit", help="mark open positions due to close into the ledger")
    ex.add_argument("--asof", default=None, help="exit date YYYY-MM-DD (default today)")
    ex.set_defaults(func=run_exit)

    fex = sub.add_parser(
        "forward-exit",
        help="managed mid-seeking exit + parallel hard-stop book, with cost reconciliation",
    )
    fex.add_argument("--asof", default=None, help="exit date YYYY-MM-DD (default today)")
    fex.add_argument(
        "--transmit", action="store_true", help="place the managed buy-back and book the real fill"
    )
    fex.add_argument("--dry-run", action="store_true", default=False, help="never transmit")
    fex.add_argument(
        "--offline", action="store_true", help="book from an injected quote, no gateway"
    )
    fex.add_argument("--call-bid", type=float, default=None, help="offline: ATM call bid")
    fex.add_argument("--call-ask", type=float, default=None, help="offline: ATM call ask")
    fex.add_argument("--put-bid", type=float, default=None, help="offline: ATM put bid")
    fex.add_argument("--put-ask", type=float, default=None, help="offline: ATM put ask")
    fex.add_argument("--spot-exit", type=float, default=None, help="offline: post-event spot")
    fex.add_argument("--iv-exit", type=float, default=None, help="offline: post-event ATM IV")
    fex.set_defaults(func=run_forward_exit)
    return p


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args and dispatch to the sub-command."""
    _ = STRATEGY  # config is the single source of truth; referenced for clarity
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
