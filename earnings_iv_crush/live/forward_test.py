"""
forward_test.py
Forward paper-test logic for the locked term q=0.80 baseline: the managed
mid-seeking exit and the parallel hard-stop book.

This module is the decision layer the forward harness validates. It is pure
(no broker, no network, no I/O): the orchestration in
``scripts/paper_trade_ibkr.py`` pulls the live chain and feeds prices in, so every
function here is unit-testable offline. Three jobs:

* **Managed exit.** The straddle is bought back with a marketable limit placed a
  configurable fraction of the way from mid toward the touch
  (``exit_limit_cross_frac``), at the post-print open. If the limit does not fill
  it falls back to crossing fully to the touch. ``exit_limit_cross_frac`` is the
  core thing under test: the research model says a mid-seeking exit is what keeps
  the edge net-positive at the measured exit spread.
* **Parallel hard-stop book.** A second book runs the same entries but force-closes
  at a stop near ``stop_loss_rom`` of margin. Run side by side with the no-stop
  book, the difference measures the stop's *real* slippage on the earnings gap -
  the one cost the historical model can only upper-bound.
* **Cost reconciliation.** Every exit records the realised fill against the assumed
  mid mark and the realised quoted spread against the assumed spread, with the
  realised round-trip cost compared to the canonical break-even threshold, so the
  forward book is scored on the same basis as the backtest.

The canonical break-even (see ``BREAKEVEN_ROUND_TRIP``) is the round-trip premium
cost, defined as the half-cross of the entry spread plus the half-cross of the
exit spread - a single, unambiguous number the forward test is keyed to.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import LIVE
from ..engine.costs import CostModel
from ..engine.pnl import (
    CONTRACT_MULTIPLIER,
    COST_PER_CONTRACT,
    FILLS_PER_STRADDLE,
    LEDGER_COLUMNS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Canonical break-even (Task A)
# ─────────────────────────────────────────────────────────────────────────────

# Measured entry/exit-split MEAN relative spreads (full quoted width / mid) from
# the closing-NBBO sample (scripts/measure_spread.py -> measured_spread.csv).
ASSUMED_ENTRY_SPREAD = 0.0613
ASSUMED_EXIT_SPREAD = 0.1647


def round_trip_cost_frac(entry_spread: float, exit_spread: float) -> float:
    """Round-trip transaction cost as a fraction of premium, the canonical basis.

    Each crossing pays half the full quoted spread of its own leg (mid to the
    touch). A round trip is two crossings - one in at entry, one out at exit - so
    the cost is ``entry_spread / 2 + exit_spread / 2``. Spreads are full quoted
    widths over mid; the division by two is the mid-to-touch half-cross, not a
    second discount.
    """
    return entry_spread / 2.0 + exit_spread / 2.0


# The forward-test break-even threshold. At the measured exit spread the straddle
# net per-trade Sharpe crosses zero at an exit width of ~17.1% (entry held at the
# measured 6.13%), i.e. a round-trip cost of round_trip_cost_frac(0.0613, 0.171).
BREAKEVEN_EXIT_SPREAD = 0.171
BREAKEVEN_ROUND_TRIP = round_trip_cost_frac(ASSUMED_ENTRY_SPREAD, BREAKEVEN_EXIT_SPREAD)


# ─────────────────────────────────────────────────────────────────────────────
# Forward-test configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ForwardTestConfig:
    """Knobs for the forward paper test, isolated from the research config.

    The locked signal baseline is the term gate at the 0.80 percentile with the
    move gate dropped; ``LiveConfig.term_pctl`` already carries the 0.80, so this
    only adds the things specific to the forward execution study. These would fold
    into ``LiveConfig`` once that file's owner merges them; they are kept here so
    the forward test can run without editing the shared config.

    Attributes
    ----------
    term_pctl : float
        Term-gate percentile, mirrored from ``LiveConfig`` (0.80).
    use_skew_gate, use_move_gate : bool
        Both ``False`` on the locked baseline (term-only selection).
    exit_limit_cross_frac : float
        Fraction of the way from mid to the touch the buy-back limit is placed
        (0.0 = mid, 1.0 = the touch). The lever under test; mirrors
        ``LiveConfig.limit_cross_frac`` so entry and exit share one knob unless
        overridden.
    exit_fallback_full_cross : bool
        If the limit does not fill, cross fully to the touch. Defaults to ``True``.
    stop_loss_rom : float
        Hard-stop level for the parallel book, as a return on margin. The stop
        book force-closes when the mark-to-market loss reaches this. Defaults to
        ``-0.30``.
    nostop_ledger_path, stop_ledger_path, reconciliation_path : str
        Parquet stores for the two parallel books and the fill/spread
        reconciliation, under ``outputs/live``.
    """

    term_pctl: float = LIVE.term_pctl
    use_skew_gate: bool = False
    use_move_gate: bool = False

    exit_limit_cross_frac: float = LIVE.limit_cross_frac
    exit_fallback_full_cross: bool = True

    stop_loss_rom: float = -0.30

    nostop_ledger_path: str = "outputs/live/forward_ledger_nostop.parquet"
    stop_ledger_path: str = "outputs/live/forward_ledger_stop.parquet"
    reconciliation_path: str = "outputs/live/forward_reconciliation.parquet"


FORWARD = ForwardTestConfig()


# ─────────────────────────────────────────────────────────────────────────────
# Two-leg marking and the managed exit price
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StraddleQuote:
    """The two-leg ATM straddle quote at one moment (per share, USD)."""

    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float

    @property
    def mid(self) -> float:
        """Straddle mid: the sum of the two leg mids."""
        return 0.5 * (self.call_bid + self.call_ask) + 0.5 * (self.put_bid + self.put_ask)

    @property
    def half_spread(self) -> float:
        """USD distance from mid to the touch (the sum of the two leg half-spreads)."""
        return 0.5 * (self.call_ask - self.call_bid) + 0.5 * (self.put_ask - self.put_bid)

    @property
    def touch_buy(self) -> float:
        """Price to buy the straddle back fully crossing to the ask (the touch)."""
        return self.call_ask + self.put_ask

    @property
    def relative_spread(self) -> float:
        """Full quoted spread over mid, ``(ask - bid) / mid`` summed across legs."""
        m = self.mid
        return float(2.0 * self.half_spread / m) if m > 0 else float("nan")


def managed_exit_price(quote: StraddleQuote, cross_frac: float) -> float:
    """Buy-back limit price a fraction ``cross_frac`` of the way from mid to touch.

    ``cross_frac = 0`` rests at mid (cheapest, least likely to fill); ``1`` is the
    touch (a full cross). Buying to close, so we step *up* from mid by
    ``cross_frac`` of the half-spread.
    """
    return float(quote.mid + max(0.0, cross_frac) * quote.half_spread)


def realised_exit_price(
    quote: StraddleQuote,
    cross_frac: float,
    *,
    filled_at_limit: bool,
    fallback_full_cross: bool,
) -> float:
    """The exit fill: the limit price if it filled, else the fallback.

    In dry-run modelling ``filled_at_limit`` is assumed ``True`` (the limit is
    taken to fill at its posted price); live, the harness passes the broker's
    actual fill flag. When unfilled and ``fallback_full_cross`` is set, the close
    crosses fully to the touch.
    """
    if filled_at_limit:
        return managed_exit_price(quote, cross_frac)
    if fallback_full_cross:
        return float(quote.touch_buy)
    return managed_exit_price(quote, cross_frac)


# ─────────────────────────────────────────────────────────────────────────────
# Parallel hard-stop book
# ─────────────────────────────────────────────────────────────────────────────


def mark_to_market_rom(
    entry_credit_ps: float,
    mark_ps: float,
    margin: float,
    contracts: int,
) -> float:
    """Return on margin of an open short straddle at a buy-back mark.

    P&L per share is the credit collected minus the cost to close now; scaled by
    the contract multiplier and lot, over the posted margin.
    """
    if margin <= 0:
        return float("nan")
    pnl = (entry_credit_ps - mark_ps) * CONTRACT_MULTIPLIER * contracts
    return float(pnl / margin)


def stop_triggered(
    entry_credit_ps: float,
    mark_ps: float,
    margin: float,
    contracts: int,
    stop_loss_rom: float,
) -> bool:
    """Whether the open straddle's mark-to-market loss has reached the stop."""
    rom = mark_to_market_rom(entry_credit_ps, mark_ps, margin, contracts)
    return bool(np.isfinite(rom) and rom <= stop_loss_rom)


