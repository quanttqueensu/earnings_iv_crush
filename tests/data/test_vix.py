"""Tests for earnings_iv_crush.data.vix: FRED CSV parsing, missing points, failed series."""

from __future__ import annotations

import logging

import requests

from earnings_iv_crush.data import vix
from tests.data.conftest import FakeResponse

# Minimal fredgraph CSV bodies keyed by series id. A '.' marks a missing point.
_CSV = {
    "VIXCLS": "observation_date,VIXCLS\n2026-05-01,13.5\n2026-05-02,.\n",
    "VXVCLS": "observation_date,VXVCLS\n2026-05-01,15.0\n2026-05-02,15.2\n",
}


def _fake_get(csv_by_series):
    def _get(url, timeout=None, **kwargs):
        series_id = next(s for s in csv_by_series if f"id={s}" in url)
        return FakeResponse(text=csv_by_series[series_id])

    return _get


def test_fetch_index_vol_merges_series(monkeypatch):
    monkeypatch.setattr(vix.requests, "get", _fake_get(_CSV))
    df = vix.fetch_index_vol("2026-05-01", "2026-05-02")

    assert list(df.columns) == ["date", "vix", "vix3m"]
    assert len(df) == 2
    # '.' must parse to NaN, not a string or zero.
    assert df.loc[df["date"] == "2026-05-02", "vix"].isna().all()
    assert df.loc[df["date"] == "2026-05-01", "vix"].iloc[0] == 13.5
    assert df.loc[df["date"] == "2026-05-02", "vix3m"].iloc[0] == 15.2


def test_one_failed_series_does_not_kill_the_rest(monkeypatch, caplog):
    def _get(url, timeout=None, **kwargs):
        if "id=VXVCLS" in url:
            raise requests.ConnectionError("boom")
        return FakeResponse(text=_CSV["VIXCLS"])

    monkeypatch.setattr(vix.requests, "get", _get)
    with caplog.at_level(logging.WARNING):
        df = vix.fetch_index_vol("2026-05-01", "2026-05-02")

    assert "vix" in df.columns
    assert "vix3m" not in df.columns  # the failed series is absent
    assert "could not fetch" in caplog.text.lower()  # warning logged, not raised


def test_all_series_fail_returns_empty_frame(monkeypatch):
    def _get(url, timeout=None, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(vix.requests, "get", _get)
    df = vix.fetch_index_vol("2026-05-01", "2026-05-02")
    assert list(df.columns) == ["date", "vix", "vix3m"]
    assert df.empty
