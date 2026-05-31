"""The two cross-sectional filters that define a tradeable event.

This selection step is the strategy's edge: the unfiltered trade (Agent 0)
does not survive costs, so an event must pass both gates to be traded.
"""
from __future__ import annotations

import pandas as pd

IMPLIED_FAIR_RATIO = 1.20
TERM_SPREAD_PCTL = 0.75
TRAILING_WINDOW = 30


def passes_move_filter(implied_move, fair_move, ratio=IMPLIED_FAIR_RATIO):
    """True when the implied event move is at least `ratio` times the fair move."""
    return implied_move >= ratio * fair_move


def passes_term_filter(events: pd.DataFrame, pctl=TERM_SPREAD_PCTL, window=TRAILING_WINDOW):
    """Boolean series: front-minus-back ATM IV above its trailing percentile.

    `events` must hold `iv_term_spread` indexed by date.
    """
    threshold = events["iv_term_spread"].rolling(window).quantile(pctl)
    return events["iv_term_spread"] > threshold


def select_events(events: pd.DataFrame, fair_move,
                  ratio=IMPLIED_FAIR_RATIO, pctl=TERM_SPREAD_PCTL,
                  window=TRAILING_WINDOW) -> pd.DataFrame:
    """Return only the events that pass BOTH filters.

    Gate 1: implied event move >= `ratio` x the fair move (`fair_move` aligned
    to `events` by position). Gate 2: the front-minus-back ATM IV term spread is
    above its trailing `window`-day `pctl`. `events` must hold `implied_move`
    and `iv_term_spread`.
    """
    fair = pd.Series(list(fair_move), index=events.index)
    move_ok = passes_move_filter(events["implied_move"], fair, ratio)
    term_ok = passes_term_filter(events, pctl, window)
    mask = (move_ok & term_ok).fillna(False)
    return events[mask]