# ─────────────────────────────────────────────────────────────────────────────
# Ledger rows (real two-leg marks) and reconciliation
# ─────────────────────────────────────────────────────────────────────────────


def _commission(contracts: int) -> float:
    """Round-trip commission for one straddle lot (four fills)."""
    return COST_PER_CONTRACT * FILLS_PER_STRADDLE * contracts


def forward_ledger_row(
    position: dict,
    *,
    spot_exit: float,
    iv_exit: float,
    exit_date,
    t_exit: float,
    exit_fill_ps: float,
) -> dict:
    """One completed-trade row in the backtest ``LEDGER_COLUMNS`` schema, priced on
    the *real* two-leg marks: the credit booked at entry and the actual buy-back
    fill at exit (commission deducted; the spread cost is already inside the fill).
    """
    contracts = int(position["contracts"])
    credit_ps = float(position["entry_credit"]) / (CONTRACT_MULTIPLIER * contracts)
    scale = CONTRACT_MULTIPLIER * contracts
    entry_credit = credit_ps * scale
    exit_value = float(exit_fill_ps) * scale
    commissions = _commission(contracts)
    pnl = entry_credit - exit_value - commissions
    margin = float(position["margin"])
    row = {
        "ticker": position["ticker"],
        "entry_date": position["entry_date"],
        "exit_date": exit_date,
        "strike": float(position["strike"]),
        "contracts": contracts,
        "spot_entry": float(position["spot_entry"]),
        "spot_exit": float(spot_exit),
        "iv_entry": float(position["iv_entry"]),
        "iv_exit": float(iv_exit),
        "t_entry": float(position["t_entry"]),
        "t_exit": float(t_exit),
        "entry_credit": entry_credit,
        "exit_value": exit_value,
        "commissions": commissions,
        "pnl": pnl,
        "margin": margin,
        "return_on_margin": pnl / margin if margin else float("nan"),
    }
    return {c: row[c] for c in LEDGER_COLUMNS}


