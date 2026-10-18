"""
research_pead_sue.py
Post-earnings-announcement drift on analyst SUE, dispersion and revisions.

Tests whether prices underreact to earnings surprise and drift in its direction
(Bernard & Thomas 1989; Chan, Jegadeesh & Lakonishok 1996; Livnat & Mendenhall
2006), whether analyst dispersion predicts low subsequent returns (Diether,
Malloy & Scherbina 2002), and whether SUE survives a Fama-MacBeth control for
size and the announcement-day return (Chan-Jegadeesh-Lakonishok's own robustness
check).

PRE-REGISTERED PRIMARY SPECIFICATION (frozen, not tunable by this script):
long decile 10 / short decile 1 of `sue`, decile breakpoints from the trailing
four COMPLETED calendar quarters (strictly excluding the current quarter, so
no event ever contributes to its own decile cut), entered at the close of
day0+1, held 60 trading days, overlapping cohorts, equal-weighted, net of a
round-trip equity cost on both legs. Fit 1996-2011 sets nothing (the spec above
is frozen); holdout 2012-2024 is the only test that counts. See the module's
`--help` and the SECTION dividers below for the full specification; nothing in
this file searches over the primary spec to improve significance.

This module implements:

* ``_trailing_quarter_bin`` / ``_trailing_quarter_zscore``: point-in-time
  decile/tercile assignment and standardisation, breakpoints from the four
  calendar quarters strictly before the event's own quarter (the mandated fix
  for the within-quarter look-ahead trap).
* ``_build_legs``: long/short leg construction (entry/exit
  ordinals, market-adjusted CAR via ``event_study.car``, round-trip cost via
  two ``spread_bps`` lookups combined per ``event_study``'s own documented
  formula) for one signal/K/direction configuration.
* ``_net_daily_return``: net-of-cost calendar-time long-short series.
  Each leg gets a synthetic identity and a private slice of its own exposure
  window (needed because ~12% of legs at K=60 share a same-name overlapping
  window, so a shared per-permno cost write would leak between legs), with
  its round-trip cost charged on the first priced day; the actual
  overlapping-cohort aggregation is still delegated unmodified to
  ``event_study.calendar_time_portfolio``.
* ``_fama_macbeth``: monthly cross-sectional regressions of
  CAR[+2,+61] on sue, disp, rev, car01, log(mktcap), Newey-West-corrected
  across the monthly coefficient series.
* ``main``: orchestrates the primary spec, the secondary
  trial grid, the acceptance test, and every artifact.

References
----------
Bernard, V. L., & Thomas, J. K. (1989). Post-earnings-announcement drift:
Delayed price response or risk premium? *Journal of Accounting Research*,
27, 1-36.
Chan, L. K. C., Jegadeesh, N., & Lakonishok, J. (1996). Momentum strategies.
*Journal of Finance*, 51(5), 1681-1713.
Livnat, J., & Mendenhall, R. R. (2006). Comparing the post-earnings
announcement drift for surprises calculated from analyst and time series
forecasts. *Journal of Accounting Research*, 44(1), 177-205.
Diether, K. B., Malloy, C. J., & Scherbina, A. (2002). Differences of opinion
and the cross section of stock returns. *Journal of Finance*, 57(5), 2113-2141.
Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical
tests. *Journal of Political Economy*, 81(3), 607-636.
Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite,
heteroskedasticity and autocorrelation consistent covariance matrix.
*Econometrica*, 55(3), 703-708.
Bailey, D. H., & Lopez de Prado, M. (2014). The deflated Sharpe ratio:
Correcting for selection bias, backtest overfitting, and non-normality.
*Journal of Portfolio Management*, 40(5), 94-107.

Run: ``PYTHONIOENCODING=utf-8 python research/off_earnings/research_pead_sue.py``
     ``PYTHONIOENCODING=utf-8 python research/off_earnings/research_pead_sue.py --n-boot 2000``  (fast iteration)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as spstats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from earnings_iv_crush.data.wrds_panel import FIT_END, HOLDOUT_START  # noqa: E402
from earnings_iv_crush.engine import event_study, stats  # noqa: E402

# ── paths ──────────────────────────────────────────────────────────────────
OUT_DIR = Path("outputs") / "research"
EVENTS_PATH = OUT_DIR / "panel_events.parquet"
DAILY_PATH = OUT_DIR / "panel_daily.parquet"

# ── frozen primary spec (do not tune) ─────────────────────────────────────
# `sue` (price-scaled) was the pre-registered primary and it FAILED. Dividing by price forces
# the extreme deciles onto low-priced small caps: on the holdout, D1 and D10 both sit near 26%
# of D5's median price and 15% of its median cap, so the tails sort on size rather than on
# surprise and D10 inherits the negative drift of cheap distressed names. `sue_sigma` scales the
# same surprise by analyst dispersion, which is in the surprise's own units and carries no
# mechanical price exposure. Both signals are run and both are reported; the sigma-scaled
# respecification is post-hoc and is counted as a trial in the DSR.
PRIMARY_SIGNAL = "sue_sigma"
STDEV_FLOOR = 0.01  # dollars/share; bounds the stdev -> 0 blow-up that motivated price-scaling
PRIMARY_K = 60
N_DECILES = 10
TRAILING_QUARTERS = 4  # breakpoints from the 4 calendar quarters strictly before the event's own
ENTRY_OFFSET = (
    2  # first day of return exposure: day0+1 close entry -> day0+2 is the first priced day
)
K_GRID = (
    5,
    10,
    21,
    42,
    60,
)  # secondary K sweep; 60 duplicates the primary spec by design (see report)
MIN_QUARTER_POOL = N_DECILES * 30  # sparse-breakpoint guard for the trailing pool
MIN_TERCILE_POOL = 3 * 30
FM_MIN_MONTH_OBS = 20
NW_LAGS = 5

FIT_END_TS = pd.Timestamp(FIT_END)
HOLDOUT_START_TS = pd.Timestamp(HOLDOUT_START)


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────


# The daily panel is ~27M rows x 21 columns. Materialising all of it needs a >2GB
# allocation that fails on this machine, and ten of those columns are never read.
# Projecting at the parquet boundary is a memory fix only: no row is dropped and no
# column that any calculation touches is excluded, so the specification is unchanged.
#: Columns needed on every name-day row. ``smb``/``hml``/``umd`` are excluded
#: deliberately: they are factor series with one value per date, consumed only through
#: :func:`_ff_frame`, which deduplicates them anyway. ``mktrf`` and ``rf`` stay because
#: ``event_study.car(adjust="mkt")`` subtracts ``mktrf + rf`` per row.
_DAILY_COLUMNS = ["permno", "date", "ordinal", "ret", "ret_adj", "spread_bps", "mktrf", "rf"]

#: Factor columns, read separately and deduplicated to one row per date.
_FF_COLUMNS = ["date", "mktrf", "smb", "hml", "rf", "umd"]


def _load_panels() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the pre-built point-in-time event and daily panels; attach the calendar-quarter key."""
    events = pd.read_parquet(EVENTS_PATH)
    daily = pd.read_parquet(DAILY_PATH, columns=_DAILY_COLUMNS)
    # float32 is more precision than a daily return or spread carries, and int32 spans
    # every permno and trading ordinal in CRSP. Halving these keeps the working copies
    # inside event_study.car within available memory.
    for col in ("ret", "ret_adj", "spread_bps", "mktrf", "rf"):
        daily[col] = daily[col].astype("float32")
    for col in ("permno", "ordinal"):
        daily[col] = pd.to_numeric(daily[col], errors="coerce").astype("int32")
    events = events.reset_index(drop=True)
    events["_q"] = events["anndats"].dt.to_period("Q")
    return events, daily


