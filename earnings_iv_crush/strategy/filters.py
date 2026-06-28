"""
filters.py
The two cross-sectional filters that define a tradeable event.

This selection step is the strategy's edge: the unfiltered trade (Agent 0)
does not survive costs, so an event must pass both gates to be traded.
"""

from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from ..config import STRATEGY

# Sourced from the central config (see ``earnings_iv_crush/config.py``).
IMPLIED_FAIR_RATIO = STRATEGY.implied_fair_ratio
USE_MOVE_GATE = STRATEGY.use_move_gate  # whether Gate 1 (move filter) is applied
TERM_SPREAD_PCTL = STRATEGY.term_spread_pctl
TRAILING_WINDOW = STRATEGY.trailing_window  # trailing days (panel form) or events (legacy form)
TERM_MIN_PERIODS = STRATEGY.term_min_periods  # min daily obs before the panel gate will fire


# ── Gate 1: rich implied move ────────────────────────────────────────────────


def passes_move_filter(implied_move, fair_move, ratio=IMPLIED_FAIR_RATIO):
    """True when the implied event move is at least ``ratio`` times the fair move.

    Parameters
    ----------
    implied_move, fair_move : float or Series
        The market-implied event move and the regression fair move.
    ratio : float
        Required richness multiple. Defaults to ``IMPLIED_FAIR_RATIO`` (1.20).

    Returns
    -------
    bool or Series
        Whether ``implied_move >= ratio * fair_move``.
    """
    return implied_move >= ratio * fair_move


# ── Gate 2: steep term structure ─────────────────────────────────────────────


def passes_term_filter(events: pd.DataFrame, pctl=TERM_SPREAD_PCTL, window=TRAILING_WINDOW):
    """LEGACY: term spread above its trailing percentile over the EVENTS frame.

    Rolls over `events["iv_term_spread"]` by row, so it needs `window` prior
    events to warm up and assumes the frame is one name ordered by date. Correct
    on the dense synthetic path; on a sparse, multi-name real sample it mixes
    names and rejects everything until 30 events exist - use
    `passes_term_filter_panel` there instead.
    """
    threshold = events["iv_term_spread"].rolling(window).quantile(pctl)
    return events["iv_term_spread"] > threshold


def passes_term_filter_panel(
    events: pd.DataFrame,
    panel: pd.DataFrame,
    pctl=TERM_SPREAD_PCTL,
    window_days=TRAILING_WINDOW,
    min_periods=TERM_MIN_PERIODS,
    asof_offset_days=1,
) -> pd.Series:
    """Per-name trailing-DAY percentile gate over a 30-day distribution.

    For each event the threshold is the `pctl` quantile of that ticker's daily
    `iv_term_spread` over the `window_days` trading days strictly before entry
    (entry = announce_date - `asof_offset_days` business days). The event passes
    when its own `iv_term_spread` exceeds that threshold. Events with fewer than
    `min_periods` daily observations in the window are rejected.

    Unlike the legacy form, each event carries its own trailing window, so there
    is no global warm-up and names are never mixed.

    Parameters
    ----------
    panel : DataFrame with `ticker`, `date`, `iv_term_spread` (one row per
        ticker per trading day).
    """
    if panel is None or len(panel) == 0:
        return pd.Series(False, index=events.index)
    p = panel.copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p.dropna(subset=["iv_term_spread"]).sort_values("date")
    by_ticker = {t: g for t, g in p.groupby("ticker")}

    flags = []
    for _, ev in events.iterrows():
        entry = pd.Timestamp(pd.to_datetime(ev["announce_date"])) - BDay(asof_offset_days)
        g = by_ticker.get(ev["ticker"])
        if g is None:
            flags.append(False)
            continue
        hist = g[g["date"] < entry].tail(window_days)
        if len(hist) < min_periods:
            flags.append(False)
            continue
        threshold = hist["iv_term_spread"].quantile(pctl)
        flags.append(bool(ev["iv_term_spread"] > threshold))
    return pd.Series(flags, index=events.index)


# ── Combined selection ───────────────────────────────────────────────────────


def select_events(
    events: pd.DataFrame,
    fair_move,
    ratio=IMPLIED_FAIR_RATIO,
    pctl=TERM_SPREAD_PCTL,
    window=TRAILING_WINDOW,
    *,
    use_move_gate: bool = USE_MOVE_GATE,
    term_panel: pd.DataFrame | None = None,
    window_days=TRAILING_WINDOW,
    min_periods=TERM_MIN_PERIODS,
    asof_offset_days=1,
) -> pd.DataFrame:
    """Return only the events that pass the active filters.

    Gate 1 (optional): implied event move >= ``ratio`` x the fair move, applied
    only when ``use_move_gate`` is true. Gate 2: the term spread is steep versus
    its recent history - the per-name trailing-day percentile when ``term_panel``
    is supplied (preferred), else the legacy events-rolling percentile.

    Parameters
    ----------
    events : pd.DataFrame
        Must hold ``implied_move`` and ``iv_term_spread`` (and ``ticker`` /
        ``announce_date`` when ``term_panel`` is used).
    fair_move : sequence
        Predicted fair move per event, aligned to ``events`` by position.
    ratio, pctl, window : see the module constants.
    use_move_gate : bool
        Whether Gate 1 is applied. Defaults to ``USE_MOVE_GATE`` (the config
        value, ``False`` in the term-only baseline). When false the move filter
        is a pass-through and selection rests on the term gate alone.
    term_panel : pd.DataFrame, optional
        Per-name daily term-spread panel; switches Gate 2 to the trailing-day form.
    window_days, min_periods, asof_offset_days :
        Panel-gate parameters (ignored by the legacy gate).

    Returns
    -------
    pd.DataFrame
        The subset of ``events`` that clears the active gates.
    """
    fair = pd.Series(list(fair_move), index=events.index)
    if use_move_gate:
        move_ok = passes_move_filter(events["implied_move"], fair, ratio)
    else:
        move_ok = pd.Series(True, index=events.index)
    if term_panel is not None:
        term_ok = passes_term_filter_panel(
            events, term_panel, pctl, window_days, min_periods, asof_offset_days
        )
    else:
        term_ok = passes_term_filter(events, pctl, window)
    mask = (move_ok & term_ok).fillna(False)
    return events[mask]
