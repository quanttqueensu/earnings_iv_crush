"""
study.py
Confirmation on 2025-2026: beta-hedged long of the lowest post-event term-slope decile, scored
exactly as frozen in ``prereg.md``. Run once.

Usage
-----
    python research/selection/2026-10-21-inversion-confirm/study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
FEATS = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold"
START = pd.Timestamp("2025-01-01")
DOWNLOAD_FROM = "2023-12-01"  # 250 sessions of beta history before the first 2025 exit
BETA_WINDOW, BETA_MIN = 250, 200
HEDGE_COST_BPS = 0.5  # SPY per side
N_TRIALS = 1544
SR_TRIALS_STD = 0.127475


def download(tickers: list[str]) -> pd.DataFrame:
    """Adjusted closes from yfinance, cached so a rerun does not refetch."""
    cache = OUT / "yf_closes.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    import yfinance as yf

    px = yf.download(
        tickers, start=DOWNLOAD_FROM, end="2026-10-20", auto_adjust=True, progress=False
    )["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    OUT.mkdir(parents=True, exist_ok=True)
    px.to_parquet(cache)
    return px


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    feat = pd.read_parquet(FEATS / "features.parquet")
    feat = feat[feat["exit_date"].dt.year >= 2013]
    d = feat[np.isfinite(feat["post_slope"])].copy()
    d["bin"] = hh.causal_bins(d["post_slope"], d["exit_date"], 10, HEDGED.decile_min_prior)
    t = d[(d["exit_date"] >= START) & (d["bin"] >= 0)].copy()
    n_block = int((feat["exit_date"] >= START).sum())
    print(f"funnel: {n_block} events from 2025, {len(t)} with signal and decile")

    crsp = pd.read_parquet(FEATS / "crsp_paths.parquet")
    for c in ("prc", "bid", "ask"):
        crsp[c] = crsp[c].astype(float)
    c24 = crsp[crsp["date"].dt.year == 2024]
    hs = ((c24["ask"] - c24["bid"]) / 2 / c24["prc"].abs()).where(
        (c24["bid"] > 0) & (c24["ask"] > c24["bid"])
    )
    half_2024 = hs.groupby(c24["permno"]).median()

    yt = {tk: tk.replace(".", "-") for tk in t["ticker"].unique()}
    # CRSP name records end in 2024, so 2025-26 events carry no permno; the 2024 spread lookup
    # uses the permno of the same ticker's most recent linked event
    linked = feat[feat["permno"].notna()].sort_values("entry_date")
    last_permno = linked.groupby("ticker")["permno"].last()
    t["permno"] = t["permno"].fillna(t["ticker"].map(last_permno))
    print(
        f"  permno via the ticker's last linked event: {int(t['permno'].notna().sum())} of {len(t)}"
    )
    px = download(sorted(set(yt.values())) + ["SPY", "^IRX"])
    ret = px.pct_change(fill_method=None)
    rf = (px["^IRX"] / 100.0 / 252.0).reindex(ret.index).ffill()
    mkt = ret["SPY"] - rf
    floor = HEDGED.equity_cost_floor_bps / 1e4
    rows, why = [], []
    for _, e in t.iterrows():
        tk = yt[e["ticker"]]
        if tk not in ret.columns or not np.isfinite(e["permno"]):
            rows.append((np.nan, np.nan)), why.append("no_price")
            continue
        s = ret[tk]
        if e["exit_date"] not in s.index:
            rows.append((np.nan, np.nan)), why.append("no_entry_day")
            continue
        i = s.index.get_loc(e["exit_date"])
        fut = s.iloc[i + 1 : i + 1 + HEDGED.equity_hold_days]
        hist_idx = s.index[max(0, i - BETA_WINDOW + 1) : i + 1]
        if len(fut) < HEDGED.equity_hold_days or fut.isna().any():
            rows.append((np.nan, np.nan)), why.append("window_incomplete")
            continue
        hx = (s.reindex(hist_idx) - rf.reindex(hist_idx)).to_numpy(float)
        hm = mkt.reindex(hist_idx).to_numpy(float)
        ok = np.isfinite(hx) & np.isfinite(hm)
        if ok.sum() < BETA_MIN:
            rows.append((np.nan, np.nan)), why.append("no_beta")
            continue
        beta = float(np.cov(hx[ok], hm[ok])[0, 1] / np.var(hm[ok], ddof=1))
        h = half_2024.get(int(e["permno"]), np.nan)
        if not np.isfinite(h):
            rows.append((np.nan, np.nan)), why.append("no_2024_spread")
            continue
        fi = fut.index
        stock_x = float(np.prod(1 + fut.to_numpy(float)) - np.prod(1 + rf.reindex(fi)))
        mkt_x = float(np.prod(1 + ret["SPY"].reindex(fi)) - np.prod(1 + rf.reindex(fi)))
        cost = 2 * max(h, floor) + 2 * HEDGE_COST_BPS / 1e4 * abs(beta)
        rows.append((stock_x - beta * mkt_x, cost))
        why.append("ok")
    t["gross_abn"] = [g for g, _ in rows]
    t["cost"] = [c for _, c in rows]
    t["net_abn"] = t["gross_abn"] - t["cost"]
    t["reason"] = why
    print(f"  outcome funnel: {t['reason'].value_counts().to_dict()}")
    ok = t[t["reason"] == "ok"]

    res: dict = {"prereg_sha256": verify_prereg(PREREG, RECORD)}
    for label, b in (("lowest_decile", 0), ("highest_decile", 9)):
        s = ok[ok["bin"] == b]
        ci = date_clustered_ci(s["net_abn"].to_numpy(float), s["exit_date"], stat=np.mean)
        sd = float(s["net_abn"].std(ddof=1))
        res[label] = {
            "n": int(len(s)),
            "mean_net_abn": ci.point,
            "ci": [ci.low, ci.high],
            "per_position_sharpe": per_trade_sharpe(s["net_abn"]),
            "dsr": float(deflated_sharpe_ratio(s["net_abn"], N_TRIALS, SR_TRIALS_STD)),
            "mde_80pct_power": 2.8 * sd / np.sqrt(len(s)),
        }
        print(
            f"  {label}: mean net CAPM-abnormal per 20-day position {ci}; Sharpe"
            f" {res[label]['per_position_sharpe']:+.3f}; MDE (80% power, 5% two-sided)"
            f" {res[label]['mde_80pct_power']:.4f}"
        )
    ls = ok[ok["bin"].isin([0, 9])]
    sign = np.where(ls["bin"] == 0, 1.0, -1.0)
    pos = sign * ls["gross_abn"].to_numpy(float) - ls["cost"].to_numpy(float)
    ci = date_clustered_ci(pos, ls["exit_date"], stat=np.mean)
    res["long_short"] = {"n": int(len(pos)), "mean": ci.point, "ci": [ci.low, ci.high]}
    print(f"  long lowest / short highest (secondary, net of both legs' costs): {ci}")
    dec = ok.groupby("bin")["net_abn"].agg(["size", "mean"])
    print(f"  deciles (net CAPM-abnormal):\n{dec.to_string()}")
    res["deciles"] = dec.reset_index().to_dict(orient="records")
    res["pass"] = bool(res["lowest_decile"]["ci"][0] > 0)
    print(f"verdict: {'PASS' if res['pass'] else 'FAIL or inconclusive'}")
    (OUT / "summary.json").write_text(json.dumps(res, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
