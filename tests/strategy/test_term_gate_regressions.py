"""
test_term_gate_regressions.py
Regressions for the panel term gate: calendar-bounded trailing window, the
nearest-expiry event statistic, and the rejection accounting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from earnings_iv_crush.strategy.filters import expanding_gate_rank, passes_term_filter_panel


def _panel(ticker, dates, spreads):
    return pd.DataFrame(
        {"ticker": ticker, "date": pd.to_datetime(dates), "iv_term_spread": spreads}
    )


def test_window_is_calendar_bounded_not_row_bounded():
    # 25 panel rows exist, but they end ~60 business days before entry. The old
    # .tail(window_days) reached back to them and gated on stale history; the
    # calendar-bounded window finds < min_periods obs and rejects instead.
    stale_dates = pd.bdate_range(end="2024-03-15", periods=25)
    panel = _panel("AAA", stale_dates, [0.10] * 25)
    events = pd.DataFrame(
        {"ticker": ["AAA"], "announce_date": ["2024-06-10"], "iv_term_spread": [0.99]}
    )
    stats: dict = {}
    ok = passes_term_filter_panel(events, panel, min_periods=15, stats_out=stats)
    assert list(ok) == [False]
    assert stats["below_min_periods"] == 1


def test_gate_prefers_nearest_expiry_statistic_when_present():
    dates = pd.bdate_range(end="2024-06-06", periods=25)
    panel = _panel("AAA", dates, [0.10] * 25)
    # Executed-expiry spread is inflated (0.99) but the panel-consistent
    # nearest-expiry statistic is below the trailing threshold: must reject.
    events = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "announce_date": ["2024-06-10"],
            "iv_term_spread": [0.99],
            "iv_term_spread_nearest": [0.05],
        }
    )
    ok = passes_term_filter_panel(events, panel, min_periods=15)
    assert list(ok) == [False]
    # And passes when the consistent statistic clears the threshold.
    events.loc[0, "iv_term_spread_nearest"] = 0.30
    assert list(passes_term_filter_panel(events, panel, min_periods=15)) == [True]


def test_missing_nearest_statistic_is_counted_not_silent():
    dates = pd.bdate_range(end="2024-06-06", periods=25)
    panel = _panel("AAA", dates, [0.10] * 25)
    events = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "announce_date": ["2024-06-10"],
            "iv_term_spread": [0.30],
            "iv_term_spread_nearest": [float("nan")],
        }
    )
    stats: dict = {}
    ok = passes_term_filter_panel(events, panel, min_periods=15, stats_out=stats)
    assert list(ok) == [False]
    assert stats["no_event_stat"] == 1


def test_stats_out_accounts_for_every_event():
    dates = pd.bdate_range(end="2024-06-06", periods=25)
    panel = _panel("AAA", dates, [0.10] * 25)
    events = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "ZZZ"],
            "announce_date": ["2024-06-10"] * 3,
            "iv_term_spread": [0.30, 0.01, 0.30],
        }
    )
    stats: dict = {}
    passes_term_filter_panel(events, panel, min_periods=15, stats_out=stats)
    assert sum(stats.values()) == len(events)
    assert stats["no_panel_history"] == 1  # ZZZ
    assert stats["passed"] == 1 and stats["below_threshold"] == 1


# ── expanding gate: the frozen selector ──────────────────────────────────────


def test_expanding_gate_rank_matches_the_quantile_it_reproduces():
    """``rank >= p`` must equal ``value >= np.quantile(prior, p)`` at every p.

    The rank column exists so a percentile sweep is one comparison rather than a
    re-scan. If it ever stops agreeing with the quantile it stands in for, every
    swept result silently moves. The empirical fraction ``(prior <= v).mean()`` is
    the wrong convention here: it places the value at ``p*n`` where ``np.quantile``
    places it at ``p*(n-1)``.
    """
    rng = np.random.default_rng(11)
    n = 300
    values = rng.normal(0.1, 0.05, n)
    dates = np.sort(pd.to_datetime(rng.choice(pd.date_range("2016-01-01", periods=1200), n)))

    rank = expanding_gate_rank(values, dates, min_hist=25)

    for p in (0.50, 0.75, 0.80, 0.90, 1.00):
        for i in range(n):
            prior = values[dates < dates[i]]
            prior = prior[np.isfinite(prior)]
            if len(prior) < 25:
                assert np.isnan(rank[i])
                continue
            expected = values[i] >= np.quantile(prior, p)
            got = (rank[i] if np.isfinite(rank[i]) else -9.0) >= p
            assert got == expected, f"p={p} event={i}"


def test_expanding_gate_is_strictly_causal():
    """Same-day events must not enter one another's threshold, and later events never do."""
    rng = np.random.default_rng(3)
    n = 120
    values = rng.normal(0.1, 0.05, n)
    dates = np.repeat(pd.to_datetime(pd.date_range("2020-01-01", periods=n // 4)), 4)

    rank = expanding_gate_rank(values, dates, min_hist=10)

    # Rewriting every value dated on or after event i must not change event i's rank.
    checked = 0
    for i in np.flatnonzero(np.isfinite(rank)):
        tampered = values.copy()
        tampered[dates >= dates[i]] = 99.0
        tampered[i] = values[i]
        again = expanding_gate_rank(tampered, dates, min_hist=10)
        assert again[i] == rank[i], f"event {i} moved when only same-day and later events changed"
        checked += 1
    assert checked > 0, "no event had enough history to test causality on"


def test_expanding_gate_withholds_on_thin_history():
    """Below ``min_hist`` prior events the gate returns NaN rather than admitting."""
    values = np.linspace(0.0, 1.0, 40)
    dates = pd.to_datetime(pd.date_range("2021-01-01", periods=40))
    rank = expanding_gate_rank(values, dates, min_hist=25)
    assert np.isnan(rank[:25]).all()
    assert np.isfinite(rank[25:]).all()