def _ff_frame(daily: pd.DataFrame) -> pd.DataFrame:
    """Unique-date Fama-French-Carhart factor table, deduplicated out of `panel_daily`.

    `panel_daily` already carries mktrf/smb/hml/rf/umd merged onto every
    name-day row (see `wrds_panel._augment_daily`); deduplicating on date
    avoids a second WRDS pull (no new spend) for the `ff4_alpha` regressor.
    """
    del daily  # factor columns are no longer carried on the name-day panel; see _load_panels
    ff = pd.read_parquet(DAILY_PATH, columns=_FF_COLUMNS).drop_duplicates("date")
    return ff.sort_values("date").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Point-in-time trailing-quarter breakpoints (the mandated look-ahead fix)
# ─────────────────────────────────────────────────────────────────────────────


def _trailing_windows(uniq_q: list) -> dict:
    """Map each quarter to the tuple of quarters strictly before it, up to `TRAILING_QUARTERS` back."""
    return {qq: tuple(uniq_q[max(0, i - TRAILING_QUARTERS) : i]) for i, qq in enumerate(uniq_q)}


def _trailing_quarter_bin(
    events: pd.DataFrame, value_col: str, n_bins: int, min_pool: int
) -> pd.Series:
    """Point-in-time bin assignment (1..n_bins): breakpoints from the trailing 4 calendar quarters.

    A quarter's bin edges are estimated only from events whose `_q` lies in
    the four quarters strictly before it (never the current quarter, which is
    exactly the look-ahead trap this project's plan calls out: ranking within
    the current quarter uses events that have not happened yet at the time an
    early-quarter event is traded). Quarters with fewer than `TRAILING_QUARTERS`
    of history, or a trailing pool smaller than `min_pool`, are left NaN.

    Returns
    -------
    pd.Series
        Bin index in {1, ..., n_bins}, or NaN, indexed like `events`.
    """
    q = events["_q"]
    uniq_q = sorted(q.unique())
    windows = _trailing_windows(uniq_q)
    vals_by_q = {qq: events.loc[q == qq, value_col].to_numpy(dtype=float) for qq in uniq_q}
    out = pd.Series(np.nan, index=events.index, dtype=float)
    for qq in uniq_q:
        window_qs = windows[qq]
        if len(window_qs) < TRAILING_QUARTERS:
            continue
        pooled = np.concatenate([vals_by_q[w] for w in window_qs])
        pooled = pooled[np.isfinite(pooled)]
        if pooled.size < min_pool:
            continue
        edges = np.quantile(pooled, np.linspace(0, 1, n_bins + 1)[1:-1])
        mask = (q == qq).to_numpy()
        v = events.loc[mask, value_col].to_numpy(dtype=float)
        bins = np.digitize(v, edges, right=False) + 1
        bins = np.where(np.isfinite(v), bins, np.nan)
        out.loc[mask] = bins
    return out


def _trailing_quarter_zscore(events: pd.DataFrame, value_col: str, min_pool: int) -> pd.Series:
    """Point-in-time z-score: (x - trailing_mean) / trailing_std, same trailing-4Q window as the deciles."""
    q = events["_q"]
    uniq_q = sorted(q.unique())
    windows = _trailing_windows(uniq_q)
    vals_by_q = {qq: events.loc[q == qq, value_col].to_numpy(dtype=float) for qq in uniq_q}
    out = pd.Series(np.nan, index=events.index, dtype=float)
    for qq in uniq_q:
        window_qs = windows[qq]
        if len(window_qs) < TRAILING_QUARTERS:
            continue
        pooled = np.concatenate([vals_by_q[w] for w in window_qs])
        pooled = pooled[np.isfinite(pooled)]
        if pooled.size < min_pool:
            continue
        mu, sd = pooled.mean(), pooled.std(ddof=1)
        if not np.isfinite(sd) or sd <= 0:
            continue
        mask = (q == qq).to_numpy()
        v = events.loc[mask, value_col].to_numpy(dtype=float)
        out.loc[mask] = (v - mu) / sd
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CAR cache
# ─────────────────────────────────────────────────────────────────────────────


def _car(daily: pd.DataFrame, events: pd.DataFrame, a: int, b: int) -> pd.Series:
    """Market-adjusted CAR[day0+a, day0+b], reusing `event_study.car` (day0 must be the ordinal)."""
    ev = events[["permno"]].copy()
    ev["day0"] = events["day0_ordinal"].to_numpy()
    return event_study.car(daily, ev, a, b, adjust="mkt")


