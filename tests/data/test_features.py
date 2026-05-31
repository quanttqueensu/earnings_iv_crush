"""Tests for src.data.features: the pure per-event feature maths."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data import features


def _rows(expiry, strikes, ivs, mids):
    """Build chain rows (a call and a put per strike) for one expiry."""
    out = []
    for k, iv, m in zip(strikes, ivs, mids):
        for right in ("C", "P"):
            out.append({
                "expiry": pd.Timestamp(expiry), "strike": float(k), "right": right,
                "bid": m - 0.05, "ask": m + 0.05, "iv": iv, "open_interest": 100,
            })
    return out


# --- atm_strike --------------------------------------------------------------

def test_atm_strike_picks_closest():
    chain = pd.DataFrame(_rows("2026-06-05", [90, 95, 100, 105], [.5] * 4, [1] * 4))
    assert features.atm_strike(chain, 101.0) == 100.0
    assert features.atm_strike(chain, 103.0) == 105.0  # ties broken toward nearer


# --- nearest_expiries --------------------------------------------------------

def _multi_expiry_chain(expiries):
    rows = []
    for e in expiries:
        rows += _rows(e, [100], [.5], [3.0])
    return pd.DataFrame(rows)


def test_nearest_expiries_front_and_back():
    chain = _multi_expiry_chain(
        ["2026-05-28", "2026-06-05", "2026-06-12", "2026-07-03"]
    )
    front, back = features.nearest_expiries(chain, "2026-06-01")
    assert front == pd.Timestamp("2026-06-05")     # first expiry after announce
    assert back == pd.Timestamp("2026-07-03")       # >= front + 21 days


def test_nearest_expiries_back_falls_back_to_latest():
    chain = _multi_expiry_chain(["2026-06-05", "2026-06-12"])  # gap < 21 days
    front, back = features.nearest_expiries(chain, "2026-06-01")
    assert front == pd.Timestamp("2026-06-05")
    assert back == pd.Timestamp("2026-06-12")        # latest available


def test_nearest_expiries_single_expiry_gives_no_back():
    chain = _multi_expiry_chain(["2026-06-05"])
    front, back = features.nearest_expiries(chain, "2026-06-01")
    assert front == pd.Timestamp("2026-06-05")
    assert back is None


# --- implied_move ------------------------------------------------------------

def test_implied_move_is_atm_straddle_over_spot():
    # ATM strike 100, call mid = put mid = 3.0 -> straddle 6.0, spot 100 -> 0.06.
    chain = pd.DataFrame(_rows("2026-06-05", [95, 100, 105], [.5, .5, .5], [4, 3, 2]))
    mv = features.implied_move(chain, 100.0, pd.Timestamp("2026-06-05"), 100.0)
    assert mv == pytest.approx(0.06)


# --- realised_vol ------------------------------------------------------------

def test_realised_vol_zero_for_flat_prices():
    prices = pd.DataFrame({"close": [100.0] * 10})
    assert features.realised_vol(prices) == 0.0


def test_realised_vol_hand_computed():
    prices = pd.DataFrame({"close": [100, 110, 100, 110, 100]})
    # log returns alternate +/-ln(1.1); std(ddof=1) * sqrt(252).
    r = np.log(1.1)
    expected = np.std([r, -r, r, -r], ddof=1) * np.sqrt(252)
    assert features.realised_vol(prices) == pytest.approx(expected)


def test_realised_vol_uses_only_trailing_window():
    closes = [1.0] * 50 + [100, 120, 90, 130]  # flat then volatile tail
    prices = pd.DataFrame({"close": closes})
    assert features.realised_vol(prices, window=3) > 0  # window catches the tail


# --- skew_25d ----------------------------------------------------------------

def _smile_chain(expiry, slope):
    """IV decreasing (slope<0) / flat / increasing across strikes 80..120."""
    strikes = list(range(80, 121, 5))
    base = 0.50
    ivs = [base + slope * (k - 100) / 100 for k in strikes]
    return pd.DataFrame(_rows(expiry, strikes, ivs, [3.0] * len(strikes)))


def test_skew_zero_for_flat_smile():
    chain = _smile_chain("2026-06-05", slope=0.0)
    s = features.skew_25d(chain, pd.Timestamp("2026-06-05"), 100.0, t_years=0.1)
    assert s == pytest.approx(0.0, abs=1e-9)


def test_skew_positive_when_puts_richer():
    # IV falls as strike rises -> low-strike (put) IV richer -> positive skew.
    chain = _smile_chain("2026-06-05", slope=-0.30)
    s = features.skew_25d(chain, pd.Timestamp("2026-06-05"), 100.0, t_years=0.1)
    assert s > 0


def test_skew_nan_for_nonpositive_tenor():
    chain = _smile_chain("2026-06-05", slope=-0.3)
    assert np.isnan(features.skew_25d(chain, pd.Timestamp("2026-06-05"), 100.0, 0.0))


# --- event_features ----------------------------------------------------------

def test_event_features_assembles_all_keys():
    front = _rows("2026-06-05", [95, 100, 105], [.5, .5, .5], [4, 3, 2])
    back = _rows("2026-07-03", [95, 100, 105], [.4, .4, .4], [5, 4, 3])
    chain = pd.DataFrame(front + back)
    prices = pd.DataFrame({"close": [100, 102, 99, 101, 100]})

    feats = features.event_features(
        chain, spot=100.0, announce_date="2026-06-01",
        asof_date="2026-05-29", price_history=prices,
    )
    assert set(feats) == set(features.FEATURE_KEYS)
    assert feats["front_atm_iv"] == pytest.approx(0.5)
    assert feats["back_atm_iv"] == pytest.approx(0.4)
    assert feats["iv_term_spread"] == pytest.approx(0.1)
    assert feats["implied_move"] == pytest.approx(0.06)
    assert feats["trailing_rv"] > 0


def test_event_features_handles_per_expiry_strike_grids():
    # Regression: front expiry lists only 310/315, while 312.5 exists only in the
    # back expiry. A global ATM strike of 312.5 would miss the front and yield
    # NaN; the per-expiry strike picks 310/315 and prices correctly.
    front = _rows("2026-06-05", [310, 315], [0.50, 0.50], [6, 5])
    back = _rows("2026-07-03", [305, 310, 312.5, 315], [0.40] * 4, [7, 6, 5.5, 5])
    chain = pd.DataFrame(front + back)
    prices = pd.DataFrame({"close": [312.5] * 5})

    feats = features.event_features(
        chain, spot=312.5, announce_date="2026-06-01",
        asof_date="2026-05-29", price_history=prices,
    )
    assert not np.isnan(feats["front_atm_iv"])
    assert not np.isnan(feats["implied_move"])
    assert not np.isnan(feats["iv_term_spread"])


def test_event_features_empty_chain_is_all_nan_but_rv():
    prices = pd.DataFrame({"close": [100, 101, 100, 102]})
    feats = features.event_features(
        pd.DataFrame(columns=["expiry", "strike", "right", "bid", "ask", "iv", "open_interest"]),
        spot=100.0, announce_date="2026-06-01", asof_date="2026-05-29",
        price_history=prices,
    )
    assert np.isnan(feats["front_atm_iv"])
    assert np.isnan(feats["implied_move"])
    assert feats["trailing_rv"] > 0
