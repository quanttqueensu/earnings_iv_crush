"""Tests for engine.sensitivity (threshold sweep) and engine.walkforward."""

from __future__ import annotations

from earnings_iv_crush.engine.sensitivity import SWEEP_COLUMNS, sweep_dsr_params, threshold_sweep
from earnings_iv_crush.engine.simulate import simulate_events
from earnings_iv_crush.engine.walkforward import walk_forward_backtest
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel


def _fitted():
    ev = simulate_events(n=300, seed=7, edge_frac=0.35)
    return ev, FairMoveModel().fit(ev, ev["realised_move"])


# --- sensitivity sweep -------------------------------------------------------


def test_sweep_covers_full_grid():
    ev, model = _fitted()
    ratios, pctls = [1.1, 1.2, 1.3], [0.6, 0.75, 0.9]
    sweep = threshold_sweep(ev, model, ratios, pctls)
    assert list(sweep.columns) == SWEEP_COLUMNS
    assert len(sweep) == len(ratios) * len(pctls)


def test_stricter_ratio_trades_no_more():
    ev, model = _fitted()
    sweep = threshold_sweep(ev, model, [1.10, 1.50], [0.75])
    loose = sweep[sweep["ratio"] == 1.10]["n_trades"].iloc[0]
    strict = sweep[sweep["ratio"] == 1.50]["n_trades"].iloc[0]
    assert strict <= loose


def test_sweep_dsr_params():
    ev, model = _fitted()
    sweep = threshold_sweep(ev, model, [1.1, 1.2, 1.3], [0.6, 0.75])
    n_trials, sr_std = sweep_dsr_params(sweep)
    assert n_trials == 6
    assert sr_std >= 0.0


# --- walk-forward ------------------------------------------------------------


def test_walk_forward_is_out_of_sample():
    ev, _ = _fitted()
    stats, ledger = walk_forward_backtest(ev, ev["realised_move"], min_train=20)
    # Only events past the warm-up get an OOS prediction.
    assert stats["n_oos"] == len(ev) - 20
    assert 0 <= stats["n_selected"] <= stats["n_oos"]
    assert len(ledger) == stats["n_trades"]


def test_walk_forward_selects_a_subset():
    ev, _ = _fitted()
    stats, _ = walk_forward_backtest(ev, ev["realised_move"], min_train=20)
    assert stats["n_selected"] < stats["n_oos"]  # the filter bites out of sample
