"""
research_p1_skew_reaction.py
P1: does the pre-announcement put skew predict the earnings-window stock return?

Scores ``research/selection/preregs/p1_skew_reaction_prereg.md`` exactly as frozen (hash in
``outputs/research/prereg_p1_skew_reaction.json``). The option surface is the signal; the
position is in the stock.

    signal   25-delta put IV minus ATM call IV, Black-76 on the 15:59 ET quote mid, forward from
             put-call parity, front expiry spanning the event (the straddle book's expiry)
    outcome  [0, +2] session return minus SPY from the entry-day close (yfinance adjusted)
    sort     deciles within calendar-month buckets (merged to at least 50 events)
    primary  decile 1 (flattest) minus decile 10 (steepest) mean, net of 5 bp per side,
             date-clustered bootstrap (5,000 draws, seed 0), Spearman of decile means, matched
             within-bucket permutation null (1,000 draws)

Usage:
    python research/selection/research_p1_skew_reaction.py --stage signal
    python research/selection/research_p1_skew_reaction.py --stage score
    python research/selection/research_p1_skew_reaction.py --stage all

References
----------
Xing, Y., Zhang, X. and Zhao, R. (2010). What Does the Individual Option Volatility Smirk Tell
Us About Future Equity Returns? *Journal of Financial and Quantitative Analysis* 45(3), 641-662.
Jin, W., Livnat, J. and Zhang, Y. (2012). Option Prices Leading Equity Prices: Do Option Traders
Have an Information Advantage? *Journal of Accounting Research* 50(2), 401-432.
Black, F. (1976). The Pricing of Commodity Contracts. *Journal of Financial Economics* 3, 167-179.
Bailey, D. H. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio
Management* 40(5), 94-107.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.config import STRATEGY  # noqa: E402
from earnings_iv_crush.data.features import select_execution_expiry  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.greeks import implied_vol  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

# ── constants (all fixed by the pre-registration) ────────────────────────────

PREREG = Path("research/selection/preregs/p1_skew_reaction_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_p1_skew_reaction.json")
EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
CHAINS = Path("data/cache/backfill_chains")
EDGAR = Path("outputs/research/edgar_sessions/agreement.csv")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/p1_skew_reaction")
PRICES = OUT / "prices.parquet"

TARGET_DELTA = 0.25
MAX_REL_SPREAD = 0.50  # (ask - bid) / mid on any contract used
PARITY_STRIKES = 3  # strikes with the smallest |C - P| used for the forward
IV_HI = 10.0  # upper Brent bracket; front-expiry event IVs can exceed 500%
RATE = 0.0  # GlobalConfig risk-free rate
HORIZON = 2  # sessions after entry
PLACEBO_BACK = 3  # placebo window: t-3 close to t close
MIN_BUCKET = 50
N_DECILES = 10
COST_PER_SIDE = 0.0005
LEG_ROUND_TRIP = 2 * COST_PER_SIDE  # one leg, in and out
LS_COST = 2 * LEG_ROUND_TRIP  # long and short legs
SPEARMAN_KILL = -0.60
NULL_PCT_PASS = 0.95
N_NULL = 1000
N_BOOT = 5000
SEED = 0
N_TRIALS = 1498
PRICE_PAD_DAYS = 20


# ── signal ───────────────────────────────────────────────────────────────────


def usable(ch: pd.DataFrame) -> pd.DataFrame:
    """Contracts with a two-sided quote and relative spread at most ``MAX_REL_SPREAD``."""
    bid, ask = ch["bid_px_00"].astype(float), ch["ask_px_00"].astype(float)
    mid = (bid + ask) / 2
    ok = (bid > 0) & (ask > bid) & ((ask - bid) / mid <= MAX_REL_SPREAD)
    return ch[ok].assign(mid=mid[ok])


def parity_forward(calls: pd.Series, puts: pd.Series) -> float:
    """Forward from put-call parity at the strikes where call and put mids are closest.

    Parameters
    ----------
    calls, puts : pandas.Series
        Mid prices indexed by strike.

    Returns
    -------
    float
        ``median(K + C - P)`` over the ``PARITY_STRIKES`` strikes with smallest ``|C - P|``;
        NaN when no strike carries both.
    """
    both = calls.index.intersection(puts.index)
    if len(both) == 0:
        return float("nan")
    diff = calls[both] - puts[both]
    near = diff.abs().nsmallest(PARITY_STRIKES).index
    return float(np.median(np.asarray(near, dtype=float) + diff[near].to_numpy()))


def _ivs(mids: pd.Series, fwd: float, t: float, right: str) -> pd.Series:
    """Black-76 IV per strike (zero rate); NaN where the mid cannot be inverted."""
    ks = np.asarray(mids.index, dtype=float)
    iv = [
        implied_vol(float(m), fwd, float(k), t, RATE, right, hi=IV_HI)
        for k, m in zip(ks, mids.to_numpy(dtype=float), strict=True)
    ]
    return pd.Series(iv, index=mids.index, dtype=float).dropna()


def atm_call_iv(call_iv: pd.Series, fwd: float) -> float:
    """Call IV interpolated linearly in strike to ``K = F`` between the bracketing strikes."""
    s = call_iv.sort_index()
    if fwd in s.index:
        return float(s[fwd])
    lo, hi = s[s.index < fwd], s[s.index > fwd]
    if lo.empty or hi.empty:
        return float("nan")
    k0, k1 = float(lo.index[-1]), float(hi.index[0])
    v0, v1 = float(lo.iloc[-1]), float(hi.iloc[0])
    return v0 + (v1 - v0) * (fwd - k0) / (k1 - k0)


def put_abs_delta(fwd: float, strike: float, t: float, sigma: float) -> float:
    """Forward put delta magnitude ``N(-d1)`` under Black-76."""
    d1 = (np.log(fwd / strike) + 0.5 * sigma * sigma * t) / (sigma * np.sqrt(t))
    return float(norm.cdf(-d1))


def put25_iv(put_iv: pd.Series, fwd: float, t: float) -> float:
    """Put IV at 25 forward delta, interpolated linearly in delta magnitude.

    Scans OTM puts (``K <= F``) from the strike nearest ``F`` outward and uses the first
    adjacent pair whose delta magnitudes bracket ``TARGET_DELTA``. No extrapolation.
    """
    s = put_iv[put_iv.index <= fwd].sort_index(ascending=False)
    if len(s) < 2:
        return float("nan")
    ks = np.asarray(s.index, dtype=float)
    vs = s.to_numpy(dtype=float)
    ds = np.array([put_abs_delta(fwd, k, t, v) for k, v in zip(ks, vs, strict=True)])
    for i in range(len(ks) - 1):
        d0, d1 = ds[i], ds[i + 1]  # d0 nearer the money, larger in magnitude
        if d0 >= TARGET_DELTA >= d1 and d0 > d1:
            w = (d0 - TARGET_DELTA) / (d0 - d1)
            return float(vs[i] + w * (vs[i + 1] - vs[i]))
    return float("nan")


def skew_from_chain(
    ch: pd.DataFrame, announce: pd.Timestamp, entry: pd.Timestamp, exit_: pd.Timestamp
) -> tuple[dict[str, Any], str]:
    """Skew and its inputs from one parsed entry chain.

    Returns
    -------
    tuple
        ``(fields, status)``; ``status`` is ``"ok"`` or the first failing step.
    """
    front, _ = select_execution_expiry(ch, announce, exit_, min_dte_days=STRATEGY.min_exit_dte_days)
    if front is None:
        return {}, "no_expiry"
    t = (pd.Timestamp(front) - entry).days / 365.0
    leg = usable(ch[ch["expiry"] == front])
    calls = leg[leg["right"] == "C"].groupby("strike")["mid"].last()
    puts = leg[leg["right"] == "P"].groupby("strike")["mid"].last()
    fwd = parity_forward(calls, puts)
    if not np.isfinite(fwd) or fwd <= 0:
        return {}, "no_forward"
    atm = atm_call_iv(_ivs(calls, fwd, t, "C"), fwd)
    if not np.isfinite(atm):
        return {}, "no_atm_call_iv"
    p25 = put25_iv(_ivs(puts, fwd, t, "P"), fwd, t)
    if not np.isfinite(p25):
        return {}, "no_put25_iv"
    fields = {
        "expiry": pd.Timestamp(front),
        "t_years": t,
        "forward": fwd,
        "atm_call_iv": atm,
        "put25_iv": p25,
        "skew": p25 - atm,
    }
    return fields, "ok"


def build_signal() -> pd.DataFrame:
    """Skew for every event with an entry chain, printing the funnel."""
    from earnings_iv_crush.research.chains import _parse_chain

    ev = pd.read_parquet(EVENTS, columns=["ticker", "announce_date", "entry_date", "exit_date"])
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).dt.normalize()
    funnel: dict[str, int] = {"events": len(ev)}
    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for _, e in ev.iterrows():
        f = CHAINS / f"{e['ticker']}_{e['entry_date'].date()}.parquet"
        if not f.exists():
            status = "no_entry_chain"
        else:
            ch = _parse_chain(pd.read_parquet(f))
            if ch is None:
                status = "empty_chain"
            else:
                fields, status = skew_from_chain(
                    ch, e["announce_date"], e["entry_date"], e["exit_date"]
                )
                if status == "ok":
                    rows.append({**{str(k): v for k, v in e.items()}, **fields})
        status_counts[status] = status_counts.get(status, 0) + 1
    for k in ("no_entry_chain", "empty_chain", "no_expiry", "no_forward"):
        funnel[k] = status_counts.get(k, 0)
    funnel["no_atm_call_iv"] = status_counts.get("no_atm_call_iv", 0)
    funnel["no_put25_iv"] = status_counts.get("no_put25_iv", 0)
    funnel["signal_formed"] = len(rows)
    _print_funnel("signal", funnel)
    if not rows:
        raise SystemExit("no event produced a skew signal - refusing to continue")
    out = pd.DataFrame(rows)
    out.attrs["funnel"] = funnel
    return out


# ── EDGAR timing exclusion ───────────────────────────────────────────────────


def edgar_exclusion(sig: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop events whose EDGAR reaction session is on or before the entry date."""
    if not EDGAR.exists():
        raise SystemExit(f"{EDGAR} missing: run python -m earnings_iv_crush.data.edgar_sessions")
    ed = pd.read_csv(EDGAR, parse_dates=["announce_date", "edgar_reaction"])
    ed = ed.dropna(subset=["edgar_reaction"])[
        ["ticker", "announce_date", "edgar_reaction", "edgar_session", "verdict"]
    ].drop_duplicates(["ticker", "announce_date"])
    d = sig.merge(ed, on=["ticker", "announce_date"], how="left", validate="one_to_one")
    pre = d["edgar_reaction"].notna() & (d["edgar_reaction"] <= d["entry_date"])
    stats = {
        "edgar_matched": int(d["edgar_reaction"].notna().sum()),
        "released_before_snapshot": int(pre.sum()),
        "after_timing_exclusion": int((~pre).sum()),
    }
    _print_funnel("edgar timing", stats)
    kept = d[~pre].copy()
    if kept.empty:
        raise SystemExit("EDGAR timing exclusion removed every event")
    return kept, stats


