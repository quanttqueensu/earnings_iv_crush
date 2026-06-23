"""Tests for earnings_iv_crush.data.databento_options.

The Databento transport (``_get_df``) and the spot lookup are monkeypatched so
the instrument selection, publisher consolidation, schema mapping and local IV
inversion are tested offline. The disk cache is redirected to a tmp dir. One
opt-in `live` test hits the real OPRA API (run it with the sandbox disabled).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import databento_options as do
from earnings_iv_crush.data.options import CHAIN_COLUMNS
from earnings_iv_crush.engine.greeks import bs_price

ASOF = pd.Timestamp("2022-06-15")
SPOT = 135.0
SIGMA = 0.50


def _osi(strike: float, right: str, exp: pd.Timestamp) -> str:
    return f"AAPL  {exp.strftime('%y%m%d')}{right}{int(strike*1000):08d}"


def _definition() -> pd.DataFrame:
    """Synthetic OPRA definitions: 3 front weeklies + one ~30d back, C and P."""
    rows = []
    for exp in (ASOF + pd.Timedelta(days=d) for d in (2, 9, 16, 30)):
        for k in range(115, 156, 5):
            for right in ("C", "P"):
                rows.append(
                    {
                        "raw_symbol": _osi(k, right, exp),
                        "instrument_class": right,
                        "strike_price": float(k),
                        "expiration": exp.tz_localize("UTC"),
                    }
                )
    return pd.DataFrame(rows)


def _ohlcv(symbols: list[str], meta: pd.DataFrame) -> pd.DataFrame:
    """Two publisher rows per symbol; the high-volume one carries the true close."""
    m = meta.set_index("raw_symbol")
    rows = []
    for s in symbols:
        strike = m.loc[s, "strike_price"]
        right = m.loc[s, "instrument_class"]
        exp = pd.to_datetime(m.loc[s, "expiration"]).tz_localize(None)
        t = (exp - ASOF).days / 365.0
        close = float(bs_price(SPOT, strike, t, 0.0, SIGMA, right))
        rows.append({"symbol": s, "close": close, "volume": 500})  # liquid venue, true mark
        rows.append({"symbol": s, "close": close * 1.5, "volume": 5})  # stale venue, wrong mark
    return pd.DataFrame(rows)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Wire the synthetic definition/ohlcv transport and a tmp cache dir."""
    defn = _definition()
    meta = defn.copy()
    calls = {"ohlcv": 0, "defn": 0}

    def fake_get_df(schema, symbols, start, end, stype_in):
        if schema == "definition":
            calls["defn"] += 1
            return defn
        calls["ohlcv"] += 1
        return _ohlcv(symbols, meta)

    monkeypatch.setattr(do, "_get_df", fake_get_df)
    monkeypatch.setattr(do, "_spot_on_or_before", lambda *a, **k: SPOT)
    monkeypatch.setattr(do, "_CACHE_ROOT", tmp_path)
    return calls


def test_schema_matches_canonical_chain(patched):
    df = do.fetch_option_chain("AAPL", "2022-06-15")
    assert list(df.columns) == CHAIN_COLUMNS
    assert set(df["right"]) == {"C", "P"}
    assert (df["bid"] == df["ask"]).all()  # close on both sides, no NBBO
    assert df["open_interest"].isna().all()
    assert (df["expiry"] > ASOF).all()


def test_iv_inverts_back_to_input_sigma(patched):
    df = do.fetch_option_chain("AAPL", "2022-06-15")
    atm = df[np.isclose(df["strike"], 135.0)]
    assert not atm.empty
    # Recovered IV must match the sigma the closes were generated at - and must
    # come from the liquid venue's close, not the 1.5x stale-venue print.
    assert np.allclose(atm["iv"], SIGMA, atol=1e-2)


def test_front_block_and_back_leg_selected(patched):
    df = do.fetch_option_chain("AAPL", "2022-06-15")
    exps = sorted(pd.to_datetime(df["expiry"].unique()))
    # Three front weeklies carry wings; a back expiry >=21d out is present for term.
    assert len(exps) >= 4
    assert (exps[-1] - ASOF).days >= do._BACK_GAP_DAYS
    # The far back leg is ATM-only (narrower band than the front block).
    back = df[df["expiry"] == exps[-1]]
    front = df[df["expiry"] == exps[0]]
    assert back["strike"].nunique() < front["strike"].nunique()


def test_cache_hit_avoids_network(patched):
    do.fetch_option_chain("AAPL", "2022-06-15")
    first = dict(patched)
    do.fetch_option_chain("AAPL", "2022-06-15")  # second call: served from cache
    assert dict(patched) == first  # no further definition/ohlcv pulls


