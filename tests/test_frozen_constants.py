"""
test_frozen_constants.py
The frozen constants must agree with config, and the reconciliation gate must bite.

The failure this guards against is not hypothetical. A research script imported a
neighbouring module's ``TERM_PCTL`` of 0.75 in place of the frozen 0.80 and produced a
baseline of n=246 / +0.031665 where the spec gives n=198 / +0.087393. Both look like
plausible numbers; only a comparison against a recorded target separates them.
"""

from __future__ import annotations

import pytest

from earnings_iv_crush.config import GLOBAL, STRATEGY
from earnings_iv_crush.frozen import EXEC, RECONCILIATION, SPEC, assert_reconciles


def test_spec_mirrors_config() -> None:
    assert SPEC.term_spread_pctl == STRATEGY.term_spread_pctl == 0.80
    assert SPEC.use_move_gate == STRATEGY.use_move_gate is False
    assert SPEC.back_month_min_gap_days == GLOBAL.back_month_min_gap_days


def test_execution_widths_match_half_crosses() -> None:
    assert EXEC.entry_full_width * EXEC.cross_fraction == pytest.approx(EXEC.entry_half_cross)
    assert EXEC.exit_full_width * EXEC.cross_fraction == pytest.approx(EXEC.exit_half_cross)
    # the exit touch is the wider side; a symmetric model understates the round trip
    assert EXEC.exit_half_cross > EXEC.entry_half_cross


@pytest.mark.parametrize("block", sorted(RECONCILIATION))
def test_recorded_targets_reconcile_with_themselves(block: str) -> None:
    t = RECONCILIATION[block]
    assert_reconciles(block, t.n_trades, t.per_trade_sharpe)


def test_wrong_percentile_baseline_is_rejected() -> None:
    """The actual 0.75-gate numbers must not pass as the 0.80 baseline."""
    with pytest.raises(AssertionError, match="reconciliation failed"):
        assert_reconciles("2019-2024", 246, 0.031665)


def test_sharpe_drift_alone_is_rejected() -> None:
    t = RECONCILIATION["2013-2018"]
    with pytest.raises(AssertionError):
        assert_reconciles("2013-2018", t.n_trades, t.per_trade_sharpe + 0.01)


def test_unknown_block_raises() -> None:
    with pytest.raises(KeyError):
        assert_reconciles("2025-2026", 10, 0.0)