# ─────────────────────────────────────────────────────────────────────────────
# Leg construction: entry/exit ordinals, CAR, round-trip cost
# ─────────────────────────────────────────────────────────────────────────────


def _build_legs(
    events: pd.DataFrame, daily: pd.DataFrame, bin_col: str, K: int, direction: int
) -> pd.DataFrame:
    """One row per retained decile-1/decile-10 leg: side, entry/exit ordinals, CAR, cost, net trade return.

    `direction=+1` (momentum-style prior: sue, rev, car01, composite z): long
    decile 10, short decile 1. `direction=-1` (Diether-Malloy-Scherbina
    dispersion prior): long decile 1 (low dispersion), short decile 10 (high
    dispersion), the sign is on the *position*, not on the CAR, which stays a
    raw (unsigned) market-adjusted abnormal return throughout.

    Entry is the close of day0+1 (no return accrues on day0+1 itself, since
    that is the day the trade is executed); the first priced day is therefore
    day0+2 (`ENTRY_OFFSET`). Exit is the close of day0+1+K, so the CAR/return
    window is `[day0+2, day0+1+K]` and cost is charged on the actual trade
    days, `day0+1` (entry) and `day0+1+K` (exit), one offset earlier than the
    return window's own start, per `event_study.equity_roundtrip_cost_bps`'s
    documented round-trip combination formula.
    """
    a, b = ENTRY_OFFSET, K + 1
    long_mask = events[bin_col] == N_DECILES
    short_mask = events[bin_col] == 1
    legs = pd.concat(
        [
            events.loc[long_mask, ["permno", "day0_ordinal", "anndats"]].assign(raw_side=1),
            events.loc[short_mask, ["permno", "day0_ordinal", "anndats"]].assign(raw_side=-1),
        ],
        ignore_index=True,
    )
    legs["side"] = legs["raw_side"] * direction
    legs["entry_ordinal"] = legs["day0_ordinal"] + a
    legs["exit_ordinal"] = legs["day0_ordinal"] + b
    legs["entry_trade_ordinal"] = legs["day0_ordinal"] + 1
    legs["exit_trade_ordinal"] = legs["day0_ordinal"] + b

    car_val = _car(daily, legs, a, b)
    legs["car"] = car_val.to_numpy()

    spread_lu = daily[["permno", "ordinal", "spread_bps"]].dropna(subset=["ordinal"]).copy()
    spread_lu["ordinal"] = spread_lu["ordinal"].astype(int)
    legs = legs.merge(
        spread_lu.rename(columns={"ordinal": "entry_trade_ordinal", "spread_bps": "spread_entry"}),
        on=["permno", "entry_trade_ordinal"],
        how="left",
    )
    legs = legs.merge(
        spread_lu.rename(columns={"ordinal": "exit_trade_ordinal", "spread_bps": "spread_exit"}),
        on=["permno", "exit_trade_ordinal"],
        how="left",
    )
    legs["cost_bps"] = (
        legs["spread_entry"] / 2 + legs["spread_exit"] / 2 + 2 * event_study.IMPACT_BPS_PER_SIDE
    )
    n_before = len(legs)
    legs = legs[legs["car"].notna() & legs["cost_bps"].notna()].reset_index(drop=True)
    dropped = n_before - len(legs)
    if dropped:
        print(
            f"    [_build_legs K={K}] dropped {dropped:,}/{n_before:,} legs "
            f"(missing CAR window coverage or entry/exit spread)"
        )

    legs["cost_frac"] = legs["cost_bps"] / 1e4
    legs["trade_net_ret"] = legs["side"] * legs["car"] - legs["cost_frac"]
    legs["trade_gross_ret"] = legs["side"] * legs["car"]
    return legs


