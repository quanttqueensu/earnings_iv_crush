"""
research_ml_ratio.py
Pre-registered test: a frozen machine-learned predictor of realised over implied earnings move.

``research/selection/preregs/ml_ratio_prereg.md``. Two stages so the evaluation sets are opened only after the model,
features and threshold are frozen and hashed:

    --select   train on 2013-2018, choose among nine candidates on 2019-2021, refit on 2013-2021,
               freeze the model and threshold (writes model.pkl and its SHA-256)
    --test     open the 2022-2024 megacap test and the 2025-2026 broad confirmation once

Usage:
    python research/selection/research_ml_ratio.py --select
    python research/selection/research_ml_ratio.py --test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from research.selection.research_date_shift import shifts  # noqa: E402

PREREG = Path("research/selection/preregs/ml_ratio_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_ml_ratio.json")
PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
BROAD = Path("outputs/research/oos_2026_attrition_audit/events.csv")
BROAD_EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
OUT = Path("outputs/research/ml_ratio")
MODEL = OUT / "model.pkl"
FROZEN = OUT / "frozen.json"
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
FEATURES = [*BASE, "log_implied", "implied_over_daily_rv", "shift", "name_prior_ratio"]
Q_SELL = 0.20
N_BOOT = 5000
N_NULL = 1000
SEED = 0
N_TRIALS = 1520


def _check_prereg() -> None:
    want = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != want:
        raise SystemExit("pre-registration hash mismatch")


# ── data ─────────────────────────────────────────────────────────────────────


def _derive(d: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["announce_date"] = pd.to_datetime(d["announce_date"])
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["y"] = d["realised_move"] / d["implied_move"]
    d["log_implied"] = np.log(d["implied_move"])
    d["implied_over_daily_rv"] = d["implied_move"] / (d["trailing_rv"] * np.sqrt(1 / 252))
    m = d.merge(q, left_on="ticker", right_on="tic", how="left")
    m = m[(m["rdq"] - m["announce_date"]).dt.days.abs() <= 3]
    m = m.sort_values("shift").drop_duplicates(["ticker", "announce_date"])
    d = d.merge(m[["ticker", "announce_date", "shift"]], on=["ticker", "announce_date"], how="left")
    d = d.sort_values(["ticker", "entry_date"])
    prior_sum = d.groupby("ticker")["y"].transform(lambda s: s.shift(1).expanding().sum())
    prior_n = d.groupby("ticker").cumcount()
    d["name_prior_ratio"] = np.where(prior_n >= 2, prior_sum / prior_n.clip(lower=1), np.nan)
    return d.sort_values("entry_date").reset_index(drop=True)


def panel() -> pd.DataFrame:
    p = pd.read_parquet(PANEL)
    p = p.rename(columns={"return_on_margin": "rom"})
    return _derive(p, shifts())


def broad() -> pd.DataFrame:
    b = pd.read_csv(BROAD, parse_dates=["entry_date"]).drop_duplicates(["ticker", "entry_date"])
    ev = pd.read_parquet(BROAD_EVENTS).drop_duplicates(["ticker", "entry_date"])
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    d = b.rename(columns={"net_rom": "rom"})[["ticker", "entry_date", "rom"]].merge(
        ev, on=["ticker", "entry_date"], how="inner", validate="one_to_one"
    )
    return _derive(d, shifts())


def _candidates() -> dict[str, Any]:
    c: dict[str, Any] = {}
    for a in (1, 10, 100):
        c[f"ridge_a{a}"] = make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=a)
        )
    for depth in (2, 3):
        for it in (100, 300):
            c[f"hgb_d{depth}_i{it}"] = HistGradientBoostingRegressor(
                max_depth=depth,
                learning_rate=0.05,
                max_iter=it,
                l2_regularization=1.0,
                min_samples_leaf=40,
                random_state=0,
            )
    return c


# ── select ───────────────────────────────────────────────────────────────────


def select() -> None:
    _check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)
    d = panel().dropna(subset=["y"])
    yr = d["entry_date"].dt.year
    tr, va = d[yr <= 2018], d[(yr >= 2019) & (yr <= 2021)]
    print(f"  train {len(tr)}, validation {len(va)}", flush=True)
    scores = {}
    for name, model in _candidates().items():
        model.fit(tr[FEATURES], tr["y"])
        scores[name] = float(spearmanr(model.predict(va[FEATURES]), va["y"])[0])
        print(f"    {name:<22} validation Spearman {scores[name]:+.4f}", flush=True)
    best = max(scores, key=lambda k: scores[k])
    fit = d[yr <= 2021]
    model = _candidates()[best]
    model.fit(fit[FEATURES], fit["y"])
    thr = float(np.quantile(model.predict(fit[FEATURES]), Q_SELL))
    MODEL.write_bytes(pickle.dumps(model))
    frozen = {
        "winner": best,
        "validation_spearman": scores,
        "threshold": thr,
        "features": FEATURES,
        "model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "refit_rows": len(fit),
    }
    FROZEN.write_text(json.dumps(frozen, indent=1))
    print(json.dumps(frozen, indent=1))


# ── test ─────────────────────────────────────────────────────────────────────


def _evaluate(d: pd.DataFrame, model: Any, thr: float, label: str) -> dict[str, Any]:
    d = d.dropna(subset=["y", "rom"]).reset_index(drop=True)
    pred = model.predict(d[FEATURES])
    keys = d["announce_date"].dt.strftime("%Y-%m-%d").to_numpy()
    rho = float(spearmanr(pred, d["y"])[0])
    yv = d["y"].to_numpy()

    def rstat(ix: np.ndarray) -> float:
        j = ix.astype(int)
        return float(spearmanr(pred[j], yv[j])[0])

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(d), dtype=float), keys, rstat, n_boot=N_BOOT, seed=SEED
    )
    sel = pred <= thr
    rom = d["rom"].to_numpy()
    rng = np.random.default_rng(SEED)
    null = np.array(
        [rom[rng.choice(len(rom), int(sel.sum()), replace=False)].mean() for _ in range(N_NULL)]
    )
    x = pd.Series(rom[sel])
    mlo, mhi = cluster_bootstrap_ci(
        x.to_numpy(), keys[sel], lambda v: float(np.mean(v)), n_boot=N_BOOT, seed=SEED
    )
    out = {
        "set": label,
        "n": len(d),
        "n_selected": int(sel.sum()),
        "spearman": rho,
        "spearman_ci": [float(lo), float(hi)],
        "selected_mean_rom": float(x.mean()),
        "selected_mean_ci": [float(mlo), float(mhi)],
        "all_mean_rom": float(rom.mean()),
        "null_p95": float(np.quantile(null, 0.95)),
        "null_pct": float((null < x.mean()).mean()),
        "selected_sharpe": float(x.mean() / x.std(ddof=1)) if len(x) > 1 else float("nan"),
        "selected_dsr": float(deflated_sharpe_ratio(x, n_trials=N_TRIALS)) if len(x) > 2 else 0.0,
        "selected_mean_y": float(yv[sel].mean()),
        "unselected_mean_y": float(yv[~sel].mean()),
    }
    out["pass"] = bool(lo > 0 and x.mean() > out["null_p95"] and x.mean() > 0)
    return out


def test() -> None:
    _check_prereg()
    frozen = json.loads(FROZEN.read_text())
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != frozen["model_sha256"]:
        raise SystemExit("frozen model hash mismatch")
    model = pickle.loads(MODEL.read_bytes())
    p = panel()
    res = {
        "test_megacap_2022_2024": _evaluate(
            p[p["entry_date"].dt.year >= 2022], model, frozen["threshold"], "megacap 2022-2024"
        ),
        "confirm_broad_2025_2026": _evaluate(
            broad(), model, frozen["threshold"], "broad 2025-2026"
        ),
    }
    res["verdict"] = (
        "PASS" if all(v["pass"] for v in res.values() if isinstance(v, dict)) else "FAIL"
    )
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(OUT / "test_result.json", "w"), indent=1, default=str)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.select:
        select()
    if a.test:
        test()


if __name__ == "__main__":
    main()
