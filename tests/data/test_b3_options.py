"""
test_b3_options.py
Offline tests for the B3 COTAHIST chain adapter.

Builds synthetic fixed-width COTAHIST type-01 records at the real byte offsets and
monkeypatches the downloader, so parsing, the vista-spot resolution, right mapping
(070->C, 080->P), strike/horizon windowing and the local IV inversion run with no
network. The inversion is checked against an independently priced mid.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest

from earnings_iv_crush.data import b3_options
from earnings_iv_crush.data.options import CHAIN_COLUMNS
from earnings_iv_crush.engine.greeks import bs_price


def _p13(x: float) -> str:
    """A COTAHIST N(13) price field: value with two implied decimals, zero-filled."""
    return str(int(round(x * 100))).zfill(13)


def _rec(
    tpmerc, codneg, preult=0.0, preofc=0.0, preofv=0.0, quatot=0, preexe=0.0, datven="20250814"
):
    """One 245-char COTAHIST type-01 record with fields at their real offsets."""
    line = [" "] * 245

    def put(start, end, s):
        s = str(s)[: end - start]
        line[start:end] = list(s.ljust(end - start))

    put(0, 2, "01")
    put(2, 10, "20250715")
    put(10, 12, "78")
    put(12, 24, codneg)
    put(24, 27, tpmerc)
    put(108, 121, _p13(preult))
    put(121, 134, _p13(preofc))
    put(134, 147, _p13(preofv))
    put(152, 170, str(int(quatot)).zfill(18))
    put(170, 188, "0" * 18)
    put(188, 201, _p13(preexe))
    put(202, 210, datven)
    return "".join(line)


def _cotahist_zip(records) -> bytes:
    header = "00COTAHIST.2025BOVESPA " + " " * 223
    body = "\r\n".join([header, *records])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("COTAHIST_D15072025.TXT", body.encode("latin-1"))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clear_cache():
    b3_options._DAILY_CACHE.clear()
    yield
    b3_options._DAILY_CACHE.clear()


def _install(monkeypatch, zip_bytes):
    monkeypatch.setattr(b3_options, "_download_cotahist", lambda yyyymmdd: zip_bytes)


def test_schema_and_right_mapping(monkeypatch, tmp_path):
    spot = 40.0
    mark_c = bs_price(spot, spot, 30 / 365.0, 0.0, 0.30, "C")
    mark_p = bs_price(spot, spot, 30 / 365.0, 0.0, 0.30, "P")
    recs = [
        _rec("010", "PETR4", preult=spot, quatot=1_000_000),
        _rec("070", "PETRH40", preofc=mark_c * 0.98, preofv=mark_c * 1.02, preexe=spot),
        _rec("080", "PETRT40", preofc=mark_p * 0.98, preofv=mark_p * 1.02, preexe=spot),
    ]
    _install(monkeypatch, _cotahist_zip(recs))
    ch = b3_options.fetch_option_chain("PETR4", "2025-07-15", cache_dir=tmp_path)
    assert list(ch.columns) == CHAIN_COLUMNS
    assert set(ch["right"]) == {"C", "P"}
    assert (ch["bid"] < ch["ask"]).all()  # real COTAHIST bid/ask, not a stamped mark
    assert ch["open_interest"].isna().all()  # COTAHIST carries no OI


def test_iv_inversion_recovers_sigma(monkeypatch, tmp_path):
    spot, sigma = 40.0, 0.35
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, sigma, "C")
    recs = [
        _rec("010", "PETR4", preult=spot, quatot=1_000_000),
        _rec("070", "PETRH40", preofc=mark, preofv=mark, preexe=spot),  # bid=ask -> mid=mark
    ]
    _install(monkeypatch, _cotahist_zip(recs))
    ch = b3_options.fetch_option_chain("PETR4", "2025-07-15", cache_dir=tmp_path)
    assert len(ch) == 1
    assert ch["iv"].iloc[0] == pytest.approx(sigma, abs=1e-3)


def test_vista_spot_resolves_liquid_class(monkeypatch, tmp_path):
    # Two vista classes share the root; the more liquid one sets spot.
    spot = 40.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.30, "C")
    recs = [
        _rec("010", "PETR3", preult=999.0, quatot=10),  # illiquid class, wrong price
        _rec("010", "PETR4", preult=spot, quatot=1_000_000),  # liquid class wins
        _rec("070", "PETRH40", preofc=mark, preofv=mark, preexe=spot),
    ]
    _install(monkeypatch, _cotahist_zip(recs))
    ch = b3_options.fetch_option_chain("PETR4", "2025-07-15", cache_dir=tmp_path)
    # If spot resolved to 999, the strike-40 option would fall outside the band.
    assert len(ch) == 1
    assert ch["iv"].iloc[0] == pytest.approx(0.30, abs=1e-3)


def test_other_name_and_windows_excluded(monkeypatch, tmp_path):
    spot = 40.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.30, "C")
    recs = [
        _rec("010", "PETR4", preult=spot, quatot=1_000_000),
        _rec("070", "PETRH40", preofc=mark, preofv=mark, preexe=spot),  # ATM, kept
        _rec("070", "PETRH60", preofc=mark, preofv=mark, preexe=60.0),  # +50%, out of band
        _rec("070", "PETRA40", preofc=mark, preofv=mark, preexe=spot, datven="20251215"),  # >90d
        _rec("010", "VALE3", preult=55.0, quatot=1_000_000),
        _rec("070", "VALEH55", preofc=mark, preofv=mark, preexe=55.0),  # different root
    ]
    _install(monkeypatch, _cotahist_zip(recs))
    ch = b3_options.fetch_option_chain(
        "PETR4", "2025-07-15", horizon_days=90, strike_window=0.20, cache_dir=tmp_path
    )
    assert len(ch) == 1
    assert ch["strike"].iloc[0] == 40.0


def test_missing_spot_returns_empty(monkeypatch, tmp_path):
    # Options present but no vista record for the root -> no spot -> empty.
    mark = bs_price(40.0, 40.0, 30 / 365.0, 0.0, 0.30, "C")
    recs = [_rec("070", "PETRH40", preofc=mark, preofv=mark, preexe=40.0)]
    _install(monkeypatch, _cotahist_zip(recs))
    ch = b3_options.fetch_option_chain("PETR4", "2025-07-15", cache_dir=tmp_path)
    assert ch.empty
    assert list(ch.columns) == CHAIN_COLUMNS


def test_bad_ticker_raises(tmp_path):
    with pytest.raises(ValueError, match="ticker"):
        b3_options.fetch_option_chain("PETR4; DROP", "2025-07-15", cache_dir=tmp_path)


def test_underlying_ohlcv_from_vista(monkeypatch, tmp_path):
    spot = 40.0
    _install(monkeypatch, _cotahist_zip([_rec("010", "PETR4", preult=spot, quatot=1_000_000)]))
    px = b3_options.fetch_underlying_ohlcv("PETR4", "2025-07-15", "2025-07-17", cache_dir=tmp_path)
    assert list(px.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert (px["close"] == spot).all()
    assert np.isnan(px["volume"]).all()
