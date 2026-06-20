"""Tests for the per-cohort comparison."""

from __future__ import annotations

import numpy as np
import pandas as pd

from earnings_iv_crush.engine.cohorts import COHORT_METRICS, cohort_table, compare_cohorts


def _ledger(n=200, seed=3):
    rng = np.random.default_rng(seed)
    half = n // 2
    return pd.DataFrame(
        {
            "cohort": ["megacap"] * half + ["broad-only"] * half,
            "pnl": np.concatenate([rng.normal(500, 800, half), rng.normal(-200, 800, half)]),
            "exit_date": pd.bdate_range("2025-01-02", periods=n).astype(str),
        }
    )


def test_cohort_table_shape_and_values():
    table = cohort_table(_ledger())
    assert list(table.columns) == COHORT_METRICS
    assert set(table["cohort"]) == {"megacap", "broad-only"}
    mega = table.set_index("cohort").loc["megacap"]
    assert mega["n_trades"] == 100
    assert mega["hit_rate"] > 0.5


def test_compare_cohorts_detects_planted_difference():
    cmp = compare_cohorts(_ledger())
    assert cmp["mean_diff"] > 0
    assert cmp["significant"]
    assert cmp["diff_ci_low"] > 0


def test_compare_cohorts_no_difference():
    rng = np.random.default_rng(0)
    led = pd.DataFrame(
        {"cohort": ["megacap"] * 100 + ["broad-only"] * 100, "pnl": rng.normal(0, 500, 200)}
    )
    cmp = compare_cohorts(led)
    assert not cmp["significant"]


def test_empty_or_unlabelled_ledger():
    assert cohort_table(pd.DataFrame()).empty
    cmp = compare_cohorts(pd.DataFrame({"pnl": [1.0]}))
    assert cmp["n_a"] == 0 and not cmp["significant"]
