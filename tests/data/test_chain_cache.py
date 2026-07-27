"""Tests for the disk-cached chain fetcher (synthetic fetch, tmp cache)."""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data.chain_cache import cached_chain_fetcher
from earnings_iv_crush.data.options import CHAIN_COLUMNS


def _fake_fetch(calls):
    def fetch(ticker, asof, strike_window=None, horizon_days=None):
        calls.append((ticker, asof, strike_window, horizon_days))
        if ticker == "EMPTY":
            return pd.DataFrame(columns=CHAIN_COLUMNS)
        return pd.DataFrame(
            [
                {
                    "expiry": pd.Timestamp("2026-07-17"),
                    "strike": 100.0,
                    "right": "C",
                    "bid": 3.0,
                    "ask": 3.0,
                    "iv": 0.4,
                    "open_interest": 100,
                }
            ]
        )

    return fetch


def test_second_call_served_from_disk(tmp_path):
    calls = []
    fetcher = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    a = fetcher("AAPL", "2026-05-01")
    b = fetcher("AAPL", "2026-05-01")
    assert len(calls) == 1  # second hit came from disk
    assert len(a) == len(b) == 1
    assert pd.api.types.is_datetime64_any_dtype(b["expiry"])


def test_empty_result_cached_as_sentinel(tmp_path):
    calls = []
    fetcher = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    fetcher("EMPTY", "2026-05-01")
    out = fetcher("EMPTY", "2026-05-01")
    assert len(calls) == 1  # the empty result was not re-fetched
    assert out.empty


def test_variants_use_distinct_keys_and_params(tmp_path):
    calls = []
    entry = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    panel = cached_chain_fetcher("panel", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    entry("AAPL", "2026-05-01")
    panel("AAPL", "2026-05-01")
    assert len(calls) == 2  # different keys, both fetched
    assert calls[0][2:] == (0.20, 90)
    assert calls[1][2:] == (0.06, 70)


def test_refresh_empty_refetches_only_empty_sentinels(tmp_path):
    calls = []
    fetcher = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    fetcher("EMPTY", "2026-05-01")
    fetcher("AAPL", "2026-05-01")
    healer = cached_chain_fetcher(
        "entry", cache_dir=tmp_path, fetch=_fake_fetch(calls), refresh_empty=True
    )
    healer("EMPTY", "2026-05-01")  # empty sentinel -> refetched
    healer("AAPL", "2026-05-01")  # populated snapshot -> still served from disk
    assert [c[0] for c in calls] == ["EMPTY", "AAPL", "EMPTY"]


def test_empty_served_counter_tracks_sentinel_hits(tmp_path):
    calls = []
    fetcher = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    fetcher("EMPTY", "2026-05-01")
    assert fetcher.empty_served == 0  # first miss fetched, not served from cache
    fetcher("EMPTY", "2026-05-01")
    fetcher("EMPTY", "2026-05-01")
    assert fetcher.empty_served == 2


def test_changed_variant_geometry_changes_the_key(tmp_path, monkeypatch):
    from earnings_iv_crush.data import chain_cache

    calls = []
    fetcher = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    fetcher("AAPL", "2026-05-01")
    monkeypatch.setitem(chain_cache.VARIANTS, "entry", (0.30, 120))
    drifted = cached_chain_fetcher("entry", cache_dir=tmp_path, fetch=_fake_fetch(calls))
    drifted("AAPL", "2026-05-01")
    # The geometry drift must miss the old cache entry and refetch.
    assert len(calls) == 2
    assert calls[1][2:] == (0.30, 120)