# ── prices and outcome ───────────────────────────────────────────────────────


def _yf_symbol(t: str) -> str:
    return t.replace(".", "-")


def load_prices(tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Adjusted daily closes (wide, one column per ticker plus SPY), cached on disk."""
    if PRICES.exists():
        px = pd.read_parquet(PRICES)
        if set(tickers + ["SPY"]).issubset(px.columns):
            return px
    import yfinance as yf

    syms = sorted({_yf_symbol(t) for t in tickers} | {"SPY"})
    raw = yf.download(
        syms,
        start=str((start - pd.Timedelta(days=PRICE_PAD_DAYS)).date()),
        end=str((end + pd.Timedelta(days=PRICE_PAD_DAYS)).date()),
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if raw is None or raw.empty:
        raise SystemExit("yfinance returned no prices - refusing to score")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    inv = {_yf_symbol(t): t for t in tickers}
    close = close.rename(columns=lambda c: inv.get(c, c))
    PRICES.parent.mkdir(parents=True, exist_ok=True)
    close.to_parquet(PRICES)
    return close


def window_return(px: pd.DataFrame, ticker: str, i0: int, i1: int) -> float:
    """Market-adjusted simple return between session positions ``i0`` and ``i1``."""
    if ticker not in px.columns or i0 < 0 or i1 >= len(px):
        return float("nan")
    s, m = px[ticker], px["SPY"]
    a, b, ma, mb = s.iloc[i0], s.iloc[i1], m.iloc[i0], m.iloc[i1]
    if not (np.isfinite(a) and np.isfinite(b) and a > 0 and ma > 0):
        return float("nan")
    return float((b / a - 1) - (mb / ma - 1))


def attach_outcomes(d: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """[0,+2] primary, [0,+1] and the [-3,0] placebo, on SPY's session index."""
    spy = px["SPY"].dropna()
    px = px.loc[spy.index]
    pos = {ts: i for i, ts in enumerate(px.index)}
    out = d.copy()
    r2, r1, plc = [], [], []
    for _, e in out.iterrows():
        i = pos.get(e["entry_date"])
        if i is None:
            r2.append(np.nan)
            r1.append(np.nan)
            plc.append(np.nan)
            continue
        r2.append(window_return(px, e["ticker"], i, i + HORIZON))
        r1.append(window_return(px, e["ticker"], i, i + 1))
        plc.append(window_return(px, e["ticker"], i - PLACEBO_BACK, i))
    out["ret_0_2"], out["ret_0_1"], out["ret_placebo"] = r2, r1, plc
    return out


# ── deciles and statistics ───────────────────────────────────────────────────


def month_buckets(entry: pd.Series, min_size: int = MIN_BUCKET) -> pd.Series:
    """Calendar-month bucket labels, short months merged forward (a short tail backward)."""
    months = entry.dt.to_period("M")
    counts = months.value_counts().sort_index()
    label: dict[pd.Period, str] = {}
    pending: list[pd.Period] = []
    groups: list[list[pd.Period]] = []
    acc = 0
    for m, c in counts.items():
        pending.append(m)
        acc += int(c)
        if acc >= min_size:
            groups.append(pending)
            pending, acc = [], 0
    if pending:
        if groups:
            groups[-1].extend(pending)
        else:
            groups.append(pending)
    for g in groups:
        name = f"{g[0]}..{g[-1]}" if len(g) > 1 else str(g[0])
        for m in g:
            label[m] = name
    return months.map(label)


def assign_deciles(d: pd.DataFrame, by: str | None) -> np.ndarray:
    """Decile 1 (lowest skew) to 10 within each group (or pooled when ``by`` is None)."""
    out = np.zeros(len(d), dtype=int)
    groups = (
        [np.arange(len(d))]
        if by is None
        else [np.flatnonzero((d[by] == g).to_numpy()) for g in d[by].unique()]
    )
    for idx in groups:
        sub = d.iloc[idx]
        order = np.lexsort((sub["ticker"].to_numpy(), sub["skew"].to_numpy()))
        n = len(idx)
        ranks = np.empty(n, dtype=int)
        ranks[order] = np.arange(1, n + 1)
        out[idx] = (N_DECILES * (ranks - 1)) // n + 1
    return out


def gap(r: np.ndarray, dec: np.ndarray) -> float:
    lo, hi = r[dec == 1], r[dec == N_DECILES]
    if lo.size == 0 or hi.size == 0:
        return float("nan")
    return float(lo.mean() - hi.mean())


def gap_ci(r: np.ndarray, dec: np.ndarray, dates: pd.Series) -> tuple[float, float]:
    """Date-clustered bootstrap CI on the decile-1 minus decile-10 gap."""
    keys = pd.to_datetime(dates).dt.strftime("%Y-%m-%d").to_numpy()

    def stat(ix: np.ndarray) -> float:
        j = ix.astype(int)
        return gap(r[j], dec[j])

    return cluster_bootstrap_ci(
        np.arange(len(r), dtype=float), keys, stat, n_boot=N_BOOT, seed=SEED
    )


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def permutation_null(r: np.ndarray, dec: np.ndarray, buckets: np.ndarray) -> np.ndarray:
    """Within-bucket permutation of decile labels (equivalent to permuting the skew)."""
    rng = np.random.default_rng(SEED)
    idx_by = [np.flatnonzero(buckets == b) for b in np.unique(buckets)]
    out = np.empty(N_NULL)
    for k in range(N_NULL):
        perm = dec.copy()
        for idx in idx_by:
            perm[idx] = rng.permutation(dec[idx])
        out[k] = gap(r, perm)
    return out


def decile_table(d: pd.DataFrame, col: str, dec: np.ndarray) -> pd.DataFrame:
    g = d.assign(decile=dec).groupby("decile")
    return pd.DataFrame(
        {
            "n": g[col].size(),
            "mean_skew": g["skew"].mean(),
            "mean_ret": g[col].mean(),
            "median_ret": g[col].median(),
            "sd_ret": g[col].std(ddof=1),
            "hit_rate": g[col].apply(lambda x: float((x > 0).mean())),
        }
    )


def spearman_deciles(tab: pd.DataFrame) -> float:
    rho = spearmanr(tab.index.to_numpy(), tab["mean_ret"].to_numpy())[0]
    return float(rho)


def ls_series(r: np.ndarray, dec: np.ndarray) -> np.ndarray:
    """Per-event long-short series net of a round trip at 5 bp per side."""
    long_, short_ = r[dec == 1] - LEG_ROUND_TRIP, -r[dec == N_DECILES] - LEG_ROUND_TRIP
    return np.concatenate([long_, short_])


def score_variant(d: pd.DataFrame, col: str, by: str | None, label: str) -> dict[str, Any]:
    """Gap, CI, Spearman for one variant (secondary variants skip the null)."""
    x = d.dropna(subset=[col]).reset_index(drop=True)
    dec = assign_deciles(x, by)
    r = x[col].to_numpy(dtype=float)
    tab = decile_table(x, col, dec)
    g = gap(r, dec)
    lo, hi = gap_ci(r, dec, x["entry_date"])
    return {
        "variant": label,
        "n": len(x),
        "gap_gross": g,
        "gap_net": g - LS_COST,
        "ci_gross_low": lo,
        "ci_gross_high": hi,
        "ci_net_low": lo - LS_COST,
        "ci_net_high": hi - LS_COST,
        "spearman": spearman_deciles(tab),
        "d1_mean": float(tab["mean_ret"].loc[1]),
        "d10_mean": float(tab["mean_ret"].loc[N_DECILES]),
    }


def score(sig: pd.DataFrame) -> dict[str, Any]:
    """Run the pre-registered scoring; return everything the write-up needs."""
    n_raw = len(sig)
    sig = sig.drop_duplicates(["ticker", "announce_date"]).reset_index(drop=True)
    _print_funnel("dedup", {"signal_rows": n_raw, "duplicate_events_dropped": n_raw - len(sig)})
    d, ed_stats = edgar_exclusion(sig)
    ed_stats["duplicate_events_dropped"] = n_raw - len(sig)
    start, end = d["entry_date"].min(), d["entry_date"].max()
    px = load_prices(sorted(d["ticker"].unique()), start, end)
    d = attach_outcomes(d, px)
    n_before = len(d)
    d = d.dropna(subset=["ret_0_2"]).reset_index(drop=True)
    price_funnel = {"before_price_join": n_before, "with_0_2_return": len(d)}
    missing = sorted(
        t for t in set(sig["ticker"]) if t not in px.columns or px[t].notna().sum() == 0
    )
    _print_funnel("prices", {**price_funnel, "tickers_without_prices": len(missing)})
    if missing:
        print(f"    no yfinance history: {', '.join(missing)}")
    if len(d) < 10 * N_DECILES:
        raise SystemExit(f"only {len(d)} scored events - too few for deciles")

    d["bucket"] = month_buckets(d["entry_date"])
    dec = assign_deciles(d, "bucket")
    d["decile"] = dec
    r = d["ret_0_2"].to_numpy(dtype=float)
    tab = decile_table(d, "ret_0_2", dec)
    g = gap(r, dec)
    lo, hi = gap_ci(r, dec, d["entry_date"])
    rho = spearman_deciles(tab)
    null = permutation_null(r, dec, d["bucket"].to_numpy())
    ls = ls_series(r, dec)
    ls_dates = pd.concat(
        [d.loc[dec == 1, "entry_date"], d.loc[dec == N_DECILES, "entry_date"]], ignore_index=True
    )
    ls_lo, ls_hi = cluster_bootstrap_ci(
        ls, ls_dates.dt.strftime("%Y-%m-%d").to_numpy(), sharpe, n_boot=N_BOOT, seed=SEED
    )
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])
    dsr = float(deflated_sharpe_ratio(pd.Series(ls), n_trials=N_TRIALS, sr_trials_std=sr_std))

    primary = {
        "n_scored": len(d),
        "n_buckets": int(d["bucket"].nunique()),
        "gap_gross": g,
        "gap_net": g - LS_COST,
        "ci_gross": [lo, hi],
        "ci_net": [lo - LS_COST, hi - LS_COST],
        "spearman": rho,
        "null_median": float(np.median(null)),
        "null_p95": float(np.quantile(null, NULL_PCT_PASS)),
        "null_percentile": float((null < g).mean()),
        "ls_n": len(ls),
        "ls_mean_net": float(ls.mean()),
        "ls_sharpe_per_trade": sharpe(ls),
        "ls_sharpe_ci": [ls_lo, ls_hi],
        "dsr": dsr,
        "dsr_trials": N_TRIALS,
        "sr_trials_std": sr_std,
    }
    kill_a = rho > SPEARMAN_KILL
    kill_b = (lo - LS_COST) <= 0 <= (hi - LS_COST)
    null_p95 = float(np.quantile(null, NULL_PCT_PASS))
    passed = not kill_a and (lo - LS_COST) > 0 and g >= null_p95
    primary.update({"kill_a_monotone": bool(kill_a), "kill_b_ci_zero": bool(kill_b)})
    primary["verdict"] = "PASS" if passed else "FAIL"

    secondary = [
        score_variant(d, "ret_0_2", None, "pooled deciles"),
        score_variant(d[d["edgar_reaction"].notna()], "ret_0_2", "bucket", "EDGAR-matched only"),
        score_variant(d, "ret_0_1", "bucket", "[0,+1] window"),
        score_variant(d, "ret_placebo", "bucket", "placebo [-3,0]"),
    ]
    sess = pd.read_parquet(
        Path("outputs/research/events_master_broad.parquet"),
        columns=["ticker", "announce_date", "session"],
    )
    sess["announce_date"] = pd.to_datetime(sess["announce_date"]).dt.normalize()
    sess = sess.drop_duplicates(["ticker", "announce_date"])
    d = d.merge(sess, on=["ticker", "announce_date"], how="left", validate="one_to_one")
    for s_lab in ("bmo", "amc"):
        sub = d[d["session"] == s_lab]
        if len(sub) >= 10 * N_DECILES:
            sub = sub.assign(bucket=month_buckets(sub["entry_date"]))
            secondary.append(score_variant(sub, "ret_0_2", "bucket", f"{s_lab.upper()} only"))
    mech_ok = abs(secondary[3]["gap_gross"]) < abs(g)

    return {
        "funnel_signal": sig.attrs.get("funnel", {}),
        "funnel_edgar": ed_stats,
        "funnel_prices": price_funnel,
        "missing_tickers": missing,
        "primary": primary,
        "mechanism_placebo_smaller": bool(mech_ok),
        "deciles": tab,
        "secondary": pd.DataFrame(secondary),
        "scored": d,
        "null": null,
    }


