"""
wf.py
Walk-forward combined model for the hedged event hold (lane E, alpha hunt 2). Fits heavily
regularised models on ranked point-in-time features, refit each calendar quarter on events whose
outcome was known before the quarter began, predicts that quarter, and scores the out-of-sample
predictions on residual value against a cell-matched (implied-move tercile x tenor, same quarter)
random null. Every scored configuration is appended to trials.csv.

Blocks (fixed before any outcome was read)
------------------------------------------
discovery   test quarters 2016Q1 to 2021Q4 (training expands from 2013)
heldout     test quarters 2022Q1 to 2024Q4 (refused unless freeze_<slug>.md exists)
viewed      test quarters 2025Q1 to 2026Q4 (read by many earlier trials: descriptive only;
            the forensics panel has no rows here, so those features sit at their neutral rank)

Outcome and basis
-----------------
y      hedged hold to expiry, net at the touch (entry at the 15:59 bid), per unit of entry mid
       premium (y = H * m0 / mid0), per trade.
y_ex   y minus the mean of y over events in the same announcement quarter and the same
       implied-move tercile x tenor cell: the residual value a tenor-matched random pick of the
       same cell would not earn. A random selection within cell has y_ex zero in expectation.
y_exs  as y_ex but also within the causal entry half-spread tercile: what is left once the
       known spread effect is held fixed (the spread-gate check).
H      level of the book, net at the touch, per trade on margin m0 = 0.20 x forward + premium.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/wf.py --round r1
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNetCV, RidgeCV
from sklearn.model_selection import TimeSeriesSplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci, per_trade_sharpe  # noqa: E402

warnings.filterwarnings("ignore", category=ConvergenceWarning)

# ── configuration (every number named) ───────────────────────────────────────

TRIALS = HERE / "trials.csv"
OOS = HERE / "oos"
BLOCKS = {"discovery": ("2016Q1", "2021Q4"), "heldout": ("2022Q1", "2024Q4"),
          "viewed": ("2025Q1", "2026Q4")}
MIN_TRAIN = 1000  # events with a known outcome before the first test quarter
TOP_Q = 0.80  # top quintile of prediction
THRESH_LOOKBACK_Q = 4  # quarters of training events whose predictions set the causal cut
WINSOR = (0.01, 0.99)  # training-target winsorisation, training quantiles only
MISS_IND_MIN = 0.05  # add a missingness indicator when training missing share exceeds this
RIDGE_ALPHAS = np.logspace(0, 5, 11)  # chosen inside training by time-ordered CV
CV_SPLITS = 4
EN_L1 = 0.5
GBM = dict(max_depth=2, max_iter=150, learning_rate=0.03, min_samples_leaf=300,
           l2_regularization=1.0, max_features=0.5, random_state=0)
N_NULL = 2000
SEED = 0
FIELDS = ["trial_id", "hypothesis", "mechanism", "block", "N", "effect", "ci_low", "ci_high",
          "t", "null_pct", "basis", "verdict", "n_selected", "share_selected", "ic_pooled",
          "ic_ci_low", "ic_ci_high", "ic_by_year", "effect_spread_neutral", "esn_ci_low",
          "esn_ci_high", "effect_mid", "em_ci_low", "em_ci_high", "excess_by_quintile", "H_selected", "H_sel_ci_low", "H_sel_ci_high", "H_all",
          "sharpe_H_selected", "rho_pred_half_spread", "label"]


# ── data ─────────────────────────────────────────────────────────────────────


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_parquet(HERE / "panel.parquet")
    fm = pd.read_csv(HERE / "feature_map.csv")
    n0 = len(d)
    d = d[d["im_bin"] >= 0].copy()
    d["q"] = d["announce_date"].dt.to_period("Q")
    d["qcell"] = d["q"].astype(str) + "_" + d["cell"].astype(str)
    d["y_ex"] = d["y"] - d.groupby("qcell")["y"].transform("mean")
    d["y_mid"] = d["H_mid"] * d["m0"] / d["mid0"]  # same hold, entry at the mid: no spread paid
    d["ym_ex"] = d["y_mid"] - d.groupby("qcell")["y_mid"].transform("mean")
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    print(f"funnel: {n0} events, {len(d)} with a causal cell; "
          f"quarters {d['q'].min()} to {d['q'].max()}")
    return d, fm


# ── features ─────────────────────────────────────────────────────────────────


def _ecdf(train: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Mid-rank of x within the training values, centred on zero; NaN to the neutral 0."""
    t = np.sort(train[np.isfinite(train)])
    out = np.zeros(x.shape)
    if t.size == 0:
        return out
    ok = np.isfinite(x)
    lo = np.searchsorted(t, x[ok], side="left")
    hi = np.searchsorted(t, x[ok], side="right")
    out[ok] = (lo + hi) / (2.0 * t.size) - 0.5
    return out


