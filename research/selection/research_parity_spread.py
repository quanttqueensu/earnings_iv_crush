"""
research_parity_spread.py
Pre-registered test: does the option-implied forward premium predict the earnings-window return?

``research/selection/preregs/parity_spread_prereg.md`` with amendment 01. The signal is
log(parity forward / cash-and-carry forward) from the 15:59 ET front-expiry chain of the entry
session against the 15:59 IEX stock price; the outcome runs from that same price to the close two
sessions later, market-adjusted with SPY built the same way (Cremers and Weinbaum 2010; Atilgan
2014; Ofek, Richardson and Whitelaw 2004).

Stages:
    --signal    parity forwards from data/cache/backfill_chains
    --prices    15:59 IEX bars (Alpaca), dividends and raw closes (yfinance), 3-month bill (FRED)
    --score     the pre-registered decile test

Usage:
    python research/selection/research_parity_spread.py --signal --prices --score
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.config import STRATEGY  # noqa: E402
from earnings_iv_crush.data.features import select_execution_expiry  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from research.selection.research_p1_skew_reaction import (  # noqa: E402
    edgar_exclusion,
    load_prices,
    month_buckets,
    usable,
)

PREREG = Path("research/selection/preregs/parity_spread_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_parity_spread.json")
EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
CHAINS = Path("data/cache/backfill_chains")
OUT = Path("outputs/research/parity_spread")
SIGNAL = OUT / "signal.parquet"
BARS = OUT / "bars_1559.parquet"
DIVS = OUT / "dividends.parquet"
RAW = OUT / "raw_close.parquet"
RATES = OUT / "dtb3.parquet"

PARITY_STRIKES = 3
HORIZON = 2
PLACEBO_BACK = 3
SPLIT_TOL = 0.10  # amendment 01
COST_PER_SIDE = 0.0005
LS_COST = 4 * COST_PER_SIDE  # in and out on both legs
N_DECILES = 10
SPEARMAN_PASS = 0.60
N_NULL = 1000
N_BOOT = 5000
SEED = 0
N_TRIALS = 1503
TZ = "America/New_York"


def _check_prereg() -> None:
    want = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != want:
        raise SystemExit(f"pre-registration hash mismatch: {got} != {want}")


def _funnel(stage: str, f: dict[str, int]) -> None:
    print(f"  funnel [{stage}]: " + ", ".join(f"{k}={v}" for k, v in f.items()), flush=True)


# ── signal ───────────────────────────────────────────────────────────────────


def build_signal() -> pd.DataFrame:
    from earnings_iv_crush.research.chains import _parse_chain

    ev = pd.read_parquet(EVENTS, columns=["ticker", "announce_date", "entry_date", "exit_date"])
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).dt.normalize()
    n0 = len(ev)
    ev = ev.drop_duplicates(["ticker", "announce_date"]).reset_index(drop=True)
    f: dict[str, int] = {"events": n0, "duplicates": n0 - len(ev)}
    rows = []
    for _, e in ev.iterrows():
        p = CHAINS / f"{e['ticker']}_{e['entry_date'].date()}.parquet"
        if not p.exists():
            f["no_chain"] = f.get("no_chain", 0) + 1
            continue
        ch = _parse_chain(pd.read_parquet(p))
        if ch is None:
            f["empty_chain"] = f.get("empty_chain", 0) + 1
            continue
        front, _ = select_execution_expiry(
            ch, e["announce_date"], e["exit_date"], min_dte_days=STRATEGY.min_exit_dte_days
        )
        if front is None:
            f["no_expiry"] = f.get("no_expiry", 0) + 1
            continue
        leg = usable(ch[ch["expiry"] == front])
        calls = leg[leg["right"] == "C"].groupby("strike")["mid"].last()
        puts = leg[leg["right"] == "P"].groupby("strike")["mid"].last()
        both = calls.index.intersection(puts.index)
        if len(both) < PARITY_STRIKES:
            f["few_parity_strikes"] = f.get("few_parity_strikes", 0) + 1
            continue
        diff = calls[both] - puts[both]
        near = diff.abs().nsmallest(PARITY_STRIKES).index
        rows.append(
            {
                **e.to_dict(),
                "expiry": pd.Timestamp(front),
                "t_years": (pd.Timestamp(front) - e["entry_date"]).days / 365.0,
                "parity_k": np.asarray(near, dtype=float),
                "parity_cp": diff[near].to_numpy(dtype=float),
            }
        )
    out = pd.DataFrame(rows)
    f["signal_inputs"] = len(out)
    _funnel("signal", f)
    if out.empty:
        raise SystemExit("no parity inputs formed")
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(SIGNAL)
    return out


# ── prices ───────────────────────────────────────────────────────────────────


def _alpaca_bars(symbols: list[str], day: pd.Timestamp) -> dict[str, float]:
    from earnings_iv_crush.data.alpaca_options import _DATA_HOST, _get

    t0 = pd.Timestamp(f"{day.date()} 15:50", tz=TZ).tz_convert("UTC")
    t1 = pd.Timestamp(f"{day.date()} 16:00", tz=TZ).tz_convert("UTC")
    out: dict[str, float] = {}
    token = None
    while True:
        params: dict[str, Any] = {
            "symbols": ",".join(s.replace("-", ".") for s in symbols),
            "timeframe": "1Min",
            "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": "iex",
            "adjustment": "raw",
            "limit": 10000,
        }
        if token:
            params["page_token"] = token
        body = _get(_DATA_HOST, "/v2/stocks/bars", params)
        for sym, bars in (body.get("bars") or {}).items():
            keep = [b for b in bars if pd.Timestamp(b["t"]) < t1]  # bars starting by 15:59
            if keep:
                last = max(keep, key=lambda b: pd.Timestamp(b["t"]))
                out[sym.replace(".", "-")] = float(last["c"])
        token = body.get("next_page_token")
        if not token:
            return out


def pull_prices(sig: pd.DataFrame) -> None:
    import yfinance as yf

    rows = []
    for day, g in sig.groupby("entry_date"):
        syms = sorted(set(g["ticker"]) | {"SPY"})
        got = _alpaca_bars(syms, pd.Timestamp(day))
        rows += [{"entry_date": day, "ticker": s, "s1559": got.get(s, np.nan)} for s in syms]
    bars = pd.DataFrame(rows).drop_duplicates(["entry_date", "ticker"])
    bars.to_parquet(BARS)
    print(f"  15:59 bars: {int(bars['s1559'].notna().sum())}/{len(bars)}", flush=True)

    tickers = sorted(set(sig["ticker"]) | {"SPY"})
    start = sig["entry_date"].min() - pd.Timedelta(days=10)
    end = sig["expiry"].max() + pd.Timedelta(days=10)
    raw = yf.download(
        tickers,
        start=str(start.date()),
        end=str(end.date()),
        auto_adjust=False,
        actions=True,
        progress=False,
        threads=True,
    )
    close = raw["Close"]
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    close.to_parquet(RAW)
    div = raw["Dividends"]
    div.index = pd.to_datetime(div.index).tz_localize(None).normalize()
    div = div.stack().rename("dividend").reset_index()
    div.columns = ["ex_date", "ticker", "dividend"]
    div[div["dividend"] > 0].to_parquet(DIVS)

    csv = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=30).text
    r = pd.read_csv(io.StringIO(csv))
    r.columns = ["date", "dtb3"]
    r["date"] = pd.to_datetime(r["date"])
    r["dtb3"] = pd.to_numeric(r["dtb3"], errors="coerce")
    r.dropna().to_parquet(RATES)


# ── score ────────────────────────────────────────────────────────────────────


def assemble(sig: pd.DataFrame) -> pd.DataFrame:
    bars = pd.read_parquet(BARS)
    raw = pd.read_parquet(RAW)
    divs = pd.read_parquet(DIVS)
    rates = pd.read_parquet(RATES).set_index("date")["dtb3"].sort_index()
    d = sig.merge(bars, on=["entry_date", "ticker"], how="left", validate="one_to_one")
    spy = bars[bars["ticker"] == "SPY"].set_index("entry_date")["s1559"]
    f: dict[str, int] = {"in": len(d)}
    d = d[d["s1559"].notna()]
    f["with_1559_bar"] = len(d)
    fps = []
    for _, e in d.iterrows():
        dtb3 = rates.loc[: e["entry_date"]].iloc[-1] / 100
        r = float(np.log(1 + dtb3 * 91 / 360) * 365 / 91)  # bank discount to continuous, approx
        f_par = float(np.mean(e["parity_k"] + e["parity_cp"] * np.exp(r * e["t_years"])))
        dv = divs[
            (divs["ticker"] == e["ticker"])
            & (divs["ex_date"] > e["entry_date"])
            & (divs["ex_date"] <= e["expiry"])
        ]
        tau = (dv["ex_date"] - e["entry_date"]).dt.days.to_numpy() / 365.0
        pv = float(np.sum(dv["dividend"].to_numpy() * np.exp(-r * tau)))
        f_cc = (e["s1559"] - pv) * np.exp(r * e["t_years"])
        f_cc_nodiv = e["s1559"] * np.exp(r * e["t_years"])
        fps.append((np.log(f_par / f_cc), np.log(f_par / f_cc_nodiv), pv))
    d["fp"], d["fp_nodiv"], d["pv_div"] = zip(*fps, strict=True)

    idx = raw.index
    pos = {ts: i for i, ts in enumerate(idx)}
    adj = load_prices(sorted(d["ticker"].unique().tolist()), idx.min(), idx.max())
    out = []
    for _, e in d.iterrows():
        i = pos.get(e["entry_date"])
        rec = {"ret_0_2": np.nan, "ret_0_1": np.nan, "ret_placebo": np.nan, "basis_ok": False}
        if i is not None and i + HORIZON < len(idx) and e["entry_date"] in spy.index:
            t, sp = e["ticker"], spy.loc[e["entry_date"]]
            ct, cm = raw[t].iloc[i], raw["SPY"].iloc[i]
            ok = abs(ct / e["s1559"] - 1) <= SPLIT_TOL and abs(cm / sp - 1) <= SPLIT_TOL
            rec["basis_ok"] = bool(ok)
            if ok:

                def leg(sym: str, s0: float, c0: float, k: int, i: int = i) -> float:
                    a = adj[sym]
                    d0 = a.index.get_loc(idx[i])
                    return float((a.iloc[d0 + k] / a.iloc[d0]) * (c0 / s0) - 1)

                rec["ret_0_2"] = leg(t, e["s1559"], ct, HORIZON) - leg("SPY", sp, cm, HORIZON)
                rec["ret_0_1"] = leg(t, e["s1559"], ct, 1) - leg("SPY", sp, cm, 1)
                a, m = adj[t], adj["SPY"]
                d0 = a.index.get_loc(idx[i])
                rec["ret_placebo"] = float(
                    (a.iloc[d0] / a.iloc[d0 - PLACEBO_BACK] * (e["s1559"] / ct) - 1)
                    - (m.iloc[d0] / m.iloc[d0 - PLACEBO_BACK] * (sp / cm) - 1)
                )
        out.append(rec)
    d = pd.concat([d.reset_index(drop=True), pd.DataFrame(out)], axis=1)
    f["basis_ok"] = int(d["basis_ok"].sum())
    d = d[d["basis_ok"] & d["ret_0_2"].notna()].reset_index(drop=True)
    f["scored"] = len(d)
    _funnel("assemble", f)
    return d


def _deciles(d: pd.DataFrame, col: str, by: str | None) -> np.ndarray:
    out = np.zeros(len(d), dtype=int)
    groups = (
        [np.arange(len(d))]
        if by is None
        else [np.flatnonzero((d[by] == g).to_numpy()) for g in d[by].unique()]
    )
    for ix in groups:
        sub = d.iloc[ix]
        order = np.lexsort((sub["ticker"].to_numpy(), sub[col].to_numpy()))
        ranks = np.empty(len(ix), dtype=int)
        ranks[order] = np.arange(1, len(ix) + 1)
        out[ix] = (N_DECILES * (ranks - 1)) // len(ix) + 1
    return out


def _gap(r: np.ndarray, dec: np.ndarray) -> float:
    return float(r[dec == N_DECILES].mean() - r[dec == 1].mean())


def _gap_ci(r: np.ndarray, dec: np.ndarray, dates: pd.Series) -> tuple[float, float]:
    keys = pd.to_datetime(dates).dt.strftime("%Y-%m-%d").to_numpy()

    def stat(ix: np.ndarray) -> float:
        j = ix.astype(int)
        return _gap(r[j], dec[j])

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(r), dtype=float), keys, stat, n_boot=N_BOOT, seed=SEED
    )
    return float(lo), float(hi)


def _variant(d: pd.DataFrame, sig: str, col: str, by: str | None) -> dict[str, Any]:
    x = d.dropna(subset=[col]).reset_index(drop=True)
    dec = _deciles(x, sig, by)
    r = x[col].to_numpy(dtype=float)
    means = x.assign(dec=dec).groupby("dec")[col].mean()
    lo, hi = _gap_ci(r, dec, x["entry_date"])
    return {
        "n": len(x),
        "gap_gross": _gap(r, dec),
        "ci_gross": [lo, hi],
        "spearman": float(spearmanr(means.index, means.to_numpy())[0]),
        "decile_means": means.round(5).to_dict(),
    }


def score() -> None:
    _check_prereg()
    sig = pd.read_parquet(SIGNAL)
    sig, _ = edgar_exclusion(sig)
    d = assemble(sig)
    d["bucket"] = month_buckets(d["entry_date"])
    d.drop(columns=["parity_k", "parity_cp"]).to_csv(OUT / "scored_events.csv", index=False)
    dec = _deciles(d, "fp", "bucket")
    r = d["ret_0_2"].to_numpy(dtype=float)
    g = _gap(r, dec)
    lo, hi = _gap_ci(r, dec, d["entry_date"])
    means = d.assign(dec=dec).groupby("dec")["ret_0_2"].agg(["mean", "count", "std"])
    means["mean_fp"] = d.assign(dec=dec).groupby("dec")["fp"].mean()
    rho = float(spearmanr(means.index, means["mean"].to_numpy())[0])
    rng = np.random.default_rng(SEED)
    buckets = d["bucket"].to_numpy()
    idx_by = [np.flatnonzero(buckets == b) for b in np.unique(buckets)]
    null = np.empty(N_NULL)
    for k in range(N_NULL):
        perm = dec.copy()
        for ix in idx_by:
            perm[ix] = rng.permutation(dec[ix])
        null[k] = _gap(r, perm)
    pct = float((null < g).mean())
    ls = np.concatenate([r[dec == N_DECILES], -r[dec == 1]]) - 2 * COST_PER_SIDE
    res: dict[str, Any] = {
        "n": len(d),
        "n_dates": int(d["entry_date"].nunique()),
        "gap_gross": g,
        "ci_gross": [lo, hi],
        "gap_net": g - LS_COST,
        "ci_net": [lo - LS_COST, hi - LS_COST],
        "spearman": rho,
        "null_pct": pct,
        "null_p95": float(np.quantile(null, 0.95)),
        "ls_sharpe_per_trade": float(ls.mean() / ls.std(ddof=1)),
        "ls_n": len(ls),
        "dsr": float(deflated_sharpe_ratio(pd.Series(ls), n_trials=N_TRIALS)),
        "fp_bp_median": float(d["fp"].median() * 1e4),
        "fp_bp_iqr": [float(d["fp"].quantile(q) * 1e4) for q in (0.25, 0.75)],
    }
    res["pass"] = bool(rho >= SPEARMAN_PASS and lo - LS_COST > 0 and pct >= 0.95)
    res["verdict"] = "PASS" if res["pass"] else "FAIL"
    print(means.round(5).to_string())
    sec = {
        "pooled": _variant(d, "fp", "ret_0_2", None),
        "ret_0_1": _variant(d, "fp", "ret_0_1", "bucket"),
        "placebo": _variant(d, "fp", "ret_placebo", "bucket"),
        "no_dividends": _variant(d, "fp_nodiv", "ret_0_2", "bucket"),
    }
    for sess in ("BMO", "AMC"):
        sub = d[d["edgar_session"].astype(str).str.upper().eq(sess)]
        if len(sub) >= 10 * N_DECILES:
            sec[sess.lower()] = _variant(sub.reset_index(drop=True), "fp", "ret_0_2", None)
    res["secondary"] = sec
    means.to_csv(OUT / "deciles.csv")
    print(json.dumps(res, indent=1, default=float))
    json.dump(res, open(OUT / "summary.json", "w"), indent=1, default=float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--signal", action="store_true")
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    _check_prereg()
    if a.signal:
        build_signal()
    if a.prices:
        pull_prices(pd.read_parquet(SIGNAL))
    if a.score:
        score()


if __name__ == "__main__":
    main()
