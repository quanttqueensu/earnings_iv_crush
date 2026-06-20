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
