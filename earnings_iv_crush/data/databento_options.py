"""
databento_options.py
Historical option chains via Databento's OPRA.PILLAR dataset.

This is the multi-year historical provider. It marks options off the **daily
close** (``ohlcv-1d``, trade-based) and inverts implied vol locally, exactly as
the Alpaca adapter does, so the two sources are methodologically consistent. The
difference is reach and resolution: OPRA daily bars, instrument definitions and
statistics go back to 2013-04-01, and the full weekly + monthly expiry ladder is
present - so an event-timed straddle can be bracketed on the precise entry and
exit sessions, which the sparse free sources could not do.

NBBO quotes on OPRA only begin 2023-03-28, so pre-2023 there is no bid/ask mid;
``bid`` and ``ask`` therefore both carry the close (the spread lives in
``engine.costs``), matching the Alpaca convention. ``open_interest`` is not pulled
(it would need the ``statistics`` schema); it is left NaN, so any feature that
needs OI must source it elsewhere for this provider.

Cost discipline (the account runs on metered credits):
* Every call is scoped to a handful of expiries and an ATM strike band, never the
  full ~2000-instrument parent universe, so one event costs cents not dollars.
* Definitions are pulled to resolve the instrument set, then ``ohlcv-1d`` is
  requested for **only** the selected OSI symbols.
* Every resolved chain is cached to disk, so a re-run never re-bills.

Requires ``DATABENTO_API_KEY`` in ``.env``. The result matches
``options.CHAIN_COLUMNS`` exactly, so it is a drop-in for
``options.fetch_option_chain`` / ``alpaca_options.fetch_option_chain`` and injects
as the ``fetch_chain`` argument of the event and surface builders unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..engine.greeks import implied_vol
from .config import require
from .equities import fetch_equity_ohlcv
from .options import CHAIN_COLUMNS

_DATASET = "OPRA.PILLAR"
_CACHE_ROOT = Path("data/processed/databento")

# Chain shape - the cost/coverage trade-off. The front block carries the wing
# strikes the skew and BKM features need; the back leg is ATM-only because it
# feeds the term-structure spread, which only reads the back ATM IV.
_N_FRONT_EXPIRIES = 3  # nearest expiries after asof: enough for front-roll selection
_STRIKE_WINDOW = 0.12  # +/- fraction of spot for the front block
_BACK_TARGET_DAYS = 28  # pull the expiry nearest this DTE for the back leg
_BACK_GAP_DAYS = 21  # back must sit at least this far beyond the front
_BACK_WINDOW = 0.06  # +/- fraction of spot for the ATM-only back leg
_HORIZON_DAYS = 75  # hard cap on how far out any pulled expiry may sit

_client_cache: Any = None


def _opra_root(ticker: str) -> str:
    """Map a yfinance ticker to its OPRA underlying root.

    OPRA concatenates share-class suffixes that yfinance hyphenates: ``BRK-B`` ->
    ``BRKB``. The equity/split lookups keep the yfinance form; only the OPRA parent
    symbol uses this root. Plain tickers pass through unchanged.
    """
    return ticker.replace("-", "").replace(".", "").upper()


# ── Databento client ─────────────────────────────────────────────────────────


def _client() -> Any:
    """Return a cached ``databento.Historical`` client (lazy import + key)."""
    global _client_cache
    if _client_cache is None:
        import databento as db  # lazy: the package imports without the dependency

        _client_cache = db.Historical(require("DATABENTO_API_KEY"))
    return _client_cache


_MAX_RETRIES = 8  # the constrained link cold-fails connections often; retry hard


def _retry(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call ``fn`` with retries: this network frequently times out a cold connect,
    then succeeds on a warm retry, so a short fixed backoff beats giving up."""
    import time

    last_error: Exception | None = None
    for _ in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # network/5xx/rate transients (incl. connect timeout)
            last_error = exc
            time.sleep(2.0)
    assert last_error is not None
    raise last_error


def _get_df(schema: str, symbols: list[str], start: str, end: str, stype_in: str) -> pd.DataFrame:
    """``timeseries.get_range(...).to_df()`` with retries on transients.

    Guards an empty ``symbols`` list: Databento treats "no symbols" as "the whole
    dataset", so an empty request would silently pull (and bill) the entire parent
    universe. Callers that select nothing must get an empty frame, never that.
    """
    if not symbols:
        return pd.DataFrame()
    data = _retry(
        _client().timeseries.get_range,
        dataset=_DATASET,
        symbols=symbols,
        schema=schema,
        start=start,
        end=end,
        stype_in=stype_in,
    )
    return data.to_df()


def get_cost(symbols: list[str], start: str, end: str, schema: str = "ohlcv-1d") -> float:
    """Retried ``metadata.get_cost`` (USD) for a raw-symbol request - free to call."""
    return float(
        _retry(
            _client().metadata.get_cost,
            dataset=_DATASET,
            symbols=symbols,
            schema=schema,
            start=start,
            end=end,
            stype_in="raw_symbol",
        )
    )


# ── Spot and instrument selection ────────────────────────────────────────────


_splits_cache: dict[str, pd.Series] = {}


