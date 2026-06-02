"""regime.py
Per-event trade-structure selection from the volatility regime.

The strategy switches structure with the regime (spec §2): defined-risk iron
flies when index volatility is elevated, calendars when the term-structure
premium dominates the absolute level mispricing, and the naked short straddle
otherwise. This module consumes the VIX level fetched by ``data.vix`` and the
per-event features to label each event with its structure, without yet routing
the structure economics through the production ledger.

This module implements:

* ``select_structure``   — pick a structure for one event.
* ``assign_structures``  — vectorise the choice across an event frame.

Structure labels: ``"iron_fly"``, ``"calendar"``, ``"straddle"``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import STRATEGY

IRON_FLY = "iron_fly"
CALENDAR = "calendar"
STRADDLE = "straddle"

# Sourced from the central config (see ``src/config.py``).
VIX_DEFENSIVE_THRESHOLD = STRATEGY.vix_defensive_threshold
CALENDAR_MIN_TERM_SPREAD = STRATEGY.calendar_min_term_spread
CALENDAR_DOMINANCE = STRATEGY.calendar_dominance


def select_structure(vix: float, term_spread: float, level_richness: float,
                     vix_threshold: float = VIX_DEFENSIVE_THRESHOLD,
                     calendar_min_term_spread: float = CALENDAR_MIN_TERM_SPREAD,
                     calendar_dominance: float = CALENDAR_DOMINANCE) -> str:
    """
    Choose the trade structure for a single event.

    Decision order:

    1. ``iron_fly`` when ``vix`` exceeds ``vix_threshold`` — cap the tail in a
       high-volatility regime.
    2. ``calendar`` when the term-structure premium is both material
       (``term_spread >= calendar_min_term_spread``) and dominates the level
       mispricing (``term_spread >= calendar_dominance * level_richness``).
    3. ``straddle`` otherwise.

    Parameters
    ----------
    vix : float
        Spot VIX level (index points, e.g. ``18.5``). ``nan`` skips the gate.
    term_spread : float
        Front-week minus back-month ATM IV (volatility points).
    level_richness : float
        Implied-vs-fair move richness, ``implied_move / fair_move - 1`` (a
        dimensionless excess; ``0.20`` is the magnitude-filter trigger).
    vix_threshold : float
        VIX level above which the defined-risk iron fly is used. Defaults to
        ``25.0``.
    calendar_min_term_spread : float
        Minimum term spread to consider a calendar. Defaults to ``0.10``.
    calendar_dominance : float
        Multiple by which the term spread must exceed level richness to favour
        a calendar. Defaults to ``1.0``.

    Returns
    -------
    str
        One of ``"iron_fly"``, ``"calendar"``, ``"straddle"``.
    """
    if np.isfinite(vix) and vix > vix_threshold:
        return IRON_FLY
    if (np.isfinite(term_spread) and term_spread >= calendar_min_term_spread
            and term_spread >= calendar_dominance * max(level_richness, 0.0)):
        return CALENDAR
    return STRADDLE


def assign_structures(events: pd.DataFrame, fair_move,
                      vix_level: float | None = None,
                      vix_col: str = "vix",
                      vix_threshold: float = VIX_DEFENSIVE_THRESHOLD,
                      calendar_min_term_spread: float = CALENDAR_MIN_TERM_SPREAD,
                      calendar_dominance: float = CALENDAR_DOMINANCE) -> pd.Series:
    """
    Label every event with its trade structure.

    Parameters
    ----------
    events : pd.DataFrame
        Per-event frame carrying ``implied_move`` and ``iv_term_spread``; an
        optional ``vix`` column supplies a per-event VIX level.
    fair_move : array-like
        Fair (model-implied) event move aligned to ``events`` by position; used
        with ``implied_move`` to form the level richness.
    vix_level : float, optional
        A single VIX level applied to all events when no ``vix_col`` is present.
        ``None`` and no column means the VIX gate never fires.
    vix_col : str
        Column name holding a per-event VIX level. Defaults to ``"vix"``.
    vix_threshold, calendar_min_term_spread, calendar_dominance :
        See ``select_structure``.

    Returns
    -------
    pd.Series
        Structure label per event, indexed like ``events``.
    """
    fair = pd.Series(np.asarray(fair_move, dtype=float), index=events.index)
    implied = pd.to_numeric(events["implied_move"], errors="coerce")
    richness = implied / fair.replace(0.0, np.nan) - 1.0
    term = pd.to_numeric(events["iv_term_spread"], errors="coerce")

    if vix_col in events.columns:
        vix = pd.to_numeric(events[vix_col], errors="coerce")
    else:
        fill = vix_level if vix_level is not None else float("nan")
        vix = pd.Series(fill, index=events.index)

    labels = [
        select_structure(
            float(vix.iloc[i]) if pd.notna(vix.iloc[i]) else float("nan"),
            float(term.iloc[i]) if pd.notna(term.iloc[i]) else float("nan"),
            float(richness.iloc[i]) if pd.notna(richness.iloc[i]) else 0.0,
            vix_threshold, calendar_min_term_spread, calendar_dominance,
        )
        for i in range(len(events))
    ]
    return pd.Series(labels, index=events.index, name="structure")
