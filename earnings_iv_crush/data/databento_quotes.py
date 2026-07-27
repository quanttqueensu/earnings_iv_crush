"""
databento_quotes.py
Quote-marked option chains from OPRA consolidated BBO (``cbbo-1m``).

Why this exists
---------------
``data.databento_options`` marks off ``ohlcv-1d``, the daily closing *trade*. On a thin
strike that print can be hours old, and the staleness is asymmetric across a strike's
two legs, so the straddle it produces can sit below its own intrinsic value ``|S - K|``.
On the q=0.80 mega-cap book that happened on 20.1% of exit marks, concentrated in the
large-move tercile, and it is directional: an understated buy-back flatters a short.

That module's header states NBBO on OPRA begins 2023-03-28, which forced the trade-based
design. The claim is true only of ``cmbp-1`` and ``tcbbo``. **``cbbo-1m`` - consolidated
best bid and offer, sampled once a minute - starts 2013-04-01**, verified against
``metadata.get_dataset_range``, and therefore covers the entire sample. Quotes were
available the whole time.

Consolidated quotes are also *cheaper* than the daily bars, which is counter-intuitive
until you notice that ``ohlcv-1d`` bills one bar per participating OPRA venue per
symbol-day (hence ``databento_options._consolidate``), whereas ``cbbo-1m`` is a single
consolidated stream. Measured on real filtered symbol lists: $0.0124/event against
$0.0590.

Marking convention
------------------
Two marks are produced from the same pulled bars, at no extra data cost:

* **snapshot** - the last bar at or before 15:59 ET. This is the headline. It is a
  price that existed at a moment, so it is the one a systematic book could have traded
  near, and it is like-for-like against the close-marked history it replaces.
* **window** - the median mid over 15:45-15:59 ET, carried as ``mid_window``. Not a
  tradeable price, but the gap between the two is a per-contract staleness measure that
  costs nothing to compute and needs no second pull.

Both sides of the quote are genuine here, so ``bid != ask`` and every consumer that
reads a side explicitly (see ``engine.quotes``) starts behaving differently from the
close-marked path. That is the point.

Cost discipline
---------------
The instrument set is rebuilt from the chains already cached by
``data.databento_options`` rather than re-pulling ``definition``, which is what makes a
full re-mark of the existing book cost about $13 rather than $15. Every resolved chain
is cached to its own root, so the trade-marked and quote-marked books coexist and can be
compared rather than one silently overwriting the other.

Requires ``DATABENTO_API_KEY`` in ``.env``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..engine.greeks import implied_vol
from .config import require
from .databento_options import _opra_root, _spot_on_or_before
from .options import CHAIN_COLUMNS

_DATASET = "OPRA.PILLAR"
_SCHEMA = "cbbo-1m"
_CACHE_ROOT = Path("data/processed/databento_quotes")

# Exchange timezone. OPRA timestamps arrive in UTC; the session boundary has to be
# resolved in local exchange time or the mark lands an hour out for half the year.
_EXCHANGE_TZ = "America/New_York"

# The headline mark is the last consolidated quote at or before this local time. 15:59
# rather than 16:00 because the closing auction prints at 16:00 and the minute bar
# stamped 16:00 straddles it.
_SNAPSHOT_TIME = "15:59"
# The staleness diagnostic averages over this trailing window on the same session.
_WINDOW_START = "15:45"

_client_cache: Any = None


def _client() -> Any:
    """Return a cached ``databento.Historical`` client (lazy import + key)."""
    global _client_cache
    if _client_cache is None:
        import databento as db

        _client_cache = db.Historical(require("DATABENTO_API_KEY"))
    return _client_cache


# ── Symbology ────────────────────────────────────────────────────────────────


def osi_symbol(root: str, expiry: pd.Timestamp, right: str, strike: float) -> str:
    """Build an OSI option symbol.

    The OCC format is a six-character root left-justified and space padded, then
    ``YYMMDD``, then ``C``/``P``, then the strike in thousandths as eight digits.
    Databento's OPRA ``raw_symbol`` uses exactly this, so a chain already on disk can
    be turned back into a billable symbol list without paying for ``definition`` again.
    """
    return (
        f"{root:<6}{pd.Timestamp(expiry).strftime('%y%m%d')}"
        f"{right.upper()[0]}{int(round(float(strike) * 1000)):08d}"
    )


def symbols_for_chain(
    ticker: str, chain: pd.DataFrame, asof: pd.Timestamp | None = None
) -> list[str]:
    """The OSI symbols covering every contract in a cached chain.

    ``asof`` resolves the root against the ticker's own history, so a pre-2022 Meta event
    builds ``FB`` symbols rather than ``META`` ones that OPRA never listed.
    """
    root = _opra_root(ticker, asof)
    return sorted(
        {
            osi_symbol(root, e, r, k)
            for e, k, r in zip(chain["expiry"], chain["strike"], chain["right"], strict=True)
        }
    )


# ── Quote extraction ─────────────────────────────────────────────────────────


def _numeric_col(frame: pd.DataFrame, column: str) -> pd.Series:
    """A float Series for ``column``, all-NaN when the feed omitted it."""
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _session_marks(bars: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Snapshot and window marks per symbol for one session.

    ``bars`` is the raw ``cbbo-1m`` frame, indexed by ``ts_recv`` in UTC. Converting to
    exchange-local time before slicing is not cosmetic: the UTC offset moves by an hour
    across daylight saving, so a fixed UTC cut would mark half the sample at 14:59 local
    and the other half at 15:59.
    """
    if bars.empty:
        return pd.DataFrame()

    local = bars.copy()
    idx = pd.DatetimeIndex(local.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(_EXCHANGE_TZ)
    local.index = idx
    session = pd.Timestamp(asof).normalize().tz_localize(_EXCHANGE_TZ)
    day = local[idx.normalize() == session]
    if day.empty:
        return pd.DataFrame()

    bid = _numeric_col(day, "bid_px_00")
    ask = _numeric_col(day, "ask_px_00")
    day = day.assign(
        _bid=bid, _ask=ask, _mid=np.where(bid.notna() & ask.notna(), (bid + ask) / 2, np.nan)
    )

    day_idx = pd.DatetimeIndex(day.index)
    cut = session + pd.Timedelta(_SNAPSHOT_TIME + ":59")
    win = session + pd.Timedelta(_WINDOW_START + ":00")

    snap_rows = day[day_idx <= cut]
    # Last quote at or before the cut, per symbol: sort then take the tail of each group
    # so a symbol that stopped quoting mid-session still marks on its final quote rather
    # than dropping out entirely.
    snap = (
        snap_rows.sort_index()
        .groupby("symbol")
        .agg(bid=("_bid", "last"), ask=("_ask", "last"), last_quote=("_bid", "size"))
    )
    window = (
        day[(day_idx >= win) & (day_idx <= cut)]
        .groupby("symbol")
        .agg(mid_window=("_mid", "median"), n_window_bars=("_mid", "count"))
    )
    return snap.join(window, how="left")


def _chain_from_marks(
    marks: pd.DataFrame, meta: pd.DataFrame, asof: pd.Timestamp, spot: float, r: float
) -> pd.DataFrame:
    """Map per-symbol quote marks plus contract metadata onto ``CHAIN_COLUMNS``."""
    if marks.empty or meta.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    df = meta.merge(marks, left_on="symbol", right_index=True, how="inner")
    df = df[df["expiry"] > pd.Timestamp(asof)]
    if df.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    t = (df["expiry"] - pd.Timestamp(asof)).dt.days / 365.0
    mid = np.where(
        df["bid"].notna() & df["ask"].notna(),
        (df["bid"] + df["ask"]) / 2.0,
        df["bid"].fillna(df["ask"]),
    )
    iv = [
        implied_vol(m, spot, k, ti, r, right)
        for m, k, ti, right in zip(mid, df["strike"], t, df["right"], strict=True)
    ]
    out = pd.DataFrame(
        {
            "expiry": df["expiry"].to_numpy(),
            "strike": df["strike"].astype(float).to_numpy(),
            "right": df["right"].to_numpy(),
            "bid": df["bid"].astype(float).to_numpy(),
            "ask": df["ask"].astype(float).to_numpy(),
            "iv": iv,
            "open_interest": np.nan,
        },
        columns=CHAIN_COLUMNS,
    )
    # Carried past the canonical schema for the staleness gate and the measured-spread
    # cost path; consumers keyed on CHAIN_COLUMNS ignore them.
    out["mid_window"] = df["mid_window"].to_numpy()
    out["n_window_bars"] = df["n_window_bars"].to_numpy()
    return out


# ── Cache ────────────────────────────────────────────────────────────────────


def cache_path(ticker: str, asof: pd.Timestamp) -> Path:
    return _CACHE_ROOT / ticker / f"{pd.Timestamp(asof).strftime('%Y-%m-%d')}_chain.parquet"


def _save(path: Path, chain: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chain.to_parquet(path, index=False)


# ── Public API ───────────────────────────────────────────────────────────────


def get_cost(symbols: list[str], start: str, end: str) -> float:
    """Retried ``metadata.get_cost`` in USD for a raw-symbol quote request. Free."""
    if not symbols:
        return 0.0
    return float(
        _client().metadata.get_cost(
            dataset=_DATASET,
            symbols=symbols,
            schema=_SCHEMA,
            start=start,
            end=end,
            stype_in="raw_symbol",
        )
    )


def _chain_from_definitions(
    ticker: str, asof: pd.Timestamp, spot: float | None, *, dry_run: bool = False
) -> pd.DataFrame:
    """A minimal ``expiry``/``strike``/``right`` frame from OPRA instrument definitions.

    Only the three columns :func:`symbols_for_chain` needs are populated; this is an
    instrument list, not a priced chain. Contract selection reuses
    ``databento_options._select_instruments`` so the extension prices the same front-block
    and back-leg structure as the original book rather than a differently-shaped universe,
    which would make the two periods non-comparable.

    Parameters
    ----------
    ticker : str
        Underlying ticker.
    asof : pandas.Timestamp
        Date whose instrument set is wanted.
    spot : float or None
        Underlying price, used to centre the strike window. Returns empty when absent,
        since an uncentred window would request the entire strike ladder.
    dry_run : bool, optional
        Return empty without pulling. Definitions are billed, so a dry run must not call.

    Returns
    -------
    pandas.DataFrame
        Columns ``expiry``, ``strike``, ``right``; empty when unavailable.
    """
    from . import databento_options as dbo

    if dry_run or spot is None or not (spot == spot):
        return pd.DataFrame(columns=["expiry", "strike", "right"])
    start = asof.strftime("%Y-%m-%d")
    end = (asof + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    defn = dbo._get_df("definition", [f"{dbo._opra_root(ticker, asof)}.OPT"], start, end, "parent")
    if defn.empty:
        return pd.DataFrame(columns=["expiry", "strike", "right"])
    meta = dbo._select_instruments(defn, asof, float(spot))
    if meta.empty:
        return pd.DataFrame(columns=["expiry", "strike", "right"])
    out = pd.DataFrame(
        {
            "expiry": pd.to_datetime(meta["exp"]),
            "strike": pd.to_numeric(meta["strike_price"], errors="coerce"),
            # Taken as-is, matching how the trade path assigns `right`. Anything that is
            # not a call or a put is dropped rather than coerced: a mislabelled right
            # would build a valid-looking OSI symbol for a contract that does not exist,
            # and the pull would pay for it and return nothing.
            "right": meta["instrument_class"],
        }
    )
    return out[out["right"].isin(("C", "P"))].dropna(subset=["strike", "expiry"])


def prefetch_event(
    ticker: str,
    entry: str,
    exit_: str,
    *,
    source_chain_dir: Path | None = None,
    allow_definition: bool = False,
    spot_entry: float | None = None,
    spot_exit: float | None = None,
    r: float = 0.0,
    dry_run: bool = False,
) -> float:
    """Populate the quote-marked entry and exit chain caches for one event.

    The instrument set is taken from the trade-marked chain already on disk for the
    entry date, so the same contracts are marked and the two books differ only in how
    they were priced. Returns the USD billed (0.0 when cached or dry-run), so a caller
    can keep a running spend against a hard cap.

    Parameters
    ----------
    ticker : str
        Underlying ticker.
    entry, exit_ : str
        Entry and exit dates (``YYYY-MM-DD``).
    source_chain_dir : Path or None, optional
        Root of the trade-marked chain cache supplying the instrument set. Defaults to
        ``data/processed/databento``.
    allow_definition : bool, optional
        When no cached chain exists, pull OPRA instrument definitions to build the symbol
        list instead of skipping the event. Off by default because definitions are billed
        separately; required for events predating the trade-marked book.
    r : float, optional
        Rate for the local IV inversion. Defaults to ``0.0``; the measured error from
        this assumption is 0.03% of credit (``scripts/research_pricing_model_error.py``).
    dry_run : bool, optional
        Price the request and return the estimate without pulling.

    Returns
    -------
    float
        USD billed for this event.
    """
    from .databento_options import _CACHE_ROOT as TRADE_ROOT

    entry_ts, exit_ts = pd.Timestamp(entry).normalize(), pd.Timestamp(exit_).normalize()
    ep, xp = cache_path(ticker, entry_ts), cache_path(ticker, exit_ts)
    if ep.exists() and xp.exists():
        return 0.0

    root = Path(source_chain_dir) if source_chain_dir is not None else TRADE_ROOT
    src = root / ticker / f"{entry_ts:%Y-%m-%d}_chain.parquet"
    empty = pd.DataFrame(columns=CHAIN_COLUMNS)
    start = entry_ts.strftime("%Y-%m-%d")
    end = (exit_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    source = pd.read_parquet(src) if src.exists() else empty
    if source.empty:
        # No trade-marked chain to borrow the instrument set from. That is the normal case
        # for any event predating the trade-marked book, so fall back to pulling the
        # instrument definitions and selecting contracts the same way the trade path does.
        # Falling back rather than returning empty is what lets the sample extend backwards;
        # returning empty here would silently drop every pre-2019 event.
        if allow_definition:
            if spot_entry is None or not (spot_entry == spot_entry):
                # Caching an empty chain here would mark the event permanently "done" and
                # drop it from every later build, when the only thing missing is a spot the
                # caller failed to supply. Refuse loudly and leave the cache untouched so a
                # rerun retries it.
                print(f"  SKIP {ticker} {entry_ts:%Y-%m-%d}: no spot, cannot centre strikes")
                return 0.0
            source = _chain_from_definitions(ticker, entry_ts, spot_entry, dry_run=dry_run)
        if source.empty:
            _save(ep, empty)
            _save(xp, empty)
            return 0.0

    symbols = symbols_for_chain(ticker, source, entry_ts)
    estimate = get_cost(symbols, start, end)
    if dry_run:
        return estimate

    data = _client().timeseries.get_range(
        dataset=_DATASET,
        symbols=symbols,
        schema=_SCHEMA,
        start=start,
        end=end,
        stype_in="raw_symbol",
    )
    bars = data.to_df()

    meta = (
        source[["expiry", "strike", "right"]]
        .drop_duplicates()
        .assign(
            symbol=lambda d: [
                osi_symbol(_opra_root(ticker, entry_ts), e, r_, k)
                for e, k, r_ in zip(d["expiry"], d["strike"], d["right"], strict=True)
            ]
        )
    )
    for asof, path, given in ((entry_ts, ep, spot_entry), (exit_ts, xp, spot_exit)):
        # Prefer the caller's spot. The event table already carries both, on the raw
        # unadjusted basis that matches OPRA's historical strikes, and re-deriving them
        # means two yfinance round trips per event - about 2,100 network calls over the
        # book, which dominates the runtime and buys nothing.
        day_spot = float(given) if given is not None and given == given else None
        if day_spot is None:
            day_spot = _spot_on_or_before(ticker, asof)
        marks = _session_marks(bars, asof) if not bars.empty else pd.DataFrame()
        chain = (
            _chain_from_marks(marks, meta, asof, float(day_spot), r)
            if not marks.empty and day_spot and day_spot == day_spot
            else empty
        )
        _save(path, chain)
    return estimate


def fetch_option_chain(ticker: str, asof: str) -> pd.DataFrame:
    """Read a quote-marked chain from cache. Never pulls; use :func:`prefetch_event`.

    Drop-in for ``options.fetch_option_chain`` in shape, but deliberately read-only:
    every pull on this path is billed, so it happens in one place under an explicit cap
    rather than being triggered incidentally by a consumer.
    """
    path = cache_path(ticker, pd.Timestamp(asof).normalize())
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=CHAIN_COLUMNS)
