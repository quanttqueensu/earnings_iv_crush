"""
test_term_gate_regressions.py
Regressions for the panel term gate: calendar-bounded trailing window, the
nearest-expiry event statistic, and the rejection accounting.
"""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.strategy.filters import passes_term_filter_panel


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
