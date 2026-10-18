"""
sweep_term_panel.py
Daily universe-wide sweep that accrues the trailing term-spread panel the live
gate reads.

The term gate needs ``StrategyConfig.term_min_periods`` daily observations for a
name inside the ``trailing_window`` trading days before entry. Those observations
have to exist *before* the name becomes a candidate, so they cannot be written by
the entry pass: a name reporting quarterly would accrue roughly one observation
per quarter and never reach the minimum, leaving the gate permanently closed.
This script writes one observation per name per trading day for the whole
validated universe, which is the distribution ``passes_term_filter_panel``
assumes it is quantiling over.

Measurement parity matters here. The panel is defined on NEAREST-expiry term
spreads, so the sweep resolves ``(front, back)`` relative to *today* using the
same ``nearest_expiries`` rule the entry signal applies relative to the
announcement. Measuring the panel any other way shifts the distribution against
the event statistic and biases the live pass rate.

Usage
-----
    python scripts/sweep_term_panel.py
    python scripts/sweep_term_panel.py --names GOOGL,IBM --dry-run
    python scripts/sweep_term_panel.py --asof 2026-07-21
"""

from __future__ import annotations

import argparse

import pandas as pd

from earnings_iv_crush.config import LIVE
from earnings_iv_crush.data.features import atm_iv, nearest_expiries, nearest_strike
from earnings_iv_crush.live import ib_market, paper_book
from earnings_iv_crush.live.ib_connection import connect_paper

# Only the ATM strike is read, so a tight band and a short horizon keep 50 names
# inside IB's concurrent market-data lines. The horizon still has to clear the
# back expiry, which sits ~1 month past the front.
SWEEP_STRIKE_WINDOW = 0.06
SWEEP_HORIZON_DAYS = 75
SWEEP_CLIENT_ID = LIVE.ib_client_id + 1


# ── observation ──────────────────────────────────────────────────────────────


def term_spread_asof(chain: pd.DataFrame, spot: float, asof: pd.Timestamp) -> float:
    """Nearest-expiry ATM term spread (front IV minus back IV) as of ``asof``.

    Front is the first expiry strictly after ``asof``; back is the first expiry
    at least ``BACK_MONTH_MIN_GAP_DAYS`` beyond it. Returns NaN when either leg
    is missing, which the caller reports rather than records.
    """
    front, back = nearest_expiries(chain, asof)
    if front is None or back is None:
        return float("nan")
    front_iv = atm_iv(chain, front, nearest_strike(chain, front, spot))
    back_iv = atm_iv(chain, back, nearest_strike(chain, back, spot))
    if not (front_iv == front_iv and back_iv == back_iv):
        return float("nan")
    return float(front_iv - back_iv)


def observe(ib, ticker: str, asof: pd.Timestamp) -> float | None:
    """One name's term spread, or ``None`` with a printed reason if unavailable.

    Every ``None`` path prints why, so a name that stops accruing is visible in
    the log rather than inferred later from a gap in the panel.
    """
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        chain = ib_market.snapshot_chain(
            ib,
            underlying,
            horizon_days=SWEEP_HORIZON_DAYS,
            strike_window=SWEEP_STRIKE_WINDOW,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: no observation ({exc}).")
        return None
    if chain.empty:
        print(f"  {ticker}: no observation (empty chain).")
        return None
    spread = term_spread_asof(chain, underlying.spot, asof)
    if spread != spread:  # NaN
        print(f"  {ticker}: no observation (no nearest-expiry pair or missing ATM IV).")
        return None
    return spread


def already_recorded(asof: pd.Timestamp) -> set[str]:
    """Tickers that already carry an observation for ``asof``.

    Makes a re-run idempotent: the scheduled task retrying after a partial
    failure must not double-weight a day in the quantile.
    """
    panel = paper_book._read(LIVE.term_panel_path, ["ticker", "date", "iv_term_spread"])
    if panel.empty:
        return set()
    dates = pd.to_datetime(panel["date"]).dt.normalize()
    return set(panel.loc[dates == asof.normalize(), "ticker"])


# ── sweep ────────────────────────────────────────────────────────────────────


def run_sweep(args: argparse.Namespace) -> None:
    """Snapshot every universe name and append today's term spread to the panel."""
    asof = pd.Timestamp(args.asof).normalize() if args.asof else pd.Timestamp.today().normalize()
    if args.names:
        universe = sorted({n.strip().upper() for n in args.names.split(",") if n.strip()})
    else:
        from scripts.paper_trade_ibkr import validated_universe

        universe = sorted(validated_universe())
    if not universe:
        raise SystemExit("Empty universe: cannot build the panel. Check LiveConfig.skew_seed_path.")

    done = already_recorded(asof)
    todo = [t for t in universe if t not in done]
    print(f"Term-panel sweep for {asof.date()}: {len(todo)} to do, {len(done)} already recorded.")
    if not todo:
        return

    ib = connect_paper(client_id=SWEEP_CLIENT_ID)
    print(
        f"Connected on {LIVE.ib_host}:{LIVE.ib_paper_port}. "
        f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}"
    )
    n_ok = 0
    try:
        # Two passes. A burst of ~50 names throttles IB's delayed feed often
        # enough that ~20% of a single pass comes back with no underlying price
        # or no ATM IV, and those names silently stop accruing. Retrying the
        # failures alone, against a quiet connection, recovers them.
        pending = list(todo)
        for attempt in (1, 2):
            if not pending:
                break
            if attempt == 2:
                print(f"  retrying {len(pending)} name(s) that failed the first pass.")
            failed: list[str] = []
            for ticker in pending:
                spread = observe(ib, ticker, asof)
                if spread is None:
                    failed.append(ticker)
                    continue
                if not args.dry_run:
                    paper_book.record_term_observation(ticker, asof, spread)
                n_ok += 1
                print(f"  {ticker}: term_spread={spread:+.4f}")
            pending = failed
        for ticker in pending:
            print(f"  {ticker}: FAILED both passes; no observation recorded today.")
    finally:
        if ib.isConnected():
            ib.disconnect()

    print(f"  sweep summary: {n_ok} recorded, {len(pending)} failed, of {len(todo)} attempted.")
    # A sweep that records nothing is a harness or entitlement fault, not a quiet
    # market. Left silent it would look identical to a normal day in the panel,
    # and the gate would stay closed for reasons no log explains.
    if todo and n_ok == 0:
        raise SystemExit(
            "ALARM: the sweep recorded no observations. The panel did not advance today. "
            "Check the IB connection and market-data entitlement before trusting the gate."
        )


# ── entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Accrue the daily term-spread panel for the live gate.")
    p.add_argument("--asof", default=None, help="Observation date (default: today).")
    p.add_argument("--names", default=None, help="Comma-separated override of the universe.")
    p.add_argument("--dry-run", action="store_true", help="Compute and print without writing.")
    run_sweep(p.parse_args())


if __name__ == "__main__":
    main()
