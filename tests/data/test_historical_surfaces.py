"""Tests for the offline historical-surface pipeline and the on-disk cache.

Everything runs against injected synthetic providers and a temp directory, so no
network or real data access is involved.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data import cache, historical_surfaces as hs


def _rows(expiry, strikes, ivs, mids):
    out = []
    for k, iv, m in zip(strikes, ivs, mids):
        for right in ("C", "P"):
            out.append({"expiry": pd.Timestamp(expiry), "strike": float(k),
                        "right": right, "bid": m - 0.05, "ask": m + 0.05,
                        "iv": iv, "open_interest": 100})
    return out


def _fetch_chain(ticker, asof):
    front = _rows("2026-06-05", [95, 100, 105], [0.5, 0.5, 0.5], [4, 3, 2])
    back = _rows("2026-07-03", [95, 100, 105], [0.4, 0.4, 0.4], [5, 4, 3])
    return pd.DataFrame(front + back)


def _spot(ticker, asof):
    return 100.0


# --- surface panel -----------------------------------------------------------

def test_build_surface_panel_shape_and_features():
    panel = hs.build_surface_panel(
        ["AAPL"], ["2026-05-28", "2026-05-29"], _fetch_chain, _spot
    )
    assert list(panel.columns) == hs.PANEL_COLUMNS
    assert len(panel) == 2
    assert (panel["front_atm_iv"] == 0.5).all()
    assert (panel["back_atm_iv"] == 0.4).all()
    assert panel["iv_term_spread"].iloc[0] == pytest.approx(0.1)
    assert panel["implied_move"].iloc[0] == pytest.approx(0.06)


def test_build_surface_panel_skips_missing_chains():
    def empty_chain(ticker, asof):
        return pd.DataFrame(columns=["expiry", "strike", "right", "bid", "ask",
                                     "iv", "open_interest"])
    panel = hs.build_surface_panel(["AAPL"], ["2026-05-29"], empty_chain, _spot)
    assert panel.empty
    assert list(panel.columns) == hs.PANEL_COLUMNS


# --- join --------------------------------------------------------------------

def test_join_earnings_to_surfaces_picks_pre_event_snapshot():
    panel = hs.build_surface_panel(
        ["AAPL"], ["2026-05-28", "2026-05-29"], _fetch_chain, _spot
    )
    calendar = pd.DataFrame({"ticker": ["AAPL"], "announce_date": ["2026-06-01"]})
    joined = hs.join_earnings_to_surfaces(
        calendar, panel, realised_move_fn=lambda t, d: 0.08
    )
    assert len(joined) == 1
    row = joined.iloc[0]
    assert row["realised_move"] == pytest.approx(0.08)
    assert row["front_atm_iv"] == pytest.approx(0.5)
    # The entry snapshot is the last on/before announce - 1 BDay (2026-05-29).
    assert pd.Timestamp(row["date"]) == pd.Timestamp("2026-05-29")


def test_join_skips_events_without_prior_surface():
    panel = hs.build_surface_panel(["AAPL"], ["2026-06-10"], _fetch_chain, _spot)
    calendar = pd.DataFrame({"ticker": ["AAPL"], "announce_date": ["2026-06-01"]})
    joined = hs.join_earnings_to_surfaces(calendar, panel, lambda t, d: 0.05)
    assert joined.empty   # only surface is after the event -> nothing to enter on


# --- cache -------------------------------------------------------------------

def test_cache_round_trip(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})
    assert not cache.has_frame("panel", tmp_path)
    cache.write_frame(df, "panel", tmp_path)
    assert cache.has_frame("panel", tmp_path)
    loaded = cache.read_frame("panel", tmp_path)
    pd.testing.assert_frame_equal(loaded.reset_index(drop=True), df)


def test_cache_missing_key_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cache.read_frame("nope", tmp_path)