def reconciliation_row(
    position: dict,
    quote: StraddleQuote,
    *,
    nostop_fill_ps: float,
    stop_fill_ps: float | None,
    stop_was_triggered: bool,
    assumed_entry_spread: float = ASSUMED_ENTRY_SPREAD,
    assumed_exit_spread: float = ASSUMED_EXIT_SPREAD,
) -> dict:
    """Realised fill vs assumed mid mark, realised vs assumed exit spread, and the
    realised round-trip cost against the canonical break-even.

    ``slippage_vs_mid_ps`` is what the managed exit actually paid over the mid mark
    the backtest assumes; ``stop_gap_slippage_ps`` is the extra the stop book paid
    on the gap versus the no-stop managed exit (the quantity only the live test can
    pin down). The round-trip is the realised exit spread half-crossed plus the
    assumed entry half-cross, flagged over/under break-even.
    """
    mid = quote.mid
    realised_exit_spread = quote.relative_spread
    rt = round_trip_cost_frac(assumed_entry_spread, realised_exit_spread)
    stop_gap = (
        float(stop_fill_ps - nostop_fill_ps)
        if (stop_was_triggered and stop_fill_ps is not None)
        else 0.0
    )
    return {
        "ticker": position["ticker"],
        "entry_date": position["entry_date"],
        "exit_date": position.get("exit_date"),
        "assumed_mid_mark_ps": float(mid),
        "nostop_fill_ps": float(nostop_fill_ps),
        "slippage_vs_mid_ps": float(nostop_fill_ps - mid),
        "assumed_exit_spread": float(assumed_exit_spread),
        "realised_exit_spread": float(realised_exit_spread),
        "stop_was_triggered": bool(stop_was_triggered),
        "stop_fill_ps": float(stop_fill_ps) if stop_fill_ps is not None else float("nan"),
        "stop_gap_slippage_ps": stop_gap,
        "realised_round_trip_cost": float(rt),
        "breakeven_round_trip": float(BREAKEVEN_ROUND_TRIP),
        "over_breakeven": bool(rt > BREAKEVEN_ROUND_TRIP),
    }


