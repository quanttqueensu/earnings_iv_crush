"""
test_forward_report.py
Forward-report statistics on a synthetic ledger: bases, factors, and honesty gates.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from scripts.forward_report import (
    MIN_TRADES_FOR_CI,
    MIN_TRADES_FOR_DECISION,
    N_BOOT,
    SEED,
    book_stats,
    clustered_ci,
    derived_periods_per_year,
    reconciliation_stats,
)


def _ledger(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n, freq="7B")
    return pd.DataFrame(
        {
            "return_on_margin": rng.normal(0.01, 0.05, n),
            "exit_date": dates,
        }
    )


def test_empty_book_reports_no_trades():
    lines = book_stats(pd.DataFrame(), "empty")
    assert any("No completed trades" in line for line in lines)
    assert not any("Sharpe" in line for line in lines)


def test_small_book_withholds_ci():
    lines = book_stats(_ledger(MIN_TRADES_FOR_CI - 1), "small")
    joined = "\n".join(lines)
    assert "CI withheld" in joined
    assert "per trade" in joined


def test_forward_report_withholds_profitability_decision_until_40_trades():
    lines = book_stats(_ledger(MIN_TRADES_FOR_DECISION - 1), "small")
    assert "observational only" in "\n".join(lines)


def test_forward_report_reports_premium_return_when_canonical_fields_exist():
    led = _ledger(MIN_TRADES_FOR_CI)
    led["entry_credit"] = 100.0
    led["exit_value"] = 95.0
    led["pnl"] = 4.0
    joined = "\n".join(book_stats(led, "book"))
    assert "return on premium" in joined


def test_annualisation_factor_comes_from_cadence_not_252():
    # 30 trades at weekly-ish spacing: the honest factor is ~52/1.4, never 252.
    lines = book_stats(_ledger(30), "book")
    joined = "\n".join(lines)
    assert "sqrt(252)" not in joined
    assert "from the book's own cadence" in joined
    assert "(secondary)" in joined


def test_per_trade_sharpe_matches_direct_computation():
    led = _ledger(40)
    rom = led["return_on_margin"]
    expected = rom.mean() / rom.std()
    joined = "\n".join(book_stats(led, "book"))
    reported = float(joined.split("Sharpe: ")[1].split(" ")[0])
    assert reported == pytest.approx(expected, abs=5e-4)


# ── date-clustered intervals ─────────────────────────────────────────────────


def _iid_percentile_ci(
    x: np.ndarray, stat: Callable[[np.ndarray], float], n_boot: int = N_BOOT, seed: int = SEED
) -> tuple[float, float]:
    """Independent reference: the textbook i.i.d. percentile bootstrap over trades."""
    rng = np.random.default_rng(seed)
    draws = np.array(
        [stat(x[rng.choice(len(x), size=len(x), replace=True)]) for _ in range(n_boot)]
    )
    return float(np.nanpercentile(draws, 2.5)), float(np.nanpercentile(draws, 97.5))


def _sr(x: np.ndarray) -> float:
    return float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else float("nan")


@pytest.mark.parametrize("stat", [np.mean, _sr], ids=["mean", "sharpe"])
@pytest.mark.parametrize("n, seed", [(12, 0), (25, 1), (60, 2)])
def test_one_trade_per_date_reduces_to_the_iid_bootstrap(stat, n: int, seed: int) -> None:
    """With singleton clusters, resampling dates is resampling trades, draw for draw."""
    x = np.random.default_rng(seed).normal(0.01, 0.05, n)
    keys = pd.bdate_range("2026-01-05", periods=n).strftime("%Y-%m-%d").to_numpy()
    assert clustered_ci(x, keys, stat) == pytest.approx(_iid_percentile_ci(x, stat), abs=1e-12)


@pytest.mark.parametrize("k", [2, 3, 5])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_perfectly_correlated_trades_within_a_date_widen_the_interval(k: int, seed: int) -> None:
    """k identical trades per date carry one date's information, not k trades' worth.

    The i.i.d. bootstrap treats them as independent and narrows the interval by about
    sqrt(k); the clustered interval must stay near the one-trade-per-date width.
    """
    n_dates = 20
    base = np.random.default_rng(seed).normal(0.01, 0.05, n_dates)
    x = np.repeat(base, k)
    days = pd.bdate_range("2026-01-05", periods=n_dates).strftime("%Y-%m-%d").to_numpy()
    keys = np.repeat(days, k)
    lo_c, hi_c = clustered_ci(x, keys, np.mean)
    lo_i, hi_i = _iid_percentile_ci(x, np.mean)
    lo_1, hi_1 = clustered_ci(base, days, np.mean)
    assert hi_c - lo_c > hi_i - lo_i
    assert (hi_c - lo_c) / (hi_i - lo_i) > 0.75 * np.sqrt(k)
    assert hi_c - lo_c == pytest.approx(hi_1 - lo_1, rel=0.25)


def test_report_clusters_on_announcement_dates_and_labels_the_basis() -> None:
    led = _ledger(12)
    led["exit_date"] = np.repeat(pd.bdate_range("2026-01-05", periods=6, freq="7B"), 2)
    joined = "\n".join(book_stats(led, "book"))
    assert "across 6 announcement date(s)" in joined
    assert "date-clustered bootstrap, 5,000 draws over 6 dates, seed 0" in joined
    assert "per trade" in joined.split("95% CI, Sharpe")[1]


def test_too_few_dates_withholds_the_interval_even_with_many_trades() -> None:
    led = _ledger(MIN_TRADES_FOR_DECISION)
    led["exit_date"] = pd.Timestamp("2026-01-05")
    joined = "\n".join(book_stats(led, "book"))
    assert "CI withheld" in joined
    assert "Annualised Sharpe withheld" in joined


@pytest.mark.parametrize(
    "dates, expected",
    [
        (["2026-01-05"] * 4, None),
        (["2026-01-05", "2026-01-12"], None),  # span below the minimum
        (list(pd.date_range("2026-01-05", periods=27, freq="14D")), 27 * 365.25 / 364),
    ],
)
def test_periods_per_year_is_derived_or_withheld_never_defaulted(dates, expected) -> None:
    got = derived_periods_per_year(pd.Series(pd.to_datetime(dates)))
    if expected is None:
        assert got is None
    else:
        assert got is not None and got[0] == pytest.approx(expected)


def test_reconciliation_reports_stop_gap_slippage_when_triggered():
    recon = pd.DataFrame(
        {
            "realised_round_trip_cost": [0.10, 0.14, 0.09],
            "over_breakeven": [False, True, False],
            "slippage_vs_mid_ps": [0.01, 0.03, 0.02],
            "stop_was_triggered": [False, True, True],
            "stop_gap_slippage_ps": [0.0, 0.05, 0.01],
        }
    )
    joined = "\n".join(reconciliation_stats(recon))
    assert "Stop triggered on 2 exit(s)" in joined
    assert "+0.0300" in joined  # mean gap slippage over the triggered exits only


def test_reconciliation_empty_and_filled():
    assert any("No exits" in line for line in reconciliation_stats(pd.DataFrame()))
    recon = pd.DataFrame(
        {
            "realised_round_trip_cost": [0.10, 0.14],
            "over_breakeven": [False, True],
            "slippage_vs_mid_ps": [0.01, 0.03],
            "stop_was_triggered": [False, False],
            "stop_gap_slippage_ps": [0.0, 0.0],
        }
    )
    joined = "\n".join(reconciliation_stats(recon))
    assert "break-even" in joined
    assert "Stop never triggered" in joined


# ── harness liveness ─────────────────────────────────────────────────────────


def _heartbeat(days_ago: int, candidates: int, priced: int) -> pd.DataFrame:
    asof = pd.Timestamp.today().normalize() - pd.Timedelta(days=days_ago)
    return pd.DataFrame(
        [
            {
                "asof": asof,
                "n_candidates": candidates,
                "n_priced": priced,
                "n_gated": 0,
                "n_entered": 0,
            }
        ]
    )


def _health(monkeypatch, hb: pd.DataFrame) -> str:
    import scripts.forward_report as fr

    monkeypatch.setattr(fr.paper_book, "load_heartbeat", lambda *a, **k: hb)
    return "\n".join(fr.harness_health())


def test_no_heartbeat_ever_alarms(monkeypatch):
    """An empty book with no heartbeat must not read as a patient harness."""
    assert "ALARM" in _health(monkeypatch, pd.DataFrame())


def test_candidates_seen_none_priced_alarms(monkeypatch):
    """The six-week silent failure: every candidate dropped on a data fault."""
    out = _health(monkeypatch, _heartbeat(days_ago=0, candidates=6, priced=0))
    assert "ALARM" in out
    assert "failed to price" in out


def test_stale_pass_alarms(monkeypatch):
    """A scheduled task that stopped firing is a fault, not an empty market."""
    out = _health(monkeypatch, _heartbeat(days_ago=21, candidates=4, priced=4))
    assert "ALARM" in out
    assert "21 days ago" in out


def test_quiet_day_does_not_alarm(monkeypatch):
    """Zero candidates on a day with no announcements is healthy, not a fault."""
    assert "ALARM" not in _health(monkeypatch, _heartbeat(days_ago=0, candidates=0, priced=0))


def test_healthy_pass_does_not_alarm(monkeypatch):
    """Candidates seen and priced is the normal state; no false positive."""
    assert "ALARM" not in _health(monkeypatch, _heartbeat(days_ago=0, candidates=5, priced=5))
