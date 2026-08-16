"""Tests for the shared candidate scoring contract.

The two failures this module exists to prevent are an unstated Sharpe basis and a
silently empty selection, so both are asserted directly rather than inferred.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.screen import (
    DegenerateScreenError,
    ScreenResult,
    gross_gate,
    results_table,
    score_signal,
)


@pytest.fixture
def monthly_returns() -> tuple[pd.Series, pd.Series]:
    """Five years of monthly returns with a small positive mean."""
    rng = np.random.default_rng(11)
    dates = pd.date_range("2015-01-31", periods=60, freq="ME")
    return pd.Series(rng.normal(0.01, 0.04, 60)), pd.Series(dates)


# ── basis handling ───────────────────────────────────────────────────────────


def test_per_trade_is_the_default_basis_and_factor_is_still_reported(monthly_returns):
    ret, dates = monthly_returns
    res = score_signal(ret, dates, "cal", cadence="calendar")
    assert res.sharpe_basis == "per-trade"
    # The factor is recorded even when unused, so a reader can convert.
    assert res.periods_per_year == pytest.approx(12.0, abs=0.5)


def test_annualised_basis_scales_by_sqrt_of_inferred_cadence(monthly_returns):
    ret, dates = monthly_returns
    per_trade = score_signal(ret, dates, "cal", cadence="calendar")
    annual = score_signal(ret, dates, "cal", cadence="calendar", basis="annualised")

    assert annual.sharpe_basis == "annualised"
    assert annual.sharpe == pytest.approx(per_trade.sharpe * np.sqrt(annual.periods_per_year))


def test_sparse_event_book_does_not_get_a_252_factor():
    """The canonical failure: 30 trades a year must not annualise as if daily."""
    rng = np.random.default_rng(3)
    dates = pd.date_range("2015-01-05", periods=90, freq="12D")
    res = score_signal(
        pd.Series(rng.normal(0.02, 0.05, 90)),
        pd.Series(dates),
        "event",
        cadence="event",
        basis="annualised",
    )
    assert res.periods_per_year < 60.0


# ── degenerate input raises rather than returning NaN ────────────────────────


def test_empty_selection_raises_with_a_diagnostic_message():
    with pytest.raises(DegenerateScreenError, match="empty selection"):
        score_signal(
            pd.Series([np.nan, np.nan, np.nan]),
            pd.Series(pd.date_range("2020-01-31", periods=3, freq="ME")),
            "broken-join",
            cadence="calendar",
        )


def test_zero_variance_raises():
    with pytest.raises(DegenerateScreenError, match="zero or non-finite variance"):
        score_signal(
            pd.Series([0.01] * 12),
            pd.Series(pd.date_range("2020-01-31", periods=12, freq="ME")),
            "constant",
            cadence="calendar",
        )


def test_length_mismatch_raises():
    with pytest.raises(DegenerateScreenError, match="differ in length"):
        score_signal(
            pd.Series([0.01, 0.02, 0.03]),
            pd.Series(pd.date_range("2020-01-31", periods=2, freq="ME")),
            "mismatch",
            cadence="calendar",
        )


# ── clustering ───────────────────────────────────────────────────────────────


def test_clustered_interval_is_wider_than_the_unclustered_one():
    """Many names on one date are not independent draws; the CI must show it."""
    rng = np.random.default_rng(5)
    # 20 clusters of 10 rows; rows inside a cluster share a common shock.
    shocks = rng.normal(0.01, 0.05, 20)
    values, dates, keys = [], [], []
    for i, shock in enumerate(shocks):
        day = pd.Timestamp("2020-01-31") + pd.Timedelta(days=30 * i)
        for _ in range(10):
            values.append(shock + rng.normal(0.0, 0.002))
            dates.append(day)
            keys.append(day)

    clustered = score_signal(
        pd.Series(values),
        pd.Series(dates),
        "clustered",
        cadence="event",
        cluster_keys=pd.Series(keys),
    )
    unclustered = score_signal(
        pd.Series(values),
        pd.Series(dates),
        "unclustered",
        cadence="event",
        cluster_keys=pd.Series(range(len(values))),
    )
    assert clustered.n_clusters == 20
    assert (clustered.ci_high - clustered.ci_low) > (unclustered.ci_high - unclustered.ci_low)


# ── gross-first gate ─────────────────────────────────────────────────────────


def test_gate_fails_a_negative_gross_mean_and_says_why():
    outcome = gross_gate(pd.Series([-0.02] * 40), "no-signal")
    assert not outcome.passed
    assert "no cost model can rescue it" in outcome.reason


def test_gate_fails_on_thin_sample():
    outcome = gross_gate(pd.Series([0.02] * 5), "thin", min_n=30)
    assert not outcome.passed
    assert "below minimum" in outcome.reason


def test_gate_passes_a_positive_gross_mean_and_prints_the_funnel():
    outcome = gross_gate(
        pd.Series(np.linspace(0.001, 0.05, 60)),
        "candidate",
        funnel={"raw events": 5000, "after gate": 60},
    )
    assert outcome.passed
    report = outcome.report()
    assert "raw events" in report and "5,000" in report


def test_long_short_spread_can_opt_out_of_the_positive_mean_requirement():
    outcome = gross_gate(pd.Series([-0.01] * 40), "spread", require_positive_mean=False)
    assert outcome.passed


# ── result record ────────────────────────────────────────────────────────────


def test_interval_containing_zero_is_flagged_and_summarised(monthly_returns):
    ret, dates = monthly_returns
    res = score_signal(ret, dates, "cal", cadence="calendar")
    assert res.interval_contains_zero == (res.ci_low <= 0.0 <= res.ci_high)
    assert res.sharpe_basis in res.summary()


def test_results_table_orders_by_dsr(monthly_returns):
    ret, dates = monthly_returns
    strong = score_signal(ret + 0.03, dates, "strong", cadence="calendar", n_trials=1)
    weak = score_signal(ret - 0.01, dates, "weak", cadence="calendar", n_trials=500)
    table = results_table([weak, strong])
    assert list(table["label"]) == ["strong", "weak"]
    assert "sharpe_basis" in table.columns


def test_results_table_is_empty_for_no_results():
    assert results_table([]).empty


def test_screen_result_is_frozen(monthly_returns):
    ret, dates = monthly_returns
    res = score_signal(ret, dates, "cal", cadence="calendar")
    with pytest.raises(AttributeError):
        res.sharpe = 99.0  # type: ignore[misc]
    assert isinstance(res, ScreenResult)