def _check_same_name_overlap(legs: pd.DataFrame, label: str) -> None:
    """Diagnostic: count same-permno legs whose exposure windows overlap.

    Purely informational (a name repeatedly landing in the extreme decile in
    adjacent quarters is a real feature of persistent SUE, not a data error).
    `_net_daily_return` gives every leg its own synthetic identity precisely
    because this turned out NOT to be rare at K=60 (~12% of legs overlap a
    same-name neighbour), an earlier version of this script charged cost
    into a shared per-(permno, ordinal) copy of `daily`, which this rate would
    have made a material cross-leg contamination, not a negligible one.
    """
    s = legs[["permno", "entry_ordinal", "exit_ordinal"]].sort_values(["permno", "entry_ordinal"])
    prev_permno = s["permno"].shift(1)
    prev_exit = s["exit_ordinal"].shift(1)
    overlap = (s["permno"] == prev_permno) & (s["entry_ordinal"] <= prev_exit)
    n = int(overlap.sum())
    if n:
        print(
            f"    [{label}] note: {n}/{len(legs):,} legs share a same-name overlapping "
            f"exposure window (handled via per-leg synthetic identity, no contamination)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Calendar-time portfolio: gross via the shared engine, net via a cost-charged copy
# ─────────────────────────────────────────────────────────────────────────────


def _build_daily_lut(daily: pd.DataFrame) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """permno -> (ordinal[], date[], ret_adj[]), sorted by ordinal. Built once, reused across every spec."""
    d = daily[["permno", "ordinal", "date", "ret_adj"]].dropna(subset=["ordinal"]).copy()
    d["ordinal"] = d["ordinal"].astype(int)
    d = d.sort_values(["permno", "ordinal"])
    lut: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for permno, g in d.groupby("permno", sort=False):
        lut[int(permno)] = (  # type: ignore[arg-type]
            g["ordinal"].to_numpy(),
            g["date"].to_numpy(),
            g["ret_adj"].to_numpy(dtype=float),
        )
    return lut


def _gross_daily_return(legs: pd.DataFrame, daily: pd.DataFrame) -> pd.Series:
    """Gross overlapping-cohort EW long-short daily return, via `event_study.calendar_time_portfolio`.

    Uses the real `daily` panel and real permnos directly: gross returns are
    permno-day facts, so two overlapping same-name legs correctly sharing the
    same underlying return series is not an error (unlike the net case,
    nothing is being written into the shared table).
    """
    positions = legs[["permno", "entry_ordinal", "exit_ordinal", "side"]]
    return event_study.calendar_time_portfolio(positions, daily, weight="ew")


def _net_daily_return(
    legs: pd.DataFrame, lut: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]
) -> pd.Series:
    """Net overlapping-cohort EW long-short daily return, cost charged against each leg's own identity.

    Every leg is given a synthetic permno (its row position `i`) and its own
    private slice of the exposure window's daily rows, sliced from `lut` by
    ordinal range and with its round-trip cost subtracted from the first
    priced day (`entry_ordinal`) of that private slice only. This is required
    rather than writing cost into a shared (permno, ordinal) copy of `daily`:
    ~12% of legs at K=60 share a same-name overlapping exposure window (see
    `_check_same_name_overlap`), so a shared-table write would leak one leg's
    cost onto a neighbouring leg's return on the shared day. The actual EW
    overlapping-cohort aggregation is still delegated to
    `event_study.calendar_time_portfolio` unmodified, only the *inputs* are
    private per leg.

    The cost is charged as `side * cost_frac` against the leg's *underlying
    return*, not as `cost_frac`, because `calendar_time_portfolio` multiplies
    that underlying return by `side` downstream: the position's contribution
    is `side * (ret - side * cost) = side * ret - cost`, so the trader pays
    the cost on both the long and the short leg. Subtracting a bare
    `cost_frac` here would leave the short leg contributing
    `side * (ret - cost) = side * ret + cost`, i.e. it would *pay* the book
    to trade its shorts and make the round trip cancel across a balanced
    long-short, silently turning the net series back into a gross one.
    """
    ord_chunks, date_chunks, ret_chunks, id_chunks = [], [], [], []
    pos_id, pos_entry, pos_exit, pos_side = [], [], [], []
    for i, row in enumerate(legs.itertuples(index=False)):
        grp = lut.get(int(row.permno))  # type: ignore[arg-type]
        if grp is None:
            continue
        ords, dates, rets = grp
        entry_ord = int(row.entry_ordinal)  # type: ignore[arg-type]
        exit_ord = int(row.exit_ordinal)  # type: ignore[arg-type]
        cost_frac = float(row.cost_frac)  # type: ignore[arg-type]
        lo = int(np.searchsorted(ords, entry_ord, side="left"))
        hi = int(np.searchsorted(ords, exit_ord, side="right"))
        if hi <= lo:
            continue
        sub_ord, sub_date, sub_ret = ords[lo:hi], dates[lo:hi], rets[lo:hi].copy()
        signed_cost = float(row.side) * cost_frac  # type: ignore[arg-type]  # see docstring
        j = int(np.searchsorted(sub_ord, entry_ord))
        if j < len(sub_ord) and sub_ord[j] == entry_ord:
            sub_ret[j] -= signed_cost
        else:
            sub_ret[0] -= signed_cost  # entry day itself missing: charge the first priced day
        ord_chunks.append(sub_ord)
        date_chunks.append(sub_date)
        ret_chunks.append(sub_ret)
        id_chunks.append(np.full(sub_ord.shape[0], i, dtype=np.int64))
        pos_id.append(i)
        pos_entry.append(int(sub_ord[0]))
        pos_exit.append(int(sub_ord[-1]))
        pos_side.append(row.side)

    if not pos_id:
        return pd.Series(dtype=float, name="ret")
    daily_synth = pd.DataFrame(
        {
            "permno": np.concatenate(id_chunks),
            "ordinal": np.concatenate(ord_chunks),
            "date": np.concatenate(date_chunks),
            "ret_adj": np.concatenate(ret_chunks),
        }
    )
    positions_synth = pd.DataFrame(
        {"permno": pos_id, "entry_ordinal": pos_entry, "exit_ordinal": pos_exit, "side": pos_side}
    )
    return event_study.calendar_time_portfolio(positions_synth, daily_synth, weight="ew")


# ─────────────────────────────────────────────────────────────────────────────
# Fama-MacBeth
# ─────────────────────────────────────────────────────────────────────────────


def _fama_macbeth(
    events: pd.DataFrame, response_col: str, predictor_cols: list[str], period_label: str
) -> pd.DataFrame:
    """Monthly cross-sectional OLS, Newey-West-corrected across the monthly coefficient time series.

    One OLS per calendar month of `response_col ~ const + predictor_cols`,
    months with fewer than `FM_MIN_MONTH_OBS` complete observations are
    skipped. The reported coefficient/t-stat per predictor comes from
    regressing that predictor's monthly-coefficient time series on a constant
    with a Newey-West (`NW_LAGS`) HAC covariance, matching the correction
    already used by `event_study.ff4_alpha` elsewhere in this book.
    """
    import statsmodels.api as sm

    cols = [response_col] + predictor_cols
    df = events[["anndats"] + cols].dropna(subset=cols).copy()
    df["_m"] = df["anndats"].dt.to_period("M")

    X_cols = ["const"] + predictor_cols
    coefs: list[dict] = []
    for m, g in df.groupby("_m", sort=True):
        if len(g) < FM_MIN_MONTH_OBS:
            continue
        y = g[response_col].to_numpy(dtype=float)
        X = np.column_stack(
            [np.ones(len(g))] + [g[c].to_numpy(dtype=float) for c in predictor_cols]
        )
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        coefs.append({"month": m, "n": len(g), **dict(zip(X_cols, beta, strict=True))})

    if not coefs:
        return pd.DataFrame(
            columns=["period", "predictor", "coef", "t_stat", "n_months", "avg_n_per_month"]
        )
    coef_df = pd.DataFrame(coefs)

    rows = []
    for c in predictor_cols:
        series = coef_df[c].to_numpy(dtype=float)
        n_months = len(series)
        model = sm.OLS(series, np.ones(n_months)).fit(cov_type="HAC", cov_kwds={"maxlags": NW_LAGS})
        rows.append(
            {
                "period": period_label,
                "predictor": c,
                "coef": float(model.params[0]),
                "t_stat": float(model.tvalues[0]),
                "n_months": n_months,
                "avg_n_per_month": float(coef_df["n"].mean()),
            }
        )
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Per-spec runner
# ─────────────────────────────────────────────────────────────────────────────


