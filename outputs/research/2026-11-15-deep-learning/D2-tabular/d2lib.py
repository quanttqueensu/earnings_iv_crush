"""
d2lib.py
Lane D2 (tabular control), numpy side: the predictive densities of H_net in % of m0 under a
Gaussian-mixture or Student-t head on the Yeo-Johnson loss-ratio scale, the Jacobian, the
predictive mean by deterministic quadrature, the data assembly for real and synthetic runs, the
fold definitions, and the selected-book comparators.

Scale. The network models z = yj(-h / U, k) with ``h`` the outcome in % of m0 and ``U`` the
15:59 premium in % of m0, the transform of the L4 champion (``online_bayes.yj``, k = 0). The
density of ``h`` is

    log p_H(h) = log p_z(yj(-h / U)) + yj_logderiv(-h / U, k) - log U,

as in ``online_bayes.run_online``'s transformed score. Under a Gaussian or Gaussian-mixture z
the mean of h is finite and is computed by Gauss-Legendre quadrature on each side of z = 0, the
branch point of ``yj_inv``; under a Student-t z it is infinite and is never computed.

Usage
-----
    import d2lib; ev = d2lib.load_real(heldout=False)   # development rows only
    ev = d2lib.synthetic(n=3000, seed=0)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow  # noqa: F401  (pyarrow must load before torch on this machine, or reads crash)
import pyarrow.parquet  # noqa: F401
from scipy.special import gammaln, logsumexp, ndtr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
L4_DIR = ROOT / "outputs" / "research" / "2026-11-14-slate-tests" / "L4-bayes"
sys.path.append(str(L4_DIR))  # appended: L4 has its own score_heldout.py

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    log_block_view,
    matched_random_null,
)

D0 = HERE.parent / "D0-surface"
TARGETS = D0 / "targets.parquet"
L4_INPUTS = D0 / "l4_inputs.parquet"
L4_SCORES = D0 / "l4_scores.parquet"
READY = D0 / "TARGETS_READY.txt"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
KEYS = ["ticker", "entry_date"]
FEATURES = [*ob.FEATURES, "name_effect_at_entry"]
YJ_POWER = C.ONLINE_BAYES_L4_MODEL.yj_power  # the L4 champion's transform, k = 0
PCT = C.ONLINE_BAYES.pct_per_unit  # fraction of m0 to % of m0
DEV_YEARS = (2016, 2017, 2018)
HELDOUT_BLOCK = "2019-24"
EXPLORATORY_BLOCK = "2025-26"
DEV_LAST = pd.Timestamp("2019-01-01")  # rows entered on or after this are held out
# Gauss-Legendre nodes per side of z = 0 and the standard-normal window. 128 nodes integrate a
# Gaussian-weighted smooth integrand over a window of 30 sd to about 1e-12 (tested against
# adaptive quadrature); 12 sd leaves Gaussian mass below 1e-32 outside.
QUAD_NODES = 128
QUAD_SD = 12.0
NULL_PASS_PCT = 95.0
# Input groups for the occlusion read, by the channel each carries.
OCCLUSION: dict[str, list[str]] = {
    "spread": ["log_half_spread"],
    "implied_move": ["log_implied_move"],
    "term_spread": ["iv_term_spread", "iv_term_spread_missing"],
    "depth": ["log_depth"],
    "tenor": ["log1p_dte"],
    "forward": ["log_forward"],
    "name_effect": ["name_effect_at_entry"],
}
OUTCOME_FAMILY = "hedged_hold_H_net"
FEATURE_FAMILY = "d2_tabular_mdn_l4_declared"


# ── densities on the transformed and original scales ──────────────────────────


def gm_logpdf(z: np.ndarray, logw: np.ndarray, mu: np.ndarray, sig: np.ndarray) -> np.ndarray:
    """Log density of a Gaussian mixture at ``z``; parameters have shape (n, K)."""
    z = np.asarray(z, float)[:, None]
    lp = logw - 0.5 * np.log(2 * np.pi) - np.log(sig) - 0.5 * ((z - mu) / sig) ** 2
    return logsumexp(lp, axis=1)


def t_logpdf(z: np.ndarray, mu: np.ndarray, sig: np.ndarray, df: np.ndarray) -> np.ndarray:
    """Log density of a Student-t location-scale law at ``z``; parameters have shape (n,)."""
    u = (np.asarray(z, float) - mu) / sig
    return (
        gammaln((df + 1) / 2)
        - gammaln(df / 2)
        - 0.5 * np.log(df * np.pi)
        - np.log(sig)
        - (df + 1) / 2 * np.log1p(u * u / df)
    )


def to_z(h: np.ndarray, unit: np.ndarray, k: float = YJ_POWER) -> np.ndarray:
    """z = yj(-h / U, k)."""
    return ob.yj(-np.asarray(h, float) / np.asarray(unit, float), k)


def log_jacobian(h: np.ndarray, unit: np.ndarray, k: float = YJ_POWER) -> np.ndarray:
    """log |dz / dh| at ``h``: yj_logderiv(-h / U) - log U."""
    x = -np.asarray(h, float) / np.asarray(unit, float)
    return ob.yj_logderiv(x, k) - np.log(unit)


def log_score_h(logpz: np.ndarray, h: np.ndarray, unit: np.ndarray, k: float = YJ_POWER):
    """Log density of ``h`` (% of m0) from the log density of its z."""
    return np.asarray(logpz, float) + log_jacobian(h, unit, k)


# ── predictive moments by quadrature ─────────────────────────────────────────


# Computed at import, before any torch import: on this machine numpy's LAPACK must initialise
# before torch's libraries load, or the eigen-solver behind leggauss crashes.
_GL_X, _GL_W = np.polynomial.legendre.leggauss(QUAD_NODES)


def _side_integral(
    a: np.ndarray, b: np.ndarray, mu: np.ndarray, sig: np.ndarray, power: int, k: float
) -> np.ndarray:
    """Integral over u in [a, b] of yj_inv(mu + sig u)^power phi(u) du, elementwise."""
    x, w = _GL_X, _GL_W
    half = (b - a)[..., None] / 2
    mid = (b + a)[..., None] / 2
    u = mid + half * x
    z = mu[..., None] + sig[..., None] * u
    with np.errstate(over="ignore", invalid="ignore"):
        f = ob.yj_inv(z.ravel(), k).reshape(z.shape) ** power
    phi = np.exp(-0.5 * u * u) / np.sqrt(2 * np.pi)
    val = (half * w * f * phi).sum(axis=-1)
    return np.where(b > a, val, 0.0)


def gm_x_moments(
    logw: np.ndarray, mu: np.ndarray, sig: np.ndarray, k: float = YJ_POWER
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """E[x], E[x^2] and P(x < 0) for x = yj_inv(z), z a Gaussian mixture (shape (n, K)).

    Each component is integrated in its standard-normal coordinate u on two intervals split
    at the branch point z = 0 (u = c = -mu / sig): [-12, c] and [c, max(c, sig) + 12]. The upper
    window is shifted by sig because under k = 0 the integrand exp(sig u) phi(u) peaks at u =
    sig; with k > 0 the growth is polynomial and the window is wider than needed.
    """
    mu, sig = np.asarray(mu, float), np.asarray(sig, float)
    w = np.exp(np.asarray(logw, float))
    c = -mu / sig
    lo = np.full_like(c, -QUAD_SD)
    b_neg = np.clip(c, -QUAD_SD, None)
    a_pos = np.clip(c, -QUAD_SD, None)
    b_pos = np.maximum(a_pos, sig) + QUAD_SD
    m1 = _side_integral(lo, b_neg, mu, sig, 1, k) + _side_integral(a_pos, b_pos, mu, sig, 1, k)
    m2 = _side_integral(lo, b_neg, mu, sig, 2, k) + _side_integral(a_pos, b_pos, mu, sig, 2, k)
    p_neg = ndtr(c)  # P(z < 0) = P(x < 0)
    return (w * m1).sum(axis=1), (w * m2).sum(axis=1), (w * p_neg).sum(axis=1)


def gm_h_summary(
    logw: np.ndarray, mu: np.ndarray, sig: np.ndarray, unit: np.ndarray, k: float = YJ_POWER
) -> pd.DataFrame:
    """Predictive mean, sd and P(h > 0) of h = -U yj_inv(z), by quadrature."""
    ex, ex2, p_neg = gm_x_moments(logw, mu, sig, k)
    unit = np.asarray(unit, float)
    mean = -unit * ex
    var = unit * unit * (ex2 - ex * ex)
    if (~np.isfinite(mean)).any():
        raise FloatingPointError(f"{int((~np.isfinite(mean)).sum())} non-finite quadrature means")
    return pd.DataFrame({"pred_mean": mean, "pred_sd": np.sqrt(np.maximum(var, 0)), "p_pos": p_neg})


# ── real data ────────────────────────────────────────────────────────────────


def _check_ready() -> None:
    if not READY.exists():
        raise FileNotFoundError(f"{READY} missing: D0 has not released the targets")


def log_view(period: str, note: str, kind: str = "trial", outcome: str = OUTCOME_FAMILY) -> None:
    """Record a block view with a UTC clock stamp taken now, at load time."""
    log_block_view(
        BLOCKS_VIEWED,
        panel="D0_targets_base_corrected",
        period=period,
        outcome_family=outcome,
        feature_family=FEATURE_FAMILY,
        viewed_by=f"D2 {note}",
        kind=kind,
    )


def load_real(
    heldout: bool,
    note: str = "development",
    block: str | None = None,
    max_entry: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per event: keys, dates, outcome (% of m0), U, residual value, features, L4 scores.

    With ``heldout`` False, outcomes, residual values and L4 scores are read only for events
    entered before 2019 (parquet filters at read time); later rows carry NaN outcomes and are
    never scored. With ``heldout`` True (the frozen scorer only) rows entered before
    ``max_entry`` are read (every row when it is None), and the view of ``block`` is logged.
    """
    _check_ready()
    if heldout:
        if block is None:
            raise ValueError("a held-out load names its block")
        log_view(block, note)
        cut = max_entry
    else:
        cut = DEV_LAST
    log_view("2013-18", note)
    flt = None if cut is None else [("entry_date", "<", cut)]
    import l4lib  # the L4 design, imported and not edited

    cfg = C.ONLINE_BAYES_L4_MODEL
    d = l4lib.load()
    X, usable, _raw = l4lib.design(d, cfg)
    feats = pd.DataFrame(X[:, 1:], columns=list(ob.FEATURES))
    base = d[KEYS + ["expiry", "announce_date", "block", "half_spread"]].copy()
    base = pd.concat([base, feats], axis=1)
    base["l4_usable"] = usable
    tg = pd.read_parquet(TARGETS, filters=flt)
    li = pd.read_parquet(L4_INPUTS)
    sc = pd.read_parquet(L4_SCORES, filters=flt)
    for f in (tg, li, sc):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    ev = _join(base, tg, li, sc, heldout)
    return ev


