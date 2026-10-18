"""
research_ml_zoo.py
Walk-forward model zoo for earnings straddle selection: many model families, targets, parameters
and selection thresholds, scored year by year on predictions made only from earlier years.

Stages:
    --build   one unified event table (megacap 2013-2024, corrected broad 2025-2026, July-August
              2026) with an enriched feature set, written to outputs/research/ml_zoo/events.parquet
    --run     expanding-window walk-forward over the configuration grid; every configuration's
              out-of-sample predictions, per-year metrics and summary are written to disk

This is an exploratory search, run without a pre-registration at the owner's request. Every
configuration counts as a trial, and the best one is reported against the deflated Sharpe ratio
for the number tried, which is the honest measure of how much of its result is selection.

Usage:
    python research/selection/research_ml_zoo.py --build
    python research/selection/research_ml_zoo.py --run [--workers 6]
"""

from __future__ import annotations

import argparse
import glob
import io
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = Path("outputs/research/ml_zoo")
# worker processes re-import this module, so the event table is chosen by environment variable
EVENTS = Path(os.environ.get("ZOO_EVENTS", str(OUT / "events.parquet")))
PRICES = OUT / "prices.parquet"
FIRST_TEST_YEAR = 2016
SEED = 0

BASE = [
    "front_atm_iv",
    "back_atm_iv",
    "iv_term_spread",
    "implied_move",
    "trailing_rv",
    "skew_25d",
    "vol_premium",
    "variance_risk_premium",
    "bkm_skew",
    "bkm_kurt",
    "t_entry",
]
EXTRA = [
    "log_implied",
    "implied_over_daily_rv",
    "shift",
    "name_prior_ratio",
    "vix",
    "vix_chg_20d",
    "hist_move_8",
    "implied_over_hist",
    "hist_move_dispersion",
    "ret_5d",
    "ret_20d",
    "ret_250d",
    "rv_60d",
    "dist_52w_high",
    "log_mcap",
    "is_amc",
    "dow",
    "season_pos",
    "sic1",
]
FEATURES = BASE + EXTRA


# ── build ────────────────────────────────────────────────────────────────────


def _base_events() -> pd.DataFrame:
    from research.selection.research_ml_ratio import broad, panel
    from research.selection.research_ml_ratio_confirm2 import outcomes as c2_outcomes

    p = panel().assign(block="megacap")
    p = p[p["entry_date"].dt.year <= 2024]
    b = broad().assign(block="broad")
    new = pd.read_parquet("outputs/research/ml_ratio_confirm2/features.parquet")
    new["entry_date"] = pd.to_datetime(new["entry_date"])
    o = c2_outcomes(new)
    new = new.merge(o[["ticker", "entry_date", "rom"]], on=["ticker", "entry_date"], how="inner")
    new = new.assign(block="broad_2026h2")
    keep = ["ticker", "announce_date", "entry_date", "exit_date", "rom", "realised_move", *BASE]
    d = pd.concat([p[keep + ["block"]], b[keep + ["block"]], new[keep + ["block"]]])
    d["announce_date"] = pd.to_datetime(d["announce_date"])
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    return d.drop_duplicates(["ticker", "entry_date"]).reset_index(drop=True)


def _prices(tickers: list[str]) -> pd.DataFrame:
    if PRICES.exists():
        px = pd.read_parquet(PRICES)
        if set(tickers) <= set(px.columns):
            return px
    import yfinance as yf

    raw = yf.download(
        sorted(set(tickers) | {"SPY"}),
        start="2010-01-01",
        end="2026-10-15",
        auto_adjust=True,
        progress=False,
        threads=True,
    )["Close"]
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw.to_parquet(PRICES)
    return raw


def _vix() -> pd.Series:
    csv = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS", timeout=30).text
    v = pd.read_csv(io.StringIO(csv))
    v.columns = ["date", "vix"]
    v["date"] = pd.to_datetime(v["date"])
    v["vix"] = pd.to_numeric(v["vix"], errors="coerce")
    return v.dropna().set_index("date")["vix"]


