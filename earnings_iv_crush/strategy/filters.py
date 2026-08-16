"""
filters.py
The two cross-sectional filters that define a tradeable event.

This selection step is the strategy's edge: the unfiltered trade (Agent 0)
does not survive costs, so an event must pass both gates to be traded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from ..config import STRATEGY
from ..frozen import SPEC

# Sourced from the central config (see ``earnings_iv_crush/config.py``).
IMPLIED_FAIR_RATIO = STRATEGY.implied_fair_ratio
USE_MOVE_GATE = STRATEGY.use_move_gate  # whether Gate 1 (move filter) is applied
TERM_SPREAD_PCTL = STRATEGY.term_spread_pctl
TRAILING_WINDOW = STRATEGY.trailing_window  # trailing days (panel form) or events (legacy form)
TERM_MIN_PERIODS = STRATEGY.term_min_periods  # min daily obs before the panel gate will fire
MIN_HIST = SPEC.min_hist  # prior events required before the expanding gate will fire

#: Rank assigned to an event below every prior observation. The gate admits at every
#: percentile including zero, so this must sort below the lowest admissible cut rather
#: than tie with it.
BELOW_ALL = -1.0


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
    stats_out: dict | None = None,
    stat_col: str | None = None,
) -> pd.Series:
    """Per-name trailing-DAY percentile gate over a 30-day distribution.

    For each event the threshold is the `pctl` quantile of that ticker's daily
    `iv_term_spread` over the `window_days` TRADING DAYS strictly before entry
    (entry = announce_date - `asof_offset_days` business days). The window is
    calendar-bounded, not row-bounded: a panel with gaps contributes fewer
    observations rather than silently reaching further back in time. The event
    passes when its own `iv_term_spread` exceeds that threshold. Events with
    fewer than `min_periods` daily observations in the window are rejected.

    Unlike the legacy form, each event carries its own trailing window, so there
    is no global warm-up and names are never mixed.

    Parameters
    ----------
    panel : DataFrame with `ticker`, `date`, `iv_term_spread` (one row per
        ticker per trading day).
    stats_out : dict, optional
        When supplied, filled with rejection accounting: ``no_panel_history``
        (ticker absent from the panel), ``below_min_periods`` (window too
        sparse), ``below_threshold`` and ``passed`` - so gate attrition is
        visible rather than silently folded into "did not pass".
    stat_col : str, optional
        Events column holding the statistic to gate. Defaults to
        ``iv_term_spread_nearest`` when present, else ``iv_term_spread``. The
        panel distribution is built from nearest-expiry spreads, so the event
        statistic must use the same definition; the executed-expiry spread runs
        systematically above it and inflates the pass rate.
    """
    if stat_col is None:
        stat_col = (
            "iv_term_spread_nearest"
            if "iv_term_spread_nearest" in events.columns
            else "iv_term_spread"
        )
    counts = {
        "no_panel_history": 0,
        "below_min_periods": 0,
        "no_event_stat": 0,
        "below_threshold": 0,
        "passed": 0,
    }
    if panel is None or len(panel) == 0:
        if stats_out is not None:
            counts["no_panel_history"] = len(events)
            stats_out.update(counts)
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
            counts["no_panel_history"] += 1
            flags.append(False)
            continue
        window_start = entry - BDay(window_days)
        hist = g[(g["date"] < entry) & (g["date"] >= window_start)]
        if len(hist) < min_periods:
            counts["below_min_periods"] += 1
            flags.append(False)
            continue
        stat = ev.get(stat_col)
        if stat is None or stat != stat:
            counts["no_event_stat"] += 1
            flags.append(False)
            continue
        threshold = hist["iv_term_spread"].quantile(pctl)
        passed = bool(stat > threshold)
        counts["passed" if passed else "below_threshold"] += 1
        flags.append(passed)
    if stats_out is not None:
        stats_out.update(counts)
    return pd.Series(flags, index=events.index)


# ── Gate 2, expanding form: the frozen selector ──────────────────────────────


def expanding_gate_rank(
    values: np.ndarray, dates: np.ndarray, min_hist: int = MIN_HIST
) -> np.ndarray:
    """The largest percentile at which the frozen term gate would still admit each event.

    This is the frozen specification's selection rule. The gate keeps event ``i`` when
    ``values[i] >= quantile(prior, p)``, where ``prior`` is every event announcing
    strictly earlier. Since ``np.quantile`` is piecewise linear and increasing in ``p``,
    that condition holds exactly when ``p`` is at or below the point where the
    interpolated quantile curve passes through ``values[i]``. Returning that crossing
    point makes ``rank >= p`` identical to the gate at every ``p``, so a sweep over the
    percentile grid becomes a comparison against one stored column.

    The window is expanding rather than fixed, and strictly causal: only events dated
    before event ``i`` enter its threshold. Using the full-sample percentile instead is
    look-ahead, and on this book it was worth roughly 0.05 of per-trade Sharpe on its own.

    A plain empirical fraction ``(prior <= v).mean()`` is *not* identical: it places the
    value at index ``p*n`` where ``np.quantile`` places it at ``p*(n-1)``, and on this
    book the difference admits fourteen extra events at ``p=0.80``. The distinction is
    the difference between reproducing the gate and reproducing something near it.

    Parameters
    ----------
    values : ndarray
        The gated statistic per event, normally the front-minus-back term spread.
    dates : ndarray
        Announcement date per event, same length as ``values``. Comparison is strict,
        so same-day events never enter one another's threshold.
    min_hist : int
        Prior events required before the gate fires at all. Below this the event is
        left as NaN and excluded rather than admitted on a thin threshold.

    Returns
    -------
    ndarray
        Crossing percentile per event in ``[0, 1]``, ``BELOW_ALL`` for an event under
        every prior observation, and NaN where history was insufficient.
    """
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        prior = values[dates < dates[i]]
        prior = prior[np.isfinite(prior)]
        if len(prior) < min_hist or not np.isfinite(values[i]):
            continue
        a = np.sort(prior)
        v = float(values[i])
        n = len(a)
        if v >= a[-1]:
            out[i] = 1.0
            continue
        if v < a[0]:
            out[i] = BELOW_ALL
            continue
        j = int(np.searchsorted(a, v, side="right")) - 1
        if j >= n - 1:
            out[i] = 1.0
            continue
        step = a[j + 1] - a[j]
        frac = (v - a[j]) / step if step > 0 else 0.0
        out[i] = (j + frac) / (n - 1)
    return out


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
