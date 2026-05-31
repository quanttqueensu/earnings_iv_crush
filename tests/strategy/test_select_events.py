"""Tests for filters.select_events: the two gates combined, with boundaries."""
from __future__ import annotations

import pandas as pd

from src.strategy import filters


def _events(term_spreads, implied_moves):
    return pd.DataFrame({
        "iv_term_spread": term_spreads,
        "implied_move": implied_moves,
    })


def test_keeps_only_rows_passing_both_gates():
    # Flat baseline then a spike, so only the spike clears its trailing 75th pctl.
    term = [0.03, 0.03, 0.03, 0.03, 0.03, 0.20]
    implied = [0.10] * 6
    fair = [0.05] * 6                              # implied/fair = 2.0 >= 1.20 for all
    ev = _events(term, implied)

    out = filters.select_events(ev, fair, window=5)
    # Move gate passes for all; term gate (spread > trailing 75th pctl) only the spike.
    assert list(out.index) == [5]


def test_move_gate_boundary_is_inclusive():
    ev = _events([0.20, 0.20], [0.06, 0.05])
    fair = [0.05, 0.05]      # 1.20*fair = 0.06; row0 implied==0.06 passes, row1 0.05 fails
    # Make both clear term-spread passers by using a tiny window and a rising series.
    ev = _events([0.01, 0.50], [0.06, 0.05])
    out = filters.select_events(ev, [0.05, 0.05], window=1, pctl=0.5)
    # Row1 fails the move gate (0.05 < 0.06) regardless of term gate.
    assert 1 not in out.index


def test_term_gate_is_strict_greater_than():
    # All term spreads equal -> nothing exceeds the percentile -> empty.
    ev = _events([0.10, 0.10, 0.10, 0.10], [0.10] * 4)
    out = filters.select_events(ev, [0.01] * 4, window=2)
    assert out.empty


def test_returns_subset_of_input():
    ev = _events([0.01, 0.02, 0.03, 0.50], [0.10] * 4)
    out = filters.select_events(ev, [0.05] * 4, window=2)
    assert set(out.index).issubset(set(ev.index))
    assert list(out.columns) == list(ev.columns)