def _join(
    base: pd.DataFrame, tg: pd.DataFrame, li: pd.DataFrame, sc: pd.DataFrame, heldout: bool
) -> pd.DataFrame:
    """Join D0's targets, L4 inputs and L4 scores one to one on the keys.

    ``U`` is D0's ``U_pct`` (the premium in % of m0, L4's ``unit``); ``h`` and ``rv`` are
    ``H_net`` and ``residual_value`` times 100 (% of m0). L4's scores are D0's ``m_log_score``
    (champion) and ``b_log_score`` (baseline), already in % of m0 units with the Jacobian.
    """
    tcols = KEYS + ["H_net", "U_pct", "residual_value", "expiry", "announce_date", "target_ok"]
    miss = [c for c in tcols if c not in tg.columns]
    if miss:
        raise KeyError(f"targets.parquet lacks {miss}")
    t = tg[tcols].rename(columns={"expiry": "expiry_t", "announce_date": "ann_t", "U_pct": "U"})
    ev = base.merge(t, on=KEYS, how="left", validate="1:1")
    got = ev["expiry_t"].notna()
    for a, b in (("expiry_t", "expiry"), ("ann_t", "announce_date")):
        if not (pd.to_datetime(ev.loc[got, a]).dt.normalize() == ev.loc[got, b]).all():
            raise ValueError(f"{b} disagrees between targets.parquet and the L4 design")
    ev = ev.drop(columns=["expiry_t", "ann_t"])
    ev = ev.merge(
        li[KEYS + ["m_name_effect_at_entry", "m_n_settled_at_entry", "U_pct"]].rename(
            columns={"m_name_effect_at_entry": "name_effect_at_entry", "U_pct": "U_li"}
        ),
        on=KEYS,
        how="left",
        validate="1:1",
    )
    both = np.isfinite(ev["U"]) & np.isfinite(ev["U_li"])
    if not np.allclose(ev.loc[both, "U"], ev.loc[both, "U_li"]):
        raise ValueError("U_pct disagrees between targets.parquet and l4_inputs.parquet")
    ev = ev.drop(columns="U_li")
    scols = ["m_log_score", "b_log_score", "m_scored", "b_scored", "m_pit", "b_pit"]
    ev = ev.merge(
        sc[KEYS + scols].rename(columns={"m_log_score": "l4_model_log_score",
                                         "b_log_score": "l4_base_log_score"}),
        on=KEYS, how="left", validate="1:1",
    )  # fmt: skip
    ev["h"] = ev["H_net"] * PCT
    ev["rv"] = ev["residual_value"] * PCT
    ev["year"] = ev["entry_date"].dt.year
    if not heldout:
        late = ev["entry_date"] >= DEV_LAST
        held = ev.loc[late, ["h", "rv", "l4_model_log_score", "l4_base_log_score"]]
        if held.notna().any().any():
            raise AssertionError("a held-out outcome or score was loaded in development mode")
    print(
        f"[d2 load] {len(ev)} events; l4 usable {int(ev['l4_usable'].sum())}; "
        f"H_net finite {int(ev['h'].notna().sum())} (target_ok False "
        f"{int((ev['target_ok'] == False).sum())}); U finite "  # noqa: E712
        f"{int(np.isfinite(ev['U']).sum())}; name effect finite "
        f"{int(np.isfinite(ev['name_effect_at_entry']).sum())}"
    )
    return ev