def _sic() -> dict[str, int]:
    out: dict[str, tuple[pd.Timestamp, int]] = {}
    for f in glob.glob("data/processed/wrds/raw/crsp_a_stock.dsenames.*.parquet"):
        d = pd.read_parquet(f)
        if not {"ticker", "siccd"} <= set(d.columns):
            continue
        end = pd.to_datetime(d.get("nameendt", pd.Timestamp("2100-01-01")), errors="coerce")
        for t, s, e in zip(d["ticker"], d["siccd"], end, strict=False):
            if pd.isna(t) or pd.isna(s):
                continue
            t = str(t).replace(".", "-")
            e = e if pd.notna(e) else pd.Timestamp("2100-01-01")
            if t not in out or e > out[t][0]:
                out[t] = (e, int(s))
    return {k: v[1] for k, v in out.items()}


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = enrich(_base_events())
    d.to_parquet(EVENTS, index=False)
    print(f"  wrote {len(d)} events to {EVENTS}", flush=True)


def enrich(d: pd.DataFrame) -> pd.DataFrame:
    """Add every derived feature to a base event table (BASE columns, rom, realised_move)."""
    from research.selection.research_date_shift import FUNDQ, shifts

    print(f"  base events {len(d)}: {d['block'].value_counts().to_dict()}", flush=True)
    d = d.copy()
    d["y"] = d["realised_move"] / d["implied_move"]
    d["log_implied"] = np.log(d["implied_move"])
    d["implied_over_daily_rv"] = d["implied_move"] / (d["trailing_rv"] * np.sqrt(1 / 252))
    # date shift
    q = shifts()
    m = d.merge(q, left_on="ticker", right_on="tic", how="left")
    m = m[(m["rdq"] - m["announce_date"]).dt.days.abs() <= 3]
    m = m.sort_values("shift").drop_duplicates(["ticker", "announce_date"])
    d = d.merge(m[["ticker", "announce_date", "shift"]], on=["ticker", "announce_date"], how="left")
    # name prior realised/implied, causal
    d = d.sort_values(["ticker", "entry_date"]).reset_index(drop=True)
    prior_sum = d.groupby("ticker")["y"].transform(lambda s: s.shift(1).expanding().sum())
    prior_n = d.groupby("ticker").cumcount()
    d["name_prior_ratio"] = np.where(prior_n >= 2, prior_sum / prior_n.clip(lower=1), np.nan)
    # VIX
    vix = _vix()
    d["vix"] = vix.reindex(d["entry_date"], method="ffill").to_numpy()
    d["vix_chg_20d"] = (
        d["vix"] - vix.reindex(d["entry_date"] - pd.Timedelta(days=28), method="ffill").to_numpy()
    )
    # prices and historical earnings moves from Compustat report dates
    px = _prices(sorted(d["ticker"].unique()))
    rets = px.pct_change(fill_method=None)
    rdq = pd.concat([pd.read_parquet(p) for p in FUNDQ]).dropna(subset=["rdq"])
    rdq["tic"] = rdq["tic"].astype(str).str.replace(".", "-", regex=False)
    rdq["rdq"] = pd.to_datetime(rdq["rdq"])
    rdq = rdq.drop_duplicates(["tic", "rdq"])
    feats = []
    idx = px.index
    for _, e in d.iterrows():
        t, t0 = e["ticker"], e["entry_date"]
        f: dict[str, Any] = {}
        if t in px.columns:
            s, r = px[t], rets[t]
            i = int(idx.searchsorted(t0, side="right")) - 1
            if i >= 260 and pd.notna(s.iloc[i]):
                f["ret_5d"] = s.iloc[i] / s.iloc[i - 5] - 1
                f["ret_20d"] = s.iloc[i] / s.iloc[i - 20] - 1
                f["ret_250d"] = s.iloc[i] / s.iloc[i - 250] - 1
                f["rv_60d"] = float(r.iloc[i - 59 : i + 1].std() * np.sqrt(252))
                f["dist_52w_high"] = s.iloc[i] / s.iloc[i - 251 : i + 1].max() - 1
            past = rdq[
                (rdq["tic"] == t) & (rdq["rdq"] < e["announce_date"] - pd.Timedelta(days=20))
            ]
            past = past.sort_values("rdq").tail(8)
            moves = []
            for dd in past["rdq"]:
                j = int(idx.searchsorted(dd))
                if 1 <= j < len(idx) - 1:
                    moves.append(max(abs(r.iloc[j]), abs(r.iloc[j + 1])))
            moves = [x for x in moves if np.isfinite(x)]
            if len(moves) >= 4:
                f["hist_move_8"] = float(np.mean(moves))
                f["hist_move_dispersion"] = float(np.std(moves))
        feats.append(f)
    d = pd.concat([d, pd.DataFrame(feats)], axis=1)
    d["implied_over_hist"] = d["implied_move"] / d["hist_move_8"]
    mc = pd.concat(
        [
            pd.read_parquet(p)
            for p in glob.glob("data/processed/wrds/raw/comp_na_daily_all.fundq.*.parquet")
            if "mkvaltq" in pq_columns(p)
        ]
    )
    mc = mc.dropna(subset=["rdq", "mkvaltq"])
    mc["tic"] = mc["tic"].astype(str).str.replace(".", "-", regex=False) if "tic" in mc else np.nan
    mc["rdq"] = pd.to_datetime(mc["rdq"]).astype("datetime64[ns]")
    mc = mc.dropna(subset=["tic"]).sort_values("rdq")
    d["announce_date"] = d["announce_date"].astype("datetime64[ns]")
    d = d.sort_values("announce_date")
    d = pd.merge_asof(
        d,
        mc[["tic", "rdq", "mkvaltq"]].rename(columns={"tic": "ticker", "rdq": "mc_date"}),
        left_on="announce_date",
        right_on="mc_date",
        by="ticker",
        direction="backward",
        allow_exact_matches=False,
    )
    mk = pd.to_numeric(d["mkvaltq"], errors="coerce")
    d["log_mcap"] = np.log(mk.where(mk > 0).astype(float))
    d["is_amc"] = (d["entry_date"] == d["announce_date"]).astype(int)
    d["dow"] = d["announce_date"].dt.dayofweek
    qstart = d["announce_date"].dt.to_period("Q").dt.start_time
    d["season_pos"] = (d["announce_date"] - qstart).dt.days
    sic = _sic()
    d["sic1"] = d["ticker"].map(lambda t: sic.get(t, np.nan) // 1000 if t in sic else np.nan)
    d = d.sort_values("entry_date").reset_index(drop=True)
    cover = d[FEATURES].notna().mean().round(3).to_dict()
    print(f"  feature coverage: {cover}", flush=True)
    return d


def pq_columns(path: str) -> list[str]:
    import pyarrow.parquet as pq

    return pq.read_schema(path).names


# ── models ───────────────────────────────────────────────────────────────────


def configs() -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = []
    for target in ("y", "rom"):
        for a in (0.1, 1, 10, 100, 1000):
            grid.append({"model": "ridge", "alpha": a, "target": target})
        for a in (0.0005, 0.002, 0.01, 0.05):
            grid.append({"model": "lasso", "alpha": a, "target": target})
        for a in (0.01, 0.1):
            for l1 in (0.2, 0.5, 0.8):
                grid.append({"model": "enet", "alpha": a, "l1_ratio": l1, "target": target})
        for eps in (1.35, 2.0):
            grid.append({"model": "huber", "epsilon": eps, "target": target})
        for k in (2, 4):
            grid.append({"model": "pls", "n_components": k, "target": target})
        for k in (25, 75, 200):
            grid.append({"model": "knn", "k": k, "target": target})
        for c in (0.1, 1.0):
            grid.append({"model": "svr", "C": c, "target": target})
        for depth in (3, 6, None):
            for leaf in (10, 40):
                grid.append({"model": "rf", "max_depth": depth, "leaf": leaf, "target": target})
                grid.append({"model": "et", "max_depth": depth, "leaf": leaf, "target": target})
        for depth in (2, 3, 5):
            for lr in (0.02, 0.05, 0.1):
                for it in (100, 300):
                    grid.append(
                        {"model": "hgb", "depth": depth, "lr": lr, "iter": it, "target": target}
                    )
        for h in ((16,), (32, 16), (64, 32)):
            for a in (1e-3, 1e-1):
                grid.append({"model": "mlp", "hidden": h, "alpha": a, "target": target})
    for c in (0.01, 0.1, 1.0):
        grid.append({"model": "logit", "C": c, "target": "loss"})
    for depth in (2, 3):
        grid.append({"model": "hgbc", "depth": depth, "target": "loss"})
    return grid


def make_model(c: dict[str, Any]) -> Any:
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.ensemble import (
        ExtraTreesRegressor,
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
        RandomForestRegressor,
    )
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, HuberRegressor, Lasso, LogisticRegression, Ridge
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import QuantileTransformer, StandardScaler
    from sklearn.svm import SVR

    def lin(est: Any) -> Any:
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), est)

    def rank(est: Any) -> Any:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            QuantileTransformer(n_quantiles=200, output_distribution="normal", random_state=SEED),
            est,
        )

    m = c["model"]
    if m == "ridge":
        return lin(Ridge(alpha=c["alpha"]))
    if m == "lasso":
        return lin(Lasso(alpha=c["alpha"], max_iter=5000))
    if m == "enet":
        return lin(ElasticNet(alpha=c["alpha"], l1_ratio=c["l1_ratio"], max_iter=5000))
    if m == "huber":
        return lin(HuberRegressor(epsilon=c["epsilon"], max_iter=500))
    if m == "pls":
        return lin(PLSRegression(n_components=c["n_components"]))
    if m == "knn":
        return rank(KNeighborsRegressor(n_neighbors=c["k"], weights="distance"))
    if m == "svr":
        return rank(SVR(C=c["C"], epsilon=0.1))
    if m == "rf":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestRegressor(
                n_estimators=300,
                max_depth=c["max_depth"],
                min_samples_leaf=c["leaf"],
                max_features=0.5,
                random_state=SEED,
                n_jobs=1,
            ),
        )
    if m == "et":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            ExtraTreesRegressor(
                n_estimators=300,
                max_depth=c["max_depth"],
                min_samples_leaf=c["leaf"],
                max_features=0.5,
                random_state=SEED,
                n_jobs=1,
            ),
        )
    if m == "hgb":
        return HistGradientBoostingRegressor(
            max_depth=c["depth"],
            learning_rate=c["lr"],
            max_iter=c["iter"],
            l2_regularization=1.0,
            min_samples_leaf=40,
            random_state=SEED,
        )
    if m == "mlp":
        return rank(
            MLPRegressor(
                hidden_layer_sizes=c["hidden"],
                alpha=c["alpha"],
                max_iter=500,
                early_stopping=True,
                random_state=SEED,
            )
        )
    if m == "logit":
        return lin(LogisticRegression(C=c["C"], max_iter=2000))
    if m == "hgbc":
        return HistGradientBoostingClassifier(
            max_depth=c["depth"], learning_rate=0.05, max_iter=200, random_state=SEED
        )
    raise ValueError(m)