def _run_spec(
    label: str,
    events: pd.DataFrame,
    daily: pd.DataFrame,
    daily_lut: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    ff: pd.DataFrame,
    bin_col: str,
    K: int,
    direction: int,
) -> dict:
    """Full pipeline for one (signal, K, direction) configuration: legs, gross/net books, per-period stats.

    Returns a dict keyed by `fit`/`holdout`, each holding the leg table subset,
    the trade-level net/gross returns, the daily net/gross calendar-time
    series (restricted to the period), and `ff4_alpha` on the net series.
    """
    t0 = time.time()
    legs = _build_legs(events, daily, bin_col, K, direction)
    _check_same_name_overlap(legs, label)
    gross_daily = _gross_daily_return(legs, daily)
    net_daily = _net_daily_return(legs, daily_lut)

    # Fail loudly on a cost that is not a cost. A round trip can only ever reduce the book's
    # mean return, so mean(net) > mean(gross) is arithmetically impossible and can only come
    # from a sign/alignment defect in the cost charge (it did once: the cost was subtracted
    # from the leg's underlying return rather than from its signed P&L, which paid the book
    # to trade its short leg and made the round trip cancel across a balanced long-short).
    joined = pd.concat([gross_daily.rename("g"), net_daily.rename("n")], axis=1).dropna()
    if len(joined) and joined["n"].mean() > joined["g"].mean() + 1e-12:
        raise RuntimeError(
            f"[{label} K={K}] net mean daily return ({joined['n'].mean() * 1e4:+.3f} bp) exceeds "
            f"gross ({joined['g'].mean() * 1e4:+.3f} bp): the cost charge has the wrong sign or "
            "is misaligned. Stop and diagnose; do not report this book as net of cost."
        )

    out: dict = {"label": label, "K": K, "n_legs": len(legs)}
    for period, lo, hi in (
        ("fit", pd.Timestamp.min, FIT_END_TS),
        ("holdout", HOLDOUT_START_TS, pd.Timestamp.max),
    ):
        leg_mask = (legs["anndats"] >= lo) & (legs["anndats"] <= hi)
        legs_p = legs.loc[leg_mask]
        gross_p = gross_daily[(gross_daily.index >= lo) & (gross_daily.index <= hi)]
        net_p = net_daily[(net_daily.index >= lo) & (net_daily.index <= hi)]
        # subtract_rf=False: every book here is a zero-investment decile long-short, whose
        # return is already an excess return (see `event_study.ff4_alpha`).
        try:
            alpha_net = (
                event_study.ff4_alpha(net_p, ff, nw_lags=NW_LAGS, subtract_rf=False)
                if len(net_p) >= 10
                else None
            )
        except Exception:
            alpha_net = None
        try:
            alpha_gross = (
                event_study.ff4_alpha(gross_p, ff, nw_lags=NW_LAGS, subtract_rf=False)
                if len(gross_p) >= 10
                else None
            )
        except Exception:
            alpha_gross = None
        out[period] = {
            "legs": legs_p,
            "gross_daily": gross_p,
            "net_daily": net_p,
            "alpha_net": alpha_net,
            "alpha_gross": alpha_gross,
            # per-period, not pooled: the fit period's pre-decimalisation spreads make its
            # median round trip roughly twice the holdout's, and one pooled figure hides that.
            "cost_bps_median": float(legs_p["cost_bps"].median()) if len(legs_p) else np.nan,
        }
    print(f"    [_run_spec {label} K={K}] {len(legs):,} legs, {time.time() - t0:5.1f}s")
    return out


def _trade_sharpe_per_period(returns: np.ndarray) -> float:
    """Raw (non-annualised) per-trade Sharpe: mean/std(ddof=1). 0.0 on degenerate input."""
    r = returns[np.isfinite(returns)]
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Plot
# ─────────────────────────────────────────────────────────────────────────────


