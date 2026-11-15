"""
test_protocol.py
The research protocol helpers against independent references.

The interval is checked against a direct re-implementation of the date-clustered percentile
bootstrap, the Sharpe against the textbook formula, and the matched null against its
defining property (random draws of the same size centre on the population statistic).
"""

from __future__ import annotations

import json
from pathlib import Path

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


_PREREG_TEXT = "Hypothesis: something falsifiable.\n## Mechanism\nwhy.\n## Power\nMDE 0.01.\n"


def test_freeze_then_verify_and_detect_an_edit(tmp_path) -> None:
    text = tmp_path / "x_prereg.md"
    text.write_text(_PREREG_TEXT, encoding="utf-8")
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


# ── freeze of scorer and inputs, unblinding ──────────────────────────────────


def _frozen_study(tmp_path):
    text = tmp_path / "prereg.md"
    text.write_text(_PREREG_TEXT, encoding="utf-8")
    scorer = tmp_path / "study.py"
    scorer.write_text("print('v1')\n", encoding="utf-8")
    data = tmp_path / "events.csv"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    record = tmp_path / "prereg_s.json"
    pr.freeze_prereg(
        text,
        record,
        trial_id="s",
        n_trials_declared=1,
        declared_utc="2026-11-12",
        scorer=scorer,
        inputs=[data],
    )
    return text, scorer, data, record


def test_freeze_refuses_a_text_without_mechanism_and_power(tmp_path) -> None:
    text = tmp_path / "prereg.md"
    text.write_text("Hypothesis only.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="required sections"):
        pr.freeze_prereg(
            text, tmp_path / "r.json", trial_id="x", n_trials_declared=1, declared_utc="2026-11-12"
        )


def test_scorer_change_after_unblinding_raises(tmp_path) -> None:
    text, scorer, _, record = _frozen_study(tmp_path)
    pr.verify_prereg(text, record, unblind=True)
    scorer.write_text("print('v2')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="after an unblinded run"):
        pr.verify_prereg(text, record)


def test_scorer_change_before_unblinding_is_logged_not_fatal(tmp_path) -> None:
    text, scorer, _, record = _frozen_study(tmp_path)
    scorer.write_text("print('fixed crash')\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="before unblinding"):
        pr.verify_prereg(text, record)
    log = record.with_name(record.stem + pr.RUN_LOG_SUFFIX).read_text(encoding="utf-8")
    assert "code_change_pre_unblind" in log
    pr.verify_prereg(text, record, unblind=True)  # the fixed scorer is now the frozen one


def test_second_unblinded_run_needs_a_reason(tmp_path) -> None:
    text, _, _, record = _frozen_study(tmp_path)
    pr.verify_prereg(text, record, unblind=True)
    with pytest.raises(ValueError, match="already has an unblinded run"):
        pr.verify_prereg(text, record, unblind=True)
    pr.verify_prereg(text, record, unblind=True, rerun_reason="crashed at block 2")


def test_input_change_raises(tmp_path) -> None:
    text, _, data, record = _frozen_study(tmp_path)
    data.write_text("a,b\n1,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed or is missing"):
        pr.verify_prereg(text, record)


# ── blinding, staging, power, significance, FDR ──────────────────────────────


def test_blind_keeps_each_date_multiset_and_breaks_order() -> None:
    v, d = _book(n_dates=30, per_date=6)
    b = pr.blind(v, d, seed=3)
    keys = pd.to_datetime(pd.Series(d)).dt.normalize().to_numpy()
    for k in np.unique(keys):
        m = keys == k
        assert np.allclose(np.sort(v[m]), np.sort(b[m]))
    assert not np.allclose(v, b)


def test_staged_scoring_stops_at_the_first_failure() -> None:
    calls: list[str] = []

    def score(block: str) -> dict:
        calls.append(block)
        return {"stat": {"disc": -1.0, "val": 2.0, "conf": 2.0}[block]}

    out = pr.staged_scoring(["disc", "val", "conf"], score, lambda r: r["stat"] > 0)
    assert calls == ["disc"]
    assert out["stopped_at"] == "disc" and not out["passed"]
    assert set(out["blocks"]) == {"disc"}


@pytest.mark.parametrize("n_t, n_c, sd", [(50, 500, 0.1), (200, 2000, 0.05), (16, 1800, 0.3)])
def test_mde_matches_closed_form(n_t: int, n_c: int, sd: float) -> None:
    from scipy.stats import norm

    ref = (norm.ppf(0.975) + norm.ppf(0.8)) * sd * np.sqrt(1 / n_t + 1 / n_c)
    assert pr.min_detectable_effect(n_t, n_c, sd) == pytest.approx(ref)
    assert pr.min_detectable_effect(n_t, n_c, sd, design_effect=4.0) == pytest.approx(2 * ref)


def test_rate_ratio_flags_a_16_event_tail_trial_as_unpowered() -> None:
    # 5.8% base tail rate, 16 treated: only a ratio above 2 could be detected
    assert pr.min_detectable_rate_ratio(0.058, 16) > 2.0


@pytest.mark.parametrize("shift, small", [(0.0, False), (0.05, True)])
def test_pvalue_tracks_the_interval(shift: float, small: bool) -> None:
    v, d = _book(n_dates=60, per_date=4, seed=5)
    v = v - v.mean() + shift
    p = pr.date_clustered_pvalue(v, d, np.mean, n_boot=1000)
    ci = pr.date_clustered_ci(v, d, np.mean, n_boot=1000)
    assert (p < 0.05) == small == ci.excludes_zero


def test_lond_alphas_sum_below_target_without_discoveries() -> None:
    total = sum(pr.lond_alpha(i, 0, target=0.05) for i in range(1, 20001))
    assert total <= 0.05
    assert pr.lond_alpha(10, 2) == pytest.approx(3 * pr.lond_alpha(10, 0))


def test_block_ledger_marks_descendants_dirty_and_others_clean(tmp_path) -> None:
    led = tmp_path / "blocks.csv"
    pr.log_block_view(
        led,
        panel="hedged_hold",
        period="2025-26",
        outcome_family="tail",
        feature_family="own_history",
        viewed_by="1,621",
    )
    pr.log_block_view(
        led,
        panel="hedged_hold",
        period="2020-24",
        outcome_family="*",
        feature_family="*",
        viewed_by="pre-ledger",
        kind="descriptive",
    )
    clean, _ = pr.block_is_clean(
        led,
        panel="hedged_hold",
        period="2025-26",
        outcome_family="tail",
        feature_family="own_history",
    )
    assert not clean
    clean, _ = pr.block_is_clean(
        led,
        panel="hedged_hold",
        period="2025-26",
        outcome_family="tail",
        feature_family="filing_text",
    )
    assert clean
    clean, hits = pr.block_is_clean(
        led, panel="hedged_hold", period="2020-24", outcome_family="anything", feature_family="new"
    )
    assert not clean and len(hits) == 1


def test_freeze_records_repository_relative_paths() -> None:
    root = Path(pr.__file__).resolve().parents[2]
    inside = root / "research" / "_template" / "prereg.md"
    assert pr._repo_relative(inside) == "research/_template/prereg.md"
    assert pr._recorded_file("research/_template/prereg.md") == inside


@pytest.mark.parametrize("outside", ["elsewhere/x.md", "/tmp/elsewhere/x.md"])
def test_paths_outside_the_repository_are_kept_as_given(outside: str) -> None:
    assert pr._repo_relative(Path(outside).resolve()).endswith("elsewhere/x.md")
    assert pr._recorded_file(outside) == Path(outside)
