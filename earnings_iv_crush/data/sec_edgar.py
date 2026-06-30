"""
sec_edgar.py
SEC EDGAR access - no API key, but a User-Agent is required.

Set SEC_USER_AGENT in .env (format: "Name email"). SEC blocks requests
without it and rate-limits to ~10 requests/second.

Provides:
  - cik_map / get_cik : ticker -> 10-digit CIK
  - earnings_8ks      : recent earnings 8-Ks (Item 2.02) + BMO/AMC session
  - reported_eps      : reported diluted EPS history (XBRL)
"""

from __future__ import annotations

import functools
from datetime import time as dtime

import pandas as pd
import requests

from .config import SEC_USER_AGENT

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/" "CIK{cik}/us-gaap/EarningsPerShareDiluted.json"
)


def _headers() -> dict:
    if not SEC_USER_AGENT:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. Add it to .env, e.g. "
            "'SEC_USER_AGENT=Your Name your.email@example.com'."
        )
    return {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


# ── Ticker -> CIK resolution ─────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def cik_map() -> dict:
    """Ticker -> 10-digit zero-padded CIK. Cached for the process run."""
    r = requests.get(_TICKERS_URL, headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()}


def get_cik(ticker: str) -> str:
    """Resolve a ticker to its 10-digit CIK, raising ``KeyError`` if unknown."""
    cik = cik_map().get(ticker.upper())
    if cik is None:
        raise KeyError(f"No CIK found for ticker {ticker!r}")
    return cik


# ── Filings: 8-Ks and session ────────────────────────────────────────────────


def infer_session(acceptance) -> str:
    """BMO / AMC / ambiguous from an EDGAR acceptance timestamp.

    EDGAR acceptance times are Eastern wall-clock (the trailing ``Z`` is a
    quirk, not real UTC). Validate once against a known print. Logic:
    before 09:30 ET -> ``"bmo"`` ; at/after 16:00 ET -> ``"amc"`` ; else
    ``"ambiguous"``.

    Parameters
    ----------
    acceptance : str or datetime-like
        EDGAR acceptance timestamp.

    Returns
    -------
    str
        One of ``"bmo"``, ``"amc"`` or ``"ambiguous"``.
    """
    ts = pd.to_datetime(acceptance)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)  # keep the wall-clock digits, drop tz
    t = ts.time()
    if t < dtime(9, 30):
        return "bmo"
    if t >= dtime(16, 0):
        return "amc"
    return "ambiguous"


def earnings_8ks(ticker: str) -> pd.DataFrame:
    """Recent earnings 8-Ks (Item 2.02) with acceptance time and session.

    Note: the submissions ``recent`` block only covers roughly the last year /
    ~1000 filings. For a multi-year backtest, page through the older shards under
    ``filings.files``; the deeper history is sourced from WRDS where available.

    Parameters
    ----------
    ticker : str
        Underlying symbol.

    Returns
    -------
    pandas.DataFrame
        Columns ``accession``, ``acceptance`` and ``session``. Empty when no
        matching 8-K is found.
    """
    cik = get_cik(ticker)
    r = requests.get(_SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=30)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    rows = []
    for form, items, acc, accn in zip(
        recent["form"],
        recent["items"],
        recent["acceptanceDateTime"],
        recent["accessionNumber"],
        strict=False,  # tolerate a ragged response from the live API
    ):
        if form == "8-K" and items and "2.02" in items:
            rows.append({"accession": accn, "acceptance": acc})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["acceptance"] = pd.to_datetime(df["acceptance"])
        df["session"] = df["acceptance"].apply(infer_session)
    return df


# ── XBRL: reported EPS ───────────────────────────────────────────────────────


def reported_eps(ticker: str) -> pd.DataFrame:
    """Reported diluted EPS history from XBRL.

    Parameters
    ----------
    ticker : str
        Underlying symbol.

    Returns
    -------
    pandas.DataFrame
        Columns ``end`` (period end), ``val`` (EPS), ``filed`` and ``form``,
        sorted by ``end``. Empty when XBRL has no data.
    """
    cik = get_cik(ticker)
    r = requests.get(_CONCEPT_URL.format(cik=cik), headers=_headers(), timeout=30)
    r.raise_for_status()
    units = r.json().get("units", {})
    rows = []
    for entries in units.values():  # unit key like "USD/shares"
        for e in entries:
            rows.append(
                {
                    "end": e.get("end"),
                    "val": e.get("val"),
                    "filed": e.get("filed"),
                    "form": e.get("form"),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["end"] = pd.to_datetime(df["end"])
        df = df.sort_values("end").reset_index(drop=True)
    return df
