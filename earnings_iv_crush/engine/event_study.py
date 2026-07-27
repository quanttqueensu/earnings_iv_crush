"""
event_study.py
Reusable event-study engine: trading-day windows, delisting-aware CAR, an
overlapping-cohort calendar-time portfolio, Fama-French-Carhart alpha, the
equity round-trip cost model, and cluster-robust significance tools.

This module is deliberately data-source agnostic: every function takes plain
DataFrames/Series (built by ``earnings_iv_crush.data.wrds_panel``) and does no
I/O. It is the shared engine that later pieces of the earnings-event research
programme (signal construction, portfolio formation, robustness checks) build
on without re-deriving the timing, cost, or significance machinery.

This module implements:

* ``make_trading_calendar`` / ``event_day0``      — the integer trading-day
  ordinal calendar (from the Fama-French daily factor file's own dates, i.e.
  the NYSE calendar) and bmo/amc/dmh event-day resolution.
* ``car``                                          — delisting-aware
  cumulative abnormal return over an event window (Bernard & Thomas 1989).
* ``calendar_time_portfolio``                      — Jegadeesh & Titman (1993)
  overlapping-cohort daily portfolio return, long/short/long-short.
* ``ff4_alpha``                                    — Carhart four-factor
  alpha with Newey-West/HAC standard errors (Newey & West 1987).
* ``equity_roundtrip_cost_bps``                    — the quoted-spread cost
  model building block (Frazzini & Lamont 2007 style equity trading-cost
  proxy), with a trailing-median fallback for missing NBBO.
* ``cluster_bootstrap_ci``                          — cluster (not i.i.d.)
  bootstrap confidence interval, resampling whole announcement dates so
  same-day earnings clustering does not overstate precision.
* ``summarise_book``                                — the standard trade-book
  scorecard (N, hit rate, Sharpe on both bases, significance), built on
  ``engine.stats``.

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
Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling
losers: Implications for stock market efficiency. *Journal of Finance*,
48(1), 65-91.
Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite,
heteroskedasticity and autocorrelation consistent covariance matrix.
*Econometrica*, 55(3), 703-708.
Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance*,
52(1), 327-340.
Bailey, D. H., & Lopez de Prado, M. (2014). The deflated Sharpe ratio:
Correcting for selection bias, backtest overfitting, and non-normality.
*Journal of Portfolio Management*, 40(5), 94-107.
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from . import stats

# ── cost model constants (defined once; wrds_panel.py imports these) ─────────
IMPACT_BPS_PER_SIDE = 5.0  # assumed price impact per side, in bps of notional
SPREAD_WINSOR_BPS = 500.0  # cap on quoted spread, guards against bad NBBO ticks
COST_FALLBACK_WINDOW = 60  # trailing trading days for the median-spread fallback


# ─────────────────────────────────────────────────────────────────────────────
# Trading-day calendar
# ─────────────────────────────────────────────────────────────────────────────


def make_trading_calendar(ff: pd.DataFrame) -> tuple[np.ndarray, dict[dt.date, int]]:
    """
    Build an integer trading-day calendar from the Fama-French daily dates.

    The unique dates in ``ff_all.factors_daily`` are exactly the NYSE trading
    calendar, so using them (rather than a bdate_range that would include
    market holidays) avoids off-by-one errors when arithmetic is done in
    ordinal offsets.

    Parameters
    ----------
    ff : pd.DataFrame
        Must carry a ``date`` column (any datetime-like dtype).

    Returns
    -------
    cal : np.ndarray of datetime64[D]
        Sorted unique trading dates; ``cal[i]`` is trading day ``i``.
    cal_index : dict[datetime.date, int]
        Maps each trading date to its integer ordinal (its position in
        ``cal``).
    """
    dates = pd.to_datetime(pd.Series(ff["date"])).dt.normalize().unique()
    cal = np.sort(dates).astype("datetime64[D]")
    cal_index = {pd.Timestamp(d).date(): i for i, d in enumerate(cal)}
    return cal, cal_index


def event_day0(anndats: dt.date | pd.Timestamp, session: str, cal_index: dict[dt.date, int]) -> int:
    """
    Resolve an announcement date + session to its tradeable event-day ordinal.

    ``bmo`` (before market open) trades on the announcement date itself, so
    day0 is the first trading day on or after ``anndats``. ``amc`` (after
    close), ``dmh`` (during market hours) and any unresolved session are all
    treated as day0 = the first trading day strictly after ``anndats`` — the
    conservative assumption that the same-day reaction cannot be traded
    (matches ``wrds_panel.session_from_time``'s conservative dmh -> amc-like
    handling).

    Parameters
    ----------
    anndats : date-like
        Announcement date.
    session : str
        ``"bmo"``, ``"amc"``, ``"dmh"``, or any other value (treated as amc).
    cal_index : dict[datetime.date, int]
        Trading-day ordinal lookup from :func:`make_trading_calendar`.

    Returns
    -------
    int
        The trading-day ordinal of day0.

    Notes
    -----
    This scalar form re-sorts ``cal_index``'s keys on every call, which is
    fine for ad hoc/test use but too slow to call in a loop over a large
    event panel; ``wrds_panel.py`` uses an equivalent vectorised
    ``np.searchsorted`` implementation against the ``cal`` array for the bulk
    build and is unit-tested to agree with this function.
    """
    d = pd.Timestamp(anndats).date()
    keys = sorted(cal_index)
    pos = bisect.bisect_left(keys, d) if session == "bmo" else bisect.bisect_right(keys, d)
    if pos >= len(keys):
        raise ValueError(f"no trading day on/after {d} in calendar; extend the calendar window")
    return cal_index[keys[pos]]


# ─────────────────────────────────────────────────────────────────────────────
# Cumulative abnormal return
# ─────────────────────────────────────────────────────────────────────────────


def car(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    a: int,
    b: int,
    adjust: str = "mkt",
) -> pd.Series:
    """
    Delisting-aware cumulative abnormal return over ``[day0 + a, day0 + b]``.

    Parameters
    ----------
    daily : pd.DataFrame
        Per name-day panel with ``permno``, ``ordinal`` (trading-day ordinal,
        see :func:`make_trading_calendar`), ``ret_adj`` (total return already
        incorporating the Shumway 1997 delisting adjustment — see
        ``wrds_panel.build_event_panel``), and, when ``adjust='mkt'``,
        ``mktrf`` and ``rf``.
    events : pd.DataFrame
        Must carry ``permno`` and ``day0`` (trading-day ordinal). The
        returned Series shares ``events.index``.
    a, b : int
        Trading-day offsets from day0, inclusive on both ends
        (``a <= 0 <= b`` is typical but not required).
    adjust : str
        ``"mkt"`` subtracts the market return (``mktrf + rf``) from
        ``ret_adj`` before summing (market-adjusted AR); ``"raw"`` sums
        ``ret_adj`` directly.

    Returns
    -------
    pd.Series
        One CAR per event, indexed like ``events``. ``NaN`` where the name
        has no daily observations in the window (e.g. it delisted before
        day0 + a, or the panel does not cover that permno).
    """
    cols = ["permno", "ordinal", "ret_adj"]
    if adjust == "mkt":
        cols += ["mktrf", "rf"]
    d = daily[cols].dropna(subset=["ordinal"]).copy()
    d["ordinal"] = d["ordinal"].astype(int)
    if adjust == "mkt":
        ar = d["ret_adj"].to_numpy() - (d["mktrf"].to_numpy() + d["rf"].to_numpy())
    elif adjust == "raw":
        ar = d["ret_adj"].to_numpy()
    else:
        raise ValueError(f"adjust must be 'mkt' or 'raw', got {adjust!r}")
    d = d.assign(ar=ar).sort_values(["permno", "ordinal"])

    groups: dict[int, tuple[np.ndarray, np.ndarray]] = {
        int(permno): (g["ordinal"].to_numpy(), g["ar"].to_numpy())  # type: ignore[arg-type]
        for permno, g in d.groupby("permno", sort=False)
    }

    permnos = events["permno"].to_numpy()
    day0s = events["day0"].to_numpy()
    out = np.full(len(events), np.nan)
    for i in range(len(events)):
        grp = groups.get(permnos[i])
        if grp is None:
            continue
        ords, ars = grp
        lo, hi = day0s[i] + a, day0s[i] + b
        left = np.searchsorted(ords, lo, side="left")
        right = np.searchsorted(ords, hi, side="right")
        if right > left:
            out[i] = ars[left:right].sum()
    return pd.Series(out, index=events.index, name="car")


# ─────────────────────────────────────────────────────────────────────────────
# Calendar-time portfolio
# ─────────────────────────────────────────────────────────────────────────────


def calendar_time_portfolio(
    positions: pd.DataFrame, daily: pd.DataFrame, weight: str = "ew"
) -> pd.Series:
    """
    Daily overlapping-cohort calendar-time portfolio return (Jegadeesh & Titman 1993).

    On each calendar day, every position whose ``[entry_ordinal, exit_ordinal]``
    window contains that day contributes ``side * ret_adj`` (``side = +1``
    long, ``side = -1`` short), averaged across active positions. A single
    ``positions`` table can mix long and short rows: the pooled side-weighted
    average handles a long-only, short-only, or combined long-short book with
    one formula (for the combined book this is the pooled portfolio return,
    not a fixed 50/50 gross split across separately-normalised legs — state
    this basis when quoting the book's return).

    Parameters
    ----------
    positions : pd.DataFrame
        ``permno``, ``entry_ordinal``, ``exit_ordinal`` (trading-day
        ordinals, inclusive), ``side`` (+1 or -1). For ``weight='vw'`` also
        ``entry_mktcap``.
    daily : pd.DataFrame
        Per name-day panel with ``permno``, ``ordinal``, ``date``, ``ret_adj``
        (delisting-aware).
    weight : str
        ``"ew"`` (equal-weight, default) or ``"vw"`` (value-weight on
        ``entry_mktcap``, fixed at entry — no daily cap-weight drift).

    Returns
    -------
    pd.Series
        Daily portfolio return indexed by calendar date, covering every date
        on which at least one position is active. Empty when ``positions``
        is empty.
    """
    if weight not in ("ew", "vw"):
        raise ValueError(f"weight must be 'ew' or 'vw', got {weight!r}")
    if len(positions) == 0:
        return pd.Series(dtype=float, name="ret")

    d = daily[["permno", "ordinal", "date", "ret_adj"]].dropna(subset=["ordinal"]).copy()
    d["ordinal"] = d["ordinal"].astype(int)
    groups = {permno: g.sort_values("ordinal") for permno, g in d.groupby("permno", sort=False)}

    chunks: list[pd.DataFrame] = []
    for pos in positions.itertuples(index=False):
        g = groups.get(pos.permno)
        if g is None:
            continue
        w = 1.0 if weight == "ew" else abs(float(getattr(pos, "entry_mktcap", 1.0)))
        sl = g[(g["ordinal"] >= pos.entry_ordinal) & (g["ordinal"] <= pos.exit_ordinal)]
        if sl.empty or w == 0:
            continue
        chunks.append(
            pd.DataFrame(
                {
                    "date": sl["date"].to_numpy(),
                    "wret": w * float(pos.side) * sl["ret_adj"].to_numpy(),  # type: ignore[arg-type]
                    "w": w,
                }
            )
        )
    if not chunks:
        return pd.Series(dtype=float, name="ret")

    allrows = pd.concat(chunks, ignore_index=True)
    agg = allrows.groupby("date").agg(wret_sum=("wret", "sum"), w_sum=("w", "sum"))
    ret = (agg["wret_sum"] / agg["w_sum"]).rename("ret").sort_index()
    return ret


# ─────────────────────────────────────────────────────────────────────────────
# Factor-model alpha
# ─────────────────────────────────────────────────────────────────────────────


def ff4_alpha(
    daily_ret: pd.Series, ff: pd.DataFrame, nw_lags: int = 5, *, subtract_rf: bool = True
) -> dict:
    """
    Carhart four-factor alpha with Newey-West/HAC standard errors.

    Regresses the portfolio's *excess* return on ``mktrf, smb, hml, umd`` by
    OLS with a HAC (Newey & West 1987) covariance estimator, so serial
    correlation in the overlapping-cohort calendar-time series (adjacent days
    share positions) does not understate the standard error.

    Parameters
    ----------
    daily_ret : pd.Series
        Daily portfolio return, indexed by date (e.g. the output of
        :func:`calendar_time_portfolio`).
    ff : pd.DataFrame
        Fama-French daily factors: ``date, mktrf, smb, hml, rf, umd``.
    nw_lags : int
        HAC ``maxlags``. Defaults to 5.
    subtract_rf : bool, keyword-only
        Whether ``daily_ret`` still has to be converted into an excess return
        by subtracting ``rf``. ``True`` (the default) is correct for a
        **long-only** book, whose return is earned on invested capital.
        ``False`` is **required** for a **zero-investment long-short** book:
        its return is already an excess return by construction (the short
        proceeds fund the long leg), so subtracting ``rf`` again deducts the
        risk-free rate from a portfolio that never tied up any capital and
        biases the intercept down by exactly ``mean(rf)`` over the sample.
        The Fama-French factors are themselves zero-cost spreads and are not
        rf-adjusted for precisely this reason: regressing ``umd - rf`` on the
        other factors returns UMD's true alpha minus ``mean(rf)``, which is
        the same error. Pass ``subtract_rf=False`` for any decile long-short,
        spread, or hedged book.

    Returns
    -------
    dict
        ``alpha_daily`` (per-day intercept), ``alpha_ann`` (``alpha_daily *
        252`` — an arithmetic scaling of a daily mean return, not a Sharpe
        rescaling, so ``x252`` not ``sqrt(252)`` is correct here),
        ``t_alpha``, ``betas`` (dict of the four factor loadings), ``r2``,
        ``n_days``, ``subtract_rf`` (the basis the alpha was computed on,
        carried through so a caller cannot report the number without it).
    """
    import statsmodels.api as sm

    ffi = ff.set_index(pd.to_datetime(ff["date"]).dt.normalize())[
        ["mktrf", "smb", "hml", "umd", "rf"]
    ]
    r = pd.Series(daily_ret).copy()
    r.index = pd.to_datetime(r.index).normalize()
    df = pd.DataFrame({"ret": r}).join(ffi, how="inner").dropna()
    if len(df) < 10:
        raise ValueError(
            f"only {len(df)} overlapping days between daily_ret and ff; "
            "need at least 10 for a meaningful HAC regression"
        )
    y = df["ret"] - df["rf"] if subtract_rf else df["ret"]
    X = sm.add_constant(df[["mktrf", "smb", "hml", "umd"]])
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": nw_lags})
    alpha_daily = float(model.params["const"])
    return {
        "alpha_daily": alpha_daily,
        "alpha_ann": alpha_daily * 252,  # arithmetic (x252), daily-mean basis
        "t_alpha": float(model.tvalues["const"]),
        "betas": {k: float(v) for k, v in model.params.items() if k != "const"},
        "r2": float(model.rsquared),
        "n_days": int(len(df)),
        "subtract_rf": subtract_rf,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cost model
# ─────────────────────────────────────────────────────────────────────────────


def equity_roundtrip_cost_bps(daily: pd.DataFrame) -> pd.Series:
    """
    Per name-day quoted-spread cost proxy (bps), the round-trip cost building block.

    ``quoted_spread_bps = 1e4 * (ask - bid) / mid``. When the quote is
    missing, crossed (``ask <= bid``), or the mid is non-positive, the value
    falls back to that name's trailing median quoted spread over the prior
    :data:`COST_FALLBACK_WINDOW` trading days (excluding the current day, so
    a day cannot use its own future information as its own proxy); if that
    fallback is also unavailable the result is ``NaN``. The final series is
    winsorised at :data:`SPREAD_WINSOR_BPS`.

    This function returns only the **per-day half-spread proxy**, aligned to
    ``daily``'s row index — not a combined round-trip figure, because a
    round trip needs two days (entry ``e`` and exit ``x``) that this
    function does not know about. Combine two lookups into one round-trip
    cost as::

        cost_bps = spread[e] / 2 + spread[x] / 2 + 2 * IMPACT_BPS_PER_SIDE

    (half the quoted spread crossed on each side, plus a fixed per-side
    impact assumption). For a long-short position this cost applies on both
    legs. ``wrds_panel.build_event_panel`` uses this formula to gate events
    on entry-day cost availability and to populate ``spread_bps_entry``.

    Parameters
    ----------
    daily : pd.DataFrame
        Per name-day panel with ``permno``, ``date``, ``bid``, ``ask``.

    Returns
    -------
    pd.Series
        ``spread_bps``, aligned to ``daily.index``.
    """
    d = daily[["permno", "date", "bid", "ask"]].copy()
    d["_orig_idx"] = daily.index
    d = d.sort_values(["permno", "date"])

    bid = d["bid"].to_numpy(dtype=float)
    ask = d["ask"].to_numpy(dtype=float)
    mid = (bid + ask) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where((ask > bid) & (mid > 0), 1e4 * (ask - bid) / mid, np.nan)
    d["spread"] = raw

    d["fallback"] = d.groupby("permno")["spread"].transform(
        lambda g: g.shift(1).rolling(COST_FALLBACK_WINDOW, min_periods=1).median()
    )
    d["spread_bps"] = d["spread"].where(d["spread"].notna(), d["fallback"])
    d["spread_bps"] = d["spread_bps"].clip(upper=SPREAD_WINSOR_BPS)

    out = d.set_index("_orig_idx")["spread_bps"].reindex(daily.index)
    return out.rename("spread_bps")


# ─────────────────────────────────────────────────────────────────────────────
# Cluster-robust significance
# ─────────────────────────────────────────────────────────────────────────────


def cluster_bootstrap_ci(
    values: Sequence[float] | np.ndarray | pd.Series,
    cluster_keys: Sequence | np.ndarray | pd.Series,
    stat_fn: Callable[[np.ndarray], float],
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """
    Cluster-bootstrap confidence interval, resampling whole clusters.

    Earnings events cluster hard on announcement date (dozens report the
    same day in earnings season); an i.i.d. row bootstrap treats those as
    independent draws and overstates precision. This resamples the unique
    values of ``cluster_keys`` with replacement (each draw pulls in every
    row belonging to that cluster), so within-cluster correlation is
    preserved in every bootstrap replicate (Cameron, Gelbach & Miller 2008
    cluster-bootstrap logic; Efron & Tibshirani 1993 for the underlying
    percentile-bootstrap method).

    Parameters
    ----------
    values : array-like
        The per-row values ``stat_fn`` is computed over (e.g. per-trade
        returns).
    cluster_keys : array-like
        Same length as ``values``; the cluster each row belongs to (e.g.
        announcement date).
    stat_fn : callable
        Maps a 1-D array of (resampled) values to a scalar statistic.
    n_boot : int
        Number of bootstrap replicates. Defaults to 10000.
    ci : float
        Central interval mass. Defaults to 0.95.
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    tuple of float
        ``(low, high)``. ``(nan, nan)`` if there are no clusters.
    """
    values = np.asarray(values, dtype=float)
    keys = np.asarray(cluster_keys)
    uniq = np.unique(keys)
    if len(uniq) == 0:
        return float("nan"), float("nan")

    idx_by_cluster = {k: np.where(keys == k)[0] for k in uniq}
    rng = np.random.default_rng(seed)
    boot_stats = np.empty(n_boot)
    for b in range(n_boot):
        drawn = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx_by_cluster[k] for k in drawn])
        boot_stats[b] = stat_fn(values[sel])

    lo = float(np.nanpercentile(boot_stats, 100 * (1 - ci) / 2))
    hi = float(np.nanpercentile(boot_stats, 100 * (1 + ci) / 2))
    return lo, hi


# ─────────────────────────────────────────────────────────────────────────────
# Book scorecard
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARY_BOOTSTRAP_N = 5000  # bounds the O(n_boot) Python-loop cost of the CI


def summarise_book(
    returns: pd.Series | np.ndarray, dates: pd.Series | np.ndarray, label: str
) -> dict:
    """
    Standard trade-book scorecard: N, hit rate, Sharpe on both bases, significance.

    Reuses ``engine.stats`` for every Sharpe-family figure rather than
    reimplementing them, so this scorecard and the rest of the book's
    reporting always agree. Annualises via
    :func:`engine.stats.infer_periods_per_year` (the event book's own
    realised cadence), never a fixed ``sqrt(252)`` — the canonical failure
    mode for a sparse event book.

    Parameters
    ----------
    returns : array-like
        Per-trade (or per-period) returns, net of costs.
    dates : array-like
        Dates aligned to ``returns`` (e.g. each trade's entry date), used
        both to infer the annualisation factor and as the cluster key for
        the bootstrap CI (same-day trades resampled together).
    label : str
        Free-text identifier carried through to the output dict.

    Returns
    -------
    dict
        ``label, n, hit_rate, mean_return, sharpe_per_trade,
        sharpe_annualised, periods_per_year, psr, dsr, sharpe_ci_low,
        sharpe_ci_high``. The CI is on the annualised-Sharpe basis, computed
        with :func:`cluster_bootstrap_ci` clustered on calendar date
        (``n_boot=5000``, a bounded default for the Python-loop bootstrap
        cost — pass a larger sample through ``cluster_bootstrap_ci`` directly
        for a tighter CI on a smaller book).
    """
    r = pd.Series(returns, dtype=float).reset_index(drop=True)
    d = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    n = len(r)
    if n == 0:
        return {"label": label, "n": 0}

    hit_rate = float((r > 0).mean())
    mean_ret = float(r.mean())
    sharpe_per_trade = stats.sharpe(r, periods_per_year=1.0)
    ppy = stats.infer_periods_per_year(pd.DatetimeIndex(d))
    sharpe_ann = stats.sharpe(r, periods_per_year=ppy)
    psr = stats.probabilistic_sharpe_ratio(r)
    dsr = stats.deflated_sharpe_ratio(r)

    def _ann_sharpe_stat(x: np.ndarray) -> float:
        sd = x.std(ddof=1)
        return float(x.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0

    lo, hi = cluster_bootstrap_ci(
        r.to_numpy(),
        d.dt.date.to_numpy(),
        _ann_sharpe_stat,
        n_boot=_SUMMARY_BOOTSTRAP_N,
        seed=0,
    )
    return {
        "label": label,
        "n": n,
        "hit_rate": hit_rate,
        "mean_return": mean_ret,
        "sharpe_per_trade": sharpe_per_trade,
        "sharpe_annualised": sharpe_ann,
        "periods_per_year": ppy,
        "psr": psr,
        "dsr": dsr,
        "sharpe_ci_low": lo,
        "sharpe_ci_high": hi,
    }
