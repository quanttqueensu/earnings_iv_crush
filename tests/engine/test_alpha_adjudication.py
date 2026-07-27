"""Tests for the canonical alpha-versus-risk measurements."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.alpha_adjudication import (
    add_return_measures,
    book_metrics,
    build_canonical_event_ledger,
    causal_expanding_gate,
    package_relative_spread,
    permutation_gate_test,
    temporal_quantile_rule,
)


def _scorecard_frame() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"])
    return pd.DataFrame({"return_on_margin": [0.1, -0.05, 0.2, -0.1], "announce_date": dates})


def test_package_spread_weights_legs_by_dollar_mid():
    # Equal-weighting relative widths would be (1/10 + .1/1) / 2 = 5.5%.
    # The executable package width is 1.1 / 11 = 10%.
    assert package_relative_spread([1.0, 0.1], [10.0, 1.0]) == pytest.approx(0.1)


def test_package_spread_rejects_misaligned_quotes():
    with pytest.raises(ValueError):
        package_relative_spread([1.0], [10.0, 1.0])


def test_return_measures_do_not_infer_premium_from_margin():
    frame = pd.DataFrame({"return_on_margin": [0.1, -0.2]})
    out = add_return_measures(frame)
    assert out["net_return_on_premium"].isna().all()


def test_return_measures_use_realized_credit_and_close_value():
    frame = pd.DataFrame(
        {"entry_credit": [100.0], "exit_value": [60.0], "pnl": [35.0], "return_on_margin": [0.2]}
    )
    out = add_return_measures(frame)
    assert out.loc[0, "gross_return_on_premium"] == pytest.approx(0.4)
    assert out.loc[0, "net_return_on_premium"] == pytest.approx(0.35)


def test_causal_gate_excludes_current_and_future_observations():
    dates = pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]))
    signal = pd.Series([1.0, 2.0, 3.0, 4.0])
    gate = causal_expanding_gate(signal, dates, quantile=0.5, min_prior=2)
    assert gate.tolist() == [False, False, True, True]


def test_temporal_rule_fits_only_training_window():
    dates = pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]))
    signal = pd.Series([1.0, 2.0, 100.0, 0.0])
    rule, threshold = temporal_quantile_rule(signal, dates, "2020-01-02", quantile=0.5)
    assert threshold == pytest.approx(1.5)
    assert rule.tolist() == [False, False, False, True]


def test_canonical_join_rejects_duplicate_event_keys():
    events = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL"],
            "entry_date": ["2024-01-01", "2024-01-01"],
            "announce_date": ["2024-01-02", "2024-01-02"],
            "iv_term_spread": [0.1, 0.2],
        }
    )
    ledger = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "entry_date": ["2024-01-01"],
            "pnl": [1.0],
            "entry_credit": [10.0],
            "exit_value": [9.0],
        }
    )
    with pytest.raises(ValueError):
        build_canonical_event_ledger(events, ledger)


def test_permutation_test_is_reproducible_and_detects_fixed_lift():
    outcome = pd.Series([10.0] * 5 + [0.0] * 15)
    gate = pd.Series([True] * 5 + [False] * 15)
    first = permutation_gate_test(outcome, gate, n_permutations=500, seed=7)
    second = permutation_gate_test(outcome, gate, n_permutations=500, seed=7)
    assert first == second
    assert first["observed_lift"] == pytest.approx(10.0)
    assert first["p_value"] < 0.05


def test_permutation_test_handles_degenerate_gate():
    result = permutation_gate_test(pd.Series([1.0, 2.0]), pd.Series([True, True]))
    assert np.isnan(result["p_value"])


def test_book_metrics_runs_on_default_shared_date_and_cluster_columns():
    # date_col and cluster_col share the default "announce_date"; the selection
    # must not duplicate it.
    card = book_metrics(_scorecard_frame(), "return_on_margin", n_boot=50)
    assert card["n"] == 4
    assert card["hit_rate"] == pytest.approx(0.5)
    assert np.isfinite(card["per_trade_sharpe"])


def test_book_metrics_annualises_from_the_observed_cadence():
    # Four trades spanning 274 days annualise by sqrt(ppy), never sqrt(252).
    card = book_metrics(_scorecard_frame(), "return_on_margin", n_boot=50)
    expected_ppy = 4 * 365.25 / 274
    assert card["periods_per_year"] == pytest.approx(expected_ppy, rel=1e-6)
    assert card["annualised_sharpe"] == pytest.approx(
        card["per_trade_sharpe"] * np.sqrt(expected_ppy), rel=1e-6
    )
