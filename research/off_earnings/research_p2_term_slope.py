"""
research_p2_term_slope.py
P2: the de-eventised, short-dated term-structure slope sort on free DoltHub chains.

Pre-registration ``research/off_earnings/preregs/p2_term_slope_prereg.md`` (hash in
``outputs/research/prereg_p2_term_slope.json``). Reuses the slope builder in
``research/off_earnings/pivot_vasquez_slope.py`` (universe, DTE buckets, ATM IV, parity spot) and replaces its
monthly realised-move proxy with the pre-registered trade: the middle-expiry ATM straddle bought
or sold at the month-end close and held to expiry, settled at intrinsic, with every name-month
that has an earnings announcement inside the holding window excluded.

Three stages, each cached so the pull can stop and resume:

    --pull      formation-date chains from DoltHub (date-pinned, one ticker-date per call),
                yfinance closes un-adjusted for splits, and the earnings calendars
    --score     build trades, sort, score both arms, write outputs/research/p2_term_slope/

Usage:
    python research/off_earnings/research_p2_term_slope.py --pull --workers 4
    python research/off_earnings/research_p2_term_slope.py --score

References
----------
Vasquez, A. (2017). Equity Volatility Term Structures and the Cross Section of Option Returns.
*Journal of Financial and Quantitative Analysis* 52(6), 2727-2754.
Goyal, A. and Saretto, A. (2009). Cross-section of option returns and volatility. *Journal of
Financial Economics* 94(2), 310-326.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option Pricing of Earnings
Announcement Risks. *Review of Financial Studies* 32(2), 646-687.
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-Based Improvements for
Inference with Clustered Errors. *Review of Economics and Statistics* 90(3), 414-427.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import dolthub_options as dolt  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio, nyse_sessions  # noqa: E402
from research.off_earnings.pivot_vasquez_slope import (  # noqa: E402
    DEFAULT_UNIVERSE,
    LONG_DTE,
    SHORT_DTE,
    _atm_iv,
    implied_spot,
)

# ── frozen in the pre-registration ───────────────────────────────────────────

START, END = "2021-01-01", "2026-08-31"  # formation months
MID_DTE = (21, 35)  # traded straddle: the middle of DoltHub's three expiries
BACK_WINDOW_DAYS = 59  # clean-signal subsample: no event inside the back leg either
N_QUANTILES = 5
MIN_NAMES = 10
N_BOOT = 5000
N_NULL = 1000
SEED = 0
N_TRIALS = 1497
FB_UNTIL = pd.Timestamp("2022-06-09")  # META traded as FB before this date

# ── paths and transport ──────────────────────────────────────────────────────

CACHE = Path("data/cache/dolthub_p2")
CLOSES = CACHE / "closes_unadjusted.parquet"
EARN_DOLT = CACHE / "earnings_dolthub.parquet"
SPLITS = CACHE / "splits.parquet"
EARN_COMP = CACHE / "earnings_compustat.parquet"
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/p2_term_slope")
DOLT_OPTIONS = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
DOLT_EARNINGS = "https://www.dolthub.com/api/v1alpha1/post-no-preference/earnings/master"
STRIKE_WINDOW = 0.10  # ATM and the nearest six contracts sit well inside +/-10%
PARITY_TOL = 0.03  # formation close vs chain parity spot; a split basis error misses by far more


def month_candidates() -> dict[pd.Timestamp, list[pd.Timestamp]]:
    """Candidate formation sessions per month, latest first (amendment 01).

    NYSE sessions only, from the month's last session back to no more than five calendar
    days before the calendar month-end. DoltHub snapshots exist only on some sessions, so
    each candidate is queried by its exact date and the latest non-empty one is used.
    """
    s = nyse_sessions(pd.Timestamp(START), pd.Timestamp(END))
    out = {}
    for _, g in pd.Series(s, index=s).groupby(s.to_period("M")):
        month_end = g.index.max().to_period("M").end_time.normalize()
        window = g[g.index >= month_end - pd.Timedelta(days=5)]
        out[pd.Timestamp(g.index.max())] = [pd.Timestamp(d) for d in window.index[::-1]]
    return out


def dolt_symbol(ticker: str, day: pd.Timestamp) -> str:
    return "FB" if ticker == "META" and day < FB_UNTIL else ticker


def _chain_path(ticker: str, day: pd.Timestamp) -> Path:
    return CACHE / "chains" / f"{ticker}_{day.date()}.parquet"


def _resolve(ticker: str, candidates: list[pd.Timestamp]) -> tuple[str, pd.Timestamp | None]:
    """The formation snapshot for one name-month from the cache.

    ``("ok", date)`` for the latest non-empty candidate, ``("unpulled", None)`` if a
    candidate ahead of any non-empty one has not been fetched, ``("none", None)`` if every
    candidate was fetched and empty.
    """
    for d in candidates:
        path = _chain_path(ticker, d)
        if not path.exists():
            return "unpulled", None
        if not pd.read_parquet(path).empty:
            return "ok", d
    return "none", None


# ── pull ─────────────────────────────────────────────────────────────────────


def pull_closes() -> pd.DataFrame:
    """Daily closes on the strikes' contemporaneous basis (split-unadjusted).

    yfinance's ``Close`` is split-adjusted; multiplying each close by the product of the
    split ratios dated after it restores the price the options were struck against.
    """
    import yfinance as yf

    frames = []
    for t in DEFAULT_UNIVERSE:
        tk = yf.Ticker(t)
        h = tk.history(start="2020-12-01", end="2026-10-15", auto_adjust=False)["Close"].dropna()
        idx = pd.DatetimeIndex(h.index)
        h.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
        splits = tk.splits
        factor = pd.Series(1.0, index=h.index)
        if splits is not None and len(splits):
            sidx = pd.DatetimeIndex(splits.index)
            sidx = (sidx.tz_localize(None) if sidx.tz is not None else sidx).normalize()
            for d, ratio in zip(sidx, splits.to_numpy(dtype=float), strict=True):
                factor[h.index < d] *= ratio
        frames.append(pd.DataFrame({"ticker": t, "date": h.index, "close": h.values * factor}))
    out = pd.concat(frames, ignore_index=True)
    missing = sorted(set(DEFAULT_UNIVERSE) - set(out["ticker"]))
    print(f"  closes: {len(out):,} rows, {out['ticker'].nunique()} names, missing {missing}")
    if out.empty:
        raise SystemExit("no closes pulled; refusing to continue")
    return out


def pull_splits() -> pd.DataFrame:
    """The yfinance split record per name (amendment 02)."""
    import yfinance as yf

    rows = []
    for t in DEFAULT_UNIVERSE:
        sp = yf.Ticker(t).splits
        if sp is None or not len(sp):
            continue
        idx = pd.DatetimeIndex(sp.index)
        idx = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
        rows += [
            {"ticker": t, "date": d, "ratio": float(r)}
            for d, r in zip(idx, sp.to_numpy(dtype=float), strict=True)
        ]
    out = pd.DataFrame(rows, columns=["ticker", "date", "ratio"])
    print(f"  splits: {len(out)} records across {out['ticker'].nunique()} names")
    return out


def pull_earnings_dolthub() -> pd.DataFrame:
    """DoltHub earnings_calendar, one date-bounded query per month (scans time out)."""
    syms = sorted(set(DEFAULT_UNIVERSE) | {"FB"})
    inlist = ",".join(f"'{s}'" for s in syms)
    rows: list[dict] = []
    for m in pd.period_range("2020-12", "2026-10", freq="M"):
        lo, hi = m.start_time.date(), m.end_time.date()
        sql = (
            "SELECT act_symbol, date FROM earnings_calendar "
            f"WHERE date >= '{lo}' AND date <= '{hi}' AND act_symbol IN ({inlist})"
        )
        rows += _query(DOLT_EARNINGS, sql)
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("DoltHub earnings calendar returned nothing; refusing to continue")
    df["ticker"] = df["act_symbol"].replace({"FB": "META"})
    df["announce_date"] = pd.to_datetime(df["date"])
    print(f"  DoltHub earnings: {len(df):,} events, {df['ticker'].nunique()} names")
    return df[["ticker", "announce_date"]].drop_duplicates()


def pull_earnings_compustat() -> pd.DataFrame | None:
    """Compustat rdq from the R2 mirror, or None if the mirror is unreachable."""
    from earnings_iv_crush.data.earnings import build_wrds_calendar

    try:
        cal = build_wrds_calendar("2020-12-01", "2026-10-31", list(DEFAULT_UNIVERSE))
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: Compustat calendar unavailable ({type(exc).__name__}); DoltHub only")
        return None
    print(
        f"  Compustat earnings: {len(cal):,} events, {cal['ticker'].nunique()} names, "
        f"last {pd.to_datetime(cal['announce_date']).max().date()}"
    )
    return cal[["ticker", "announce_date"]].drop_duplicates()


def _query(api: str, sql: str, retries: int = 5) -> list[dict]:
    """Run ``sql`` against a DoltHub database, retrying transient failures.

    The same contract as the adapter's transport (which is pinned to one database): a
    query-time budget overrun or a dropped connection is retried with a linear backoff,
    any other rejection raises.
    """
    import requests

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(api, params={"q": sql}, timeout=45)
            r.raise_for_status()
            body = r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last = exc
        else:
            if body.get("query_execution_status") == "Success":
                return body.get("rows") or []
            msg = str(body.get("query_execution_message", ""))
            if "deadline exceeded" not in msg.lower():
                raise RuntimeError(f"DoltHub query failed: {msg}")
            last = RuntimeError(f"DoltHub query timed out: {msg}")
        time.sleep(2.0 * attempt)
    assert last is not None
    raise last


def pull_chains(workers: int, closes: pd.DataFrame) -> None:
    """Formation-date chains, date-pinned, one ticker-date per call, cached per file."""
    (CACHE / "chains").mkdir(parents=True, exist_ok=True)
    cl = {
        (t, pd.Timestamp(d)): float(c)
        for t, d, c in zip(closes["ticker"], closes["date"], closes["close"], strict=True)
    }
    candidates = month_candidates()
    jobs = [(t, d) for d in candidates for t in DEFAULT_UNIVERSE]
    todo = [j for j in jobs if _resolve(j[0], candidates[j[1]])[0] == "unpulled"]
    print(f"  {len(jobs):,} ticker-months, {len(jobs) - len(todo):,} cached, {len(todo):,} to pull")
    lock = threading.Lock()
    state = {"done": 0, "fail": 0, "t0": time.time()}

    def fetch(t: str, d: pd.Timestamp) -> bool:
        """Pull one exact-date snapshot to cache; True when it is non-empty."""
        path = _chain_path(t, d)
        if path.exists():
            return not pd.read_parquet(path).empty
        spot = cl.get((t, d))
        sql = dolt._chain_sql(
            dolt_symbol(t, d),
            d.strftime("%Y-%m-%d"),
            d,
            BACK_WINDOW_DAYS + 5,
            spot if spot is not None and np.isfinite(spot) else None,
            STRIKE_WINDOW,
        )
        rows = _query(DOLT_OPTIONS, sql)
        chain = dolt._to_chain(rows) if rows else pd.DataFrame(columns=dolt.CHAIN_COLUMNS)
        chain.to_parquet(path)
        return not chain.empty

    def one(job: tuple[str, pd.Timestamp]) -> None:
        t, last = job
        try:
            # Step back through the month's candidate sessions until a snapshot exists.
            for d in candidates[last]:
                if fetch(t, d):
                    break
        except Exception:  # noqa: BLE001
            with lock:
                state["fail"] += 1
        with lock:
            state["done"] += 1
            n = state["done"]
            if n % 100 == 0 or n == len(todo):
                rate = n / max(time.time() - state["t0"], 1e-9)
                eta = (len(todo) - n) / max(rate, 1e-9) / 60
                print(
                    f"  {n}/{len(todo)} pulled, {state['fail']} failed, {rate:.2f}/s, "
                    f"eta {eta:.0f} min",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    print(f"  PULL DONE: {state['done']} attempted, {state['fail']} failed", flush=True)


def pull(workers: int) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if not CLOSES.exists():
        pull_closes().to_parquet(CLOSES, index=False)
    if not EARN_DOLT.exists():
        pull_earnings_dolthub().to_parquet(EARN_DOLT, index=False)
    if not SPLITS.exists():
        pull_splits().to_parquet(SPLITS, index=False)
    if not EARN_COMP.exists():
        comp = pull_earnings_compustat()
        if comp is not None:
            comp.to_parquet(EARN_COMP, index=False)
    pull_chains(workers, pd.read_parquet(CLOSES))


# ── trades ───────────────────────────────────────────────────────────────────


def straddle_quote(chain: pd.DataFrame, expiry: pd.Timestamp, spot: float) -> dict | None:
    """ATM straddle on ``expiry``: strike nearest spot with both legs quoted ask > bid > 0."""
    leg = chain[chain["expiry"] == expiry]
    c = leg[leg["right"] == "C"].set_index("strike")
    p = leg[leg["right"] == "P"].set_index("strike")
    both = c.join(p, lsuffix="_c", rsuffix="_p", how="inner")
    ok = both[
        (both["ask_c"] > both["bid_c"])
        & (both["bid_c"] > 0)
        & (both["ask_p"] > both["bid_p"])
        & (both["bid_p"] > 0)
    ]
    if ok.empty:
        return None
    strikes = ok.index.to_numpy(dtype=float)
    i = int(np.argmin(np.abs(strikes - spot)))
    k = float(strikes[i])
    r = ok.iloc[i]
    bid = float(r["bid_c"]) + float(r["bid_p"])
    ask = float(r["ask_c"]) + float(r["ask_p"])
    return {"strike": k, "bid": bid, "ask": ask, "mid": 0.5 * (bid + ask)}


def _settle_close(closes: pd.Series, expiry: pd.Timestamp) -> float | None:
    """Close of the expiry session, or the last session before it."""
    s = closes[closes.index <= expiry]
    if s.empty or (expiry - s.index[-1]).days > 4:
        return None
    return float(s.iloc[-1])


def _in_window(events: pd.Series, lo: pd.Timestamp, hi: pd.Timestamp) -> bool:
    return bool(((events >= lo) & (events <= hi)).any())


def build_trades() -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per eligible name-month: signal, entry quotes, payoff, exclusion flags."""
    closes = pd.read_parquet(CLOSES)
    by_name = {t: g.set_index("date")["close"].sort_index() for t, g in closes.groupby("ticker")}
    earn = [pd.read_parquet(EARN_DOLT)]
    if EARN_COMP.exists():
        earn.append(pd.read_parquet(EARN_COMP))
    events = pd.concat(earn, ignore_index=True)
    events["announce_date"] = pd.to_datetime(events["announce_date"])
    ev_by = {t: g["announce_date"] for t, g in events.groupby("ticker")}
    if not SPLITS.exists():
        raise SystemExit(f"{SPLITS} missing; run --pull first (amendment 02 needs it)")
    splits = pd.read_parquet(SPLITS)
    split_by = {t: pd.to_datetime(g["date"]) for t, g in splits.groupby("ticker")}
    last_close = closes["date"].max()

    funnel: dict[str, int] = {}

    def drop(why: str) -> None:
        funnel[why] = funnel.get(why, 0) + 1

    rows = []
    for last, cands in month_candidates().items():
        for t in DEFAULT_UNIVERSE:
            funnel["ticker_months"] = funnel.get("ticker_months", 0) + 1
            status, d = _resolve(t, cands)
            if status == "unpulled":
                drop("chain not pulled")
                continue
            if d is None:
                drop("no snapshot on any candidate session")
                continue
            if d != last:
                funnel["formed before the month's last session"] = (
                    funnel.get("formed before the month's last session", 0) + 1
                )
            ch = pd.read_parquet(_chain_path(t, d))
            px = by_name.get(t)
            spot = px.get(d) if px is not None else None
            if spot is None or not np.isfinite(spot):
                drop("no formation close")
                continue
            ch["expiry"] = pd.to_datetime(ch["expiry"])
            ch["dte"] = (ch["expiry"] - d).dt.days
            parity = implied_spot(ch)
            if not np.isfinite(parity) or abs(parity / spot - 1.0) > PARITY_TOL:
                drop("close disagrees with chain parity spot")
                continue
            iv_f, iv_b = _atm_iv(ch, spot, SHORT_DTE), _atm_iv(ch, spot, LONG_DTE)
            if not (np.isfinite(iv_f) and np.isfinite(iv_b)):
                drop("signal leg missing")
                continue
            mids = sorted(
                ch.loc[(ch["dte"] >= MID_DTE[0]) & (ch["dte"] < MID_DTE[1]), "expiry"].unique()
            )
            if not mids:
                drop("no middle expiry")
                continue
            expiry = pd.Timestamp(mids[0])
            if expiry > last_close:
                drop("holding window beyond coverage")
                continue
            sp = split_by.get(t)
            if sp is not None and bool(((sp > d) & (sp <= expiry)).any()):
                # Strike on the pre-split basis, settlement close on the post-split one.
                drop("split inside holding window")
                continue
            q = straddle_quote(ch, expiry, spot)
            if q is None:
                drop("traded straddle unquoted")
                continue
            s_t = _settle_close(px, expiry) if px is not None else None
            if s_t is None:
                drop("no settlement close")
                continue
            ev = ev_by.get(t, pd.Series([], dtype="datetime64[ns]"))
            rows.append(
                {
                    "ticker": t,
                    "formation": d,
                    "month": last,
                    "expiry": expiry,
                    "dte": int((expiry - d).days),
                    "spot": float(spot),
                    "iv_front": iv_f,
                    "iv_back": iv_b,
                    "slope": iv_b - iv_f,
                    **q,
                    "settle": s_t,
                    "payoff": abs(s_t - q["strike"]),
                    "event_in_hold": _in_window(ev, d, expiry),
                    "event_in_back": _in_window(ev, d, d + pd.Timedelta(days=BACK_WINDOW_DAYS)),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit(f"no trade could be built; funnel {funnel}")
    funnel["built"] = len(df)
    funnel["excluded: earnings in holding window"] = int(df["event_in_hold"].sum())
    return df, funnel


# ── scoring ──────────────────────────────────────────────────────────────────


def assign_quintiles(df: pd.DataFrame, slope: str = "slope") -> pd.Series:
    """Slope quintile within each formation month (0 lowest), NaN in thin months."""

    def q(s: pd.Series) -> pd.Series:
        if s.notna().sum() < MIN_NAMES:
            return pd.Series(np.nan, index=s.index)
        return pd.Series(
            pd.qcut(s.rank(method="first"), N_QUANTILES, labels=False), index=s.index
        ).astype(float)

    return df.groupby("month")[slope].transform(q)


def leg_returns(df: pd.DataFrame, arm: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-trade returns on premium for every row as a long and as a short straddle."""
    if arm == "mid":
        buy = sell = df["mid"].to_numpy(dtype=float)
    elif arm == "touch":
        buy, sell = df["ask"].to_numpy(dtype=float), df["bid"].to_numpy(dtype=float)
    else:
        raise ValueError(arm)
    pay = df["payoff"].to_numpy(dtype=float)
    return (pay - buy) / buy, (sell - pay) / sell


def long_short(q: np.ndarray, r_long: np.ndarray, r_short: np.ndarray) -> float:
    """Pooled mean long-leg return (top quintile) plus pooled mean short-leg (bottom)."""
    top, bot = q == N_QUANTILES - 1, q == 0
    if not top.any() or not bot.any():
        return float("nan")
    return float(r_long[top].mean() + r_short[bot].mean())


def ls_ci(df: pd.DataFrame, arm: str) -> tuple[float, float, float]:
    """Point estimate and clustered 95% CI, resampling formation months (amendment 01)."""
    rl, rs = leg_returns(df, arm)
    q = df["q"].to_numpy(dtype=float)

    def stat(i: np.ndarray) -> float:
        j = i.astype(int)
        return long_short(q[j], rl[j], rs[j])

    keys = df["month"].dt.strftime("%Y-%m-%d").to_numpy()
    lo, hi = cluster_bootstrap_ci(
        np.arange(len(df), dtype=float), keys, stat, n_boot=N_BOOT, seed=SEED
    )
    return long_short(q, rl, rs), lo, hi


def matched_null(df: pd.DataFrame, arm: str = "touch") -> np.ndarray:
    """Touch long-short with slopes permuted across names within each month."""
    rng = np.random.default_rng(SEED)
    rl, rs = leg_returns(df, arm)
    groups = [np.flatnonzero(df["month"].to_numpy() == f) for f in df["month"].unique()]
    q0 = df["q"].to_numpy(dtype=float)
    out = np.empty(N_NULL)
    for b in range(N_NULL):
        q = q0.copy()
        for g in groups:
            q[g] = q0[rng.permutation(g)]
        out[b] = long_short(q, rl, rs)
    return out


def monthly_ls(df: pd.DataFrame, arm: str) -> pd.Series:
    rl, rs = leg_returns(df, arm)
    d = df.assign(rl=rl, rs=rs)
    out = {
        f: long_short(g["q"].to_numpy(), g["rl"].to_numpy(), g["rs"].to_numpy())
        for f, g in d.groupby("month")
    }
    return pd.Series(out, dtype=float)


def score() -> int:
    trades, funnel = build_trades()
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(OUT / "trades.parquet", index=False)

    book = trades[~trades["event_in_hold"]].copy()
    book["q"] = assign_quintiles(book)
    funnel["skipped: thin month"] = int(book["q"].isna().sum())
    book = book.dropna(subset=["q"]).reset_index(drop=True)
    funnel["scored name-months"] = len(book)
    funnel["formation months scored"] = int(book["month"].nunique())
    print("── funnel ─────────────────────────────────────────────────")
    for k, v in funnel.items():
        print(f"  {k:42s} {v:,}")
    if book.empty:
        raise SystemExit("nothing scoreable after exclusions; refusing to report")

    rows = []
    for arm in ("mid", "touch"):
        est, lo, hi = ls_ci(book, arm)
        rl, rs = leg_returns(book, arm)
        top, bot = book["q"] == N_QUANTILES - 1, book["q"] == 0
        rows.append(
            {
                "arm": arm,
                "ls_mean_per_trade": est,
                "ci_low": lo,
                "ci_high": hi,
                "long_leg_mean": float(rl[top].mean()),
                "short_leg_mean": float(rs[bot].mean()),
                "n_long": int(top.sum()),
                "n_short": int(bot.sum()),
                "n_months": int(book["month"].nunique()),
                "long_hit": float((rl[top] > 0).mean()),
                "short_hit": float((rs[bot] > 0).mean()),
            }
        )
    res = pd.DataFrame(rows)

    null = matched_null(book)
    touch = res.set_index("arm").loc["touch"]
    null_p95 = float(np.percentile(null, 95))
    pct = float((null < touch["ls_mean_per_trade"]).mean())
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])
    m = monthly_ls(book, "touch").dropna()
    dsr = float(deflated_sharpe_ratio(m, n_trials=N_TRIALS, sr_trials_std=sr_std))
    res["null_median"] = [np.nan, float(np.median(null))]
    res["null_p95"] = [np.nan, null_p95]
    res["null_percentile"] = [np.nan, pct]
    res["monthly_sharpe"] = [
        float(monthly_ls(book, "mid").dropna().pipe(lambda s: s.mean() / s.std(ddof=1))),
        float(m.mean() / m.std(ddof=1)),
    ]
    res["dsr_monthly"] = [np.nan, dsr]

    quint = []
    for arm in ("mid", "touch"):
        rl, _ = leg_returns(book, arm)
        qs = book["q"].to_numpy(dtype=float)
        for qi in sorted(set(qs)):
            s = pd.Series(rl[qs == qi])
            quint.append(
                {
                    "arm": arm,
                    "quintile": int(qi),
                    "n": len(s),
                    "mean_long_return": float(s.mean()),
                    "se": float(s.std(ddof=1) / np.sqrt(len(s))),
                    "mean_slope": float(book.loc[book["q"] == qi, "slope"].mean()),
                }
            )
    quint_df = pd.DataFrame(quint)
    mid_q = quint_df[quint_df["arm"] == "mid"]
    spearman = float(mid_q["quintile"].corr(mid_q["mean_long_return"], method="spearman"))

    clean = trades[~trades["event_in_back"]].copy()
    clean["q"] = assign_quintiles(clean)
    clean = clean.dropna(subset=["q"]).reset_index(drop=True)
    clean_rows = []
    for arm in ("mid", "touch"):
        if len(clean):
            est, lo, hi = ls_ci(clean, arm)
            clean_rows.append({"arm": arm, "n": len(clean), "ls": est, "lo": lo, "hi": hi})

    passed = bool(touch["ci_low"] > 0 and touch["ls_mean_per_trade"] > null_p95)
    reversed_sign = bool(touch["ci_high"] < 0)
    mech = spearman >= 0.70

    print("\n── primary and mid arm: long-short per trade, return on premium ──")
    print(res.T.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("\n── quintile means, long straddle, per trade ──")
    print(quint_df.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    print(f"\n  mechanism check: Spearman(quintile, mid long return) = {spearman:+.2f}")
    if clean_rows:
        print("\n── clean-signal subsample (no event inside the back leg either) ──")
        print(pd.DataFrame(clean_rows).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    verdict = "PASS" if passed else ("FAIL (reversed sign)" if reversed_sign else "FAIL")
    print(f"\n  PRIMARY: {verdict}   mechanism check: {mech}")

    res.to_csv(OUT / "p2_term_slope.csv", index=False)
    quint_df.to_csv(OUT / "p2_quintiles.csv", index=False)
    pd.DataFrame(clean_rows).to_csv(OUT / "p2_clean_signal.csv", index=False)
    pd.DataFrame([funnel]).T.rename(columns={0: "count"}).to_csv(OUT / "p2_funnel.csv")
    pd.Series(null, name="touch_ls_null").to_csv(OUT / "p2_null.csv", index=False)
    print(f"  wrote {OUT.resolve()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.pull:
        pull(args.workers)
    if args.score:
        return score()
    if not args.pull:
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
