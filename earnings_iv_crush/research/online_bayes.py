"""
online_bayes.py
Sequential Bayesian regression of the hedged-hold P&L on 15:59 features, updated one settled
trade at a time, with a name-level random intercept, discounting, Student-t predictives, a book
gauge and a forward mode that reads settled paper trades.

Model
-----
Event ``j`` has standardised 15:59 features ``x_j`` (first entry the intercept), name ``n(j)``
and a known variance weight ``v_j`` fixed at entry. Its outcome is

    y_j = x_j' beta + u_{n(j)} + e_j,          e_j ~ N(0, sigma^2 v_j),
    u_n ~ N(0, kappa_u sigma^2),   beta | sigma^2 ~ N(m, sigma^2 C_beta),   sigma^2 ~ IG(a, b).

Stacking ``theta = (beta, u_1, u_2, ...)`` with the design ``F_j = (x_j, e_{n(j)})`` gives a
normal-inverse-gamma (NIG) regression with every covariance in units of ``sigma^2``. One
observation updates it in closed form (West and Harrison 1997, chapters 3 and 4):

    f = F'm,  Q = F'CF + v,  e = y - f,  A = CF / Q,
    m <- m + A e,  C <- C - A A' Q,  a <- a + 1/2,  b <- b + e^2 / (2 Q),

and the one-step predictive is Student-t with ``2a`` degrees of freedom, location ``f`` and
scale ``sqrt((b / a) Q)``. A name is enrolled in the state the first time one of its trades
settles; before that its intercept is independent of everything, so the predictive adds
``kappa_u`` to ``Q``.

Name effect. Under fixed ``beta`` and ``sigma^2`` the posterior mean of ``u_n`` after ``n``
settled trades with mean residual ``r_bar`` and unit weights is ``B r_bar`` with
``B = kappa_u / (kappa_u + 1 / n) = tau^2 / (tau^2 + sigma^2 / n)`` and ``tau^2 = kappa_u
sigma^2``: the shrinkage of ``causal_name_effect`` in
``outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/lib.py`` with target zero.
That function re-estimates ``tau^2`` by moments on every entry date; here ``kappa_u`` is one
hyperparameter, chosen by predictive score on the discovery block and then frozen, and the name
effects are estimated jointly with ``beta`` rather than on residuals of a separate fit. The
equivalence is re-derived and tested (``tests/research/test_online_bayes.py``), not copied.

Causality. Trade ``j`` enters the posterior on the first entry date strictly after its expiry,
which is when its settlement is known. On each entry date the settled batch is absorbed first,
then every event entering that date is predicted from the resulting posterior. Feature means,
standard deviations and the variance-weight normaliser use events with strictly earlier entry
dates only.

Forgetting. Before each batch of updates the coefficient block of ``C`` is divided by the
discount ``delta`` (component discounting: the name block and the cross-covariances are left
alone, so a name that stops reporting does not drift to an improper prior), and optionally
``a`` and ``b`` are multiplied by a variance discount. With ``delta = 1`` and no variance
discount the sequential posterior equals the batch conjugate posterior exactly.

Book gauge. The marginal posterior of the intercept is Student-t, so P(book mean > 0) and its
credible interval follow in closed form after every update date. The likelihood treats trades
as independent although events on one announcement date share a market move, so the raw
interval is too narrow; the gauge also reports it widened by a causal Kish design effect from
the intra-date correlation of the settled one-step residuals.

Units. The module is unit-agnostic except ``OnlineBayesConfig.prior_sigma``, which is stated in
the target's units.

Usage
-----
    python -m earnings_iv_crush.research.online_bayes --forward --state PATH [--features PATH]

References
----------
Dawid, A. P. (1984). Statistical theory: the prequential approach. Journal of the Royal
Statistical Society, Series A 147(2), 278-292.
Diebold, F. X., Gunther, T. A. and Tay, A. S. (1998). Evaluating density forecasts with
applications to financial risk management. International Economic Review 39(4), 863-883.
Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and
estimation. Journal of the American Statistical Association 102(477), 359-378.
Kish, L. (1965). Survey Sampling. Wiley.
Morris, C. N. (1983). Parametric empirical Bayes inference: theory and applications. Journal of
the American Statistical Association 78(381), 47-55.
West, M. and Harrison, J. (1997). Bayesian Forecasting and Dynamic Models, 2nd edition.
Springer Series in Statistics. Chapters 3 (the regression DLM), 4 (the dynamic linear model)
and 6 (model specification and design, where discount factors are developed).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Hashable, Sequence
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import gammaln, logsumexp, stdtr
from scipy.stats import chisquare, norm
from scipy.stats import t as student_t

from ..config import ONLINE_BAYES, ONLINE_BAYES_VARIANCE_WEIGHTS, OnlineBayesConfig
from .protocol import NullComparison

VARIANCE_WEIGHTS = ONLINE_BAYES_VARIANCE_WEIGHTS

#: Transformed 15:59 features, in design order after the intercept.
FEATURES: tuple[str, ...] = (
    "log_half_spread",
    "log_implied_move",
    "iv_term_spread",
    "iv_term_spread_missing",
    "log_depth",
    "log1p_dte",
    "log_forward",
)
#: Features whose missing values are set to their causal mean (zero after standardisation);
#: each carries a missing indicator in ``FEATURES``.
IMPUTED: tuple[str, ...] = ("iv_term_spread",)
#: Panel columns ``build_features`` reads. None is realised after 15:59 on the entry day.
RAW_COLUMNS: tuple[str, ...] = (
    "ticker",
    "half_spread",
    "implied_move",
    "iv_term_spread",
    "depth_tot",
    "dte",
    "m0",
    "s0",
)
#: The wide set's additions: (output name, lane E panel column, transform). Every column is
#: stamped 15:59 on the entry day (``q1559``) or known from the schedule (``amc``) in the lane E
#: feature map, and covers 2025-26. ``missing`` is the indicator of the named column's NaN;
#: other NaNs are set to the causal mean (zero after standardisation).
WIDE_EXTRA: tuple[tuple[str, str, str], ...] = (
    ("log_front_iv", "front_iv", "log"),
    ("jump_share", "jump_share", "raw"),
    ("jump_missing", "jump_share", "missing"),
    ("log_entry_spread", "entry_spread", "log"),
    ("depth_imb", "depth_imb", "raw"),
    ("depth_rel", "depth_rel", "raw"),
    ("log1p_atm_stale_h", "atm_stale_h", "log1p"),
    ("last_vs_mid", "last_vs_mid", "raw"),
    ("traded_frac", "traded_frac", "raw"),
    ("log1p_n_strikes", "n_strikes", "log1p"),
    ("wing_curv", "wing_curv", "raw"),
    ("wing_skew", "wing_skew", "raw"),
    ("log_wing_spread", "wing_spread", "log"),
    ("log1p_wing_gap", "wing_gap", "log1p"),
    ("wing_missing", "wing_spread", "missing"),
    ("log1p_carry_mag", "carry_mag", "log1p"),
    ("carry_missing", "carry_mag", "missing"),
    ("log_disp_iv_ratio", "disp_iv_ratio", "log"),
    ("amc", "amc", "raw"),
)
#: Feature names per ``OnlineBayesConfig.feature_set``, in design order after the intercept.
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "declared": FEATURES,
    "wide": FEATURES + tuple(name for name, _, _ in WIDE_EXTRA),
}
#: Panel columns the wide set reads beyond ``RAW_COLUMNS``.
RAW_COLUMNS_WIDE: tuple[str, ...] = tuple(dict.fromkeys(col for _, col, _ in WIDE_EXTRA))


# ── features ─────────────────────────────────────────────────────────────────


def build_feature_set(panel: pd.DataFrame, cfg: OnlineBayesConfig = ONLINE_BAYES) -> pd.DataFrame:
    """The features of ``cfg.feature_set`` plus ``premium_share``, on ``panel``'s index.

    ``"declared"`` is exactly :func:`build_features`. ``"wide"`` appends ``WIDE_EXTRA``: a
    ``log`` of a non-positive value, which the panel does not contain, raises rather than
    becoming a silent NaN; NaNs present in the panel are left for the causal imputation.

    Raises
    ------
    ValueError
        If a column is missing or a transform meets a value outside its domain.
    """
    out = build_features(panel, cfg)
    if cfg.feature_set == "declared":
        return out
    missing = [c for c in RAW_COLUMNS_WIDE if c not in panel.columns]
    if missing:
        raise ValueError(f"panel lacks {missing} for the wide feature set")
    for name, col, how in WIDE_EXTRA:
        x = panel[col].to_numpy(float)
        fin = np.isfinite(x)
        if how == "missing":
            out[name] = (~fin).astype(float)
            continue
        if how == "log":
            if (x[fin] <= 0).any():
                raise ValueError(f"{col} has non-positive values; log is undefined")
            with np.errstate(invalid="ignore"):
                out[name] = np.log(x)
        elif how == "log1p":
            if (x[fin] < 0).any():
                raise ValueError(f"{col} has negative values; log1p is not declared for them")
            out[name] = np.log1p(x)
        elif how == "raw":
            out[name] = x
        else:
            raise ValueError(f"unknown transform {how!r}")
    n_imp = {n: int(out[n].isna().sum()) for n, _, h in WIDE_EXTRA if h != "missing"}
    print(f"[features] wide set: causal-mean imputed {dict((k, v) for k, v in n_imp.items() if v)}")
    return out[[*FEATURE_SETS[cfg.feature_set], "premium_share"]]


def build_features(panel: pd.DataFrame, cfg: OnlineBayesConfig = ONLINE_BAYES) -> pd.DataFrame:
    """Transformed 15:59 features, one row per event, on ``panel``'s index.

    Parameters
    ----------
    panel : DataFrame
        Must hold ``RAW_COLUMNS``. ``half_spread`` is the straddle's relative half-spread at
        15:59 ((mid - bid) / mid), ``depth_tot`` the displayed contracts, ``dte`` the days to
        expiry, ``m0`` and ``s0`` the margin unit and the 15:59 bid per share.

    Returns
    -------
    DataFrame
        Columns ``FEATURES`` plus ``premium_share`` (``s0 / m0``, for the variance weight).

    Raises
    ------
    ValueError
        If a required column is missing, or a non-imputed feature is not finite.
    """
    missing = [c for c in RAW_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"panel lacks {missing}")
    hs = panel["half_spread"].to_numpy(float)
    im = panel["implied_move"].to_numpy(float)
    depth = panel["depth_tot"].to_numpy(float)
    dte = panel["dte"].to_numpy(float)
    m0 = panel["m0"].to_numpy(float)
    s0 = panel["s0"].to_numpy(float)
    fwd = (m0 - s0) / cfg.margin_spot_frac
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pd.DataFrame(
            {
                "log_half_spread": np.log(hs),
                "log_implied_move": np.log(im),
                "iv_term_spread": panel["iv_term_spread"].to_numpy(float),
                "iv_term_spread_missing": (~np.isfinite(panel["iv_term_spread"])).astype(float),
                "log_depth": np.log(depth),
                "log1p_dte": np.log1p(dte),
                "log_forward": np.log(fwd),
                "premium_share": s0 / m0,
            },
            index=panel.index,
        )
    bad = {
        c: int((~np.isfinite(out[c])).sum())
        for c in out.columns
        if c not in IMPUTED and (~np.isfinite(out[c])).any()
    }
    if bad:
        raise ValueError(f"non-finite features (not imputable): {bad}")
    n_imp = {c: int(out[c].isna().sum()) for c in IMPUTED}
    print(f"[features] {len(out)} events; set to the causal mean (with indicator): {n_imp}")
    return out


def causal_standardise(
    raw: pd.DataFrame, dates: pd.Series, min_prior: int
) -> tuple[pd.DataFrame, np.ndarray]:
    """Standardise each column with the mean and sd of strictly earlier dates' values.

    Missing values become zero, the causal mean. A column with zero prior variance (a flag
    never yet seen on) is set to zero rather than divided by zero.

    Parameters
    ----------
    raw : DataFrame
        Feature values, any index.
    dates : Series
        Entry date per row, aligned with ``raw``.
    min_prior : int
        Rows with fewer earlier-dated events than this are marked unusable.

    Returns
    -------
    (DataFrame, ndarray)
        The standardised frame on ``raw``'s index, and the number of strictly earlier events
        per row (rows below ``min_prior`` are NaN in the frame).
    """
    d = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    vals = raw.to_numpy(float)
    fin = np.isfinite(vals)
    v0 = np.where(fin, vals, 0.0)
    uniq, inv = np.unique(d, return_inverse=True)
    k = vals.shape[1]
    n_by = np.zeros((uniq.size, k))
    s1_by = np.zeros((uniq.size, k))
    s2_by = np.zeros((uniq.size, k))
    np.add.at(n_by, inv, fin.astype(float))
    np.add.at(s1_by, inv, v0)
    np.add.at(s2_by, inv, v0 * v0)
    # Strictly earlier dates: cumulative sums shifted by one date.
    n_c = np.vstack([np.zeros((1, k)), np.cumsum(n_by, axis=0)[:-1]])
    s1_c = np.vstack([np.zeros((1, k)), np.cumsum(s1_by, axis=0)[:-1]])
    s2_c = np.vstack([np.zeros((1, k)), np.cumsum(s2_by, axis=0)[:-1]])
    rows_by = np.bincount(inv, minlength=uniq.size).astype(float)
    n_prior_dates = np.concatenate([[0.0], np.cumsum(rows_by)[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = s1_c / n_c
        var = (s2_c - n_c * mu * mu) / (n_c - 1)
    mu_r, var_r = mu[inv], var[inv]
    sd_r = np.sqrt(np.maximum(var_r, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(sd_r > 0, (vals - mu_r) / sd_r, 0.0)
    z = np.where(fin, z, 0.0)
    n_prior = n_prior_dates[inv]
    z[n_prior < min_prior] = np.nan
    return pd.DataFrame(z, index=raw.index, columns=raw.columns), n_prior.astype(int)


def causal_variance_weight(
    premium_share: np.ndarray, dates: pd.Series, mode: str, min_prior: int, power: float = 2.0
) -> np.ndarray:
    """Variance weight ``v_j`` per event, from strictly earlier dates only.

    ``"none"`` gives ones. ``"premium_share"`` gives ``ps_j^k / mean(ps^k over earlier
    dates)`` with ``k = power`` (2 by default), NaN while fewer than ``min_prior`` earlier
    events exist.
    """
    ps = np.asarray(premium_share, float)
    if mode == "none":
        return np.ones_like(ps)
    if mode != "premium_share":
        raise ValueError(f"variance weight is one of {VARIANCE_WEIGHTS}")
    d = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    uniq, inv = np.unique(d, return_inverse=True)
    # A fractional power is undefined at a non-positive share; the square keeps its old domain.
    fin = np.isfinite(ps) & ((ps > 0) | (power == 2.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        pk = ps * ps if power == 2.0 else np.where(fin, ps, np.nan) ** power
    tot = np.bincount(inv, weights=np.where(fin, pk, 0.0), minlength=uniq.size)
    cnt = np.bincount(inv, weights=fin.astype(float), minlength=uniq.size)
    prior_tot = np.concatenate([[0.0], np.cumsum(tot)[:-1]])[inv]
    prior_cnt = np.concatenate([[0.0], np.cumsum(cnt)[:-1]])[inv]
    with np.errstate(divide="ignore", invalid="ignore"):
        v = pk / (prior_tot / prior_cnt)
    v[(prior_cnt < min_prior) | ~np.isfinite(v) | (v <= 0)] = np.nan
    return v


# ── the Student-t scale mixture ──────────────────────────────────────────────

#: Largest finite ``obs_df`` the default grid resolves (log-lambda sd 0.1 against a step of
#: 0.075); the Gaussian model is ``obs_df = inf``.
MIXTURE_MAX_DF = 200.0


@lru_cache(maxsize=64)
def lambda_grid(obs_df: float, nodes: int, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    """Nodes ``lambda_k`` and normalised log weights of ``Gamma(nu / 2, rate nu / 2)``.

    The density of ``u = log lambda`` is integrated by the trapezoid rule on ``[lo, hi]``; the
    weights are renormalised, which absorbs the truncated mass.
    """
    if not np.isfinite(obs_df):
        raise ValueError("the Gaussian model has no mixture grid")
    if obs_df > MIXTURE_MAX_DF:
        # The Gamma's sd in log lambda is about sqrt(2 / nu); beyond this the grid cannot
        # resolve it. Use obs_df = inf (the Gaussian model) instead.
        raise ValueError(f"obs_df {obs_df} exceeds {MIXTURE_MAX_DF}; use inf for the Gaussian")
    u = np.linspace(lo, hi, nodes)
    h = obs_df / 2.0
    logw = h * np.log(h) - gammaln(h) + h * u - h * np.exp(u)
    logw[[0, -1]] += np.log(0.5)
    logw = logw - logsumexp(logw)
    lam, lw = np.exp(u), logw
    lam.setflags(write=False)
    lw.setflags(write=False)
    return lam, lw


def _t_logpdf(y: np.ndarray, loc: np.ndarray, var: np.ndarray, df: np.ndarray) -> np.ndarray:
    """Log density of a Student-t with squared scale ``var`` (broadcasting)."""
    r2 = (y - loc) ** 2 / var
    return (
        gammaln((df + 1) / 2)
        - gammaln(df / 2)
        - 0.5 * np.log(df * np.pi * var)
        - (df + 1) / 2 * np.log1p(r2 / df)
    )


def mixture_predictive(
    y: np.ndarray,
    loc: np.ndarray,
    q: np.ndarray,
    v: np.ndarray,
    s2: np.ndarray,
    df: np.ndarray,
    cfg: OnlineBayesConfig,
) -> dict[str, np.ndarray]:
    """Predictive density, CDF and P(y > 0) of the scale-mixture model, per event.

    Given ``lambda`` the predictive is Student-t with ``df = 2a`` degrees of freedom, location
    ``loc`` and squared scale ``s2 (q + v / lambda)``, where ``s2 = b / a`` and ``q`` is the
    parameter-uncertainty part of the predictive variance in ``sigma^2`` units. ``lambda`` is
    integrated out on :func:`lambda_grid`. With ``obs_df = inf`` the mixture collapses to the
    single Student-t of the Gaussian model.

    Returns
    -------
    dict
        ``log_score``, ``pit`` (CDF at ``y``) and ``p_pos`` (P(y > 0)), arrays like ``y``.
    """
    y, loc, q, v, s2, df = (np.asarray(a, float) for a in (y, loc, q, v, s2, df))
    if not np.isfinite(cfg.obs_df):
        var = s2 * (q + v)
        sc = np.sqrt(var)
        return {
            "log_score": _t_logpdf(y, loc, var, df),
            "pit": stdtr(df, (y - loc) / sc),
            "p_pos": stdtr(df, loc / sc),
        }
    lam, lw = lambda_grid(cfg.obs_df, cfg.mixture_nodes, cfg.mixture_log_lo, cfg.mixture_log_hi)
    var = s2[:, None] * (q[:, None] + v[:, None] / lam[None, :])
    sc = np.sqrt(var)
    dfk = df[:, None]
    lp = _t_logpdf(y[:, None], loc[:, None], var, dfk) + lw[None, :]
    w = np.exp(lw)[None, :]
    with np.errstate(invalid="ignore"):
        pit = (w * stdtr(dfk, (y[:, None] - loc[:, None]) / sc)).sum(axis=1)
    return {
        "log_score": logsumexp(lp, axis=1),
        "pit": pit,
        "p_pos": (w * stdtr(dfk, loc[:, None] / sc)).sum(axis=1),
    }


def posterior_lambda(
    e: float, q: float, v: float, s2: float, df: float, cfg: OnlineBayesConfig
) -> float:
    """``E[lambda | e]`` for one residual under the mixture predictive (1 for the Gaussian).

    A residual in the tail gets a small ``lambda`` and so a large effective variance
    ``v / lambda`` in the update: the observation is down-weighted rather than allowed to drag
    the coefficients. This is the robust sequential approximation of West (1981): the update is
    the conjugate one at the plug-in ``lambda``, so the posterior stays normal-inverse-gamma.
    """
    if not np.isfinite(cfg.obs_df):
        return 1.0
    lam, lw = lambda_grid(cfg.obs_df, cfg.mixture_nodes, cfg.mixture_log_lo, cfg.mixture_log_hi)
    var = s2 * (q + v / lam)
    lp = _t_logpdf(np.asarray(e), np.asarray(0.0), var, np.asarray(df)) + lw
    lp = lp - lp.max()
    p = np.exp(lp)
    return float((p * lam).sum() / p.sum())


# ── the target transform ─────────────────────────────────────────────────────


def yj(x: np.ndarray, k: float) -> np.ndarray:
    """Yeo-Johnson transform with power ``k`` in [0, 2): a smooth bijection of the real line.

    Applied to the loss ratio ``x = -y / U`` (``U`` the premium in the target's units), the
    branch ``x >= 0`` is the Box-Cox transform of the payout ratio ``r = 1 + x``, so ``k`` near
    zero is close to modelling the log of realised against implied payout, the natural scale of
    the seller's outcome; ``k = 1`` is the identity. Yeo and Johnson (2000).
    """
    x = np.asarray(x, float)
    pos = x >= 0
    out = np.empty_like(x)
    xp, xn = x[pos], x[~pos]
    out[pos] = np.log1p(xp) if k == 0 else ((1 + xp) ** k - 1) / k
    out[~pos] = -np.log1p(-xn) if k == 2 else -((1 - xn) ** (2 - k) - 1) / (2 - k)
    return out


def yj_inv(z: np.ndarray, k: float) -> np.ndarray:
    """Inverse of :func:`yj`."""
    z = np.asarray(z, float)
    pos = z >= 0
    out = np.empty_like(z)
    zp, zn = z[pos], z[~pos]
    out[pos] = np.expm1(zp) if k == 0 else (1 + k * zp) ** (1 / k) - 1
    out[~pos] = -np.expm1(-zn) if k == 2 else 1 - (1 - (2 - k) * zn) ** (1 / (2 - k))
    return out


def yj_logderiv(x: np.ndarray, k: float) -> np.ndarray:
    """``log d yj(x) / dx``, the Jacobian term that puts a density on the original scale."""
    x = np.asarray(x, float)
    return np.where(x >= 0, (k - 1) * np.log1p(np.abs(x)), (1 - k) * np.log1p(np.abs(x)))


def transformed_mean(
    loc: np.ndarray,
    q: np.ndarray,
    v: np.ndarray,
    s2: np.ndarray,
    df: np.ndarray,
    unit: np.ndarray,
    cfg: OnlineBayesConfig,
) -> np.ndarray:
    """Predictive mean of ``y = -U yj_inv(z)`` by Monte Carlo with common random numbers.

    The same ``cfg.ev_draws`` uniforms (seed ``cfg.ev_seed``) drive every event, so the mean is
    a smooth function of the predictive's parameters and two events with equal parameters get
    equal means. Under a heavy-tailed ``z`` with a small power the true mean can be infinite
    (it exists when ``1 / k`` is below the tail index); the Monte Carlo value is then a finite
    sample mean and is reported, not trusted.
    """
    from scipy.stats import chi2
    from scipy.stats import gamma as gamma_dist

    rng = np.random.default_rng(cfg.ev_seed)
    m = cfg.ev_draws
    gauss = rng.standard_normal(m)
    u_chi = rng.random(m)
    u_lam = rng.random(m)
    if np.isfinite(cfg.obs_df):
        lam = gamma_dist.ppf(u_lam, cfg.obs_df / 2, scale=2 / cfg.obs_df)
    else:
        lam = np.ones(m)
    loc, q, v, s2, df, unit = (np.asarray(a, float) for a in (loc, q, v, s2, df, unit))
    out = np.full(loc.size, np.nan)
    for lo in range(0, out.size, 256):
        sl = slice(lo, lo + 256)
        dfi = df[sl][:, None]
        tdraw = gauss[None, :] / np.sqrt(chi2.ppf(u_chi[None, :], dfi) / dfi)
        sc = np.sqrt(s2[sl][:, None] * (q[sl][:, None] + v[sl][:, None] / lam[None, :]))
        z = loc[sl][:, None] + sc * tdraw
        with np.errstate(over="ignore", invalid="ignore"):
            x = yj_inv(z.ravel(), cfg.yj_power).reshape(z.shape)
        out[sl] = -unit[sl] * x.mean(axis=1)
    return out


# ── the conjugate state ──────────────────────────────────────────────────────


@dataclass
class NIGState:
    """Normal-inverse-gamma posterior over the coefficients and the enrolled intercepts.

    Attributes
    ----------
    p : int
        Size of the coefficient block (intercept first).
    m, C : ndarray
        Posterior mean and covariance (in ``sigma^2`` units) of the active state.
    a, b : float
        Inverse-gamma shape and scale of ``sigma^2``.
    name_scale : float
        ``kappa_u``; zero means names are never enrolled.
    names : dict
        Name to state index (from ``p`` upwards).
    group_scale : float
        ``kappa_g``, the prior variance of a group (industry) intercept; zero switches the level
        off. A name's intercept is then its group's plus its own, so names in one group shrink
        towards the group's mean rather than towards zero: the hierarchical model, stacked.
    groups : dict
        Group to state index.
    """

    p: int
    m: np.ndarray
    C: np.ndarray
    a: float
    b: float
    name_scale: float
    names: dict[Hashable, int] = field(default_factory=dict)
    group_scale: float = 0.0
    groups: dict[Hashable, int] = field(default_factory=dict)

    @classmethod
    def prior(
        cls, p: int, cfg: OnlineBayesConfig, *, coef_mean: np.ndarray | None = None
    ) -> NIGState:
        """The prior: zero means, diagonal covariance, ``a0 = prior_df / 2``."""
        diag = np.full(p, cfg.coef_prior_scale)
        diag[0] = cfg.intercept_prior_scale
        a0 = cfg.prior_df / 2.0
        m = np.zeros(p) if coef_mean is None else np.asarray(coef_mean, float).copy()
        return cls(
            p=p,
            m=m,
            C=np.diag(diag),
            a=a0,
            b=a0 * cfg.prior_sigma**2,
            name_scale=cfg.name_prior_scale,
            group_scale=cfg.group_prior_scale,
        )

    @property
    def dim(self) -> int:
        return int(self.m.size)

    def copy(self) -> NIGState:
        return NIGState(
            self.p,
            self.m.copy(),
            self.C.copy(),
            self.a,
            self.b,
            self.name_scale,
            dict(self.names),
            self.group_scale,
            dict(self.groups),
        )

    def _grow(self, scale: float) -> int:
        k = self.dim
        m = np.zeros(k + 1)
        m[:k] = self.m
        C = np.zeros((k + 1, k + 1))
        C[:k, :k] = self.C
        C[k, k] = scale
        self.m, self.C = m, C
        return k

    def _enrol(self, name: Hashable) -> int:
        k = self._grow(self.name_scale)
        self.names[name] = k
        return k

    def _enrol_group(self, group: Hashable) -> int:
        k = self._grow(self.group_scale)
        self.groups[group] = k
        return k

    def _uses_group(self, group: Hashable | None) -> bool:
        return self.group_scale > 0 and group is not None

    def _design(
        self, x: np.ndarray, name: Hashable, group: Hashable | None = None
    ) -> tuple[np.ndarray, float]:
        """Design over the active state and the variance unenrolled intercepts add."""
        F = np.zeros(self.dim)
        F[: self.p] = x
        extra = 0.0
        if self.name_scale > 0:
            if name in self.names:
                F[self.names[name]] = 1.0
            else:
                extra += self.name_scale
        if self._uses_group(group):
            if group in self.groups:
                F[self.groups[group]] = 1.0
            else:
                extra += self.group_scale
        return F, extra

    def predict_parts(
        self, x: np.ndarray, name: Hashable, group: Hashable | None = None
    ) -> tuple[float, float, float, float]:
        """Location ``f``, parameter variance ``q`` (``sigma^2`` units), ``s2 = b / a``, ``2a``.

        The Gaussian predictive's squared scale is ``s2 (q + v)``; the scale mixture's is
        ``s2 (q + v / lambda)``.
        """
        F, extra = self._design(np.asarray(x, float), name, group)
        f = float(F @ self.m)
        q = float(F @ self.C @ F) + extra
        return f, q, self.b / self.a, 2.0 * self.a

    def predict(
        self, x: np.ndarray, name: Hashable, v: float, group: Hashable | None = None
    ) -> tuple[float, float, float]:
        """One-step predictive: location, scale and degrees of freedom of the Student-t."""
        F, extra = self._design(np.asarray(x, float), name, group)
        f = float(F @ self.m)
        Q = float(F @ self.C @ F) + extra + float(v)
        return f, float(np.sqrt(self.b / self.a * Q)), 2.0 * self.a

    def update(
        self,
        x: np.ndarray,
        name: Hashable,
        y: float,
        v: float,
        group: Hashable | None = None,
        lam: float = 1.0,
    ) -> dict[str, Any]:
        """Absorb one settled outcome; return the residual, its variance and the mean shift.

        ``lam`` is the observation's precision multiplier from the scale mixture (1 for the
        Gaussian model): the update uses the variance weight ``v / lam``.

        Returns
        -------
        dict
            ``e`` (one-step residual), ``Q`` (its variance in ``sigma^2`` units), ``z`` (the
            residual standardised by the pre-update predictive scale), ``dm`` (shift of the
            coefficient block's mean), ``dname`` and ``dgroup`` (shifts of the name's and the
            group's intercepts).
        """
        if self.name_scale > 0 and name not in self.names:
            self._enrol(name)
        if self._uses_group(group) and group not in self.groups:
            self._enrol_group(group)
        F, extra = self._design(np.asarray(x, float), name, group)
        CF = self.C @ F
        Q = float(F @ CF) + extra + float(v) / float(lam)
        e = float(y) - float(F @ self.m)
        # An improper reference prior (a <= 0 or b = 0) has no predictive scale yet.
        s2 = self.b / self.a if self.a > 0 and self.b > 0 else float("nan")
        z = e / float(np.sqrt(s2 * Q))
        A = CF / Q
        dmean = A * e
        self.m = self.m + dmean
        self.C = self.C - np.outer(A, A) * Q
        self.C = 0.5 * (self.C + self.C.T)
        self.a += 0.5
        self.b += e * e / (2.0 * Q)
        dname = float(dmean[self.names[name]]) if name in self.names else 0.0
        dgroup = float(dmean[self.groups[group]]) if group in self.groups else 0.0
        return {
            "e": e,
            "Q": Q,
            "z": z,
            "dm": dmean[: self.p].copy(),
            "dname": dname,
            "dgroup": dgroup,
        }

    def discount(self, delta: float, var_delta: float = 1.0) -> None:
        """Inflate the coefficient block by ``1 / delta``; scale ``a`` and ``b`` by ``var_delta``."""
        if delta < 1.0:
            self.C[: self.p, : self.p] = self.C[: self.p, : self.p] / delta
        if var_delta < 1.0:
            self.a *= var_delta
            self.b *= var_delta

    def coef_marginal(self, k: int = 0) -> tuple[float, float, float]:
        """Student-t marginal of coefficient ``k``: location, scale, degrees of freedom."""
        return float(self.m[k]), float(np.sqrt(self.b / self.a * self.C[k, k])), 2.0 * self.a

    def name_effect(self, name: Hashable) -> float:
        """Posterior mean of a name's own intercept (zero if never enrolled)."""
        return float(self.m[self.names[name]]) if name in self.names else 0.0

    def group_effect(self, group: Hashable | None) -> float:
        """Posterior mean of a group's intercept (zero if never enrolled or off)."""
        return float(self.m[self.groups[group]]) if group in self.groups else 0.0

    def to_npz(self, path: str | Path, meta: dict[str, Any] | None = None) -> None:
        """Write the state (and JSON metadata) to ``path``."""
        names = sorted(self.names, key=lambda n: self.names[n])
        groups = sorted(self.groups, key=lambda g: self.groups[g])
        np.savez(
            path,
            p=self.p,
            m=self.m,
            C=self.C,
            a=self.a,
            b=self.b,
            name_scale=self.name_scale,
            names=np.array([str(n) for n in names]),
            name_idx=np.array([self.names[n] for n in names], dtype=int),
            group_scale=self.group_scale,
            groups=np.array([str(g) for g in groups]),
            group_idx=np.array([self.groups[g] for g in groups], dtype=int),
            meta=json.dumps(meta or {}),
        )

    @classmethod
    def from_npz(cls, path: str | Path) -> tuple[NIGState, dict[str, Any]]:
        """Read a state written by :meth:`to_npz`, with its metadata.

        States written before the group level existed (no index arrays) are read with the
        names at consecutive indices from ``p``, as they were written.
        """
        z = np.load(path, allow_pickle=False)
        p = int(z["p"])
        nl = z["names"].tolist()
        idx = z["name_idx"].tolist() if "name_idx" in z.files else [p + i for i in range(len(nl))]
        names: dict[Hashable, int] = {str(n): int(i) for n, i in zip(nl, idx, strict=True)}
        groups: dict[Hashable, int] = {}
        gscale = 0.0
        if "groups" in z.files:
            gscale = float(z["group_scale"])
            groups = {
                str(g): int(i)
                for g, i in zip(z["groups"].tolist(), z["group_idx"].tolist(), strict=True)
            }
        st = cls(
            p,
            z["m"],
            z["C"],
            float(z["a"]),
            float(z["b"]),
            float(z["name_scale"]),
            names,
            gscale,
            groups,
        )
        return st, json.loads(str(z["meta"]))


def batch_posterior(
    F: np.ndarray,
    y: np.ndarray,
    v: np.ndarray,
    m0: np.ndarray,
    C0: np.ndarray,
    a0: float,
    b0: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """The batch conjugate NIG posterior, for checking the sequential one.

    ``C = (C0^-1 + F' V^-1 F)^-1``, ``m = C (C0^-1 m0 + F' V^-1 y)``, ``a = a0 + n / 2`` and
    ``b = b0 + (y' V^-1 y + m0' C0^-1 m0 - m' C^-1 m) / 2``.
    """
    W = 1.0 / np.asarray(v, float)
    P0 = np.linalg.inv(C0)
    P = P0 + F.T @ (F * W[:, None])
    C = np.linalg.inv(P)
    m = C @ (P0 @ m0 + F.T @ (W * y))
    a = a0 + y.size / 2.0
    b = b0 + 0.5 * float(y @ (W * y) + m0 @ P0 @ m0 - m @ P @ m)
    return m, C, a, b


# ── the sequential run ───────────────────────────────────────────────────────


@dataclass
class OnlineRun:
    """Everything one sequential pass produces.

    Attributes
    ----------
    events : DataFrame
        One row per input event, in the input's order: prior predictive (``pred_loc``,
        ``pred_scale``, ``pred_df``, ``p_pos``, ``decide``, ``scored``), the realised
        surprise (``surprise_z``, ``pit``, ``log_score``, ``covered``), when the trade entered
        the posterior (``update_date``, ``n_settled_at_entry``), its own name effect at entry
        and the change it caused (``dname``).
    deltas : DataFrame
        Change in each coefficient's posterior mean caused by the event's update (NaN if it
        never entered), columns ``d_<coef>``.
    gauge : DataFrame
        One row per update date: intercept posterior, P(mean > 0), credible interval, design
        effect and the widened interval, and the monitor's reading. Under the loss-ratio
        transform the intercept is on the model scale and ``p_mean_pos`` is P(intercept < 0),
        the probability that the book's typical (median) trade gains.
    state : NIGState
        The posterior after the last update.
    coef_names : list of str
    path : DataFrame
        One row per update date: each coefficient's posterior location (``m_<coef>``) and the
        scale of its Student-t marginal (``s_<coef>``) after that date's batch, with its degrees
        of freedom (``df``).
    """

    events: pd.DataFrame
    deltas: pd.DataFrame
    gauge: pd.DataFrame
    state: NIGState
    coef_names: list[str]
    path: pd.DataFrame = field(default_factory=pd.DataFrame)


def _kish_deff(cnt: np.ndarray, s1: np.ndarray, s2: np.ndarray) -> tuple[float, float]:
    """One-way ANOVA intra-cluster correlation and Kish design effect, floored at one."""
    keep = cnt > 0
    n_g, t1, t2 = cnt[keep], s1[keep], s2[keep]
    G, N = n_g.size, float(n_g.sum())
    if G < 2 or N <= G:
        return float("nan"), 1.0
    grand = t1.sum() / N
    ssb = float((t1 * t1 / n_g).sum() - N * grand * grand)
    ssw = float(t2.sum() - (t1 * t1 / n_g).sum())
    msb, msw = ssb / (G - 1), ssw / (N - G)
    n_bar0 = (N - float((n_g * n_g).sum()) / N) / (G - 1)
    denom = msb + (n_bar0 - 1) * msw
    rho = (msb - msw) / denom if denom > 0 else float("nan")
    m_bar = float((n_g * n_g).sum()) / N
    deff = 1.0 + (m_bar - 1.0) * max(rho, 0.0) if np.isfinite(rho) else 1.0
    return float(rho), float(deff)


def run_online(
    frame: pd.DataFrame,
    X: np.ndarray,
    cfg: OnlineBayesConfig,
    *,
    coef_names: Sequence[str],
    y_col: str = "y",
    v_col: str = "v",
    quiet: bool = False,
) -> OnlineRun:
    """One causal pass: absorb settled trades, then predict each entry date's events.

    Parameters
    ----------
    frame : DataFrame
        One row per event with ``entry_date``, ``settle_date`` (the expiry: the outcome is
        known from the next entry date strictly after it), ``name``, ``cluster`` (the
        announcement date, for the design effect), ``y_col`` (NaN where unknown; such a trade
        is predicted but never absorbed) and ``v_col`` (the variance weight). An optional
        ``group`` column (NaN or None where unknown) carries the industry level when
        ``cfg.group_prior_scale > 0``.
    X : ndarray, shape (n, p)
        Design rows aligned with ``frame``, intercept first. A row with any NaN is not
        predicted and not absorbed.
    cfg : OnlineBayesConfig
    coef_names : sequence of str
        Names of the ``p`` coefficients.

    Returns
    -------
    OnlineRun

    Raises
    ------
    ValueError
        If any settle date is not strictly after its entry date, or shapes disagree.
    """
    n = len(frame)
    X = np.asarray(X, float)
    if X.shape[0] != n or X.shape[1] != len(coef_names):
        raise ValueError(f"X is {X.shape}; expected ({n}, {len(coef_names)})")
    entry = pd.to_datetime(frame["entry_date"]).dt.normalize().to_numpy()
    settle = pd.to_datetime(frame["settle_date"]).dt.normalize().to_numpy()
    if (settle <= entry).any():
        raise ValueError(f"{int((settle <= entry).sum())} events settle on or before entry")
    names = frame["name"].to_numpy(object)
    if "group" in frame.columns:
        groups = np.array(
            [
                None if (g is None or (isinstance(g, float) and np.isnan(g))) else g
                for g in frame["group"].to_numpy(object)
            ],
            dtype=object,
        )
    else:
        groups = np.full(n, None, dtype=object)
    mixture = bool(np.isfinite(cfg.obs_df))
    transformed = cfg.target_transform == "yj_loss"
    vector = mixture or transformed
    y = frame[y_col].to_numpy(float)
    if transformed:
        if "unit" not in frame.columns:
            raise ValueError("target_transform 'yj_loss' needs a 'unit' column (the premium)")
        unit = frame["unit"].to_numpy(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            ym = yj(np.where(np.isfinite(y) & (unit > 0), -y / unit, 0.0), cfg.yj_power)
        ym = np.where(np.isfinite(y), ym, np.nan)
    else:
        unit = np.ones(n)
        ym = y
    v = frame[v_col].to_numpy(float)
    clus_codes, clus_inv = np.unique(
        pd.to_datetime(frame["cluster"]).dt.normalize().to_numpy(), return_inverse=True
    )
    usable = np.isfinite(X).all(axis=1) & np.isfinite(v) & (v > 0)
    if transformed:
        usable = usable & np.isfinite(unit) & (unit > 0)
    absorbable = usable & np.isfinite(ym)
    p = X.shape[1]
    st = NIGState.prior(p, cfg)

    out = {
        k: np.full(n, np.nan)
        for k in (
            "pred_loc",
            "pred_scale",
            "pred_df",
            "p_pos",
            "surprise_z",
            "pit",
            "log_score",
            "covered",
            "name_effect_at_entry",
            "n_settled_at_entry",
            "dname",
            "update_z",
            "group_effect_at_entry",
            "dgroup",
            "lambda_hat",
            "quantile_resid",
            "pred_q",
            "pred_s2",
            "pred_mean_y",
            "pred_median_y",
        )
    }
    update_date = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    deltas = np.full((n, p), np.nan)
    order_settle = np.flatnonzero(absorbable)
    order_settle = order_settle[
        np.lexsort((names[order_settle].astype(str), entry[order_settle], settle[order_settle]))
    ]
    dates = np.unique(entry)
    ptr = 0
    n_settled = 0
    c_cnt = np.zeros(clus_codes.size)
    c_s1 = np.zeros(clus_codes.size)
    c_s2 = np.zeros(clus_codes.size)
    gauge_rows: list[dict[str, Any]] = []
    path_rows: list[np.ndarray] = []
    path_dates: list[Any] = []
    q_hi = 0.5 + cfg.gauge_level / 2
    t_cov = 0.5 + cfg.interval_level / 2
    for t in dates:
        batch = []
        while ptr < order_settle.size and settle[order_settle[ptr]] < t:
            batch.append(order_settle[ptr])
            ptr += 1
        if batch:
            st.discount(cfg.discount, cfg.variance_discount)
            for j in batch:
                lam = 1.0
                if mixture:
                    f_j, q_j, s2_j, df_j = st.predict_parts(X[j], names[j], groups[j])
                    lam = posterior_lambda(ym[j] - f_j, q_j, v[j], s2_j, df_j, cfg)
                r = st.update(X[j], names[j], ym[j], v[j], groups[j], lam)
                out["lambda_hat"][j] = lam
                out["dgroup"][j] = r["dgroup"]
                update_date[j] = t
                deltas[j] = r["dm"]
                out["dname"][j] = r["dname"]
                out["update_z"][j] = r["z"]
                n_settled += 1
                k = clus_inv[j]
                c_cnt[k] += 1
                c_s1[k] += r["z"]
                c_s2[k] += r["z"] * r["z"]
            sig = np.sqrt(st.b / st.a * np.diag(st.C)[:p])
            path_rows.append(np.concatenate([st.m[:p], sig, [2.0 * st.a]]))
            path_dates.append(pd.Timestamp(t))
            loc, scale, df = st.coef_marginal(0)
            rho, deff = _kish_deff(c_cnt, c_s1, c_s2)
            # On the loss-ratio scale a negative intercept is the seller's gain, so the gauge
            # reads P(book median H > 0) = P(intercept < 0); on y itself, P(intercept > 0).
            sgn = -1.0 if transformed else 1.0
            p_pos = float(student_t.sf(0.0, df, loc=sgn * loc, scale=scale))
            p_pos_d = float(student_t.sf(0.0, df, loc=sgn * loc, scale=scale * np.sqrt(deff)))
            q = float(student_t.ppf(q_hi, df))
            gauge_rows.append(
                {
                    "date": pd.Timestamp(t),
                    "n_settled": n_settled,
                    "intercept": loc,
                    "intercept_scale": scale,
                    "df": df,
                    "p_mean_pos": p_pos,
                    "ci_low": loc - q * scale,
                    "ci_high": loc + q * scale,
                    "icc": rho,
                    "deff": deff,
                    "p_mean_pos_deff": p_pos_d,
                    "ci_low_deff": loc - q * scale * np.sqrt(deff),
                    "ci_high_deff": loc + q * scale * np.sqrt(deff),
                    "sigma_hat": float(np.sqrt(st.b / st.a)),
                    "monitor": (
                        "stop"
                        if p_pos_d < cfg.gauge_stop
                        else "promote" if p_pos_d > cfg.gauge_promote else "continue"
                    ),
                }
            )
        for i in np.flatnonzero(entry == t):
            out["n_settled_at_entry"][i] = n_settled
            out["name_effect_at_entry"][i] = st.name_effect(names[i])
            out["group_effect_at_entry"][i] = st.group_effect(groups[i])
            if not usable[i]:
                continue
            f_i, q_i, s2_i, df = st.predict_parts(X[i], names[i], groups[i])
            out["pred_q"][i], out["pred_s2"][i] = q_i, s2_i
            loc, scale = f_i, float(np.sqrt(s2_i * (q_i + v[i])))
            out["pred_loc"][i], out["pred_scale"][i], out["pred_df"][i] = loc, scale, df
            if vector:
                continue  # scored after the pass, vectorised
            out["p_pos"][i] = float(student_t.sf(0.0, df, loc=loc, scale=scale))
            if np.isfinite(y[i]):
                zi = (y[i] - loc) / scale
                out["surprise_z"][i] = zi
                out["pit"][i] = float(student_t.cdf(zi, df))
                out["log_score"][i] = float(student_t.logpdf(zi, df)) - np.log(scale)
                out["covered"][i] = float(abs(zi) <= student_t.ppf(t_cov, df))
    if vector:
        ok = np.isfinite(out["pred_loc"])
        mp = mixture_predictive(
            np.where(np.isfinite(ym), ym, 0.0)[ok],
            out["pred_loc"][ok],
            out["pred_q"][ok],
            v[ok],
            out["pred_s2"][ok],
            out["pred_df"][ok],
            cfg,
        )
        has_y = ok & np.isfinite(ym)
        sub = np.isfinite(ym[ok])
        if transformed:
            # y = -U yj_inv(z) falls as z rises: P(y > 0) = P(z < 0), F_y(y) = 1 - F_z(z),
            # and the density carries the Jacobian of z with respect to y.
            x_obs = -y[has_y] / unit[has_y]
            out["p_pos"][ok] = 1.0 - mp["p_pos"]
            out["log_score"][has_y] = (
                mp["log_score"][sub] + yj_logderiv(x_obs, cfg.yj_power) - np.log(unit[has_y])
            )
            out["pit"][has_y] = 1.0 - mp["pit"][sub]
            out["surprise_z"][has_y] = (out["pred_loc"][has_y] - ym[has_y]) / out["pred_scale"][
                has_y
            ]
            out["pred_median_y"][ok] = -unit[ok] * yj_inv(out["pred_loc"][ok], cfg.yj_power)
            out["pred_mean_y"][ok] = transformed_mean(
                out["pred_loc"][ok],
                out["pred_q"][ok],
                v[ok],
                out["pred_s2"][ok],
                out["pred_df"][ok],
                unit[ok],
                cfg,
            )
        else:
            out["p_pos"][ok] = mp["p_pos"]
            out["log_score"][has_y] = mp["log_score"][sub]
            out["pit"][has_y] = mp["pit"][sub]
            out["surprise_z"][has_y] = (y[has_y] - out["pred_loc"][has_y]) / out["pred_scale"][
                has_y
            ]
        lo, hi = 0.5 - cfg.interval_level / 2, 0.5 + cfg.interval_level / 2
        out["covered"][has_y] = ((out["pit"][has_y] >= lo) & (out["pit"][has_y] <= hi)).astype(
            float
        )
    # The normalised quantile residual (Dunn and Smyth 1996): standard normal under a correct
    # predictive whatever its shape, so surprises compare across likelihoods.
    with np.errstate(divide="ignore", invalid="ignore"):
        out["quantile_resid"] = norm.ppf(np.clip(out["pit"], 1e-300, 1.0 - 1e-16))
    if not transformed:
        out["pred_median_y"] = out["pred_loc"].copy()
        # The mean exists when the predictive's tail index exceeds one.
        tail = np.minimum(out["pred_df"], cfg.obs_df)
        out["pred_mean_y"] = np.where(tail > 1, out["pred_loc"], np.nan)
    ev = pd.DataFrame(out, index=frame.index)
    ev["update_date"] = update_date
    ev["scored"] = np.isfinite(ev["pred_loc"]) & (ev["n_settled_at_entry"] >= cfg.min_settled)
    ev["decide"] = ev["scored"] & (ev["p_pos"] > cfg.decision_threshold)
    ev["decide_ev"] = ev["scored"] & (ev["pred_mean_y"] > 0)
    # Absorbed strictly after expiry, by construction; checked so a refactor cannot leak.
    upd = ev["update_date"].to_numpy("datetime64[ns]")
    has = ~np.isnat(upd)
    if (upd[has] <= settle[has]).any():
        raise AssertionError("a trade entered the posterior on or before its expiry")
    dl = pd.DataFrame(deltas, index=frame.index, columns=[f"d_{c}" for c in coef_names])
    if not quiet:
        print(
            f"[online] {n} events; usable design {int(usable.sum())}; absorbed {n_settled} of "
            f"{int(absorbable.sum())} with an outcome; scored (>= {cfg.min_settled} settled) "
            f"{int(ev['scored'].sum())}; decide trade {int(ev['decide'].sum())}"
        )
    path = pd.DataFrame(
        np.array(path_rows).reshape(len(path_rows), 2 * p + 1),
        columns=[f"m_{c}" for c in coef_names] + [f"s_{c}" for c in coef_names] + ["df"],
    )
    path.insert(0, "date", path_dates)
    return OnlineRun(ev, dl, pd.DataFrame(gauge_rows), st, list(coef_names), path)


# ── scoring ──────────────────────────────────────────────────────────────────


def pit_histogram(pit: np.ndarray, bins: int) -> dict[str, Any]:
    """Counts of PIT values in equal bins and a chi-square statistic against uniformity.

    The p-value treats events as independent, which same-date events are not; read it as
    descriptive.
    """
    u = np.asarray(pit, float)
    u = u[np.isfinite(u)]
    if u.size == 0:
        raise ValueError("no PIT values")
    cnt, _ = np.histogram(u, bins=bins, range=(0.0, 1.0))
    chi = chisquare(cnt)
    return {"counts": cnt.tolist(), "chi2": float(chi.statistic), "p_indep": float(chi.pvalue)}


def date_stratified_null(
    values: np.ndarray,
    selected: np.ndarray,
    dates: Sequence[Any] | np.ndarray | pd.Series,
    *,
    n_draws: int,
    seed: int,
) -> NullComparison:
    """Mean of the selection against random selections of the same count on each date.

    On every date the null draws as many events as the rule selected there, from that date's
    eligible events, so the null shares the rule's calendar exposure exactly.

    Raises
    ------
    ValueError
        If the selection is empty or takes every event.
    """
    y = np.asarray(values, float)
    sel = np.asarray(selected, bool)
    if y.shape != sel.shape:
        raise ValueError("values and selection differ in shape")
    k = int(sel.sum())
    if k == 0 or k == y.size:
        raise ValueError(f"selection takes {k} of {y.size}; nothing to compare")
    keys = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    _, inv = np.unique(keys, return_inverse=True)
    k_by = np.bincount(inv, weights=sel.astype(float)).astype(int)
    rng = np.random.default_rng(seed)
    draws = np.empty(n_draws)
    for b in range(n_draws):
        key = rng.random(y.size)
        order = np.lexsort((key, inv))
        start = np.concatenate([[0], np.cumsum(np.bincount(inv))[:-1]])
        rank = np.empty(y.size, int)
        rank[order] = np.arange(y.size) - np.repeat(start, np.bincount(inv))
        draws[b] = y[rank < k_by[inv]].mean()
    return NullComparison(observed=float(y[sel].mean()), null=draws, n_selected=k)


def grid(cfg: OnlineBayesConfig, *, with_features: bool) -> list[OnlineBayesConfig]:
    """The declared search space as configurations, in a fixed order.

    Without features the coefficient prior scale does not enter, so it is not crossed.
    """
    coef = cfg.coef_prior_grid if with_features else (cfg.coef_prior_scale,)
    return [
        replace(cfg, discount=d, coef_prior_scale=g, name_prior_scale=u, variance_weight=w)
        for d in cfg.discount_grid
        for g in coef
        for u in cfg.name_prior_grid
        for w in cfg.variance_weight_grid
    ]


def describe_config(cfg: OnlineBayesConfig) -> dict[str, Any]:
    """The searched fields of a configuration, for logs and freeze notes."""
    keep = (
        "discount",
        "coef_prior_scale",
        "name_prior_scale",
        "variance_weight",
        "obs_df",
        "group_prior_scale",
        "variance_power",
        "feature_set",
        "variance_discount",
        "z_clip",
        "target_transform",
        "yj_power",
    )
    return {k: v for k, v in asdict(cfg).items() if k in keep}


# ── forward mode ─────────────────────────────────────────────────────────────


def forward_store_paths(dry: bool, root: str | Path | None = None) -> dict[str, str]:
    """The paper book's store paths, as ``live.session.Stores.for_mode`` resolves them.

    ``session`` imports the order modules, so this mirrors its three read paths from the
    configs it reads them from instead of importing it. ``root`` relocates the stores (tests).
    """
    from ..config import LIVE
    from ..live.forward_test import FORWARD

    live = {
        "open_positions": LIVE.open_positions_path,
        "nostop": FORWARD.nostop_ledger_path,
        "reconciliation": FORWARD.reconciliation_path,
    }
    if root is not None:
        base = Path(root)
        return {k: str((base / "dry" if dry else base) / Path(p).name) for k, p in live.items()}
    if not dry:
        return live
    return {k: str(Path(LIVE.dry_dir) / Path(p).name) for k, p in live.items()}


def forward_update(
    state_path: str | Path | None,
    *,
    features_path: str | Path | None = None,
    dry: bool = False,
    root: str | Path | None = None,
    out_path: str | Path | None = None,
) -> int:
    """Update the frozen posterior with settled paper trades. Returns a process exit code.

    Reads closed trades through ``live.shadow.closed_trades`` and their hedged outcome
    ``H_shadow`` from the shadow book that ``scripts.shadow_book`` writes beside the stores.
    Nothing here connects to a broker or imports the order path.

    Returns
    -------
    int
        ``2`` when no settled paper trade exists (N=0), ``0`` after an update.

    Raises
    ------
    FileNotFoundError, ValueError
        If trades exist but the shadow book, the features or the state cannot be joined.
    """
    from ..config import SHADOW
    from ..live.shadow import closed_trades

    paths = forward_store_paths(dry, root)
    trades = closed_trades(
        paths["open_positions"], paths["nostop"], paths["reconciliation"], transmitted_only=not dry
    )
    book_path = Path(paths["nostop"]).parent / SHADOW.out_name
    settled = pd.DataFrame()
    if not trades.empty and book_path.exists():
        book = pd.read_csv(book_path, parse_dates=["entry_date", "expiry"])
        settled = book[(book["status"] == "ok") & np.isfinite(book["H_shadow"])]
    print(
        f"[forward] closed paper trades {len(trades)}; settled with H marked {len(settled)} "
        f"(stores: {paths['nostop']})"
    )
    if settled.empty:
        print(
            "[forward] N=0: no settled paper trade to update with; the frozen posterior is "
            "unchanged. Nothing was written."
        )
        return 2
    if state_path is None:
        raise ValueError("settled trades exist; pass --state with the frozen posterior")
    if features_path is None:
        raise ValueError("settled trades exist; pass --features with their 15:59 features")
    st, meta = NIGState.from_npz(state_path)
    cfg = OnlineBayesConfig(**meta["config"])
    feats = pd.read_parquet(features_path)
    feats["entry_date"] = pd.to_datetime(feats["entry_date"]).dt.normalize()
    d = settled.merge(feats, on=["ticker", "entry_date"], how="left", indicator=True)
    lost = int((d["_merge"] != "both").sum())
    if lost:
        raise ValueError(f"{lost} of {len(settled)} settled trades have no feature row")
    raw = build_feature_set(d, cfg)
    mu = np.asarray(meta["feature_mean"], float)
    sd = np.asarray(meta["feature_sd"], float)
    zf = (raw[list(FEATURE_SETS[cfg.feature_set])].to_numpy(float) - mu) / np.where(
        sd > 0, sd, np.inf
    )
    zf = np.clip(np.where(np.isfinite(zf), zf, 0.0), -cfg.z_clip, cfg.z_clip)
    X = np.column_stack([np.ones(len(d)), zf])
    if cfg.variance_weight == "premium_share":
        key = (
            "premium_share_pow_mean"
            if "premium_share_pow_mean" in meta
            else "premium_share_sq_mean"
        )
        norm_k = float(meta[key])
        vv = raw["premium_share"].to_numpy(float) ** cfg.variance_power / norm_k
    else:
        vv = np.ones(len(d))
    yy = d["H_shadow"].to_numpy(float) * cfg.pct_per_unit
    if cfg.target_transform == "yj_loss":
        unit = raw["premium_share"].to_numpy(float) * cfg.pct_per_unit
        yy = yj(-yy / unit, cfg.yj_power)
    gmap = meta.get("group_map", {})
    for j in np.argsort(d["expiry"].to_numpy(), kind="stable"):
        tk = d["ticker"].iloc[j]
        g = gmap.get(tk)
        f_j, q_j, s2_j, df_j = st.predict_parts(X[j], tk, g)
        lam = posterior_lambda(yy[j] - f_j, q_j, vv[j], s2_j, df_j, cfg)
        st.update(X[j], tk, yy[j], vv[j], g, lam)
    loc, scale, df = st.coef_marginal(0)
    p_pos = float(student_t.sf(0.0, df, loc=loc, scale=scale))
    print(
        f"[forward] updated with N={len(d)}; intercept {loc:+.4f} (scale {scale:.4f}); "
        f"P(book mean > 0) {p_pos:.3f} (raw, no design effect)"
    )
    dest = Path(out_path) if out_path else Path(state_path).with_name("posterior_forward.npz")
    st.to_npz(dest, {**meta, "forward_n": int(len(d))})
    print(f"[forward] written {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command line: ``--forward`` updates the frozen posterior with settled paper trades."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--forward", action="store_true", help="update with settled paper trades")
    ap.add_argument("--state", help="frozen posterior (.npz) written by the scoring run")
    ap.add_argument("--features", help="parquet of the paper trades' 15:59 features")
    ap.add_argument("--dry", action="store_true", help="read the dry stores")
    ap.add_argument("--out", help="where to write the updated posterior")
    args = ap.parse_args(argv)
    if not args.forward:
        ap.error("only --forward is implemented as a command; scoring runs live in the lane")
    return forward_update(args.state, features_path=args.features, dry=args.dry, out_path=args.out)


if __name__ == "__main__":
    sys.exit(main())