def _split_factor(ticker: str, asof: pd.Timestamp) -> float:
    """Cumulative split ratio for splits occurring strictly after ``asof``.

    yfinance closes are always split-adjusted to the present, but OPRA's historical
    strikes are the *unadjusted* levels that actually traded. Multiplying an
    adjusted close by this factor recovers the raw price on ``asof``, so the strike
    band and the local IV inversion sit on the same basis as the chain. A name with
    no later splits returns ``1.0`` (the common case).
    """
    if ticker not in _splits_cache:
        import yfinance as yf  # lazy, matching the rest of the data layer

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
    """Latest *unadjusted* underlying close on or before ``asof`` (keyless).

    Takes the yfinance close (split-adjusted) and lifts it back to the raw basis
    via :func:`_split_factor`, so the returned spot matches OPRA's historical
    strikes. Without this, a name that has since split (e.g. NVDA 10:1, AMZN 20:1)
    centres the strike band three orders of magnitude away and selects nothing.
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


def _select_instruments(defn: pd.DataFrame, asof: pd.Timestamp, spot: float) -> pd.DataFrame:
    """Pick the front-block + back-leg contracts to price.

    Front block: the nearest ``_N_FRONT_EXPIRIES`` expiries strictly after
    ``asof`` (within the horizon), across a ``_STRIKE_WINDOW`` band - wide enough
    for the wing strikes the skew/BKM features read. Back leg: the single expiry
    nearest ``asof + _BACK_TARGET_DAYS`` that also sits at least ``_BACK_GAP_DAYS``
    beyond the front, ATM-only (``_BACK_WINDOW``), since it only feeds the
    back ATM IV of the term spread.
    """
    defn = defn.copy()
    defn["exp"] = pd.to_datetime(defn["expiration"]).dt.tz_localize(None).dt.normalize()
    horizon = asof + pd.Timedelta(days=_HORIZON_DAYS)
    after = sorted(e for e in defn["exp"].unique() if asof < e <= horizon)
    if not after:
        return defn.iloc[0:0]

    front_exps = after[:_N_FRONT_EXPIRIES]
    front0 = front_exps[0]
    back_candidates = [e for e in after if (e - front0).days >= _BACK_GAP_DAYS]
    target = asof + pd.Timedelta(days=_BACK_TARGET_DAYS)
    back_exp = (
        min(back_candidates, key=lambda e: abs((e - target).days)) if back_candidates else None
    )

    lo_f, hi_f = spot * (1 - _STRIKE_WINDOW), spot * (1 + _STRIKE_WINDOW)
    front = defn[defn["exp"].isin(front_exps) & defn["strike_price"].between(lo_f, hi_f)]
    parts = [front]
    if back_exp is not None and back_exp not in front_exps:
        lo_b, hi_b = spot * (1 - _BACK_WINDOW), spot * (1 + _BACK_WINDOW)
        back = defn[(defn["exp"] == back_exp) & defn["strike_price"].between(lo_b, hi_b)]
        parts.append(back)
    return pd.concat(parts)


# ── Chain assembly ───────────────────────────────────────────────────────────


def _consolidate(bars: pd.DataFrame) -> pd.DataFrame:
    """Collapse OPRA per-publisher ``ohlcv-1d`` rows to one close per symbol.

    OPRA reports one bar per participating venue, so a symbol-day appears several
    times. The most-liquid venue's close is taken as the consolidated mark.
    """
    if bars.empty:
        return bars
    idx = bars.groupby("symbol")["volume"].idxmax()
    return bars.loc[idx, ["symbol", "close"]].reset_index(drop=True)


def _to_chain(
    closes: pd.DataFrame, meta: pd.DataFrame, asof: pd.Timestamp, spot: float, r: float
) -> pd.DataFrame:
    """Map consolidated closes + instrument metadata onto ``CHAIN_COLUMNS``."""
    df = closes.merge(
        meta[["raw_symbol", "instrument_class", "strike_price", "exp"]],
        left_on="symbol",
        right_on="raw_symbol",
        how="inner",
    )
    df = df[(df["close"] > 0) & (df["exp"] > asof)]
    if df.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    t = (df["exp"] - asof).dt.days / 365.0
    iv = [
        implied_vol(c, spot, k, ti, r, right)
        for c, k, ti, right in zip(
            df["close"], df["strike_price"], t, df["instrument_class"], strict=True
        )
    ]
    return pd.DataFrame(
        {
            "expiry": df["exp"].values,
            "strike": df["strike_price"].astype(float).values,
            "right": df["instrument_class"].values,
            "bid": df["close"].astype(float).values,  # no pre-2023 NBBO; close on both sides
            "ask": df["close"].astype(float).values,
            "iv": iv,
            "open_interest": np.nan,
        },
        columns=CHAIN_COLUMNS,
    )


def _cache_path(ticker: str, asof: pd.Timestamp) -> Path:
    return _CACHE_ROOT / ticker / f"{asof.strftime('%Y-%m-%d')}_chain.parquet"


def _save(path: Path, chain: pd.DataFrame) -> None:
    """Write a resolved chain (possibly empty) to its cache slot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    chain.to_parquet(path, index=False)


