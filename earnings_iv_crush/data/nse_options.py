"""
nse_options.py
Historical Indian single-name option chains via the free NSE F&O bhavcopy.

NSE publishes a daily derivatives bhavcopy - the end-of-day settlement file for
every F&O contract - free and without a key. From 8 July 2024 it is the UDiFF
("Unified Distilled File Format") whole-segment CSV, one zipped file per session
covering all stock and index options and futures. This adapter reads the UDiFF
stock-option rows (``FinInstrmTp == 'STO'``) and serves them through the canonical
chain interface, so the whole US backtest engine runs on Indian names unchanged.

The UDiFF file is self-contained: each option row carries the settlement price
(``SttlmPric``, the daily mark), the open interest (``OpnIntrst``) and the
underlying's own price (``UndrlygPric``). So, unlike the legacy DERIVATIVES
bhavcopy, no separate spot feed is needed - spot, mark and OI come from the one
file. There is no bid/ask (it is a settlement file), so ``bid``/``ask`` both
carry the settlement mark (``features._with_mid`` reads it as the mid) and
execution spread lives in ``engine.costs``, exactly as for the Alpaca/DoltHub
close-as-mark adapters. Implied vol is inverted locally from the settlement mark
via ``engine.greeks.implied_vol``.

Schema mapping (UDiFF ``STO`` rows -> ``options.CHAIN_COLUMNS``)::

    XpryDt      -> expiry     StrkPric   -> strike    OptnTp (CE|PE) -> right (C|P)
    SttlmPric   -> bid, ask   OpnIntrst  -> open_interest
    UndrlygPric -> spot (for the local BS inversion, not a returned column)

Coverage is the UDiFF era only (8 July 2024 onward). The pre-July-2024 legacy
``fo<DDMMMYYYY>bhav.csv`` uses different columns and carries no underlying price,
so it needs an external spot join; it is a documented follow-on, not wired here.

Caveats, by design:
* Settlement mark, not a traded price, on both sides - no NBBO, so the spread is
  synthetic; the cost model supplies the real spread.
* Dividend yield is not modelled (``q = 0``), matching the other adapters. The
  term gate reads the front-minus-back ATM IV *spread*, in which a flat carry
  error is largely common-mode, so this is acceptable for the signal test.
* Indian stock options are European and physically settled; the near-expiry
  contract behaves accordingly, but the ATM term spread the gate uses is robust
  to this.

The result matches ``options.CHAIN_COLUMNS`` exactly, so it is a drop-in for the
``fetch_chain`` argument of ``data_pipeline.build_event_dataset``,
``historical_surfaces.build_surface_panel`` and ``real_events.build_execution_events``.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from ..engine.greeks import implied_vol
from .options import CHAIN_COLUMNS

# Public UDiFF F&O bhavcopy: one zipped whole-segment CSV per session.
_UDIFF_URL = (
    "https://nsearchives.nseindia.com/content/fo/" "BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)
# NSE's archive server rejects non-browser agents; a desktop UA is required.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 30
_MAX_RETRIES = 5
_RETRY_BACKOFF = 2.0  # seconds, multiplied by the attempt number
_UDIFF_START = pd.Timestamp("2024-07-08")  # first UDiFF session

# NSE symbols are alphanumerics plus ``&``/``-``/``.`` (M&M, BAJAJ-AUTO, NIFTY).
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9&.\-]{1,20}$")

# In-process cache of parsed per-session stock-option frames, keyed by the
# YYYYMMDD session string, so a panel that revisits a date parses it once.
_DAILY_CACHE: dict[str, pd.DataFrame] = {}

# Normalised per-session columns produced by ``_parse_sto``.
_STO_COLUMNS = ["ticker", "expiry", "strike", "right", "mark", "open_interest", "spot"]


# ── HTTP transport ───────────────────────────────────────────────────────────


def _download_fo_zip(yyyymmdd: str) -> bytes | None:
    """Raw UDiFF F&O bhavcopy zip bytes for one session, or ``None``.

    Returns ``None`` for a 404 (a non-trading day, or a session not yet
    published), so the caller can step back to the previous session. Transient
    failures (dropped connections, timeouts, 5xx) are retried with a linear
    backoff. Isolated so tests monkeypatch it without the network.
    """
    url = _UDIFF_URL.format(yyyymmdd=yyyymmdd)
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        else:
            if r.status_code == 404:
                return None  # no session file (holiday/weekend/not-yet-published)
            if r.status_code < 500:
                r.raise_for_status()
                return r.content
            last_error = requests.HTTPError(f"{r.status_code} server error: {url}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    assert last_error is not None  # the loop always records a failure before here
    raise last_error


# ── Parsing ──────────────────────────────────────────────────────────────────


def _parse_sto(zip_bytes: bytes) -> pd.DataFrame:
    """Parse a UDiFF zip into normalised stock-option rows (``_STO_COLUMNS``).

    Keeps only ``FinInstrmTp == 'STO'`` (single-name stock options) with a
    ``CE``/``PE`` right, maps the columns onto the canonical names and coerces
    types. The mark is the settlement price, falling back to the close when the
    settlement is missing; rows with a non-positive mark, spot or strike are
    dropped so the inversion never sees a degenerate input.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        raw = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype=str)
    raw.columns = [c.strip() for c in raw.columns]

    df = raw[raw["FinInstrmTp"].str.strip() == "STO"].copy()
    df = df[df["OptnTp"].str.strip().isin(["CE", "PE"])]
    if df.empty:
        return pd.DataFrame(columns=_STO_COLUMNS)

    settle = pd.to_numeric(df["SttlmPric"], errors="coerce")
    close = pd.to_numeric(df["ClsPric"], errors="coerce")
    out = pd.DataFrame(
        {
            "ticker": df["TckrSymb"].str.strip(),
            "expiry": pd.to_datetime(df["XpryDt"], errors="coerce"),
            "strike": pd.to_numeric(df["StrkPric"], errors="coerce"),
            "right": df["OptnTp"].str.strip().map({"CE": "C", "PE": "P"}),
            # Settlement is the official daily mark; a stale/zero settlement on an
            # untraded strike falls back to the close so the ATM legs survive.
            "mark": settle.where(settle > 0, close),
            "open_interest": pd.to_numeric(df["OpnIntrst"], errors="coerce"),
            "spot": pd.to_numeric(df["UndrlygPric"], errors="coerce"),
        },
        columns=_STO_COLUMNS,
    )
    good = (out["mark"] > 0) & (out["spot"] > 0) & (out["strike"] > 0)
    return out[good & out["expiry"].notna()].reset_index(drop=True)