def design(tr: pd.DataFrame, te: pd.DataFrame, feats: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Ranked features fitted on training only, plus missingness indicators."""
    xs_tr, xs_te = [], []
    for c in feats:
        a, b = tr[c].to_numpy(float), te[c].to_numpy(float)
        xs_tr.append(_ecdf(a, a))
        xs_te.append(_ecdf(a, b))
        miss = float(np.mean(~np.isfinite(a)))
        if MISS_IND_MIN < miss < 1.0:
            xs_tr.append((~np.isfinite(a)).astype(float) - miss)
            xs_te.append((~np.isfinite(b)).astype(float) - miss)
    return np.column_stack(xs_tr), np.column_stack(xs_te)


def train_target(tr: pd.DataFrame, kind: str) -> np.ndarray:
    """Training target from training outcomes only."""
    col = "y_mid" if kind.startswith("mid_") else "y"
    kind = kind.removeprefix("mid_")
    y = tr[col] - tr.groupby("qcell")[col].transform("mean")
    if kind == "winsor":
        lo, hi = np.nanquantile(y, WINSOR)
        return y.clip(lo, hi).to_numpy(float)
    if kind == "rank":
        return (tr.assign(_y=y).groupby("qcell")["_y"].rank(pct=True) - 0.5).to_numpy(float)
    raise ValueError(kind)


# ── models ───────────────────────────────────────────────────────────────────


def fit_predict(model: str, xtr: np.ndarray, ytr: np.ndarray, xs: list[np.ndarray]) -> list:
    if model == "ridge":
        m = RidgeCV(alphas=RIDGE_ALPHAS, cv=TimeSeriesSplit(CV_SPLITS))
    elif model == "enet":
        m = ElasticNetCV(l1_ratio=EN_L1, alphas=20, cv=TimeSeriesSplit(CV_SPLITS),
                         max_iter=5000, random_state=SEED)
    elif model == "gbm":
        m = HistGradientBoostingRegressor(**GBM)
    elif model == "ens":
        # equal-weight average of the ridge and tree predictions, each standardised by its own
        # training-set predictions so neither scale dominates
        a = fit_predict("ridge", xtr, ytr, [xtr] + xs)
        b = fit_predict("gbm", xtr, ytr, [xtr] + xs)
        za = [(p - a[0].mean()) / a[0].std() for p in a[1:-1]]
        zb = [(p - b[0].mean()) / b[0].std() for p in b[1:-1]]
        return [0.5 * (u + v) for u, v in zip(za, zb, strict=True)] + [a[-1]]
    else:
        raise ValueError(model)
    m.fit(xtr, ytr)
    return [m.predict(x) for x in xs] + [m]


@dataclass
class Config:
    trial_id: int
    slug: str
    hypothesis: str
    mechanism: str
    model: str = "ridge"
    target: str = "winsor"
    groups_in: list[str] | None = None  # None: all groups
    groups_out: list[str] = field(default_factory=list)
    feats_only: list[str] | None = None


def features_for(cfg: Config, fm: pd.DataFrame) -> list[str]:
    if cfg.feats_only is not None:
        return list(cfg.feats_only)
    f = fm
    if cfg.groups_in is not None:
        f = f[f["group"].isin(cfg.groups_in)]
    f = f[~f["group"].isin(cfg.groups_out)]
    return f["feature"].tolist()


def walk_forward(cfg: Config, d: pd.DataFrame, fm: pd.DataFrame, block: str) -> pd.DataFrame:
    feats = features_for(cfg, fm)
    q0, q1 = (pd.Period(x) for x in BLOCKS[block])
    out = []
    coef_log = []
    for q in pd.period_range(q0, q1, freq="Q"):
        te = d[d["q"] == q]
        if te.empty:
            continue
        qs = q.start_time
        tr = d[(d["expiry"] < qs) & (d["announce_date"] < qs)]
        if len(tr) < MIN_TRAIN:
            raise ValueError(f"{cfg.slug} {q}: {len(tr)} training events")
        xtr, xte = design(tr, te, feats)
        ytr = train_target(tr, cfg.target)
        recent = (tr["q"] >= q - THRESH_LOOKBACK_Q).to_numpy()
        p_te, p_tr, m = fit_predict(cfg.model, xtr, ytr, [xte, xtr])
        cut = float(np.quantile(p_tr[recent], TOP_Q))
        # causal half-spread tercile for the spread-neutral read
        hs_cut = np.nanquantile(tr["half_spread"], [1 / 3, 2 / 3])
        o = te[["ticker", "entry_date", "announce_date", "q", "qcell", "cell", "y", "y_ex", "H",
                "half_spread", "ym_ex"]].copy()
        o["pred"] = p_te
        o["sel"] = p_te > cut
        o["hs_t"] = np.searchsorted(hs_cut, te["half_spread"].to_numpy(float))
        o["n_train"] = len(tr)
        out.append(o)
        if cfg.model in ("ridge", "enet", "ens"):
            coef_log.append((str(q), getattr(m, "alpha_", np.nan)))
    res = pd.concat(out, ignore_index=True)
    k = res["qcell"] + "_" + res["hs_t"].astype(str)
    res["y_exs"] = res["y"] - res.groupby(k)["y"].transform("mean")
    OOS.mkdir(exist_ok=True)
    res.to_parquet(OOS / f"{cfg.trial_id}_{cfg.slug}_{block}.parquet", index=False)
    if coef_log:
        al = [a for _, a in coef_log]
        print(f"   inner-CV alpha: median {np.median(al):.3g}, range {min(al):.3g} to {max(al):.3g}")
    return res


# ── scoring ──────────────────────────────────────────────────────────────────


def _ci_mean(v: np.ndarray, dates: np.ndarray):
    return date_clustered_ci(v, dates, np.mean)


def cell_null(y: np.ndarray, sel: np.ndarray, strata: np.ndarray, n: int = N_NULL) -> float:
    """Percentile of the selection's mean y among same-count random picks within each stratum."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(strata == u) for u in np.unique(strata)]
    counts = [int(sel[g].sum()) for g in groups]
    obs = y[sel].mean()
    draws = np.empty(n)
    for b in range(n):
        idx = np.concatenate([rng.choice(g, k, replace=False) for g, k in
                              zip(groups, counts, strict=True) if k])
        draws[b] = y[idx].mean()
    return float(100.0 * (draws < obs).mean())


def score(res: pd.DataFrame) -> dict:
    r: dict = {}
    dates = res["announce_date"].to_numpy()
    res = res.copy()
    res["pr"] = res.groupby("q")["pred"].rank(pct=True)
    pr, yx = res["pr"].to_numpy(float), res["y_ex"].to_numpy(float)

    def _ic(idx: np.ndarray) -> float:
        i = idx.astype(int)
        return float(spearmanr(pr[i], yx[i]).statistic)

    ic = date_clustered_ci(np.arange(len(res), dtype=float), dates, _ic)
    r.update(ic_pooled=ic.point, ic_ci_low=ic.low, ic_ci_high=ic.high)
    qic = res.groupby("q").apply(lambda g: spearmanr(g["pred"], g["y_ex"]).statistic,
                                 include_groups=False)
    by_year = qic.groupby(qic.index.year).mean()
    r["ic_by_year"] = "; ".join(f"{y}:{v:+.3f}" for y, v in by_year.items())
    sel = res["sel"].to_numpy(bool)
    r["N"], r["n_selected"] = len(res), int(sel.sum())
    r["share_selected"] = sel.mean()
    if sel.sum() < 20:
        raise ValueError(f"only {int(sel.sum())} selected")
    e = _ci_mean(yx[sel], dates[sel])
    se = (e.high - e.low) / (2 * 1.96)
    r.update(effect=e.point, ci_low=e.low, ci_high=e.high, t=e.point / se)
    r["null_pct"] = cell_null(res["y"].to_numpy(float), sel, res["qcell"].to_numpy())
    em = _ci_mean(res["ym_ex"].to_numpy(float)[sel], dates[sel])
    r.update(effect_mid=em.point, em_ci_low=em.low, em_ci_high=em.high)
    pq = np.ceil(res["pr"] * 5).clip(1, 5)
    r["excess_by_quintile"] = "; ".join(
        f"Q{int(k)}:{g['y_ex'].mean():+.3f}|{g['ym_ex'].mean():+.3f}" for k, g in res.groupby(pq))
    es = _ci_mean(res["y_exs"].to_numpy(float)[sel], dates[sel])
    r.update(effect_spread_neutral=es.point, esn_ci_low=es.low, esn_ci_high=es.high)
    h = _ci_mean(res["H"].to_numpy(float)[sel], dates[sel])
    r.update(H_selected=h.point, H_sel_ci_low=h.low, H_sel_ci_high=h.high,
             H_all=float(res["H"].mean()), sharpe_H_selected=per_trade_sharpe(res.loc[sel, "H"]))
    r["rho_pred_half_spread"] = float(spearmanr(res["pr"], res["half_spread"],
                                                nan_policy="omit").statistic)
    yr = res.assign(yr=res["announce_date"].dt.year)
    r["sel_by_year"] = yr[yr["sel"]].groupby("yr")["y_ex"].agg(["size", "mean"]).round(4)
    return r


def report(cfg: Config, block: str, r: dict, label: str) -> None:
    passed = r["ci_low"] > 0 and r["null_pct"] >= 95 and r["ic_ci_low"] > 0 and (
        block == "discovery" or r["t"] >= 3)
    r["verdict"] = "pass" if passed else "fail"
    print(f"[{cfg.trial_id} {cfg.slug} | {block}] N {r['N']}, selected {r['n_selected']} "
          f"({r['share_selected']:.1%})\n"
          f"   IC pooled {r['ic_pooled']:+.4f} [{r['ic_ci_low']:+.4f}, {r['ic_ci_high']:+.4f}]; "
          f"by year {r['ic_by_year']}\n"
          f"   top-quintile excess y (per unit premium, net touch, vs same-quarter cell) "
          f"{r['effect']:+.4f} [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] t {r['t']:+.2f}, "
          f"null pct {r['null_pct']:.1f}\n"
          f"   spread-neutral excess {r['effect_spread_neutral']:+.4f} [{r['esn_ci_low']:+.4f}, "
          f"{r['esn_ci_high']:+.4f}]; excess at mid {r['effect_mid']:+.4f} [{r['em_ci_low']:+.4f}, "
          f"{r['em_ci_high']:+.4f}]\n"
          f"   excess by prediction quintile (touch|mid) {r['excess_by_quintile']}\n"
          f"   rank corr(pred, half-spread) {r['rho_pred_half_spread']:+.3f}\n"
          f"   level H (on m0, net touch) selected {r['H_selected']:+.4f} [{r['H_sel_ci_low']:+.4f},"
          f" {r['H_sel_ci_high']:+.4f}] vs all {r['H_all']:+.4f}; per-trade Sharpe selected "
          f"{r['sharpe_H_selected']:+.3f}\n"
          f"   selected excess by year: "
          + ", ".join(f"{i}:{int(row['size'])}/{row['mean']:+.3f}"
                      for i, row in r['sel_by_year'].iterrows())
          + f"\n   -> {r['verdict'].upper()} ({label})")
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        row = {k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}
        row.update(trial_id=cfg.trial_id, hypothesis=f"{cfg.slug}: {cfg.hypothesis}",
                   mechanism=cfg.mechanism, block=f"{block} {'-'.join(BLOCKS[block])}",
                   basis="effect: mean y_ex of top-quintile picks, hedged hold to expiry, net at "
                         "touch, per unit entry mid premium, per trade; H on m0", label=label)
        w.writerow(row)


def run(cfg: Config, d: pd.DataFrame, fm: pd.DataFrame, block: str, label: str = "exploratory"):
    if block == "heldout" and not (HERE / f"freeze_{cfg.slug}.md").exists():
        raise PermissionError(f"held-out refused: no freeze_{cfg.slug}.md")
    print(f"\n== trial {cfg.trial_id} {cfg.slug} on {block}: {len(features_for(cfg, fm))} "
          f"features, model {cfg.model}, target {cfg.target}")
    res = walk_forward(cfg, d, fm, block)
    r = score(res)
    report(cfg, block, r, label)
    return res, r


# ── slates ───────────────────────────────────────────────────────────────────

SLATES: dict[str, Callable[[], list[tuple[Config, str]]]] = {}


def slate(name: str):
    def deco(fn):
        SLATES[name] = fn
        return fn
    return deco


@slate("r1")
def _r1() -> list[tuple[Config, str]]:
    return [
        (Config(1901, "ridge_all", "ridge on all 184 ranked features predicts cell residual value",
                "many weak pre-entry signals that failed one at a time add up under shrinkage",
                "ridge"), "discovery"),
        (Config(1902, "enet_all", "elastic net (l1 0.5) on all features",
                "a sparse subset of features carries the residual value", "enet"), "discovery"),
        (Config(1903, "gbm_all", "depth-2 boosted trees on all features",
                "residual value sits in interactions (richness only where quotes are tight)",
                "gbm"), "discovery"),
        (Config(1904, "ridge_noncost", "ridge on all features except the cost group",
                "information beyond spread, size and liquidity predicts residual value", "ridge",
                groups_out=["cost"]), "discovery"),
    ]



@slate("r2")
def _r2() -> list[tuple[Config, str]]:
    return [
        (Config(1905, "ridge_mid", "ridge on all features, trained on the at-mid hold",
                "with no spread in the target, shrinkage pools event-level mispricing signals",
                "ridge", target="mid_winsor"), "discovery"),
        (Config(1906, "gbm_mid", "depth-2 boosted trees on all features, trained at the mid",
                "interactions carry residual value beyond the spread", "gbm",
                target="mid_winsor"), "discovery"),
        (Config(1907, "gbm_noncost", "depth-2 boosted trees without the cost group",
                "the trees' at-mid excess in 1903 comes from non-cost information", "gbm",
                groups_out=["cost"]), "discovery"),
        (Config(1908, "gbm_mid_noncost", "boosted trees, no cost group, trained at the mid",
                "non-cost information predicts residual value with the spread fully removed",
                "gbm", target="mid_winsor", groups_out=["cost"]), "discovery"),
        (Config(1909, "gbm_cost_only", "boosted trees on the cost group alone (reference)",
                "the spread gate: tight, liquid events keep more of the premium at the touch",
                "gbm", groups_in=["cost"]), "discovery"),
    ]


@slate("r3")
def _r3() -> list[tuple[Config, str]]:
    """Decomposition of the at-mid candidate (1908): each non-cost group alone, same learner."""
    mech = {
        "surface": "15:59 surface shape (term, skew, jump share) prices the event move imperfectly",
        "history": "the name's own past moves and past realised/implied anchor the event",
        "price": "the stock's pre-event path (run-up, realised vol) forecasts the reaction",
        "fundamentals": "characteristics and filings flag uncertain reports",
        "peers": "peers that already reported reveal the shock before the name does",
        "macro": "market state on the eve changes how much of the premium is kept",
        "calendar": "schedule facts (tenor, weekday, holidays, crowding) shift the hold's value",
    }
    return [
        (Config(1910 + i, f"gbm_mid_{g}", f"boosted trees at the mid on the {g} group alone", m,
                "gbm", target="mid_winsor", groups_in=[g]), "discovery")
        for i, (g, m) in enumerate(mech.items())
    ]


@slate("r4")
def _r4() -> list[tuple[Config, str]]:
    ev = ["surface", "price", "history"]
    return [
        (Config(1917, "ridge_mid_noncost", "ridge at the mid without the cost group",
                "the linear half of the ensemble; non-cost information at the mid", "ridge",
                target="mid_winsor", groups_out=["cost"]), "discovery"),
        (Config(1918, "gbm_mid_event", "boosted trees at the mid on surface, price and history "
                "(discovery-derived from 1910-1916)", "the event-pricing groups carry the signal "
                "and the other groups add noise", "gbm", target="mid_winsor", groups_in=ev),
         "discovery"),
        (Config(1919, "ens_mid_event", "ridge plus trees averaged, at the mid, on surface, price "
                "and history (discovery-derived)", "averaging two learners on the event-pricing "
                "groups cuts model variance on a small panel", "ens", target="mid_winsor",
                groups_in=ev), "discovery"),
        (Config(1920, "ens_mid_noncost", "ridge plus trees averaged, at the mid, all non-cost "
                "groups (discovery-derived)", "averaging two learners cuts model variance; no "
                "group restriction read off the decomposition", "ens", target="mid_winsor",
                groups_out=["cost"]), "discovery"),
    ]


FROZEN = dict(model="gbm", target="mid_winsor", groups_out=["cost"])  # freeze_gbm_mid_noncost.md


@slate("r5")
def _r5() -> list[tuple[Config, str]]:
    hyp = "frozen 1908: boosted trees at the mid on all non-cost groups"
    mech = "non-cost pre-entry information predicts residual value with the spread removed"
    return [(Config(1921, "gbm_mid_noncost", hyp, mech, **FROZEN), "heldout")]


@slate("r5v")
def _r5v() -> list[tuple[Config, str]]:
    hyp = "frozen 1908 on the viewed 2025-26 block (no forensics rows)"
    mech = "as 1921; descriptive only"
    return [(Config(1922, "gbm_mid_noncost", hyp, mech, **FROZEN), "viewed")]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True, choices=sorted(SLATES))
    a = ap.parse_args()
    d, fm = load()
    for cfg, block in SLATES[a.round]():
        run(cfg, d, fm, block, "descriptive" if block == "viewed" else "exploratory")


if __name__ == "__main__":
    main()