# ── Public chain fetcher ─────────────────────────────────────────────────────


def fetch_option_chain(
    ticker: str,
    asof: str,
    horizon_days: int = _HORIZON_DAYS,
    strike_window: float = _STRIKE_WINDOW,
    spot: float | None = None,
    r: float = 0.0,
) -> pd.DataFrame:
    """Event-scoped option chain for ``ticker`` as of ``asof`` (YYYY-MM-DD).

    Drop-in for ``options.fetch_option_chain`` with the same return schema, backed
    by OPRA daily bars with locally inverted ``iv``. The chain carries the nearest
    front expiries (with wing strikes) plus an ATM back-month expiry, which is what
    the event features and execution-expiry selection need. Resolved chains are
    cached under ``data/processed/databento`` and re-read on subsequent calls, so a
    given ticker-date is billed at most once.

    Parameters
    ----------
    ticker : str
        Underlying ticker (parent symbology ``<ticker>.OPT`` is used internally).
    asof : str
        As-of date (``YYYY-MM-DD``); within dataset coverage (2013-04-01 onward).
    horizon_days, strike_window : optional
        Accepted for signature compatibility; the module-level chain-shape
        constants govern the actual pull.
    spot : float or None, optional
        Underlying price used to centre the strike band; resolved from the
        yfinance close on or before ``asof`` when ``None``.
    r : float, optional
        Risk-free rate for the local IV inversion. Defaults to ``0.0``.

    Returns
    -------
    pandas.DataFrame
        Chain with ``CHAIN_COLUMNS``; ``open_interest`` is NaN. Empty (correctly
        typed) when spot or the instrument universe cannot be resolved.
    """
    asof_ts = pd.Timestamp(asof).normalize()
    cache = _cache_path(ticker, asof_ts)
    if cache.exists():
        return pd.read_parquet(cache)

    if spot is None:
        spot = _spot_on_or_before(ticker, asof_ts)
    chain = pd.DataFrame(columns=CHAIN_COLUMNS)
    if spot and spot == spot:  # NaN-safe
        start = asof_ts.strftime("%Y-%m-%d")
        end = (asof_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        defn = _get_df("definition", [f"{_opra_root(ticker)}.OPT"], start, end, "parent")
        if not defn.empty:
            meta = _select_instruments(defn, asof_ts, spot)
            if not meta.empty:
                bars = _get_df("ohlcv-1d", meta["raw_symbol"].tolist(), start, end, "raw_symbol")
                chain = _to_chain(_consolidate(bars), meta, asof_ts, spot, r)

    _save(cache, chain)
    return chain


def prefetch_event(ticker: str, entry: str, exit_: str, r: float = 0.0) -> None:
    """Populate the entry and exit chain caches for one event in two API calls.

    The per-day :func:`fetch_option_chain` makes two calls (definition + ohlcv)
    each, so a four-leg event build is four calls. This collapses an event to one
    ``definition`` call (the instrument set is shared across the one-night hold)
    plus one ranged ``ohlcv-1d`` call covering ``entry``..``exit``, writing both
    days' chains to the same cache that ``fetch_option_chain`` reads. At ~20s per
    call in a constrained network this roughly halves a bulk build, and it is
    resumable: an event whose two caches already exist is skipped.

    Parameters
    ----------
    ticker : str
        Underlying ticker.
    entry, exit_ : str
        Entry and exit dates (``YYYY-MM-DD``); ``exit_`` is on or after ``entry``.
    r : float, optional
        Risk-free rate for the local IV inversion. Defaults to ``0.0``.
    """
    entry_ts = pd.Timestamp(entry).normalize()
    exit_ts = pd.Timestamp(exit_).normalize()
    ep, xp = _cache_path(ticker, entry_ts), _cache_path(ticker, exit_ts)
    if ep.exists() and xp.exists():
        return

    empty = pd.DataFrame(columns=CHAIN_COLUMNS)
    spot = _spot_on_or_before(ticker, entry_ts)
    if not (spot and spot == spot):  # NaN-safe: no spot -> cache empties, do not re-pull
        _save(ep, empty)
        _save(xp, empty)
        return

    start = entry_ts.strftime("%Y-%m-%d")
    defn = _get_df(
        "definition",
        [f"{_opra_root(ticker)}.OPT"],
        start,
        (entry_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "parent",
    )
    meta = _select_instruments(defn, entry_ts, spot) if not defn.empty else empty
    if meta.empty:
        _save(ep, empty)
        _save(xp, empty)
        return

    bars = _get_df(
        "ohlcv-1d",
        meta["raw_symbol"].tolist(),
        start,
        (exit_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "raw_symbol",
    )
    if not bars.empty:
        bars = bars.reset_index()
        bars["_d"] = pd.to_datetime(bars["ts_event"]).dt.tz_localize(None).dt.normalize()
    for asof, path in ((entry_ts, ep), (exit_ts, xp)):
        day = bars[bars["_d"] == asof] if not bars.empty else bars
        chain = _to_chain(_consolidate(day), meta, asof, spot, r) if len(day) else empty
        _save(path, chain)
