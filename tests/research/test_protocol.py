"""
test_protocol.py
The research protocol helpers against independent references.

The interval is checked against a direct re-implementation of the date-clustered percentile
bootstrap, the Sharpe against the textbook formula, and the matched null against its
defining property (random draws of the same size centre on the population statistic).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.research import protocol as pr


def _book(n_dates: int = 40, per_date: int = 3, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    dates = np.repeat(pd.date_range("2024-01-02", periods=n_dates, freq="B").to_numpy(), per_date)
    shock = np.repeat(rng.normal(0, 0.05, n_dates), per_date)  # shared same-day move
    return 0.01 + shock + rng.normal(0, 0.08, dates.size), dates


def _reference_ci(values, dates, stat, n_boot, seed, ci=0.95):
    keys = pd.to_datetime(pd.Series(dates)).dt.normalize().to_numpy()
    uniq = np.unique(keys)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        drawn = rng.choice(uniq, size=len(uniq), replace=True)
        out.append(stat(np.concatenate([values[keys == k] for k in drawn])))
    return np.nanpercentile(out, 100 * (1 - ci) / 2), np.nanpercentile(out, 100 * (1 + ci) / 2)


@pytest.mark.parametrize("stat", [np.mean, pr.per_trade_sharpe])
@pytest.mark.parametrize("seed", [0, 7])
def test_interval_matches_an_independent_bootstrap(stat, seed) -> None:
    v, d = _book()
    got = pr.date_clustered_ci(v, d, stat, n_boot=400, seed=seed)
    lo, hi = _reference_ci(v, d, stat, 400, seed)
    assert (got.low, got.high) == pytest.approx((lo, hi))
    assert got.n == v.size and got.clusters == 40


def test_clustering_widens_the_interval_when_dates_share_a_move() -> None:
    v, d = _book(per_date=5)
    clustered = pr.date_clustered_ci(v, d, np.mean, n_boot=800)
    iid = pr.date_clustered_ci(v, np.arange(v.size), np.mean, n_boot=800)  # one row per cluster
    assert (clustered.high - clustered.low) > (iid.high - iid.low)


def test_per_trade_sharpe_is_mean_over_sample_sd() -> None:
    x = np.array([0.02, -0.01, 0.03, 0.00, 0.01])
    assert pr.per_trade_sharpe(x) == pytest.approx(x.mean() / x.std(ddof=1))
    assert np.isnan(pr.per_trade_sharpe([0.01]))


def test_interval_refuses_mismatched_or_empty_input() -> None:
    with pytest.raises(ValueError):
        pr.date_clustered_ci([0.1, 0.2], ["2024-01-02"])
    with pytest.raises(ValueError):
        pr.date_clustered_ci([np.nan], ["2024-01-02"])


def test_matched_null_centres_on_the_population_and_ranks_a_good_rule() -> None:
    rng = np.random.default_rng(3)
    pop = rng.normal(0.0, 1.0, 2000)
    random_mask = np.zeros(pop.size, bool)
    random_mask[rng.choice(pop.size, 200, replace=False)] = True
    res = pr.matched_random_null(pop, random_mask, np.mean, n_draws=600)
    assert np.mean(res.null) == pytest.approx(pop.mean(), abs=0.02)
    best = pop >= np.quantile(pop, 0.9)  # a rule that really selects
    assert pr.matched_random_null(pop, best, np.mean, n_draws=600).percentile == 100.0


def test_matched_null_refuses_a_degenerate_selection() -> None:
    with pytest.raises(ValueError):
        pr.matched_random_null(np.ones(5), np.zeros(5, bool))


def test_freeze_then_verify_and_detect_an_edit(tmp_path) -> None:
    text = tmp_path / "x_prereg.md"
    text.write_text("Hypothesis: something falsifiable.\n", encoding="utf-8")
    record = tmp_path / "prereg_x.json"
    body = pr.freeze_prereg(
        text, record, trial_id="x", n_trials_declared=1, declared_utc="2026-10-18"
    )
    assert json.loads(record.read_text(encoding="utf-8"))["prereg_sha256"] == body["prereg_sha256"]
    assert pr.verify_prereg(text, record) == body["prereg_sha256"]
    with pytest.raises(FileExistsError):
        pr.freeze_prereg(text, record, trial_id="x", n_trials_declared=1, declared_utc="2026-10-18")
    text.write_text("Hypothesis: something else.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen hash"):
        pr.verify_prereg(text, record)