def test_missing_spot_returns_empty_typed_frame(monkeypatch, tmp_path):
    monkeypatch.setattr(do, "_spot_on_or_before", lambda *a, **k: float("nan"))
    monkeypatch.setattr(do, "_get_df", lambda *a, **k: pytest.fail("must not query"))
    monkeypatch.setattr(do, "_CACHE_ROOT", tmp_path)
    df = do.fetch_option_chain("AAPL", "2022-06-15")
    assert list(df.columns) == CHAIN_COLUMNS
    assert df.empty


def test_consolidate_takes_most_liquid_venue():
    bars = pd.DataFrame(
        {
            "symbol": ["X", "X", "Y"],
            "close": [1.0, 9.9, 2.0],
            "volume": [1000, 5, 50],
        }
    )
    out = do._consolidate(bars)
    assert out.set_index("symbol")["close"].to_dict() == {"X": 1.0, "Y": 2.0}


def test_prefetch_writes_both_day_caches(monkeypatch, tmp_path):
    """One definition + one ranged ohlcv call must cache both entry and exit days."""
    defn = _definition()
    meta = defn.copy()
    calls = {"ohlcv": 0, "defn": 0}
    entry, exit_ = ASOF, ASOF + pd.Timedelta(days=1)

    def fake_get_df(schema, symbols, start, end, stype_in):
        if schema == "definition":
            calls["defn"] += 1
            return defn
        calls["ohlcv"] += 1
        # Ranged pull: emit a bar for each requested symbol on both days.
        one = _ohlcv(symbols, meta)
        frames = []
        for day in (entry, exit_):
            d = one.copy()
            d["ts_event"] = day.tz_localize("UTC")
            frames.append(d)
        return pd.concat(frames).set_index("ts_event")

    monkeypatch.setattr(do, "_get_df", fake_get_df)
    monkeypatch.setattr(do, "_spot_on_or_before", lambda *a, **k: SPOT)
    monkeypatch.setattr(do, "_CACHE_ROOT", tmp_path)

    do.prefetch_event("AAPL", entry.strftime("%Y-%m-%d"), exit_.strftime("%Y-%m-%d"))
    assert calls == {"defn": 1, "ohlcv": 1}  # two API calls total, not four
    assert do._cache_path("AAPL", entry).exists()
    assert do._cache_path("AAPL", exit_).exists()

    # The build then reads those caches with no further network.
    monkeypatch.setattr(do, "_get_df", lambda *a, **k: pytest.fail("must not query"))
    chain = do.fetch_option_chain("AAPL", entry.strftime("%Y-%m-%d"))
    assert list(chain.columns) == CHAIN_COLUMNS
    assert not chain.empty


def test_split_factor_lifts_post_event_splits(monkeypatch):
    """A split after the event scales the factor; a split before it does not."""
    do._splits_cache.clear()
    # 20:1 on 2022-06-06 (AMZN-style).
    do._splits_cache["AMZN"] = pd.Series([20.0], index=pd.to_datetime(["2022-06-06"]))
    assert do._split_factor("AMZN", pd.Timestamp("2022-02-03")) == 20.0  # pre-split event
    assert do._split_factor("AMZN", pd.Timestamp("2022-07-01")) == 1.0  # post-split event
    do._splits_cache.clear()


def test_spot_is_unadjusted_for_split_names(monkeypatch):
    """The returned spot is lifted to the raw basis OPRA strikes are quoted in."""
    do._splits_cache.clear()
    do._splits_cache["NVDA"] = pd.Series([10.0], index=pd.to_datetime(["2024-06-10"]))
    monkeypatch.setattr(
        do,
        "fetch_equity_ohlcv",
        lambda *a, **k: pd.DataFrame({"date": [pd.Timestamp("2022-08-24")], "close": [17.22]}),
    )
    spot = do._spot_on_or_before("NVDA", pd.Timestamp("2022-08-24"))
    assert spot == pytest.approx(172.2)  # 17.22 x 10, matching the real 2022 strikes
    do._splits_cache.clear()


def test_opra_root_strips_share_class_suffix():
    assert do._opra_root("BRK-B") == "BRKB"
    assert do._opra_root("AAPL") == "AAPL"


def test_get_df_empty_symbols_does_not_hit_api(monkeypatch):
    """An empty symbol list must short-circuit, never pull the whole universe."""
    monkeypatch.setattr(do, "_client", lambda: pytest.fail("empty symbols must not query"))
    out = do._get_df("ohlcv-1d", [], "2022-08-24", "2022-08-25", "raw_symbol")
    assert out.empty


@pytest.mark.live
def test_live_databento_chain_has_atm_iv():
    """Real OPRA call (run with sandbox disabled): a 2022 AAPL chain with finite IV."""
    df = do.fetch_option_chain("AAPL", "2022-06-15", spot=135.43)
    assert list(df.columns) == CHAIN_COLUMNS
    assert not df.empty
    assert df["iv"].notna().any()
    assert set(df["right"]) == {"C", "P"}
    assert pd.to_datetime(df["expiry"]).nunique() >= 2
