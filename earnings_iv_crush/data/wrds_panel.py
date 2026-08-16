"""
wrds_panel.py
Point-in-time earnings-event panel from the WRDS R2 mirror (IBES + CRSP + Fama-French).

Builds the foundation panel later research pieces consume: a strictly
point-in-time analyst-surprise event table (``panel_events``) and its
supporting per-name daily CRSP/Fama-French panel (``panel_daily``), both
sourced from the QUANTT WRDS Cloudflare R2 mirror (``data/wrds_r2.py``). No
Databento credits are spent here; no Compustat ``fundq`` (this module's
calendar comes from I/B/E/S ``act_epsus``/``statsum_epsus``, not Compustat
``rdq`` as ``earnings.build_wrds_calendar`` uses).

The central hazard this module guards against is *look-ahead bias through
denormalisation*: I/B/E/S ``statsum_epsus`` carries the realised ``actual``
and ``anndats_act`` on every historical snapshot row of a fiscal period,
including snapshots recorded a year before the announcement. Every consensus
figure this module selects is taken from the single row whose ``statpers``
strictly precedes ``anndats_act`` - see :func:`_pit_select_consensus`.

The second hazard is memory: CRSP ``dsf`` stores prices/returns/volume as
decimal128, which pandas materialises as Python ``Decimal`` objects at
roughly 10x the memory of ``float64``. :func:`_read_arrow` casts decimal128
columns to float64 at the Arrow layer, before ``to_pandas()``, and
:func:`load_crsp_daily` reads year-by-year and downcasts to float32 so peak
memory never holds more than one year of the *unfiltered* CRSP universe at a
time.

References
----------
Bernard, V. L., & Thomas, J. K. (1989). Post-earnings-announcement drift:
Delayed price response or risk premium? *Journal of Accounting Research*,
27, 1-36.
Livnat, J., & Mendenhall, R. R. (2006). Comparing the post-earnings
announcement drift for surprises calculated from analyst and time series
forecasts. *Journal of Accounting Research*, 44(1), 177-205.
Frazzini, A., & Lamont, O. A. (2007). The earnings announcement premium and
trading volume. *NBER Working Paper 13090*.
Diether, K. B., Malloy, C. J., & Scherbina, A. (2002). Differences of opinion
and the cross section of stock returns. *Journal of Finance*, 57(5), 2113-2141.
Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance*,
52(1), 327-340.
Bailey, D. H., & Lopez de Prado, M. (2014). The deflated Sharpe ratio:
Correcting for selection bias, backtest overfitting, and non-normality.
*Journal of Portfolio Management*, 40(5), 94-107.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ..engine import event_study
from ..util.progress import ProgressBar
from . import wrds_r2

# ── universe / filter thresholds ──────────────────────────────────────────────
UNIVERSE_SHRCD = (10, 11)  # common shares only (excludes REITs, ADRs, units, ...)
UNIVERSE_EXCHCD = (1, 2, 3)  # NYSE, AMEX, NASDAQ
IBES_LINK_MAX_SCORE = 2  # ibcrsphist quality score: 1-2 are the reliable tiers
IBES_LINK_MIN_RETAIN = 0.70  # funnel gate: RAISE if the permno link retains less
MIN_NUMEST = 3  # minimum analysts backing a consensus estimate
MIN_PRICE = 5.0  # $, penny-stock screen at day0-1
MIN_ADV60 = 1_000_000.0  # $, 60-trading-day median dollar-volume floor
ADV60_WINDOW = 60
MAX_CONSENSUS_AGE_DAYS = 90  # stale-consensus guard: statpers must be this fresh
MIN_FINAL_EVENTS = 50_000  # acceptance floor; a lower count means something broke
CALENDAR_PAD_DAYS = 150  # calendar/CRSP pull padding before `start`, for adv60/prc_prev

FIT_END = "2011-12-31"
HOLDOUT_START = "2012-01-01"

_DECIMAL_DSF_COLS = ("bidlo", "askhi", "prc", "vol", "ret", "bid", "ask", "retx")

_MKT_OPEN, _MKT_CLOSE = dt.time(9, 30), dt.time(16, 0)


# ── the decimal128 memory trap ────────────────────────────────────────────────
def _read_arrow(
    schema: str,
    table: str,
    columns: Sequence[str] | None = None,
    filters: list | None = None,
) -> pd.DataFrame:
    """Read a mirror table, casting decimal128 -> float64 at the Arrow layer.

    CRSP (and Fama-French) store prices, returns and factor loadings as
    decimal128, which pandas materialises as Python ``Decimal`` objects on
    ``to_pandas()`` - roughly 10x the memory of ``float64`` and unusable in
    vectorised numpy arithmetic. Casting at the Arrow layer, before
    ``to_pandas()``, avoids ever materialising the Decimal representation.
    Measured on one year of ``crsp_a_stock.dsf``: 1.82M rows, 1,267 MB via
    ``to_pandas()`` directly, ~125 MB with this cast applied first.

    Parameters
    ----------
    schema, table : str
        Mirror location, e.g. ``("crsp_a_stock", "dsf")``.
    columns : sequence of str, optional
        Column projection, pushed to the Arrow read.
    filters : list, optional
        PyArrow DNF predicate, pushed to row-group level.

    Returns
    -------
    pandas.DataFrame
    """
    tbl = pq.read_table(
        wrds_r2._table_path(schema, table),
        columns=list(columns) if columns is not None else None,
        filters=filters,
        filesystem=wrds_r2._fs(),
    )
    for i, f in enumerate(tbl.schema):
        if pa.types.is_decimal(f.type):
            tbl = tbl.set_column(i, f.name, pc.cast(tbl.column(i), pa.float64()))
    return tbl.to_pandas()


# ── session classification ────────────────────────────────────────────────────
def session_from_time(t: dt.time | None) -> tuple[str, str]:
    """
    Classify an I/B/E/S announcement time into a reporting session.

    Reimplemented independently of ``earnings._session_from_ibes_time`` (the
    plan for this module explicitly calls for a standalone implementation
    rather than an import, so this module has no dependency on the
    Compustat-``rdq``-based calendar path).

    After the close (``>= 16:00``) is ``"amc"``; before the open
    (``<= 09:30``) is ``"bmo"``; in between is ``"dmh"``. A missing time or
    the ``00:00:00`` unknown-marker defaults to ``"amc"``, flagged
    ``"default_unknown"`` (conservative: assumes the reaction is not
    tradeable same-day).

    Parameters
    ----------
    t : datetime.time or None

    Returns
    -------
    tuple of (session, source)
    """
    if not isinstance(t, dt.time) or t == dt.time(0, 0):
        return "amc", "default_unknown"
    if t >= _MKT_CLOSE:
        return "amc", "ibes_time"
    if t <= _MKT_OPEN:
        return "bmo", "ibes_time"
    return "dmh", "ibes_time"


def _day0_vectorized(anndats: pd.Series, session: pd.Series, cal: np.ndarray) -> np.ndarray:
    """Vectorised equivalent of ``event_study.event_day0``, batch form.

    A Python-loop call to ``event_day0`` per event (re-sorting the calendar
    dict on every call) does not scale to a several-hundred-thousand-row
    panel; this uses ``np.searchsorted`` against the sorted ``cal`` array
    directly (``bisect_left``/``bisect_right`` are exactly what
    ``np.searchsorted`` computes in bulk). Agreement with the scalar
    ``event_day0`` on a sample is asserted in the test suite.
    """
    d = pd.to_datetime(anndats).to_numpy().astype("datetime64[D]")
    cal_d = cal.astype("datetime64[D]")
    is_bmo = (session == "bmo").to_numpy()
    left = np.searchsorted(cal_d, d, side="left")
    right = np.searchsorted(cal_d, d, side="right")
    ordinals = np.where(is_bmo, left, right)
    if (ordinals >= len(cal_d)).any():
        raise ValueError(
            "event date falls beyond the trading calendar's coverage; "
            "extend the ff_all pull window (increase `end` or CALENDAR_PAD_DAYS)"
        )
    return ordinals


# ── loaders ────────────────────────────────────────────────────────────────────
def load_universe(start: str, end: str) -> pd.DataFrame:
    """
    CRSP ``dsenames`` name-history rows overlapping ``[start, end]``, qualifying names only.

    Parameters
    ----------
    start, end : str
        Inclusive ``YYYY-MM-DD`` window.

    Returns
    -------
    pandas.DataFrame
        ``permno, namedt, nameendt, shrcd, exchcd, siccd, ticker`` for common
        shares (``shrcd`` in ``{10, 11}``) on NYSE/AMEX/NASDAQ (``exchcd`` in
        ``{1, 2, 3}``).
    """
    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    df = wrds_r2.read_table(
        "crsp_a_stock",
        "dsenames",
        columns=["permno", "namedt", "nameendt", "shrcd", "exchcd", "siccd", "ticker"],
        filters=[("namedt", "<=", ed), ("nameendt", ">=", sd)],
    )
    df["namedt"] = pd.to_datetime(df["namedt"])
    df["nameendt"] = pd.to_datetime(df["nameendt"])
    df["permno"] = df["permno"].astype("int64")  # CRSP ships int32; standardise for merges
    df = df[df["shrcd"].isin(UNIVERSE_SHRCD) & df["exchcd"].isin(UNIVERSE_EXCHCD)]
    return df.reset_index(drop=True)


def load_ibes_link() -> pd.DataFrame:
    """
    The I/B/E/S-to-CRSP link table, restricted to the reliable score tiers.

    Returns
    -------
    pandas.DataFrame
        ``ticker, permno, sdate, edate, score`` for ``score <= 2`` and
        non-null ``permno`` (the mirror carries ~7.3k score-6 rows with a
        null permno; both conditions exclude them, the ``permno.notna()``
        check is retained for defensiveness even though empirically no
        score<=2 row has a null permno).
    """
    df = wrds_r2.read_table(
        "wrdsapps_link_crsp_ibes",
        "ibcrsphist",
        columns=["ticker", "permno", "sdate", "edate", "score"],
    )
    df = df[(df["score"] <= IBES_LINK_MAX_SCORE) & df["permno"].notna()].copy()
    df["permno"] = df["permno"].astype("int64")
    df["sdate"] = pd.to_datetime(df["sdate"])
    df["edate"] = pd.to_datetime(df["edate"])
    return df.reset_index(drop=True)


def load_ibes_consensus(start: str, end: str) -> pd.DataFrame:
    """
    Raw I/B/E/S quarterly EPS consensus snapshots, ``anndats_act`` in ``[start, end]``.

    Every row of ``statsum_epsus`` for ``measure='EPS', fiscalp='QTR'`` whose
    (denormalised) actual-announcement date falls in the window - i.e. every
    historical consensus snapshot of every fiscal period *announced* in the
    window, not yet reduced to one row per event. See
    :func:`_pit_select_consensus` for the point-in-time reduction.

    Parameters
    ----------
    start, end : str
        Inclusive ``YYYY-MM-DD`` window, applied to ``anndats_act``.

    Returns
    -------
    pandas.DataFrame
        ``ticker, statpers, fpedats, numest, numup, numdown, medest,
        meanest, stdev, actual, anndats_act``.
    """
    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    df = wrds_r2.read_table(
        "tr_ibes",
        "statsum_epsus",
        columns=[
            "ticker",
            "statpers",
            "measure",
            "fiscalp",
            "fpedats",
            "numest",
            "numup",
            "numdown",
            "medest",
            "meanest",
            "stdev",
            "actual",
            "anndats_act",
        ],
        filters=[
            ("measure", "=", "EPS"),
            ("fiscalp", "=", "QTR"),
            ("anndats_act", ">=", sd),
            ("anndats_act", "<=", ed),
        ],
    )
    for c in ("statpers", "fpedats", "anndats_act"):
        df[c] = pd.to_datetime(df[c])
    return df.drop(columns=["measure", "fiscalp"]).reset_index(drop=True)


def load_ann_times(start: str, end: str) -> pd.DataFrame:
    """
    I/B/E/S actual-EPS announcement timestamps, ``anndats`` in ``[start, end]``.

    One row per ``(ticker, anndats)``: when both a real timestamp and the
    ``00:00:00`` unknown-marker exist for the same day (duplicate reporting),
    the real timestamp wins.

    Parameters
    ----------
    start, end : str
        Inclusive ``YYYY-MM-DD`` window.

    Returns
    -------
    pandas.DataFrame
        ``ticker, anndats, anntims``.
    """
    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    df = wrds_r2.read_table(
        "tr_ibes",
        "act_epsus",
        columns=["ticker", "measure", "pdicity", "anndats", "anntims"],
        filters=[
            ("measure", "=", "EPS"),
            ("pdicity", "=", "QTR"),
            ("anndats", ">=", sd),
            ("anndats", "<=", ed),
        ],
    )
    df["anndats"] = pd.to_datetime(df["anndats"])
    df["is_real"] = df["anntims"].map(lambda t: isinstance(t, dt.time) and t != dt.time(0, 0))
    df = (
        df.sort_values(["ticker", "anndats", "is_real"])
        .drop_duplicates(["ticker", "anndats"], keep="last")[["ticker", "anndats", "anntims"]]
        .reset_index(drop=True)
    )
    return df


def load_crsp_daily(
    permnos: Sequence[int],
    start: str,
    end: str,
    *,
    progress: bool = True,
) -> pd.DataFrame:
    """
    CRSP ``dsf`` for a permno universe, read year-by-year to bound peak memory.

    Each year is pulled with the decimal128 cast applied (see
    :func:`_read_arrow`), then immediately filtered down to ``permnos``
    *before* being appended and *before* the next year is read - so peak
    memory holds at most one year of the full (unfiltered) CRSP universe
    plus the accumulated filtered result, never the full 29-year unfiltered
    pull. Columns are downcast to float32 after filtering.

    Parameters
    ----------
    permnos : sequence of int
        The permno universe to retain.
    start, end : str
        Inclusive ``YYYY-MM-DD`` window.
    progress : bool
        Show a progress bar with ETA (the pull runs roughly 60s/year on the
        first, uncached call).

    Returns
    -------
    pandas.DataFrame
        ``permno, date, bidlo, askhi, prc, vol, ret, bid, ask, shrout,
        cfacpr, openprc, retx``, sorted by ``(permno, date)``.
    """
    cols = [
        "permno",
        "date",
        "bidlo",
        "askhi",
        "prc",
        "vol",
        "ret",
        "bid",
        "ask",
        "shrout",
        "cfacpr",
        "openprc",
        "retx",
    ]
    permno_set = set(int(p) for p in permnos)
    if not permno_set:
        return pd.DataFrame(columns=cols)

    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    years = list(range(sd.year, ed.year + 1))
    bar = ProgressBar(len(years), label="CRSP dsf", enabled=progress)
    frames: list[pd.DataFrame] = []
    for yr in years:
        y_lo = max(dt.date(yr, 1, 1), sd)
        y_hi = min(dt.date(yr, 12, 31), ed)
        df = _read_arrow(
            "crsp_a_stock",
            "dsf",
            columns=cols,
            filters=[("date", ">=", y_lo), ("date", "<=", y_hi)],
        )
        df = df[df["permno"].isin(permno_set)].copy()
        for c in _DECIMAL_DSF_COLS:
            if c in df.columns:
                df[c] = df[c].astype("float32")
        frames.append(df)
        bar.update()
    bar.close()

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
    out["date"] = pd.to_datetime(out["date"])
    out["permno"] = out["permno"].astype("int64")  # CRSP ships int32; standardise for merges
    return out.sort_values(["permno", "date"]).reset_index(drop=True)


def load_delistings() -> pd.DataFrame:
    """
    CRSP delisting events, one row per permno (first delisting kept).

    Returns
    -------
    pandas.DataFrame
        ``permno, dlstdt, dlstcd, dlret``.
    """
    df = _read_arrow("crsp_a_stock", "dsedelist", columns=["permno", "dlstdt", "dlstcd", "dlret"])
    df["dlstdt"] = pd.to_datetime(df["dlstdt"])
    df["permno"] = df["permno"].astype("int64")  # CRSP ships int32; standardise for merges
    # A permno can carry more than one dsedelist row only in rare relisting
    # cases; keeping the first is immaterial for a research panel and avoids
    # fanning out panel_daily rows on the (rare) duplicate.
    return df.drop_duplicates("permno", keep="first").reset_index(drop=True)


def load_ff_daily(start: str, end: str) -> pd.DataFrame:
    """
    Fama-French-Carhart daily factors (decimal128-cast).

    Parameters
    ----------
    start, end : str
        Inclusive ``YYYY-MM-DD`` window.

    Returns
    -------
    pandas.DataFrame
        ``date, mktrf, smb, hml, rf, umd``, sorted by date. This table's
        unique dates are the NYSE trading calendar used throughout this
        module.
    """
    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    df = _read_arrow("ff_all", "factors_daily", filters=[("date", ">=", sd), ("date", "<=", ed)])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


# ── point-in-time consensus selection ─────────────────────────────────────────
def _pit_select_consensus(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per ``(ticker, fpedats)``: the freshest snapshot strictly before ``anndats_act``.

    Implements the plan's PIT rule exactly: keep ``statpers < anndats_act``
    (strict), take the row with the maximum ``statpers`` among those, and
    take *every* field (including ``actual`` and ``anndats_act``) from that
    same row - never mixing fields across rows, which is what protects
    against the I/B/E/S split-restatement trap (a later row's ``actual``
    need not be on the same split basis as an earlier row's ``meanest``).
    Also applies the ``numest >= MIN_NUMEST`` and ``stdev > 0`` guards here
    (they are properties of the selected row itself, not a later stage).
    """
    df = raw[raw["statpers"] < raw["anndats_act"]].copy()
    df = df.sort_values(["ticker", "fpedats", "statpers"])
    df = df.drop_duplicates(["ticker", "fpedats"], keep="last")
    df = df[(df["numest"] >= MIN_NUMEST) & (df["stdev"] > 0)]
    return df.reset_index(drop=True)