def build_forward_exit(
    position: dict,
    quote: StraddleQuote,
    *,
    spot_exit: float,
    iv_exit: float,
    exit_date,
    t_exit: float,
    config: ForwardTestConfig = FORWARD,
    filled_at_limit: bool = True,
    stop_fill_ps: float | None = None,
) -> tuple[dict, dict, dict]:
    """Assemble the no-stop row, the stop-book row and the reconciliation row.

    The no-stop book exits with the managed limit (or its fallback). The stop book
    exits at the same managed fill *unless* the post-print-open mark has breached
    the stop, in which case it closes at ``stop_fill_ps`` (the realised gapped
    fill live, or the full-cross touch as the conservative dry-run model).

    Parameters
    ----------
    position : dict
        An open-position row (``OPEN_COLUMNS`` schema).
    quote : StraddleQuote
        The post-print-open two-leg straddle quote.
    spot_exit, iv_exit, exit_date, t_exit : ...
        Exit-snapshot context for the ledger rows.
    filled_at_limit : bool
        Whether the managed limit filled (live: the broker flag; dry-run: assumed
        ``True``).
    stop_fill_ps : float, optional
        The realised stop fill per share if the stop triggered live. ``None`` uses
        the full-cross touch as the conservative dry-run stop fill.

    Returns
    -------
    (nostop_row, stop_row, recon_row)
        Two ``LEDGER_COLUMNS`` rows and one reconciliation row.
    """
    contracts = int(position["contracts"])
    credit_ps = float(position["entry_credit"]) / (CONTRACT_MULTIPLIER * contracts)
    margin = float(position["margin"])

    nostop_fill = realised_exit_price(
        quote,
        config.exit_limit_cross_frac,
        filled_at_limit=filled_at_limit,
        fallback_full_cross=config.exit_fallback_full_cross,
    )

    # Stop book: evaluate the stop on the post-print-open mid mark (the gap mark).
    triggered = stop_triggered(credit_ps, quote.mid, margin, contracts, config.stop_loss_rom)
    if triggered:
        stop_fill = float(stop_fill_ps) if stop_fill_ps is not None else float(quote.touch_buy)
    else:
        stop_fill = nostop_fill

    nostop_row = forward_ledger_row(
        position,
        spot_exit=spot_exit,
        iv_exit=iv_exit,
        exit_date=exit_date,
        t_exit=t_exit,
        exit_fill_ps=nostop_fill,
    )
    stop_row = forward_ledger_row(
        position,
        spot_exit=spot_exit,
        iv_exit=iv_exit,
        exit_date=exit_date,
        t_exit=t_exit,
        exit_fill_ps=stop_fill,
    )
    recon = reconciliation_row(
        position,
        quote,
        nostop_fill_ps=nostop_fill,
        stop_fill_ps=stop_fill if triggered else None,
        stop_was_triggered=triggered,
    )
    return nostop_row, stop_row, recon


# A non-cost helper kept for callers that want the commission-only CostModel used
# elsewhere in the harness (so forward and backtest share one commission basis).
DEFAULT_COSTS = CostModel(bid_ask_pct=0.0, slippage_ticks=0.0)