# ── helpers and entry point ──────────────────────────────────────────────────


def _print_funnel(stage: str, f: dict[str, int]) -> None:
    print(f"  funnel [{stage}]:")
    for k, v in f.items():
        print(f"    {k:<28} {v}")


def _check_prereg() -> str:
    rec = json.loads(PREREG_JSON.read_text(encoding="utf-8"))
    h = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if h != rec["prereg_sha256"]:
        raise SystemExit("pre-registration file does not match its recorded hash - refusing")
    return h


def main() -> None:
    ap = argparse.ArgumentParser(description="P1 put skew vs earnings-window stock return.")
    ap.add_argument("--stage", choices=["signal", "score", "all"], default="all")
    args = ap.parse_args()
    h = _check_prereg()
    print(f"  pre-registration verified, sha256 {h}")
    OUT.mkdir(parents=True, exist_ok=True)
    sig_path = OUT / "signal.parquet"
    if args.stage in ("signal", "all"):
        sig = build_signal()
        sig.to_parquet(sig_path, index=False)
        (OUT / "funnel_signal.json").write_text(json.dumps(sig.attrs["funnel"], indent=2))
    if args.stage == "signal":
        return
    sig = pd.read_parquet(sig_path)
    sig.attrs["funnel"] = json.loads((OUT / "funnel_signal.json").read_text())
    res = score(sig)
    p = res["primary"]
    res["deciles"].to_csv(OUT / "deciles.csv")
    res["secondary"].to_csv(OUT / "secondary.csv", index=False)
    res["scored"].to_csv(OUT / "scored_events.csv", index=False)
    summary = {k: v for k, v in res.items() if k not in ("deciles", "secondary", "scored", "null")}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("\n  decile table ([0,+2] market-adjusted, per event, gross):")
    print(res["deciles"].to_string(float_format=lambda v: f"{v:.4f}"))
    print("\n  secondary (descriptive):")
    print(res["secondary"].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(
        f"\n  PRIMARY: gap gross {p['gap_gross']:+.4f} [{p['ci_gross'][0]:+.4f}, "
        f"{p['ci_gross'][1]:+.4f}], net {p['gap_net']:+.4f} [{p['ci_net'][0]:+.4f}, "
        f"{p['ci_net'][1]:+.4f}], N={p['n_scored']}; Spearman {p['spearman']:+.3f}; "
        f"null pct {p['null_percentile']:.3f} (p95 {p['null_p95']:+.4f}); "
        f"LS per-trade Sharpe {p['ls_sharpe_per_trade']:+.4f} DSR {p['dsr']:.3f}"
    )
    print(
        f"  VERDICT: {p['verdict']} (kill a monotone: {p['kill_a_monotone']}, "
        f"kill b CI spans zero: {p['kill_b_ci_zero']}); placebo smaller: "
        f"{res['mechanism_placebo_smaller']}"
    )
    print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