def _link_to_permno(events: pd.DataFrame, link: pd.DataFrame) -> pd.DataFrame:
    """Attach ``permno`` via the I/B/E/S link table, valid on ``anndats_act``."""
    merged = events.merge(link, on="ticker", how="inner")
    ok = (merged["sdate"] <= merged["anndats_act"]) & (merged["anndats_act"] <= merged["edate"])
    merged = merged[ok]
    merged = merged.drop_duplicates(["ticker", "fpedats", "statpers"], keep="first")
    return merged.drop(columns=["sdate", "edate", "score"]).reset_index(drop=True)


def _attach_universe(events: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """As-of join to the qualifying CRSP name record covering ``anndats_act`` (never the latest record)."""
    ev = events.sort_values("anndats_act")
    # `universe` carries CRSP's own `ticker` and the already-applied `shrcd`
    # filter, neither needed downstream; dropping them avoids a ticker/ticker
    # column collision with the I/B/E/S `ticker` already on `events`.
    un = universe[["permno", "namedt", "nameendt", "siccd", "exchcd"]].sort_values("namedt")
    merged = pd.merge_asof(
        ev,
        un,
        left_on="anndats_act",
        right_on="namedt",
        by="permno",
        direction="backward",
    )
    ok = merged["nameendt"].notna() & (merged["anndats_act"] <= merged["nameendt"])
    return merged[ok].reset_index(drop=True)


def _attach_session_and_day0(
    events: pd.DataFrame, ann_times: pd.DataFrame, cal: np.ndarray
) -> pd.DataFrame:
    """Attach bmo/amc/dmh session (from act_epsus) and resolve day0 (date + ordinal)."""
    merged = events.merge(
        ann_times.rename(columns={"anndats": "anndats_act"}),
        on=["ticker", "anndats_act"],
        how="left",
    )
    sess = merged["anntims"].map(session_from_time)
    merged["session"] = [s for s, _ in sess]
    merged["session_source"] = [src for _, src in sess]
    merged["day0_ordinal"] = _day0_vectorized(merged["anndats_act"], merged["session"], cal)
    merged["day0"] = cal[merged["day0_ordinal"].to_numpy()]
    merged["day0"] = pd.to_datetime(merged["day0"])
    return merged


def _augment_daily(
    daily: pd.DataFrame, ff: pd.DataFrame, delist: pd.DataFrame, cal_index: dict[dt.date, int]
) -> pd.DataFrame:
    """Add ordinal, delisting-aware total return, dollar volume/ADV60, FF factors and spread_bps."""
    d = daily.copy()
    d["ordinal"] = d["date"].dt.date.map(cal_index)

    d = d.merge(delist, on="permno", how="left")
    is_delist_day = d["date"] == d["dlstdt"]
    # An empty (or partially-empty) delist table leaves these columns
    # object-dtype after the left merge; coerce to float so NaN/comparison
    # arithmetic below is well-defined regardless of how many permnos ever
    # delisted in this panel.
    dlret = d["dlret"].astype(float).to_numpy()
    dlstcd = d["dlstcd"].astype(float).to_numpy()
    # Shumway (1997): a missing delisting return on a performance-related
    # code (500-599, e.g. liquidation/bankruptcy) is filled at -30% rather
    # than dropped or zeroed - omitting this biases the long leg upward,
    # the classic PEAD-replication error.
    performance_code = (dlstcd >= 500) & (dlstcd < 600)
    shumway_fill = np.where(performance_code & np.isnan(dlret), -0.30, dlret)
    ret = d["ret"].to_numpy()
    combined = (1 + np.nan_to_num(ret, nan=0.0)) * (1 + np.nan_to_num(shumway_fill, nan=0.0)) - 1
    d["ret_adj"] = np.where(is_delist_day.to_numpy(), combined, ret)
    d = d.drop(columns=["dlstdt", "dlstcd", "dlret"])

    d = d.merge(ff, on="date", how="left")

    # dollar volume: `vol` is already in raw shares on this mirror (verified
    # against AAPL's known 2020-01-02 volume), `shrout` is in thousands of
    # shares (verified against AAPL's known market cap the same day) - the
    # two columns are on *different* unit bases and must not share a scale
    # factor.
    d["dollar_vol"] = d["prc"].abs() * d["vol"]
    d = d.sort_values(["permno", "date"])
    d["adv60"] = d.groupby("permno")["dollar_vol"].transform(
        lambda s: s.rolling(ADV60_WINDOW, min_periods=ADV60_WINDOW).median()
    )
    d["spread_bps"] = event_study.equity_roundtrip_cost_bps(d)
    return d.reset_index(drop=True)


def _winsorize_by_quarter(
    values: pd.Series, quarter: pd.Series, lower=0.01, upper=0.99
) -> pd.Series:
    """Clip `values` at the [lower, upper] quantile within each `quarter` group."""

    def _clip(g: pd.Series) -> pd.Series:
        lo, hi = g.quantile(lower), g.quantile(upper)
        return g.clip(lo, hi)

    return values.groupby(quarter).transform(_clip)


# ── orchestrator ───────────────────────────────────────────────────────────────
def build_event_panel(
    start: str, end: str, *, progress: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build the point-in-time earnings-event panel and its supporting daily panel.

    Prints a row-count funnel at every filtering stage (fails loudly rather
    than silently degrading): raises if the I/B/E/S-to-CRSP link retains
    less than :data:`IBES_LINK_MIN_RETAIN` of PIT-selected events, or if the
    final event count falls below :data:`MIN_FINAL_EVENTS`.

    Note on return type: the plan sketch for this function names a single
    ``DataFrame`` return; this implementation returns a
    ``(panel_events, panel_daily)`` tuple instead, because both artifacts
    are produced by the same expensive CRSP pull and splitting them into two
    separate calls would force either a second CRSP pull or an awkward
    hidden cache. This is a deliberate, documented deviation from the
    literal one-line sketch, not an extension of the API surface.

    Parameters
    ----------
    start, end : str
        Inclusive ``YYYY-MM-DD`` study window (the full sample is
        ``1996-01-01`` to ``2024-12-31``; fit/holdout split is reported at
        :data:`FIT_END` / :data:`HOLDOUT_START`).
    progress : bool
        Show progress bars with ETA on the CRSP pull.

    Returns
    -------
    tuple of (pandas.DataFrame, pandas.DataFrame)
        ``(panel_events, panel_daily)``.
    """
    sd = pd.Timestamp(start)
    pad_start = (sd - pd.Timedelta(days=CALENDAR_PAD_DAYS)).strftime("%Y-%m-%d")

    print(f"building event panel {start} .. {end} (calendar padded from {pad_start})")

    ff = load_ff_daily(pad_start, end)
    cal, cal_index = event_study.make_trading_calendar(ff)

    raw = load_ibes_consensus(start, end)
    n_raw = len(raw)
    print(f"statsum EPS/QTR rows                              {n_raw:>10,}")

    pit = _pit_select_consensus(raw)
    n_pit = len(pit)
    print(f"-> PIT-selected (one per ticker,fpedats)           {n_pit:>10,}")
    del raw

    link = load_ibes_link()
    linked = _link_to_permno(pit, link)
    n_linked = len(linked)
    retain = n_linked / n_pit if n_pit else 0.0
    print(
        f"-> IBES->PERMNO linked (score<=2, in date range)   {n_linked:>10,}  ({retain:.1%} retained)"
    )
    if retain < IBES_LINK_MIN_RETAIN:
        raise RuntimeError(
            f"IBES->PERMNO link retained only {retain:.1%} of PIT-selected events "
            f"(< {IBES_LINK_MIN_RETAIN:.0%} floor); the link join is likely broken."
        )

    universe = load_universe(pad_start, end)
    in_universe = _attach_universe(linked, universe)
    n_universe = len(in_universe)
    print(f"-> CRSP universe (shrcd 10/11, exchcd 1/2/3, as-of date) {n_universe:>10,}")
    del linked

    ann_times = load_ann_times(start, end)
    events = _attach_session_and_day0(in_universe, ann_times, cal)
    del in_universe, ann_times

    candidate_permnos = sorted(events["permno"].dropna().astype(int).unique())
    daily_raw = load_crsp_daily(candidate_permnos, pad_start, end, progress=progress)
    delist = load_delistings()
    daily = _augment_daily(daily_raw, ff, delist, cal_index)
    del daily_raw

    # entry-day (day0-1 for price/mktcap/adv60, day0 for cfacpr/spread) lookups,
    # exact match on (permno, ordinal) - CRSP missing that exact trading day
    # (halt, delisted before day0) yields NaN, which the price/adv60/cost gates
    # below drop naturally rather than silently substituting a stale value.
    events["day0_minus_1"] = events["day0_ordinal"] - 1
    events["day0_minus_2"] = events["day0_ordinal"] - 2

    entry_prev = daily[["permno", "ordinal", "prc", "shrout"]].rename(
        columns={"ordinal": "day0_minus_1", "prc": "prc_prev", "shrout": "shrout_prev"}
    )
    events = events.merge(entry_prev, on=["permno", "day0_minus_1"], how="left")

    adv_lookup = daily[["permno", "ordinal", "adv60"]].rename(columns={"ordinal": "day0_minus_2"})
    events = events.merge(adv_lookup, on=["permno", "day0_minus_2"], how="left")

    day0_lookup = daily[["permno", "ordinal", "cfacpr", "spread_bps"]].rename(
        columns={"ordinal": "day0_ordinal", "spread_bps": "spread_bps_entry"}
    )
    events = events.merge(day0_lookup, on=["permno", "day0_ordinal"], how="left")

    # cfacpr as of statpers: statpers is an IBES survey date, not necessarily a
    # trading day, so this needs an as-of (backward) match rather than an exact one.
    d_cfac = daily[["permno", "date", "cfacpr"]].rename(columns={"cfacpr": "cfacpr_statpers"})
    events = events.sort_values("statpers")
    events = pd.merge_asof(
        events,
        d_cfac.sort_values("date"),
        left_on="statpers",
        right_on="date",
        by="permno",
        direction="backward",
        tolerance=pd.Timedelta(days=10),
    ).drop(columns=["date"])

    events["prc_prev"] = events["prc_prev"].abs()
    events["mktcap"] = events["prc_prev"] * events["shrout_prev"] * 1000  # shrout is in thousands

    n_before_price = len(events)
    events = events[events["prc_prev"].notna() & (events["prc_prev"] >= MIN_PRICE)]
    print(
        f"-> price >= $5 at day0-1                           {len(events):>10,}  (dropped {n_before_price - len(events):,})"
    )

    n_before_adv = len(events)
    events = events[events["adv60"].notna() & (events["adv60"] >= MIN_ADV60)]
    print(
        f"-> adv60 >= $1m                                    {len(events):>10,}  (dropped {n_before_adv - len(events):,})"
    )

    n_before_fresh = len(events)
    age_days = (events["anndats_act"] - events["statpers"]).dt.days
    events = events[age_days <= MAX_CONSENSUS_AGE_DAYS]
    print(
        f"-> consensus fresh (<=90d)                          {len(events):>10,}  (dropped {n_before_fresh - len(events):,})"
    )

    n_before_split = len(events)
    no_split = (
        events["cfacpr_statpers"].notna()
        & events["cfacpr"].notna()
        & np.isclose(events["cfacpr_statpers"], events["cfacpr"])
    )
    events = events[no_split]
    print(
        f"-> no split in [statpers, day0]                     {len(events):>10,}  (dropped {n_before_split - len(events):,})"
    )

    n_before_cost = len(events)
    events = events[events["spread_bps_entry"].notna()]
    print(
        f"-> valid bid/ask for cost                           {len(events):>10,}  (dropped {n_before_cost - len(events):,})"
    )

    events["sue"] = (events["actual"] - events["meanest"]) / events["prc_prev"].abs()
    events["disp"] = events["stdev"] / events["prc_prev"].abs()
    events["rev"] = (events["numup"] - events["numdown"]) / events["numest"]
    quarter = events["anndats_act"].dt.to_period("Q")
    events["sue"] = _winsorize_by_quarter(events["sue"], quarter)
    events["disp"] = _winsorize_by_quarter(events["disp"], quarter)

    events = events.rename(
        columns={
            "ticker": "ibes_ticker",
            "anndats_act": "anndats",
            "day0": "day0_date",
        }
    ).rename(columns={"day0_date": "day0"})

    keep_cols = [
        "permno",
        "ibes_ticker",
        "anndats",
        "anntims",
        "session",
        "session_source",
        "day0",
        "day0_ordinal",
        "fpedats",
        "statpers",
        "actual",
        "meanest",
        "medest",
        "stdev",
        "numest",
        "numup",
        "numdown",
        "prc_prev",
        "shrout_prev",
        "siccd",
        "exchcd",
        "mktcap",
        "adv60",
        "sue",
        "disp",
        "rev",
        "spread_bps_entry",
    ]
    events = events[keep_cols].rename(columns={"shrout_prev": "shrout"}).reset_index(drop=True)

    n_final = len(events)
    fit_n = int((events["anndats"] <= FIT_END).sum())
    holdout_n = int((events["anndats"] >= HOLDOUT_START).sum())
    print(
        f"=> FINAL EVENTS: N = {n_final:,}  (fit 1996-{FIT_END[:4]}: N={fit_n:,}  |  holdout {HOLDOUT_START[:4]}-2024: N={holdout_n:,})"
    )
    if n_final < MIN_FINAL_EVENTS:
        raise RuntimeError(
            f"final event count {n_final:,} is below the {MIN_FINAL_EVENTS:,} acceptance floor; "
            "something in the pipeline is broken (stop and diagnose, do not proceed)."
        )

    daily_cols = [
        "permno",
        "date",
        "ordinal",
        "prc",
        "bidlo",
        "askhi",
        "bid",
        "ask",
        "vol",
        "shrout",
        "cfacpr",
        "ret",
        "ret_adj",
        "dollar_vol",
        "adv60",
        "spread_bps",
        "mktrf",
        "smb",
        "hml",
        "rf",
        "umd",
    ]
    panel_daily = daily[daily_cols].reset_index(drop=True)

    return events, panel_daily