def _target(d: pd.DataFrame, t: str) -> np.ndarray:
    if t == "y":
        return d["y"].to_numpy()
    if t == "rom":
        return d["rom"].clip(-1.0, 1.0).to_numpy()  # winsorised so one gap does not steer the fit
    return (d["rom"] < 0).astype(int).to_numpy()


def _score(model: Any, c: dict[str, Any], x: pd.DataFrame) -> np.ndarray:
    """Higher score = better short candidate."""
    if c["target"] == "loss":
        return -model.predict_proba(x)[:, 1]
    p = np.asarray(model.predict(x)).ravel()
    return -p if c["target"] == "y" else p


def walk_forward(c: dict[str, Any]) -> pd.DataFrame:
    warnings.filterwarnings("ignore")
    d = pd.read_parquet(EVENTS).dropna(subset=["y", "rom"])
    yr = d["entry_date"].dt.year
    out = []
    for test_year in range(FIRST_TEST_YEAR, int(yr.max()) + 1):
        tr, te = d[yr < test_year], d[yr == test_year]
        if te.empty:
            continue
        model = make_model(c)
        model.fit(tr[FEATURES], _target(tr, c["target"]))
        s_tr = _score(model, c, tr[FEATURES])
        s_te = _score(model, c, te[FEATURES])
        cut = {q: float(np.quantile(s_tr, 1 - q)) for q in (0.3, 0.5, 0.7)}
        o = te[["ticker", "entry_date", "announce_date", "block", "rom", "y"]].copy()
        o["score"] = s_te
        for q, v in cut.items():
            o[f"sel_{int(q * 100)}"] = s_te >= v
        out.append(o)
    return pd.concat(out, ignore_index=True)


