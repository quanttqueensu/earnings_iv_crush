"""
lse_options.py
Historical option chains via London Strategic Edge (free, no metered credits).

Pulls daily option bars from the LSE vault via ``history(dataset='options',
timeframe='1d')``.  Two pull strategies:

1. **Bulk** (recommended for backtest builds): call ``pull_ticker_raw()`` once
   per underlying — one vault export job fetches every 1d option bar the ticker
   has ever printed.  The raw result is cached under ``data/processed/lse_raw/``
   and sliced by date when ``fetch_option_chain`` is called.

2. **Per-date** (fallback): one ``history()`` call per (ticker, date).  Used
   when no bulk cache exists.  Heavily rate-limited (~1 call per 20-30s).

IV is inverted locally using yfinance spot (matching the Databento methodology)
so the two sources are on the same basis.  The result matches
``options.CHAIN_COLUMNS`` exactly, so it is a drop-in for
``databento_options.fetch_option_chain``.

Data quality notes:
* LSE daily bars are last-trade prices, not settlement marks. The provider
  filters to contracts with volume > 0, which removes stale-price contracts
  and reduces the last-trade-vs-settlement gap on ATM contracts for liquid
  names. No bid/ask is available on historical bars; both sides carry the
  close, matching the Databento pre-2023 convention.
* Spot comes from yfinance (split-adjusted close), lifted by the cumulative
  split factor to match LSE's raw (unadjusted) historical strikes — identical
  to the Databento methodology.

Requires ``LSE_API_KEY`` in ``.env``.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..engine.greeks import implied_vol
from .config import require
from .equities import fetch_equity_ohlcv
from .options import CHAIN_COLUMNS

_logger = logging.getLogger(__name__)

_CACHE_ROOT = Path("data/processed/lse")
_RAW_CACHE_ROOT = Path("data/processed/lse_raw")
_HORIZON_DAYS = 75
_STRIKE_WINDOW = 0.12

_MAX_RETRIES = 8
_BASE_BACKOFF = 20.0
_MIN_CALL_INTERVAL = 30.0  # vault export jobs are heavily rate-limited

_client_cache: Any = None
_last_vault_call: float = 0.0


# ── LSE client ──────────────────────────────────────────────────────────────


def _client() -> Any:
    """Return a cached LSE client (lazy import + key from .env)."""
    global _client_cache
    if _client_cache is None:
        from lse import LSE

        _client_cache = LSE(api_key=require("LSE_API_KEY"))
    return _client_cache


def _lse_retry(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call *fn* with exponential backoff on 429 / transient errors."""
    from lse import LSEError

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            _throttle()
        try:
            return fn(*args, **kwargs)
        except LSEError as exc:
            last_error = exc
            if "429" in str(exc) and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF * (2**attempt) + random.uniform(0, 1)
                _logger.warning("LSE rate limit, backing off %.1fs", wait)
                time.sleep(wait)
            else:
                raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BASE_BACKOFF * (attempt + 1))
            else:
                raise
    assert last_error is not None
    raise last_error


# ── Spot resolution ─────────────────────────────────────────────────────────


_splits_cache: dict[str, pd.Series] = {}


def _split_factor(ticker: str, asof: pd.Timestamp) -> float:
    """Cumulative split ratio for splits occurring strictly after *asof*.

    yfinance closes are split-adjusted to the present, but LSE's historical
    strikes are the unadjusted levels that actually traded. Multiplying an
    adjusted close by this factor recovers the raw price on *asof*.
    """
    if ticker not in _splits_cache:
        import yfinance as yf

        try:
            splits = yf.Ticker(ticker).splits
        except Exception:
            splits = pd.Series(dtype=float)
        if splits is not None and len(splits):
            splits = splits.copy()
            splits.index = pd.to_datetime(splits.index).tz_localize(None)
        _splits_cache[ticker] = splits if splits is not None else pd.Series(dtype=float)

    splits = _splits_cache[ticker]
    if splits.empty:
        return 1.0
    after = splits[splits.index > asof]
    factor = 1.0
    for ratio in after.to_numpy():
        factor *= float(ratio)
    return factor


