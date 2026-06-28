"""
paper_trade_ibkr.py
Forward paper-trading loop for the filtered earnings IV-crush strategy.

Runs the *same* causal selection the backtest validated against a live IB
**paper** account, on the locked baseline: the term gate at the 0.80 percentile
with the move and low-skew gates OFF (term-only selection). Three sub-commands:

* ``enter`` - find names reporting on the next business day (Finnhub calendar, or
  ``--names`` for a manual test), snapshot each chain from IB, compute the entry
  signal, apply the term gate (the skew gate only binds if the forward config
  re-enables it), size with the backtest's own ``size_contracts``, and either log
  the would-be trade (``--dry-run``, the default) or transmit the two
  short-straddle legs to the paper account;
* ``exit`` - re-snapshot the chain for each open position due to close, read the
  post-event spot and front ATM implied vol (the crush), and mark the trade into
  the paper ledger via the backtest's ``build_trade``; and
* ``forward-exit`` - the execution study: exit with a managed mid-seeking
  marketable limit (``exit_limit_cross_frac`` toward the touch, full-cross
  fallback) and run a PARALLEL hard-stop book alongside the no-stop book, logging
  both in the ledger schema plus a fill/spread reconciliation keyed to the
  canonical break-even (see ``earnings_iv_crush.live.forward_test``).

Safety: ``--dry-run`` is the default; transmitting requires ``--transmit``; the
connection refuses any live-account port; the kill-switch file blocks new
entries; and ``forward-exit`` marks on the live quote without transmitting any
order. Intended to run daily from Windows Task Scheduler with TWS / IB Gateway
logged into the paper account.

Usage
-----
    python scripts/paper_trade_ibkr.py enter --dry-run
    python scripts/paper_trade_ibkr.py enter --names NVDA --announce 2026-06-22 --transmit
    python scripts/paper_trade_ibkr.py exit --dry-run
    python scripts/paper_trade_ibkr.py forward-exit
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd
from pandas.tseries.offsets import BDay

from earnings_iv_crush.config import GLOBAL, LIVE, STRATEGY
from earnings_iv_crush.data.earnings import fetch_earnings_calendar
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
from earnings_iv_crush.live import forward_test, ib_market, ib_orders, paper_book
from earnings_iv_crush.live.forward_test import FORWARD, StraddleQuote
from earnings_iv_crush.live.ib_connection import (
    connect_paper,
    kill_switch_active,
)

R = GLOBAL.risk_free_rate


@dataclass(frozen=True)
class EntrySignal:
    """Chain-derived entry signal and execution coordinates for one event."""

    front_expiry: pd.Timestamp
    strike: float
    t_entry: float
    front_atm_iv: float
    iv_term_spread: float
    skew_25d: float
    implied_move: float


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
    return EntrySignal(
        front_expiry=pd.Timestamp(front),
        strike=float(strike),
        t_entry=float(t_entry),
        front_atm_iv=float(front_iv),
        iv_term_spread=float(spread),
        skew_25d=float(skew_25d(chain, front, spot, t_entry, R)),
        implied_move=float(implied_move(chain, spot, front, strike)),
    )


# ── candidate discovery ──────────────────────────────────────────────────────


def candidate_events(
    asof: pd.Timestamp, names: list[str] | None, announce: pd.Timestamp | None
) -> pd.DataFrame:
    """Names whose announcement is the entry target (the next business day).

    With ``--names`` the calendar is bypassed for a manual test (an explicit
    ``--announce`` date is required). Otherwise the Finnhub calendar is queried
    and filtered to announcements ``entry_offset_days`` business days ahead.
    """
    target = (asof + BDay(LIVE.entry_offset_days)).normalize()
    if names:
        if announce is None:
            raise SystemExit("--names requires --announce YYYY-MM-DD")
        return pd.DataFrame(
            {"ticker": names, "announce_date": [pd.Timestamp(announce)] * len(names)}
        )
    cal = fetch_earnings_calendar(asof.strftime("%Y-%m-%d"), (asof + BDay(5)).strftime("%Y-%m-%d"))
    if cal.empty:
        return cal
    cal["announce_date"] = pd.to_datetime(cal["announce_date"]).dt.normalize()
    return cal[cal["announce_date"] == target][["ticker", "announce_date"]].reset_index(drop=True)


# ── enter ────────────────────────────────────────────────────────────────────


def run_enter(args: argparse.Namespace) -> None:
    """Snapshot, gate, size and (optionally) transmit entries for the day."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else pd.Timestamp.today().normalize()
    transmit = bool(args.transmit) and not args.dry_run
    if transmit and kill_switch_active():
        print(f"Kill-switch present ({LIVE.kill_switch_file}); no new entries. Exiting.")
        return

    events = candidate_events(asof, args.names, args.announce)
    if events.empty:
        print(
            f"No earnings candidates for entry on {asof.date()} (target {(asof + BDay(1)).date()})."
        )
        return

    costs = CostModel()
    prior_skews = paper_book.load_skew_history()
    ib = connect_paper()
    print(
        f"Connected to paper IB on {LIVE.ib_host}:{LIVE.ib_paper_port}. "
        f"Mode: {'TRANSMIT' if transmit else 'DRY-RUN (no orders)'}"
    )
    try:
        for ev in events.itertuples(index=False):
            _process_entry(
                ib, ev.ticker, pd.Timestamp(ev.announce_date), asof, prior_skews, costs, transmit
            )
    finally:
        if ib.isConnected():
            ib.disconnect()