def _summarise(cid: int, c: dict[str, Any], o: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    rho = float(spearmanr(o["score"], -o["y"])[0])
    for q in (30, 50, 70):
        s = o[f"sel_{q}"].to_numpy()
        sel, uns = o.loc[s, "rom"], o.loc[~s, "rom"]
        by_year = (
            o.assign(s=s)
            .groupby(o["entry_date"].dt.year)
            .apply(lambda g: g.loc[g["s"], "rom"].mean() - g.loc[~g["s"], "rom"].mean())
        )
        rows.append(
            {
                "cid": cid,
                **{k: str(v) for k, v in c.items()},
                "q": q,
                "n_oos": len(o),
                "n_sel": int(s.sum()),
                "spearman_vs_neg_y": rho,
                "sel_mean": float(sel.mean()) if len(sel) else np.nan,
                "uns_mean": float(uns.mean()) if len(uns) else np.nan,
                "diff": float(sel.mean() - uns.mean()) if len(sel) and len(uns) else np.nan,
                "sel_sharpe": float(sel.mean() / sel.std(ddof=1)) if len(sel) > 2 else np.nan,
                "years_diff_positive": int((by_year > 0).sum()),
                "years": int(by_year.notna().sum()),
            }
        )
    return rows


def _job(args: tuple[int, dict[str, Any]]) -> tuple[int, list[dict[str, Any]], pd.DataFrame]:
    cid, c = args
    o = walk_forward(c)
    return cid, _summarise(cid, c, o), o.assign(cid=cid)


def run(workers: int) -> None:
    grid = configs()
    print(f"  {len(grid)} model configurations x 3 thresholds", flush=True)
    rows, preds = [], []
    with ProcessPoolExecutor(workers) as ex:
        for k, (_cid, r, o) in enumerate(ex.map(_job, list(enumerate(grid))), start=1):
            rows += r
            preds.append(o[["cid", "ticker", "entry_date", "score"]])
            if k % 20 == 0:
                print(f"    {k}/{len(grid)} configurations done", flush=True)
    res = pd.DataFrame(rows).sort_values("diff", ascending=False)
    res.to_csv(OUT / "zoo_results.csv", index=False)
    pd.concat(preds).to_parquet(OUT / "zoo_predictions.parquet", index=False)
    print(res.head(25).to_string(), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.build:
        build()
    if a.run:
        run(a.workers)


if __name__ == "__main__":
    main()
