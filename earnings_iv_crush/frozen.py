"""
frozen.py
Single source of truth for the frozen strategy constants and the baseline numbers
any research script must reproduce before its own arms are believed.

Research scripts kept importing whichever constant happened to sit at module scope in a
neighbouring script. That is how a run reached the reporting stage gated at the 75th
percentile while claiming the frozen 80th: the two differ by 53 trades and 0.056 of
per-trade Sharpe, which is larger than most effects being tested. Nothing here is new
policy; every value is the one already fixed elsewhere, gathered so a script can bind to
it by name and so a drift shows up as an exception rather than as a plausible number.

Two things live here:

* the frozen specification constants, cross-checked against ``config.STRATEGY`` at import
  so this file cannot silently disagree with the dataclass it mirrors;
* the reconciliation targets, with :func:`assert_reconciles` to compare a freshly scored
  baseline against them and raise if the harness has moved.

Usage in a research script::

    from earnings_iv_crush.frozen import SPEC, EXEC, assert_reconciles

    mask = expanding_gate(events, term_spread, SPEC.term_spread_pctl)
    ledger = score(events[mask])
    assert_reconciles("2019-2024", len(ledger), per_trade_sharpe)

References
----------
Bailey, D. H. and Lopez de Prado, M. (2014). The deflated Sharpe ratio. *Journal of
    Portfolio Management* 40(5), 94-107. The trial count that deflation charges against
    is only meaningful if every trial was run on the same specification.
"""

from __future__ import annotations

from dataclasses import dataclass

from earnings_iv_crush.config import GLOBAL, STRATEGY

__all__ = ["SPEC", "EXEC", "RECONCILIATION", "ReconciliationTarget", "assert_reconciles"]


# ── frozen specification ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrozenSpec:
    """The gate and sizing constants of the frozen specification.

    Attributes
    ----------
    term_spread_pctl : float
        Percentile of the causal expanding pooled distribution of strictly prior events'
        front-minus-back ATM IV spread, at or above which an event is gated in. 0.80.
        Any script using 0.75 is using ``validate_skew_oos``'s own default, not the spec.
    use_move_gate : bool
        The implied-versus-fair move gate. Dropped: it fails out of sample.
    min_hist : int
        Events that must precede an event before the expanding gate will judge it, and
        the length of the burn-in ``_prepare`` drops from the front of an event table.
    sizing_fraction : float
        Fraction of account notional risked per straddle, through ``size_contracts``.
    back_month_min_gap_days : int
        Minimum front-to-back expiry gap when the term spread is measured. Mirrors
        ``config.GLOBAL``; it sets the denominator of any forward-variance construction
        built on top of the same two tenors.
    """

    term_spread_pctl: float = 0.80
    use_move_gate: bool = False
    min_hist: int = 25
    sizing_fraction: float = 0.05
    back_month_min_gap_days: int = 21


@dataclass(frozen=True)
class ExecutionArms:
    """The three cost arms, in the bases each is quoted in.

    The measured arm comes from the 34,672-print fixed-boundary study: unconditional
    15:59 prints, exchange-local, asymmetric between entry and exit because the exit
    session's touch is wider. ``*_half_cross`` are fractions of premium paid per side;
    ``*_full_width`` are the quoted widths those imply, which is what ``CostModel``
    takes since it charges ``cross_fraction`` of the full width. ``measured_per_side``
    is the headline 1.7871%: the print-weighted figure over the whole study, not the
    plain mean of the two sides, because the two sides carry different print counts.

    The trade-conditional arm (0.7611%/side) is deliberately absent. It is a selection
    artefact: prints cluster where the book is tight, and a fixed-boundary strategy
    cannot select into those moments. ``tests/test_fills_rescore_attainability.py``
    fails if anything promotes it.
    """

    entry_half_cross: float = 0.012714
    exit_half_cross: float = 0.030182
    entry_full_width: float = 0.025428
    exit_full_width: float = 0.060364
    cross_fraction: float = 0.5
    central_bid_ask_pct: float = 0.04  # the ~2%/side round-trip case used pre-measurement
    flat_breakeven: float = 0.116  # of premium, round trip
    measured_per_side: float = 0.017871
    n_prints: int = 34_672


SPEC = FrozenSpec()
EXEC = ExecutionArms()