def _process_entry(ib, ticker, announce_date, asof, prior_skews, costs, transmit) -> None:
    """Evaluate and (optionally) place one candidate; log every decision."""
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: skipped ({exc}).")
        return
    if chain.empty:
        print(f"  {ticker}: skipped (no chain).")
        return

    sig = compute_entry_signal(chain, underlying.spot, announce_date, asof)
    if sig is None:
        print(f"  {ticker}: skipped (no front IV / strike).")
        return

    # Record the trailing-panel and skew observations *before* gating, so the
    # histories accumulate even on names that do not pass.
    paper_book.record_term_observation(ticker, asof, sig.iv_term_spread)
    paper_book.record_skew_observation(ticker, announce_date, sig.skew_25d)

    # Locked baseline: term-only at q=0.80, skew and move gates OFF. The skew
    # observation is still recorded above so the history keeps accumulating, but
    # the gate only binds when the forward config re-enables it.
    term_ok = paper_book.passes_term_gate(ticker, announce_date, sig.iv_term_spread)
    skew_ok = (
        paper_book.passes_skew_gate(sig.skew_25d, prior_skews) if FORWARD.use_skew_gate else True
    )
    if not (term_ok and skew_ok):
        print(
            f"  {ticker}: no trade (term={term_ok}, skew={skew_ok}; "
            f"term_spread={sig.iv_term_spread:+.3f}, skew={sig.skew_25d:+.3f})."
        )
        return

    credit_ps = _straddle_value(underlying.spot, sig.strike, sig.t_entry, R, sig.front_atm_iv)
    contracts = size_contracts(ACCOUNT_SIZE, underlying.spot, sig.strike, credit_ps)
    if contracts <= 0:
        print(f"  {ticker}: no trade (sizes to zero contracts).")
        return

    mult = GLOBAL.contract_multiplier
    entry_credit = credit_ps * mult * contracts
    margin = regt_straddle_margin(underlying.spot, sig.strike, credit_ps, contracts)
    exit_date = (announce_date + BDay(1)).normalize()

    print(
        f"  {ticker}: TRADE {contracts}x straddle @ {sig.strike} exp {sig.front_expiry.date()} "
        f"credit~${entry_credit:,.0f} margin~${margin:,.0f} "
        f"(term_spread={sig.iv_term_spread:+.3f}, skew={sig.skew_25d:+.3f})."
    )

    if transmit:
        legs = ib_orders.build_straddle_legs(ib, underlying, chain, sig.front_expiry)
        trades = ib_orders.place_short_straddle(ib, legs, contracts, transmit=True)
        print(f"    transmitted {len(trades)} legs to paper account.")

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
        }
    )


# ── exit ─────────────────────────────────────────────────────────────────────