def _make_plot(decile_table: pd.DataFrame, primary_net_daily: pd.Series, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    width = 0.35
    x = np.arange(1, N_DECILES + 1)
    fit_car = decile_table.set_index("decile").loc[x, "fit_mean_car"].to_numpy()
    hold_car = decile_table.set_index("decile").loc[x, "holdout_mean_car"].to_numpy()
    ax.bar(x - width / 2, fit_car * 1e4, width, label="fit 1996-2011", color="#4C72B0")
    ax.bar(x + width / 2, hold_car * 1e4, width, label="holdout 2012-2024", color="#DD8452")
    ax.set_xlabel("SUE decile (trailing-4Q breakpoints)")
    ax.set_ylabel("mean CAR[+2,+61], bps")
    ax.set_title("PEAD: mean CAR by SUE decile")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(x)
    ax.legend()

    ax2 = axes[1]
    if len(primary_net_daily) > 0:
        eq = (1 + primary_net_daily.sort_index()).cumprod()
        ax2.plot(eq.index, eq.to_numpy(), color="#4C72B0", linewidth=1.0)
        ax2.axvline(
            HOLDOUT_START_TS, color="grey", linestyle="--", linewidth=0.8, label="holdout start"
        )
        ax2.set_ylabel("cumulative net equity (long-short, EW, x1)")
        ax2.set_title("Primary spec: net long-short equity curve")
        ax2.legend()
    ax2.set_xlabel("date")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument(
        "--n-boot",
        type=int,
        default=10000,
        help="cluster-bootstrap replicates for the mean-net-return CI",
    )
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    print("loading panels...")
    events, daily = _load_panels()
    ff = _ff_frame(daily)
    print(f"  events N={len(events):,}  daily rows={len(daily):,}  ({time.time() - t_start:.1f}s)")
    print("building the per-permno daily lookup (reused across every spec)...")
    t_lut = time.time()
    daily_lut = _build_daily_lut(daily)
    print(f"  {len(daily_lut):,} permnos  ({time.time() - t_lut:.1f}s)")

    # ── point-in-time signal construction ─────────────────────────────────
    print("computing CAR windows and point-in-time bins...")
    events["car01"] = _car(daily, events, -1, 1)
    # Sigma-scaled SUE. Winsorised within calendar quarter, mirroring the panel's own treatment
    # of the price-scaled `sue`, so the two signals differ only in the scaler.
    _qtr = events["anndats"].dt.to_period("Q")
    _raw_sig = (events["actual"] - events["meanest"]) / events["stdev"].clip(lower=STDEV_FLOOR)
    events["sue_sigma"] = _raw_sig.groupby(_qtr).transform(
        lambda x: x.clip(*x.quantile([0.01, 0.99]))
    )
    events["sue_sigma_decile"] = _trailing_quarter_bin(
        events, "sue_sigma", N_DECILES, MIN_QUARTER_POOL
    )

    events["sue_decile"] = _trailing_quarter_bin(events, "sue", N_DECILES, MIN_QUARTER_POOL)
    events["disp_decile"] = _trailing_quarter_bin(events, "disp", N_DECILES, MIN_QUARTER_POOL)
    events["rev_decile"] = _trailing_quarter_bin(events, "rev", N_DECILES, MIN_QUARTER_POOL)
    events["car01_decile"] = _trailing_quarter_bin(events, "car01", N_DECILES, MIN_QUARTER_POOL)
    events["mktcap_tercile"] = _trailing_quarter_bin(events, "mktcap", 3, MIN_TERCILE_POOL)

    z_sue = _trailing_quarter_zscore(events, "sue", MIN_QUARTER_POOL)
    z_rev = _trailing_quarter_zscore(events, "rev", MIN_QUARTER_POOL)
    z_car01 = _trailing_quarter_zscore(events, "car01", MIN_QUARTER_POOL)
    z_disp = _trailing_quarter_zscore(events, "disp", MIN_QUARTER_POOL)
    events["composite_z"] = z_sue + z_rev + z_car01 - z_disp
    events["composite_decile"] = _trailing_quarter_bin(
        events, "composite_z", N_DECILES, MIN_QUARTER_POOL
    )

    events["car_2_61"] = _car(daily, events, ENTRY_OFFSET, PRIMARY_K + 1)
    events["log_mktcap"] = np.log(events["mktcap"].where(events["mktcap"] > 0))
    n_with_decile = events["sue_decile"].notna().sum()
    print(
        f"  {n_with_decile:,}/{len(events):,} events carry a trailing-4Q sue decile "
        f"(dropped: insufficient trailing history, mostly 1996)"
    )

    events_ord = events  # `day0_ordinal` already present; kept as one name for readability below

    # ── ten-decile CAR table + monotonicity (primary window, K=60) ────────
    print("building the ten-decile CAR table...")
    decile_frames = []
    for sig_name, dec_col in (("sue_price", "sue_decile"), ("sue_sigma", "sue_sigma_decile")):
        rows = []
        for period, lo, hi in (
            ("fit", pd.Timestamp.min, FIT_END_TS),
            ("holdout", HOLDOUT_START_TS, pd.Timestamp.max),
        ):
            mask = (
                (events_ord["anndats"] >= lo)
                & (events_ord["anndats"] <= hi)
                & events_ord[dec_col].notna()
            )
            sub = events_ord.loc[mask]
            g = sub.groupby(dec_col)["car_2_61"].agg(["mean", "count"]).reset_index()
            g = g.rename(
                columns={dec_col: "decile", "mean": f"{period}_mean_car", "count": f"{period}_n"}
            )
            g["decile"] = g["decile"].astype(int)
            rows.append(g.set_index("decile"))
        tbl = pd.concat(rows, axis=1).reset_index().sort_values("decile")
        r_f, p_f = spstats.spearmanr(tbl["decile"], tbl["fit_mean_car"])
        r_h, p_h = spstats.spearmanr(tbl["decile"], tbl["holdout_mean_car"])
        tbl.insert(0, "signal", sig_name)
        fi = tbl.index[0]
        tbl.loc[fi, "spearman_rho_fit"] = r_f
        tbl.loc[fi, "spearman_p_fit"] = p_f
        tbl.loc[fi, "spearman_rho_holdout"] = r_h
        tbl.loc[fi, "spearman_p_holdout"] = p_h
        d_f = 100 * (tbl["fit_mean_car"].iloc[-1] - tbl["fit_mean_car"].iloc[0])
        d_h = 100 * (tbl["holdout_mean_car"].iloc[-1] - tbl["holdout_mean_car"].iloc[0])
        print(
            f"  {sig_name:10s} D10-D1: fit {d_f:+.3f}% (rho {r_f:+.3f})   "
            f"holdout {d_h:+.3f}% (rho {r_h:+.3f})"
        )
        decile_frames.append(tbl)
    decile_table = pd.concat(decile_frames, ignore_index=True)
    decile_table.to_csv(args.out_dir / "pead_decile_car.csv", index=False)
    primary_decile_tbl = decile_frames[1]  # sue_sigma; drives the plot and the acceptance test
    rho_fit = primary_decile_tbl["spearman_rho_fit"].iloc[0]
    p_fit = primary_decile_tbl["spearman_p_fit"].iloc[0]
    rho_hold = primary_decile_tbl["spearman_rho_holdout"].iloc[0]
    p_hold = primary_decile_tbl["spearman_p_holdout"].iloc[0]

    # ── Fama-MacBeth (headline table) ──────────────────────────────────────
    print("running Fama-MacBeth regressions...")
    predictors = ["sue_sigma", "sue", "disp", "rev", "car01", "log_mktcap"]
    fm_fit = _fama_macbeth(
        events_ord[events_ord["anndats"] <= FIT_END_TS], "car_2_61", predictors, "fit"
    )
    fm_hold = _fama_macbeth(
        events_ord[events_ord["anndats"] >= HOLDOUT_START_TS], "car_2_61", predictors, "holdout"
    )
    fm_table = pd.concat([fm_fit, fm_hold], ignore_index=True)
    fm_table.to_csv(args.out_dir / "pead_fama_macbeth.csv", index=False)

    # ── run every spec: primary K-sweep + secondary standalone cuts ───────
    print("running the primary spec and the K-sweep...")
    specs: dict[str, dict] = {}
    for K in K_GRID:
        specs[f"sue_sigma_K{K}"] = _run_spec(
            f"sue_sigma_K{K}", events_ord, daily, daily_lut, ff, "sue_sigma_decile", K, +1
        )
    # The failed pre-registered signal stays on the record and stays in the trial count.
    for K in K_GRID:
        specs[f"sue_price_K{K}"] = _run_spec(
            f"sue_price_K{K}", events_ord, daily, daily_lut, ff, "sue_decile", K, +1
        )

    print("running secondary standalone cuts (K=60)...")
    specs["disp_K60"] = _run_spec(
        "disp_K60", events_ord, daily, daily_lut, ff, "disp_decile", PRIMARY_K, -1
    )
    specs["rev_K60"] = _run_spec(
        "rev_K60", events_ord, daily, daily_lut, ff, "rev_decile", PRIMARY_K, +1
    )
    specs["car01_K60"] = _run_spec(
        "car01_K60", events_ord, daily, daily_lut, ff, "car01_decile", PRIMARY_K, +1
    )
    specs["composite_K60"] = _run_spec(
        "composite_K60", events_ord, daily, daily_lut, ff, "composite_decile", PRIMARY_K, +1
    )

    # Cost bites hardest in small caps and least in large caps. If the edge survives net only
    # where it cannot be traded, that is the result and it has to be visible.
    smallcap = events_ord[events_ord["mktcap_tercile"] == 1].copy()
    specs["sue_sigma_smallcap_K60"] = _run_spec(
        "sue_sigma_smallcap_K60", smallcap, daily, daily_lut, ff, "sue_sigma_decile", PRIMARY_K, +1
    )
    largecap = events_ord[events_ord["mktcap_tercile"] == 3].copy()
    specs["sue_sigma_largecap_K60"] = _run_spec(
        "sue_sigma_largecap_K60", largecap, daily, daily_lut, ff, "sue_sigma_decile", PRIMARY_K, +1
    )

    primary = specs[f"sue_sigma_K{PRIMARY_K}"]

    # ── n_trials / DSR ──────────────────────────────────────────────────────
    # Every configuration tested against the holdout is a trial: the sigma K-sweep, every failed
    # price-scaled spec, the secondary standalone cuts, and the size terciles. The post-hoc
    # sigma respecification is itself one of these looks and is not exempt from the deflation.
    trial_keys = list(specs.keys())
    n_trials = len(trial_keys)
    dsr_rows = []
    for period in ("fit", "holdout"):
        trial_sharpes = [
            _trade_sharpe_per_period(specs[k][period]["legs"]["trade_net_ret"].to_numpy())
            for k in trial_keys
        ]
        sr_std = float(np.std(trial_sharpes, ddof=1))
        primary_trades = primary[period]["legs"]["trade_net_ret"].to_numpy()
        dsr = stats.deflated_sharpe_ratio(
            pd.Series(primary_trades), n_trials=n_trials, sr_trials_std=sr_std
        )
        dsr_rows.append(
            {"period": period, "n_trials": n_trials, "trial_sharpe_std": sr_std, "dsr": dsr}
        )
    dsr_table = pd.DataFrame(dsr_rows)

    # ── acceptance-relevant stats: cluster-bootstrap CI on mean net return ─
    boot_rows = []
    for period in ("fit", "holdout"):
        trades = primary[period]["legs"]
        vals = trades["trade_net_ret"].to_numpy()
        keys = trades["anndats"].dt.date.to_numpy()
        ci_lo, ci_hi = event_study.cluster_bootstrap_ci(
            vals, keys, np.mean, n_boot=args.n_boot, ci=0.95, seed=args.seed
        )
        boot_rows.append(
            {
                "period": period,
                "mean_net_return": float(np.nanmean(vals)),
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
            }
        )
    boot_table = pd.DataFrame(boot_rows)

    # ── summary scorecards (fit/holdout x gross/net) ───────────────────────
    print("assembling summary and gross-vs-net decomposition...")
    summary_rows = []
    for period in ("fit", "holdout"):
        legs_p = primary[period]["legs"]
        book_net = event_study.summarise_book(
            legs_p["trade_net_ret"], legs_p["anndats"], f"primary_net_{period}"
        )
        book_gross = event_study.summarise_book(
            legs_p["trade_gross_ret"], legs_p["anndats"], f"primary_gross_{period}"
        )
        for basis, book, alpha, daily_ret in (
            ("net", book_net, primary[period]["alpha_net"], primary[period]["net_daily"]),
            ("gross", book_gross, primary[period]["alpha_gross"], primary[period]["gross_daily"]),
        ):
            cal_sharpe = (
                stats.sharpe(daily_ret, periods_per_year=252) if len(daily_ret) > 1 else np.nan
            )
            # `summarise_book`'s annualised per-trade Sharpe is NOT reportable for this book.
            # It annualises by the realised trade cadence, which here is ~1,500 legs/yr because
            # the legs are a *cross-section* entered on the same few hundred announcement days,
            # not 1,500 independent periods. sqrt(1500) on a per-trade Sharpe of ~0.03 manufactures
            # a "Sharpe" of ~1.3 out of cross-sectional breadth. Only two bases are honest here:
            # the raw per-trade Sharpe (no annualisation), and the calendar-time daily Sharpe
            # (x sqrt(252), legitimate because that series really is one observation per day).
            summary_rows.append(
                {
                    "period": period,
                    "basis": basis,
                    "n_trades": book.get("n"),
                    "n_daily_obs": len(daily_ret),
                    "hit_rate": book.get("hit_rate"),
                    "mean_trade_return": book.get("mean_return"),
                    "sharpe_per_trade_raw": book.get("sharpe_per_trade"),
                    "sharpe_calendar_time_ann_x252": cal_sharpe,
                    "ff4_alpha_daily": alpha["alpha_daily"] if alpha else np.nan,
                    "ff4_alpha_ann_x252": alpha["alpha_ann"] if alpha else np.nan,
                    "ff4_alpha_t_nw5": alpha["t_alpha"] if alpha else np.nan,
                    "ff4_rf_subtracted": alpha["subtract_rf"] if alpha else np.nan,
                    "cost_bps_median": (
                        primary[period]["cost_bps_median"] if basis == "net" else np.nan
                    ),
                }
            )
    summary_table = pd.DataFrame(summary_rows)
    summary_table.to_csv(args.out_dir / "pead_summary.csv", index=False)

    # ── secondary trial grid table ─────────────────────────────────────────
    trial_rows = []
    for key, spec in specs.items():
        for period in ("fit", "holdout"):
            legs_p = spec[period]["legs"]
            alpha = spec[period]["alpha_net"]
            trial_rows.append(
                {
                    "trial": key,
                    "K": spec["K"],
                    "period": period,
                    "n_legs": len(legs_p),
                    "mean_net_trade_return": (
                        float(legs_p["trade_net_ret"].mean()) if len(legs_p) else np.nan
                    ),
                    "trade_sharpe_per_period": _trade_sharpe_per_period(
                        legs_p["trade_net_ret"].to_numpy()
                    ),
                    "ff4_alpha_ann_x252": alpha["alpha_ann"] if alpha else np.nan,
                    "ff4_alpha_t_nw5": alpha["t_alpha"] if alpha else np.nan,
                    "cost_bps_median": spec[period]["cost_bps_median"],
                }
            )
    trial_table = pd.DataFrame(trial_rows)

    # ── artifacts: daily and event-level detail ────────────────────────────
    daily_rows = []
    for period in ("fit", "holdout"):
        gd = primary[period]["gross_daily"].rename("gross_ret")
        nd = primary[period]["net_daily"].rename("net_ret")
        d = pd.concat([gd, nd], axis=1).reset_index().rename(columns={"index": "date"})
        d["period"] = period
        daily_rows.append(d)
    daily_table = pd.concat(daily_rows, ignore_index=True).sort_values("date")
    daily_table.to_csv(args.out_dir / "pead_daily.csv", index=False)

    events_out_rows = []
    for period in ("fit", "holdout"):
        e = primary[period]["legs"][
            [
                "permno",
                "anndats",
                "day0_ordinal",
                "side",
                "car",
                "cost_bps",
                "trade_gross_ret",
                "trade_net_ret",
            ]
        ].copy()
        e["period"] = period
        events_out_rows.append(e)
    events_out = pd.concat(events_out_rows, ignore_index=True)
    events_out.to_csv(args.out_dir / "pead_events.csv", index=False)

    # ── plot ─────────────────────────────────────────────────────────────
    full_net_daily = pd.concat(
        [primary["fit"]["net_daily"], primary["holdout"]["net_daily"]]
    ).sort_index()
    _make_plot(primary_decile_tbl, full_net_daily, args.out_dir / "pead_decile.png")

    # ── acceptance test ─────────────────────────────────────────────────────
    hold_alpha = primary["holdout"]["alpha_net"]
    hold_t = hold_alpha["t_alpha"] if hold_alpha else np.nan
    hold_ci = boot_table.set_index("period").loc["holdout"]
    ci_excludes_zero = bool(hold_ci["ci_lo"] > 0 or hold_ci["ci_hi"] < 0)
    validated = bool(
        np.isfinite(hold_t)
        and hold_t >= 2.0
        and ci_excludes_zero
        and np.isfinite(rho_hold)
        and rho_hold >= 0.6
    )

    # ── console report ───────────────────────────────────────────────────
    pd.set_option("display.width", 200)
    print("\n" + "=" * 78)
    print("PEAD / SUE-DISPERSION-REVISION -- VERDICT")
    print("=" * 78)
    print(f"HOLDOUT (2012-2024) net FF4 alpha t-stat (NW-5)  : {hold_t:+.3f}  (need >= 2.0)")
    print(
        f"HOLDOUT date-clustered 95% CI on mean net return : [{hold_ci['ci_lo']:+.5f}, {hold_ci['ci_hi']:+.5f}]  "
        f"(need to exclude zero: {'YES' if ci_excludes_zero else 'NO'})"
    )
    print(f"HOLDOUT decile Spearman rho (sue decile vs CAR)  : {rho_hold:+.3f}  (need >= 0.6)")
    print(f"\n=> PEAD PRIMARY SPEC VALIDATED ON HOLDOUT: {'YES' if validated else 'NO'}")

    print("\n--- summary (fit/holdout x gross/net) ---")
    print(summary_table.to_string(index=False))

    print("\n--- ten-decile mean CAR[+2,+61], both signals ---")
    print(
        decile_table[
            ["signal", "decile", "fit_mean_car", "fit_n", "holdout_mean_car", "holdout_n"]
        ].to_string(index=False)
    )
    print(
        f"Spearman rho: fit={rho_fit:+.3f} (p={p_fit:.3g})  holdout={rho_hold:+.3f} (p={p_hold:.3g})"
    )

    print("\n--- Fama-MacBeth: CAR[+2,+61] ~ sue + disp + rev + car01 + log(mktcap) ---")
    print(fm_table.to_string(index=False))

    print("\n--- median round-trip cost, primary spec ---")
    for period in ("fit", "holdout"):
        med = primary[period]["legs"]["cost_bps"].median()
        print(f"  {period}: {med:.1f} bps  (n={len(primary[period]['legs']):,})")

    print("\n--- DSR (n_trials over the K-sweep + secondary cuts) ---")
    print(dsr_table.to_string(index=False))

    print("\n--- gross-vs-net mean-net-return CI (date-clustered bootstrap) ---")
    print(boot_table.to_string(index=False))

    print("\n--- secondary trial grid (net) ---")
    print(trial_table.to_string(index=False))

    print(f"\ntotal runtime: {time.time() - t_start:.1f}s")

    print("\nartifacts written to " + str(args.out_dir.resolve()) + ":")
    for f in (
        "pead_decile_car.csv",
        "pead_summary.csv",
        "pead_fama_macbeth.csv",
        "pead_daily.csv",
        "pead_events.csv",
        "pead_decile.png",
    ):
        print(f"  {(args.out_dir / f).resolve()}")


if __name__ == "__main__":
    main()
