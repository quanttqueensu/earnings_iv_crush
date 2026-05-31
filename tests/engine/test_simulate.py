"""Tests for the synthetic event generator and its optional enrichment."""
from __future__ import annotations

from src.engine.simulate import _SECTORS, simulate_events
from src.strategy import regime
from src.strategy.fair_move_model import FairMoveModel


def test_default_has_no_enrichment_columns():
    ev = simulate_events(n=50, seed=0)
    assert "vix" not in ev.columns
    assert "sector" not in ev.columns


def test_with_vix_adds_defensive_regime():
    ev = simulate_events(n=400, seed=1, with_vix=True, high_vix_frac=0.25)
    assert "vix" in ev.columns
    assert (ev["vix"] > 25).any()       # some defensive (iron-fly) events
    assert (ev["vix"] <= 25).any()       # and some calm ones


def test_with_sectors_uses_known_labels():
    ev = simulate_events(n=80, seed=2, with_sectors=True)
    assert "sector" in ev.columns
    assert set(ev["sector"]).issubset(set(_SECTORS))


def test_regime_mix_is_nontrivial_on_enriched_events():
    ev = simulate_events(n=400, seed=3, with_vix=True)
    model = FairMoveModel().fit(ev, ev["realised_move"])
    labels = regime.assign_structures(ev, model.predict(ev))
    kinds = set(labels)
    assert regime.IRON_FLY in kinds      # high-VIX events route to iron fly
    assert regime.STRADDLE in kinds      # most calm, rich-level events stay naked