def _spot_on_or_before(ticker: str, asof: pd.Timestamp, lookback_days: int = 7) -> float:
    """Latest *unadjusted* underlying close on or before *asof*.

    Takes the yfinance close (split-adjusted) and lifts it back to the raw
    basis via _split_factor, so the returned spot matches LSE's historical
    strikes.
    """
    prices = fetch_equity_ohlcv(
        ticker,
        (asof - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d"),
        (asof + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if prices is None or prices.empty:
        return float("nan")
    dates = pd.to_datetime(prices["date"])
    usable = prices[dates <= asof]
    if usable.empty:
        return float("nan")
    return float(usable["close"].iloc[-1]) * _split_factor(ticker, asof)


# ── Bulk raw cache (one vault export per ticker) ───────────────────────────


def _raw_cache_path(ticker: str) -> Path:
    return _RAW_CACHE_ROOT / f"{ticker}.parquet"


def pull_ticker_raw(ticker: str) -> Path:
    """Pull the full option 1d bar history for *ticker* in one vault export.

    Saves the raw result to ``data/processed/lse_raw/{ticker}.parquet`` and
    returns the path. Subsequent ``fetch_option_chain`` calls for this ticker
    slice from the cache with zero API cost.

    This is the recommended pull strategy for bulk builds: call once per
    ticker (50 calls for the megacap universe) instead of per (ticker, date).
    """
    path = _raw_cache_path(ticker)
    if path.exists():
        _logger.info("raw cache hit: %s", path)
        return path
    _throttle()
    _logger.info("vault export: %s (full history)", ticker)
    raw = _lse_retry(
        _client().history,
        ticker,
        dataset="options",
        timeframe="1d",
        dataframe=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None and not raw.empty:
        raw.to_parquet(path, index=False)
        _logger.info("cached %d raw rows -> %s", len(raw), path)
    else:
        pd.DataFrame().to_parquet(path, index=False)
        _logger.info("empty raw result -> %s (sentinel)", path)
    return path


def _load_raw_for_date(ticker: str, asof: str) -> pd.DataFrame:
    """Slice the bulk raw cache for a single date. Returns empty if not cached."""
    path = _raw_cache_path(ticker)
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_parquet(path)
    if raw.empty:
        return raw
    ts_col = next((c for c in ("ts", "date", "timestamp") if c in raw.columns), None)
    if ts_col is None:
        return pd.DataFrame()
    dates = pd.to_datetime(raw[ts_col]).dt.tz_localize(None).dt.normalize()
    target = pd.Timestamp(asof).normalize()
    return raw[dates == target].reset_index(drop=True)


# ── Per-date pull (fallback) ───────────────────────────────────────────────


def _throttle() -> None:
    """Enforce minimum spacing between vault export calls."""
    global _last_vault_call
    elapsed = time.monotonic() - _last_vault_call
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_vault_call = time.monotonic()


def _pull_chain_raw(ticker: str, asof: str) -> pd.DataFrame:
    """All option daily bars for *ticker* on *asof*.

    Checks the bulk raw cache first; falls back to a single-day vault export.
    """
    from_cache = _load_raw_for_date(ticker, asof)
    if not from_cache.empty:
        return from_cache

    raw_path = _raw_cache_path(ticker)
    if raw_path.exists():
        return pd.DataFrame()

    _throttle()
    end = (pd.Timestamp(asof) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = _lse_retry(
        _client().history,
        ticker,
        dataset="options",
        timeframe="1d",
        start=asof,
        end=end,
        dataframe=True,
    )
    if raw is None or (hasattr(raw, "empty") and raw.empty):
        return pd.DataFrame()
    return raw


_RIGHT_MAP = {
    "C": "C",
    "c": "C",
    "call": "C",
    "Call": "C",
    "CALL": "C",
    "P": "P",
    "p": "P",
    "put": "P",
    "Put": "P",
    "PUT": "P",
}


def _to_chain(
    raw: pd.DataFrame,
    asof: pd.Timestamp,
    spot: float,
    r: float,
    strike_window: float,
    horizon_days: int,
) -> pd.DataFrame:
    """Map LSE history() output to CHAIN_COLUMNS with locally inverted IV."""
    if raw.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    df = raw.copy()

    # ── parse expiry ────────────────────────────────────────────────────
    exp_col = next((c for c in ("expiry", "expiration", "exp") if c in df.columns), None)
    if exp_col is None:
        _logger.warning("no expiry column in LSE response: %s", list(df.columns))
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    df["_expiry"] = pd.to_datetime(df[exp_col], errors="coerce")
    df = df.dropna(subset=["_expiry"])

    # ── parse right ─────────────────────────────────────────────────────
    right_col = next(
        (c for c in ("opt_type", "type", "right", "contract_type") if c in df.columns), None
    )
    if right_col is None:
        _logger.warning("no right/type column in LSE response: %s", list(df.columns))
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    df["_right"] = df[right_col].astype(str).map(_RIGHT_MAP)
    df = df.dropna(subset=["_right"])

    # ── parse strike ────────────────────────────────────────────────────
    strike_col = next((c for c in ("strike", "strike_price") if c in df.columns), None)
    if strike_col is None:
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    df["_strike"] = pd.to_numeric(df[strike_col], errors="coerce")
    df = df.dropna(subset=["_strike"])
    df = df[df["_strike"] > 0]

    # ── filter: expiry horizon and strike window ────────────────────────
    df = df[df["_expiry"] > asof]
    df = df[df["_expiry"] <= asof + pd.Timedelta(days=horizon_days)]
    lo, hi = spot * (1 - strike_window), spot * (1 + strike_window)
    df = df[df["_strike"].between(lo, hi)]

    if df.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    # ── price: close (no bid/ask on historical daily bars) ────────────
    close_col = next((c for c in ("close", "last_price") if c in df.columns), None)
    if close_col is None:
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    df["_price"] = pd.to_numeric(df[close_col], errors="coerce")
    df = df[df["_price"] > 0]

    # ── volume filter: drop stale-price contracts ───────────────────────
    vol_col = next((c for c in ("volume", "vol") if c in df.columns), None)
    if vol_col is not None:
        df["_vol"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0)
        df = df[df["_vol"] > 0]

    if df.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    # ── IV: invert locally (no IV on historical bars) ───────────────────
    t = (df["_expiry"] - asof).dt.days.clip(lower=1) / 365.0
    ivs = [
        implied_vol(c, spot, k, ti, r, right)
        for c, k, ti, right in zip(df["_price"], df["_strike"], t, df["_right"], strict=True)
    ]

    # ── open interest ───────────────────────────────────────────────────
    oi_col = next((c for c in ("open_interest", "oi") if c in df.columns), None)
    if oi_col is not None:
        oi_vals = pd.to_numeric(df[oi_col], errors="coerce").astype(float).values
    else:
        oi_vals = np.full(len(df), np.nan, dtype=float)

    return pd.DataFrame(
        {
            "expiry": df["_expiry"].values,
            "strike": df["_strike"].astype(float).values,
            "right": df["_right"].values,
            "bid": df["_price"].astype(float).values,
            "ask": df["_price"].astype(float).values,
            "iv": ivs,
            "open_interest": oi_vals,
        },
        columns=CHAIN_COLUMNS,
    )


# ── Cache ───────────────────────────────────────────────────────────────────


def _cache_path(ticker: str, asof: pd.Timestamp) -> Path:
    return _CACHE_ROOT / ticker / f"{asof.strftime('%Y-%m-%d')}_chain.parquet"


def _save(path: Path, chain: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chain.to_parquet(path, index=False)


# ── Public chain fetcher ────────────────────────────────────────────────────


def fetch_option_chain(
    ticker: str,
    asof: str,
    horizon_days: int = _HORIZON_DAYS,
    strike_window: float = _STRIKE_WINDOW,
    spot: float | None = None,
    r: float = 0.0,
) -> pd.DataFrame:
    """Event-scoped option chain for *ticker* as of *asof* (YYYY-MM-DD).

    Drop-in for ``databento_options.fetch_option_chain`` with the same return
    schema, backed by LSE daily option bars with locally inverted iv.

    Parameters
    ----------
    ticker : str
        Underlying ticker.
    asof : str
        As-of date (YYYY-MM-DD).
    horizon_days : int
        Maximum DTE for included expiries.
    strike_window : float
        Fraction of spot for the strike band (+/-).
    spot : float or None
        Underlying price; resolved from yfinance when None.
    r : float
        Risk-free rate for IV inversion.

    Returns
    -------
    pandas.DataFrame
        Chain with CHAIN_COLUMNS; empty when data is unavailable.
    """
    asof_ts = pd.Timestamp(asof).normalize()
    cache = _cache_path(ticker, asof_ts)
    if cache.exists():
        return pd.read_parquet(cache)

    if spot is None:
        spot = _spot_on_or_before(ticker, asof_ts)
    chain = pd.DataFrame(columns=CHAIN_COLUMNS)
    if spot and spot == spot:  # NaN-safe
        raw = _pull_chain_raw(ticker, asof)
        if not raw.empty:
            chain = _to_chain(raw, asof_ts, spot, r, strike_window, horizon_days)

    _save(cache, chain)
    return chain


def prefetch_event(ticker: str, entry: str, exit_: str, r: float = 0.0) -> None:
    """Populate the entry and exit chain caches for one event.

    When a bulk raw cache exists (from ``pull_ticker_raw``), both chains are
    built from it with zero API cost. Otherwise falls back to per-date pulls.
    """
    entry_ts = pd.Timestamp(entry).normalize()
    exit_ts = pd.Timestamp(exit_).normalize()
    ep, xp = _cache_path(ticker, entry_ts), _cache_path(ticker, exit_ts)
    if ep.exists() and xp.exists():
        return

    empty = pd.DataFrame(columns=CHAIN_COLUMNS)
    spot = _spot_on_or_before(ticker, entry_ts)
    if not (spot and spot == spot):
        _save(ep, empty)
        _save(xp, empty)
        return

    for asof_ts, path in ((entry_ts, ep), (exit_ts, xp)):
        if path.exists():
            continue
        raw = _pull_chain_raw(ticker, asof_ts.strftime("%Y-%m-%d"))
        chain = (
            _to_chain(raw, asof_ts, spot, r, _STRIKE_WINDOW, _HORIZON_DAYS)
            if not raw.empty
            else empty
        )
        _save(path, chain)