def run_exit(args: argparse.Namespace) -> None:
    """Mark every open position due to close into the paper ledger."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else pd.Timestamp.today().normalize()
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
    chain: pd.DataFrame, front_expiry: pd.Timestamp, strike: float
) -> StraddleQuote | None:
    """Build the two-leg ATM straddle quote from a snapshot chain, or ``None``."""
    rows = chain[(chain["expiry"] == front_expiry) & (chain["strike"].sub(strike).abs() < 1e-6)]
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
    return q


def run_forward_exit(args: argparse.Namespace) -> None:
    """Mark open positions out under the managed exit, logging the no-stop and
    parallel hard-stop books plus the cost reconciliation.

    Paper-only: no order is transmitted here (the books are marked on the live
    quote). The managed exit places a marketable limit ``exit_limit_cross_frac``
    of the way to the touch; in this dry-mark it is assumed to fill at the limit,
    and the stop book crosses fully to the touch when the post-print-open mark has
    breached ``stop_loss_rom`` - the conservative slippage upper bound the live
    book then replaces with its realised gapped fill.
    """
    asof = pd.Timestamp(args.asof).normalize() if args.asof else pd.Timestamp.today().normalize()
    book = paper_book.load_open_positions()
    if book.empty:
        print("No open positions.")
        return
    due = book[pd.to_datetime(book["exit_date"]).dt.normalize() <= asof]
    if due.empty:
        print(f"No positions due to exit on {asof.date()}.")
        return

    ib = connect_paper()
    print(
        f"Connected to paper IB. Forward-marking {len(due)} position(s); "
        f"exit_limit_cross_frac={FORWARD.exit_limit_cross_frac}, stop_rom={FORWARD.stop_loss_rom}."
    )
    try:
        for _, pos in due.iterrows():
            _process_forward_exit(ib, pos, asof)
    finally:
        if ib.isConnected():
            ib.disconnect()


def _process_forward_exit(ib, pos: pd.Series, asof: pd.Timestamp) -> None:
    """Re-snapshot one name at the post-print open and book both parallel exits."""
    ticker = pos["ticker"]
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: cannot mark ({exc}).")
        return

    front = pd.Timestamp(pos["front_expiry"])
    quote = _atm_quote(chain, front, float(pos["strike"]))
    if quote is None:
        print(f"  {ticker}: cannot mark (no ATM call/put quote on {front.date()}).")
        return
    iv_exit = atm_iv(chain, front, nearest_strike(chain, front, underlying.spot))
    t_exit = max((front - asof).days / 365.0, 0.0)

    nostop_row, stop_row, recon = forward_test.build_forward_exit(
        pos.to_dict(),
        quote,
        spot_exit=float(underlying.spot),
        iv_exit=float(iv_exit) if iv_exit == iv_exit else float("nan"),
        exit_date=asof,
        t_exit=t_exit,
    )
    paper_book.record_forward_exit(
        pos,
        nostop_row,
        stop_row,
        recon,
        nostop_path=FORWARD.nostop_ledger_path,
        stop_path=FORWARD.stop_ledger_path,
        reconciliation_path=FORWARD.reconciliation_path,
    )
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


# ── cli ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Construct the sub-command argument parser."""
    p = argparse.ArgumentParser(description="Earnings IV-crush paper trading via IB.")
    sub = p.add_subparsers(dest="command", required=True)

    enter = sub.add_parser("enter", help="snapshot, gate, size and optionally transmit entries")
    enter.add_argument("--asof", default=None, help="entry date YYYY-MM-DD (default today)")
    enter.add_argument(
        "--names", nargs="*", default=None, help="manual ticker list (bypass calendar)"
    )
    enter.add_argument("--announce", default=None, help="announcement date for --names")
    enter.add_argument("--transmit", action="store_true", help="actually send orders to paper")
    enter.add_argument("--dry-run", action="store_true", default=True, help="log only (default)")
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
    fex.set_defaults(func=run_forward_exit)
    return p


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args and dispatch to the sub-command."""
    _ = STRATEGY  # config is the single source of truth; referenced for clarity
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