if SPEC.term_spread_pctl != STRATEGY.term_spread_pctl:
    raise RuntimeError(
        f"frozen.SPEC.term_spread_pctl={SPEC.term_spread_pctl} disagrees with "
        f"config.STRATEGY.term_spread_pctl={STRATEGY.term_spread_pctl}"
    )
if SPEC.use_move_gate != STRATEGY.use_move_gate:
    raise RuntimeError("frozen.SPEC.use_move_gate disagrees with config.STRATEGY")
if SPEC.back_month_min_gap_days != GLOBAL.back_month_min_gap_days:
    raise RuntimeError("frozen.SPEC.back_month_min_gap_days disagrees with config.GLOBAL")
for _side in ("entry", "exit"):
    _half = getattr(EXEC, f"{_side}_half_cross")
    _full = getattr(EXEC, f"{_side}_full_width")
    if abs(_full * EXEC.cross_fraction - _half) > 1e-12:
        raise RuntimeError(
            f"frozen.EXEC {_side} width {_full} is inconsistent with its half-cross {_half} "
            f"at cross_fraction {EXEC.cross_fraction}"
        )


# ── reconciliation ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReconciliationTarget:
    """A baseline a research harness must reproduce before its own arms are read.

    Attributes
    ----------
    events_path, chain_path : str or None
        The event table and the chain source the number was produced from. The
        2019-2024 block uses the frozen trade-marked default; 2013-2018 is not covered
        by that chain and must be marked from the quote cache, which is why passing the
        wrong one raises ``KeyError: 'credit_mkt'`` rather than quietly rescoring.
    n_trades : int
        Trades surviving the gate and the marking funnel.
    per_trade_sharpe : float
        Mean return on margin over its standard deviation, per trade. NOT annualised.
        Annualising this book needs sqrt(trades per year) ~= 5.93, never sqrt(252).
    """

    block: str
    events_path: str
    chain_path: str | None
    n_trades: int
    per_trade_sharpe: float
    note: str = ""


RECONCILIATION: dict[str, ReconciliationTarget] = {
    "2019-2024": ReconciliationTarget(
        block="2019-2024",
        events_path="outputs/research/events_megacap_databento.parquet",
        chain_path=None,
        n_trades=198,
        per_trade_sharpe=0.087393,
        note="discovery block, trade-marked default chain",
    ),
    "2013-2018": ReconciliationTarget(
        block="2013-2018",
        events_path="data/processed/events_megacap_quotes_2013_2018.parquet",
        chain_path="quote cache (databento_quotes.cache_path)",
        n_trades=193,
        per_trade_sharpe=-0.005337,
        note="true holdout, quote-marked; the frozen spec fails here",
    ),
}

POOLED_N = 391
POOLED_SHARPE = 0.055992
POOLED_SHARPE_MEASURED_COST = 0.062899


def assert_reconciles(
    block: str,
    n_trades: int,
    per_trade_sharpe: float,
    sharpe_tol: float = 1e-4,
) -> None:
    """Raise unless a freshly scored baseline matches its recorded target.

    Called before any experimental arm is read. A harness that cannot reproduce the
    baseline is not evidence about the arms it also computed, so this fails loudly
    rather than returning a flag a caller can ignore.

    Parameters
    ----------
    block : str
        Key into :data:`RECONCILIATION`.
    n_trades : int
        Trade count the harness just produced for the unmodified gate.
    per_trade_sharpe : float
        Per-trade Sharpe the harness just produced for the unmodified gate.
    sharpe_tol : float, optional
        Absolute tolerance on the Sharpe. Default 1e-4, which is tighter than any
        difference a specification change would produce and loose enough for float
        reduction order.

    Raises
    ------
    KeyError
        If ``block`` has no recorded target.
    AssertionError
        If either the trade count or the Sharpe has moved.
    """
    t = RECONCILIATION[block]
    if n_trades != t.n_trades or abs(per_trade_sharpe - t.per_trade_sharpe) > sharpe_tol:
        raise AssertionError(
            f"baseline reconciliation failed for {block}: "
            f"got n={n_trades} sharpe={per_trade_sharpe:+.6f}, "
            f"expected n={t.n_trades} sharpe={t.per_trade_sharpe:+.6f}. "
            f"The harness has moved; no arm scored through it is trustworthy. "
            f"Check the gate percentile (spec is {SPEC.term_spread_pctl}), the chain "
            f"source ({t.chain_path}), and the event table ({t.events_path})."
        )
