"""Tests for the per-name trailing-day term gate (passes_term_filter_panel)."""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.strategy.filters import passes_term_filter_panel, select_events


def _panel(ticker, dates, spreads):
    return pd.DataFrame(
        {"ticker": ticker, "date": pd.to_datetime(dates), "iv_term_spread": spreads}
    )


def _daily_panel(ticker, end, n, level):
    """n trading days of flat-ish term spread ending before `end`."""
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    return _panel(ticker, dates, [level] * n)


def test_event_above_trailing_pctl_passes_and_below_fails():
    # AAA history sits around 0.10; BBB around 0.50.
    panel = pd.concat(
        [
            _daily_panel("AAA", "2024-06-06", 25, 0.10),
            _daily_panel("BBB", "2024-06-06", 25, 0.50),
        ],
        ignore_index=True,
    )
    events = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "announce_date": ["2024-06-10", "2024-06-10"],  # entry = 2024-06-07
            "iv_term_spread": [0.30, 0.20],  # AAA spikes, BBB drops
        }
    )
    ok = passes_term_filter_panel(events, panel, asof_offset_days=1, min_periods=15)
    assert list(ok) == [True, False]


def test_too_few_obs_rejected():
    panel = _daily_panel("AAA", "2024-06-06", 5, 0.10)  # only 5 days < min_periods
    events = pd.DataFrame(
        {"ticker": ["AAA"], "announce_date": ["2024-06-10"], "iv_term_spread": [0.99]}
    )
    ok = passes_term_filter_panel(events, panel, min_periods=15)
    assert list(ok) == [False]


def test_only_uses_history_strictly_before_entry():
    # A huge spread ON/after entry must not leak into the name's own threshold.
    dates = list(pd.bdate_range(end="2024-06-06", periods=20)) + [pd.Timestamp("2024-06-07")]
    spreads = [0.10] * 20 + [5.0]  # 06-07 (entry) is huge
    panel = _panel("AAA", dates, spreads)
    events = pd.DataFrame(
        {"ticker": ["AAA"], "announce_date": ["2024-06-10"], "iv_term_spread": [0.30]}
    )
    # Threshold is from the 0.10 history only, so 0.30 passes.
    ok = passes_term_filter_panel(events, panel, asof_offset_days=1, min_periods=15)
    assert list(ok) == [True]


def test_select_events_uses_panel_when_supplied():
    panel = _daily_panel("AAA", "2024-06-06", 25, 0.10)
    events = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "announce_date": ["2024-06-10"],
            "implied_move": [0.06],
            "iv_term_spread": [0.30],
        }
    )
    fair = [0.04]  # 0.06 >= 1.2*0.04 -> move ok
    selected = select_events(events, fair, term_panel=panel, min_periods=15)
    assert len(selected) == 1
    # Without the panel the legacy gate has no warm-up data -> rejects.
    assert len(select_events(events, fair)) == 0
