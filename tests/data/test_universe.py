"""Tests for the static backtest universes."""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_iv_crush.data.universe import (
    BROAD_300,
    MEGACAP_50,
    cohort_labels,
    get_universe,
    liquidity_screen,
)


def test_megacap_size_and_uniqueness():
    assert len(MEGACAP_50) == 50
    assert len(set(MEGACAP_50)) == 50


def test_broad_size_and_uniqueness():
    assert len(BROAD_300) == len(set(BROAD_300))
    assert 290 <= len(BROAD_300) <= 360


def test_megacap_subset_of_broad():
    assert set(MEGACAP_50) <= set(BROAD_300)


def test_get_universe():
    assert get_universe("megacap") == MEGACAP_50
    assert get_universe("broad") == BROAD_300
    with pytest.raises(ValueError, match="unknown universe"):
        get_universe("nope")


def test_get_universe_returns_copy():
    u = get_universe("megacap")
    u.append("FAKE")
    assert "FAKE" not in MEGACAP_50


def test_cohort_labels():
    labels = cohort_labels()
    assert set(labels.index) == set(BROAD_300)
    assert (labels.loc[MEGACAP_50] == "megacap").all()
    assert (labels == "broad-only").sum() == len(BROAD_300) - 50


def test_liquidity_screen_annotates_without_dropping():
    tickers = [f"T{i}" for i in range(20)]
    snap = pd.DataFrame({"ticker": tickers[:15], "liquidity": range(1, 16)})
    out = liquidity_screen(tickers, snap, n_deciles=5)
    assert list(out["ticker"]) == tickers  # nothing dropped
    assert out["liquidity"].isna().sum() == 5
    deciles = out["liquidity_decile"].dropna()
    assert deciles.min() == 1 and deciles.max() == 5