def scored_set(ev: pd.DataFrame, rows: np.ndarray, d2_score: np.ndarray) -> np.ndarray:
    """Identical-event mask for a comparison: L4 champion and baseline scored with finite log
    scores (as D0 and L4's score_block define it), and a finite D2 score."""
    e = ev.iloc[rows]
    return (
        e["m_scored"].eq(True).to_numpy(bool)
        & e["b_scored"].eq(True).to_numpy(bool)
        & np.isfinite(e["l4_model_log_score"].to_numpy(float))
        & np.isfinite(e["l4_base_log_score"].to_numpy(float))
        & np.isfinite(np.asarray(d2_score, float))
    )


# ── synthetic data ───────────────────────────────────────────────────────────


def synthetic(n: int = 3000, seed: int = 0, effect: float = 0.5) -> pd.DataFrame:
    """Synthetic events with a planted nonlinear feature effect on the z location and scale.

    z = 0.15 + effect (0.4 x1 + 0.3 x2^2 - 0.3) + 0.6 exp(0.3 x3) eps, eps a two-component
    Gaussian mixture; h = -U yj_inv(z). Dates are spread over 2013-04 to 2018-12, expiries 1 to
    10 trading weeks later. Every column the fold runner reads is present; L4 scores are those
    of a constant Gaussian fitted on all rows (a deliberately weak benchmark).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2013-04-01", "2018-12-31")
    ent = pd.to_datetime(np.sort(rng.choice(dates, size=n)))
    exp = ent + pd.to_timedelta(rng.integers(3, 60, size=n), unit="D")
    Xf = rng.standard_normal((n, len(FEATURES)))
    unit = np.exp(rng.normal(np.log(8.0), 0.5, size=n))
    loc = 0.15 + effect * (0.4 * Xf[:, 0] + 0.3 * Xf[:, 1] ** 2 - 0.3)
    scale = 0.6 * np.exp(0.3 * effect * Xf[:, 2])
    comp = rng.random(n) < 0.8
    eps = np.where(comp, rng.normal(0, 0.8, n), rng.normal(0.8, 1.6, n))
    z = loc + scale * eps
    h = -unit * ob.yj_inv(z, YJ_POWER)
    ev = pd.DataFrame(Xf, columns=FEATURES)
    ev["ticker"] = [f"S{i % 400:03d}" for i in range(n)]
    ev["entry_date"] = ent
    ev["expiry"] = exp
    ev["announce_date"] = ent
    ev["block"] = "2013-18"
    ev["half_spread"] = np.exp(rng.normal(-2.5, 0.5, n))
    ev["l4_usable"] = True
    ev["h"] = h
    ev["U"] = unit
    ev["rv"] = h - np.nanmean(h)
    ev["year"] = ev["entry_date"].dt.year
    zz = to_z(h, unit)
    m, s = zz.mean(), zz.std()
    lp = -0.5 * np.log(2 * np.pi) - np.log(s) - 0.5 * ((zz - m) / s) ** 2
    ev["l4_model_log_score"] = log_score_h(lp, h, unit)
    ev["l4_base_log_score"] = ev["l4_model_log_score"]
    ev["m_scored"] = True
    ev["b_scored"] = True
    return ev


# ── folds ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fold:
    """One fit: train on expiry < origin, early-stop on entries in [origin - 1y, origin)."""

    origin: pd.Timestamp
    score_from: pd.Timestamp
    score_to: pd.Timestamp
    label: str


def dev_folds() -> list[Fold]:
    return [
        Fold(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-01-01"),
             pd.Timestamp(f"{y + 1}-01-01"), str(y))  # fmt: skip
        for y in DEV_YEARS
    ]


def quarterly_folds(first: str, last_exclusive: str) -> list[Fold]:
    qs = pd.date_range(first, last_exclusive, freq="QS")
    return [
        Fold(q, q, q + pd.offsets.QuarterBegin(startingMonth=1), f"{q.year}Q{q.quarter}")
        for q in qs
        if q < pd.Timestamp(last_exclusive)
    ]


def fit_ok(ev: pd.DataFrame) -> np.ndarray:
    """Rows with every input and the transformed outcome defined (a training candidate)."""
    X = ev[FEATURES].to_numpy(float)
    u = ev["U"].to_numpy(float)
    h = ev["h"].to_numpy(float)
    return (
        ev["l4_usable"].to_numpy(bool)
        & np.isfinite(X).all(axis=1)
        & np.isfinite(u)
        & (u > 0)
        & np.isfinite(h)
    )


def input_ok(ev: pd.DataFrame) -> np.ndarray:
    """Rows the network can predict (outcome not needed)."""
    X = ev[FEATURES].to_numpy(float)
    u = ev["U"].to_numpy(float)
    return ev["l4_usable"].to_numpy(bool) & np.isfinite(X).all(axis=1) & np.isfinite(u) & (u > 0)


def fold_masks(ev: pd.DataFrame, f: Fold) -> dict[str, np.ndarray]:
    """Train, early-stopping and score masks; raises if a training row expires on or after
    the origin."""
    ok = fit_ok(ev)
    exp = ev["expiry"].to_numpy("datetime64[ns]")
    ent = ev["entry_date"].to_numpy("datetime64[ns]")
    o = np.datetime64(f.origin)
    full = ok & (exp < o)
    val = full & (ent >= np.datetime64(f.origin - pd.DateOffset(years=1)))
    tr = full & ~val
    score = input_ok(ev) & (ent >= np.datetime64(f.score_from)) & (ent < np.datetime64(f.score_to))
    if (exp[full] >= o).any():
        raise AssertionError("a training row expires on or after the refit origin")
    for nm, m in (("train", tr), ("val", val), ("score", score)):
        if m.sum() == 0:
            raise ValueError(f"fold {f.label}: empty {nm} set")
    return {"train": tr, "val": val, "full": full, "score": score}


# ── comparators ──────────────────────────────────────────────────────────────


def tight_per_date(
    sel: np.ndarray, spread: np.ndarray, dates: np.ndarray, tickers: np.ndarray
) -> np.ndarray:
    """On each date, the same number of events as ``sel`` takes, with the smallest spreads.

    Ties break by ticker. A NaN spread raises: the screen must not silently drop events.
    """
    sel = np.asarray(sel, bool)
    spread = np.asarray(spread, float)
    if (~np.isfinite(spread)).any():
        raise ValueError(f"{int((~np.isfinite(spread)).sum())} events have no 15:59 spread")
    out = np.zeros(sel.size, bool)
    df = pd.DataFrame({"d": dates, "s": spread, "t": tickers, "i": np.arange(sel.size)})
    df = df.sort_values(["d", "s", "t"], kind="stable")
    n_by = pd.Series(sel).groupby(np.asarray(dates)).sum()
    for d, g in df.groupby("d", sort=False):
        k = int(n_by.get(d, 0))
        if k:
            out[g["i"].to_numpy()[:k]] = True
    return out


def _ci_list(c: Any) -> list[float]:
    return [round(float(c.point), 4), round(float(c.low), 4), round(float(c.high), 4)]


def diff_ci(v: np.ndarray, a: np.ndarray, b: np.ndarray, keys: np.ndarray) -> Any:
    """mean(v[a]) - mean(v[b]), date-clustered by resampling event indices by cluster."""
    v = np.asarray(v, float)

    def stat(idx: np.ndarray) -> float:
        i = idx.astype(int)
        x, y = v[i][a[i]], v[i][b[i]]
        return float(x.mean() - y.mean()) if x.size and y.size else float("nan")

    return date_clustered_ci(np.arange(v.size, dtype=float), keys, stat)


def book(
    outcome: np.ndarray, sel: np.ndarray, tight: np.ndarray, keys: np.ndarray, label: str
) -> dict[str, Any]:
    """The selected book against the unconditional book, the tight screen and the null."""
    v = np.asarray(outcome, float)
    if (~np.isfinite(v)).any():
        raise ValueError(f"{label}: {int((~np.isfinite(v)).sum())} non-finite outcomes in pool")
    allm = np.ones(v.size, bool)
    out: dict[str, Any] = {"n_pool": int(v.size), "n_selected": int(sel.sum())}
    out["unconditional"] = _ci_list(date_clustered_ci(v, keys, np.mean))
    if sel.sum() == 0 or sel.all():
        out["note"] = "rule selects nothing or everything; comparators undefined"
        return out
    out["selected"] = _ci_list(date_clustered_ci(v[sel], keys[sel], np.mean))
    out["tight_screen"] = _ci_list(date_clustered_ci(v[tight], keys[tight], np.mean))
    out["sel_minus_tight"] = _ci_list(diff_ci(v, sel, tight, keys))
    out["sel_minus_unsel"] = _ci_list(diff_ci(v, sel, ~sel, keys))
    out["sel_minus_all"] = _ci_list(diff_ci(v, sel, allm, keys))
    nl = matched_random_null(v, sel, np.mean)
    out["null_percentile"] = round(nl.percentile, 2)
    out["null_median"] = round(float(np.median(nl.null)), 4)
    out["overlap_with_tight"] = round(float((sel & tight).sum() / sel.sum()), 4)
    out["beats_tight"] = bool(out["sel_minus_tight"][1] > 0)
    out["beats_null"] = bool(nl.percentile >= NULL_PASS_PCT)
    return out