def _session_frame(yyyymmdd: str, cache_dir: str | Path | None) -> pd.DataFrame:
    """Normalised stock-option frame for one session, memoised and disk-cached.

    The raw zip is cached under ``<cache_dir>/nse_fo`` so re-runs never
    re-download it; the parsed frame is memoised in-process for the run.
    """
    if yyyymmdd in _DAILY_CACHE:
        return _DAILY_CACHE[yyyymmdd]

    root = Path(cache_dir) if cache_dir is not None else Path("data/processed")
    zdir = root / "nse_fo"
    zpath = zdir / f"BhavCopy_NSE_FO_{yyyymmdd}.csv.zip"

    if zpath.exists():
        zip_bytes: bytes | None = zpath.read_bytes()
    else:
        zip_bytes = _download_fo_zip(yyyymmdd)
        if zip_bytes is not None:
            zdir.mkdir(parents=True, exist_ok=True)
            zpath.write_bytes(zip_bytes)

    frame = _parse_sto(zip_bytes) if zip_bytes is not None else pd.DataFrame(columns=_STO_COLUMNS)
    _DAILY_CACHE[yyyymmdd] = frame
    return frame


# ── Public spot series ───────────────────────────────────────────────────────


def fetch_underlying_ohlcv(
    ticker: str,
    start: str,
    end: str,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Daily underlying close series for an NSE name, from the bhavcopy itself.

    Drop-in for ``equities.fetch_equity_ohlcv`` (same ``date``/``open``/``high``/
    ``low``/``close``/``volume`` schema) but sourced from the F&O bhavcopy's own
    ``UndrlygPric``. This is the *raw* underlying price for each session, so it
    matches the raw option strikes in the same file - unlike a yfinance series,
    which back-adjusts for later splits/bonuses and would misplace the ATM strike
    on any name with a corporate action after the event. Only ``close`` is
    meaningful (the file carries one underlying price per session); the OHLC
    columns repeat it and ``volume`` is NaN. ``end`` is inclusive.

    Parameters
    ----------
    ticker : str
        NSE symbol in bhavcopy form (e.g. ``RELIANCE``).
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form; clipped to the UDiFF era.
    cache_dir : str or Path or None, optional
        Root for the raw-zip disk cache; defaults to ``data/processed``.

    Returns
    -------
    pandas.DataFrame
        Columns ``date``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        Empty (correctly typed) when no session carries the ticker.
    """
    if not _SYMBOL_RE.match(ticker):
        raise ValueError(f"unsupported NSE symbol: {ticker!r}")
    cols = ["date", "open", "high", "low", "close", "volume"]
    lo = max(pd.Timestamp(start), _UDIFF_START)
    hi = pd.Timestamp(end)
    dates: list[pd.Timestamp] = []
    closes: list[float] = []
    for day in pd.bdate_range(lo, hi):
        frame = _session_frame(day.strftime("%Y%m%d"), cache_dir)
        if frame.empty:
            continue  # holiday / non-trading session
        sub = frame[frame["ticker"] == ticker]
        if sub.empty:
            continue
        dates.append(day)
        closes.append(float(sub["spot"].iloc[0]))
    if not dates:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [float("nan")] * len(dates),
        },
        columns=cols,
    )


# ── Public universe ──────────────────────────────────────────────────────────


def fo_underlyings(
    asof: str | None = None,
    cache_dir: str | Path | None = None,
    lookback_days: int = 7,
) -> list[str]:
    """Every NSE single-stock-option underlying, from the latest session file.

    Reads the distinct ``STO`` ticker symbols from the most recent bhavcopy on or
    before ``asof`` (default: today), so the universe is exactly the names that
    actually carry stock options that session - self-consistent with the chain
    adapter, and always current. Returns ``[]`` if no session resolves in the
    lookback window.

    Parameters
    ----------
    asof : str or None, optional
        Session date (``YYYY-MM-DD``); defaults to today.
    cache_dir : str or Path or None, optional
        Root for the raw-zip disk cache; defaults to ``data/processed``.
    lookback_days : int, optional
        Calendar days to step back to the latest session. Defaults to ``7``.

    Returns
    -------
    list[str]
        Sorted distinct stock-option underlyings (bhavcopy ``TckrSymb`` form).
    """
    asof_ts = pd.Timestamp(asof) if asof else pd.Timestamp.today().normalize()
    for back in range(lookback_days + 1):
        day = asof_ts - pd.Timedelta(days=back)
        if day < _UDIFF_START:
            break
        frame = _session_frame(day.strftime("%Y%m%d"), cache_dir)
        if not frame.empty:
            return sorted(frame["ticker"].unique().tolist())
    return []


# ── Public chain fetcher ─────────────────────────────────────────────────────


def fetch_option_chain(
    ticker: str,
    asof: str,
    horizon_days: int = 90,
    strike_window: float = 0.20,
    r: float = 0.0,
    spot: float | None = None,
    lookback_days: int = 5,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """ATM-centred option chain for ``ticker`` as of ``asof`` (YYYY-MM-DD).

    Drop-in for ``options.fetch_option_chain`` with the same return schema, but
    backed by the free NSE UDiFF F&O bhavcopy with a locally inverted ``iv``.
    When ``asof`` is not a session (weekend/holiday) the snapshot steps back up
    to ``lookback_days`` calendar days to the most recent prior session, matching
    the DoltHub/Alpaca adapters.

    Parameters
    ----------
    ticker : str
        NSE symbol in bhavcopy form (e.g. ``RELIANCE``, ``M&M``, ``BAJAJ-AUTO``).
    asof : str
        As-of date (``YYYY-MM-DD``); must fall on/after 8 July 2024 (UDiFF era).
    horizon_days : int, optional
        Calendar days past ``asof`` to include expiries. Defaults to ``90``.
    strike_window : float, optional
        Half-width of the strike band as a fraction of spot. Defaults to ``0.20``.
    r : float, optional
        Risk-free rate for the local IV inversion. Defaults to ``0.0`` (the repo
        convention; the term gate reads a spread in which carry is common-mode).
    spot : float or None, optional
        Underlying price; taken from the file's ``UndrlygPric`` when ``None``.
        Defaults to ``None``.
    lookback_days : int, optional
        Calendar days to step back to find the latest session on/before ``asof``.
        Defaults to ``5``.
    cache_dir : str or Path or None, optional
        Root for the raw-zip disk cache; defaults to ``data/processed``.

    Returns
    -------
    pandas.DataFrame
        Chain with ``CHAIN_COLUMNS`` (real ``open_interest``). Empty (correctly
        typed) when no session resolves or the ticker is absent that day.
    """
    if not _SYMBOL_RE.match(ticker):
        raise ValueError(f"unsupported NSE symbol: {ticker!r}")
    asof_ts = pd.Timestamp(asof)
    if asof_ts < _UDIFF_START:
        raise ValueError(
            f"asof {asof} precedes the UDiFF era (from {_UDIFF_START.date()}); "
            "the legacy bhavcopy format is not wired in this adapter."
        )

    session = pd.DataFrame(columns=_STO_COLUMNS)
    for back in range(lookback_days + 1):
        day = asof_ts - pd.Timedelta(days=back)
        frame = _session_frame(day.strftime("%Y%m%d"), cache_dir)
        if not frame.empty:
            session = frame
            break

    chain = session[session["ticker"] == ticker]
    if chain.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    row_spot = spot if spot is not None else float(chain["spot"].iloc[0])
    horizon = asof_ts + pd.Timedelta(days=horizon_days)
    lo = row_spot * (1 - strike_window)
    hi = row_spot * (1 + strike_window)

    days = (chain["expiry"] - asof_ts).dt.days
    keep = (days > 0) & (chain["expiry"] <= horizon) & chain["strike"].between(lo, hi)
    chain = chain[keep]
    if chain.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    t_years = (chain["expiry"] - asof_ts).dt.days / 365.0
    ivs = [
        implied_vol(mark, row_spot, strike, t, r, right)
        for mark, strike, t, right in zip(
            chain["mark"], chain["strike"], t_years, chain["right"], strict=True
        )
    ]
    return pd.DataFrame(
        {
            "expiry": chain["expiry"].to_numpy(),
            "strike": chain["strike"].to_numpy(),
            "right": chain["right"].to_numpy(),
            "bid": chain["mark"].to_numpy(),
            "ask": chain["mark"].to_numpy(),
            "iv": ivs,
            "open_interest": chain["open_interest"].to_numpy(),
        },
        columns=CHAIN_COLUMNS,
    )
