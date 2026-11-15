"""
lib.py
Lane D: a hierarchical, time-varying model of each name's scheduled earnings-jump variance, its
model-fair event straddle, and the scoring helpers (within-cell residual value, cell-matched
random null, date-clustered intervals, trial log).

The model, in the spirit of Dubinsky, Johannes, Kaeck and Seeger (2019): the reaction-session log
return is r = J + e, with e the ordinary daily diffusion (variance s^2, the name's trailing daily
variance) and J ~ N(0, (m - 1) s^2) the announcement jump. The multiplier m has an inverse-gamma
prior centred on the name's industry (two-digit SIC) mean, itself shrunk towards the cross-section
mean; the prior is worth ``kappa`` announcements. Name evidence u = r^2 / s^2 is down-weighted
geometrically by announcement age (half-life ``h_name`` announcements); industry and
cross-section evidence decays in calendar time (half-life ``h_ind`` years). Everything at an
event uses strictly earlier reaction sessions. Conjugacy gives the posterior in closed form:
E[m] = (kappa m_ind + sum w u) / (kappa + sum w), alpha' = kappa/2 + 1 + sum w / 2.

Fair straddle: with the market's diffusive variance sd2 from the two-expiry split, the front
straddle is worth E_m[Black(F, K, sd2 T + max(m - 1, 0) s^2)], averaged over the posterior of m.

References
----------
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. (2019) Option pricing of earnings
    announcement risks. Review of Financial Studies 32(2), 646-687.
Efron, B. and Morris, C. (1975) Data analysis using Stein's estimator and its generalizations.
    JASA 70, 311-319.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import invgamma, norm
from scipy.stats import t as student_t

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

TRIALS = HERE / "trials.csv"
FIELDS = ["trial_id", "hypothesis", "mechanism", "block", "n", "effect", "ci_low", "ci_high", "t",
          "null_pct", "basis", "verdict", "label"]
BLOCKS = {"discovery": (2019, 2024), "heldout": (2013, 2018), "heldout2": (2025, 2026)}
N_BOOT = 2000
SEED = 0
MIN_SIDE = 2
N_QUAD = 24  # quantile nodes for the posterior average of the straddle value


# ── model ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Hyper:
    kappa: float = 8.0
    h_name: float = 16.0
    h_ind: float = 5.0
    kappa_ind: float = 20.0
    name_on: bool = True  # False: industry prior only (no name evidence)
    ind_on: bool = True  # False: name evidence shrunk straight to the cross-section


def run_model(hist: pd.DataFrame, hp: Hyper) -> pd.DataFrame:
    """Causal posterior of the variance multiplier at every announcement in ``hist``.

    Returns ``hist`` with columns m_prior, Em, alpha, beta, w_name (effective name evidence),
    pred_var (E[m] s^2, the predicted reaction-session variance) and ll (Student-t predictive
    log density of r).
    """
    h = hist.sort_values("day0", kind="stable").reset_index(drop=True)
    day = (h["day0"] - pd.Timestamp("1990-01-01")).dt.days.to_numpy()
    perm = h["permno"].to_numpy(int)
    ind = h["sic2"].fillna(-1).to_numpy(int)
    s = h["s"].to_numpy(float)
    r = h["r"].to_numpy(float)
    u = r * r / (s * s)
    usable = np.isfinite(u)
    n = len(h)
    m_prior = np.full(n, np.nan)
    em = np.full(n, np.nan)
    alpha = np.full(n, np.nan)
    beta = np.full(n, np.nan)
    w_name = np.zeros(n)
    dn = 0.5 ** (1.0 / hp.h_name) if np.isfinite(hp.h_name) else 1.0
    lam = np.log(2) / (hp.h_ind * 365.0) if np.isfinite(hp.h_ind) else 0.0
    nw: dict[int, list[float]] = {}
    iw: dict[int, list[float]] = {}  # [W, S, last day]
    gw = [0.0, 0.0, float(day[0])]
    i = 0
    while i < n:
        j = i
        while j < n and day[j] == day[i]:
            j += 1
        d = float(day[i])
        f = np.exp(-lam * (d - gw[2]))
        gw = [gw[0] * f, gw[1] * f, d]
        mg = gw[1] / gw[0] if gw[0] > 0 else np.nan
        for k in range(i, j):
            if hp.ind_on and ind[k] >= 0 and ind[k] in iw:
                a = iw[ind[k]]
                fi = np.exp(-lam * (d - a[2]))
                wi, si = a[0] * fi, a[1] * fi
                mi = (si + hp.kappa_ind * mg) / (wi + hp.kappa_ind)
            else:
                mi = mg
            wn, sn = nw.get(perm[k], [0.0, 0.0]) if hp.name_on else (0.0, 0.0)
            m_prior[k] = mi
            em[k] = (hp.kappa * mi + sn) / (hp.kappa + wn)
            alpha[k] = hp.kappa / 2 + 1 + wn / 2
            beta[k] = hp.kappa / 2 * mi + sn / 2
            w_name[k] = wn
        for k in range(i, j):
            if not usable[k]:
                continue
            if hp.name_on:
                a = nw.setdefault(perm[k], [0.0, 0.0])
                a[0] = a[0] * dn + 1.0
                a[1] = a[1] * dn + u[k]
            if ind[k] >= 0:
                a = iw.setdefault(ind[k], [0.0, 0.0, d])
                fi = np.exp(-lam * (d - a[2]))
                a[0], a[1], a[2] = a[0] * fi + 1.0, a[1] * fi + u[k], d
            gw[0] += 1.0
            gw[1] += u[k]
        i = j
    h["m_prior"], h["Em"], h["alpha"], h["beta"], h["w_name"] = m_prior, em, alpha, beta, w_name
    h["pred_var"] = em * s * s
    scale = np.sqrt(beta / alpha) * s
    with np.errstate(invalid="ignore"):
        h["ll"] = student_t.logpdf(r, df=2 * alpha, scale=scale)
    return h


@dataclass(frozen=True)
class HyperLog:
    gamma: float = 0.5  # elasticity of jump scale to trailing daily vol
    kappa: float = 4.0  # prior worth, in announcements
    h_name: float = 8.0  # name half-life, announcements
    h_ind: float = 5.0  # industry and cross-section half-life, years
    kappa_ind: float = 20.0
    name_on: bool = True
    s_col: str = "s"  # normaliser column: "s" (60 sessions) or "s_long" (250 sessions)
    h_lvl: float = float("nan")  # level-correction half-life, years; NaN means h_ind


FLOOR = 1e-6  # (0.1%)^2 floor on r^2 so an unchanged close does not send log r^2 to -inf


def run_model_log(hist: pd.DataFrame, hp: HyperLog) -> pd.DataFrame:
    """M2: Gaussian empirical Bayes on x = log(r^2) - gamma log(s^2), causal and decayed.

    Adds lsig2 (predicted log scale^2 at the event), c2 and c1 (causal running level
    corrections, sum r^2 / sum exp(lsig2) and sum |r| / sum exp(lsig2 / 2) over strictly earlier
    announcements, calendar-decayed at ``h_ind``), pred_var = c2 exp(lsig2), pred_abs =
    c1 exp(lsig2 / 2), and z = r / exp(lsig2 / 2), the standardised move.
    """
    h = hist.sort_values("day0", kind="stable").reset_index(drop=True)
    day = (h["day0"] - pd.Timestamp("1990-01-01")).dt.days.to_numpy()
    perm = h["permno"].to_numpy(int)
    ind = h["sic2"].fillna(-1).to_numpy(int)
    s = h[hp.s_col].to_numpy(float)
    r = h["r"].to_numpy(float)
    ls2 = np.log(s * s)
    hl = hp.h_ind if not np.isfinite(hp.h_lvl) else hp.h_lvl
    lam_c = np.log(2) / (hl * 365.0) if np.isfinite(hl) else 0.0
    x = np.log(r * r + FLOOR) - hp.gamma * ls2
    usable = np.isfinite(x)
    n = len(h)
    xhat = np.full(n, np.nan)
    wn_out = np.zeros(n)
    c2 = np.full(n, np.nan)
    c1 = np.full(n, np.nan)
    dn = 0.5 ** (1.0 / hp.h_name) if np.isfinite(hp.h_name) else 1.0
    lam = np.log(2) / (hp.h_ind * 365.0) if np.isfinite(hp.h_ind) else 0.0
    nw: dict[int, list[float]] = {}
    iw: dict[int, list[float]] = {}
    gw = [0.0, 0.0, float(day[0])]
    # sum r^2, sum exp(lsig2), sum |r|, sum exp(lsig2 / 2), last day
    cw = [0.0, 0.0, 0.0, 0.0, float(day[0])]
    i = 0
    while i < n:
        j = i
        while j < n and day[j] == day[i]:
            j += 1
        d = float(day[i])
        f = np.exp(-lam * (d - gw[2]))
        gw = [gw[0] * f, gw[1] * f, d]
        fc = np.exp(-lam_c * (d - cw[4]))
        cw = [cw[0] * fc, cw[1] * fc, cw[2] * fc, cw[3] * fc, d]
        mg = gw[1] / gw[0] if gw[0] > 0 else np.nan
        for k in range(i, j):
            if ind[k] >= 0 and ind[k] in iw:
                a = iw[ind[k]]
                fi = np.exp(-lam * (d - a[2]))
                mi = (a[1] * fi + hp.kappa_ind * mg) / (a[0] * fi + hp.kappa_ind)
            else:
                mi = mg
            wn, sn = nw.get(perm[k], [0.0, 0.0]) if hp.name_on else (0.0, 0.0)
            xhat[k] = (hp.kappa * mi + sn) / (hp.kappa + wn)
            wn_out[k] = wn
            c2[k] = cw[0] / cw[1] if cw[1] > 0 else np.nan
            c1[k] = cw[2] / cw[3] if cw[3] > 0 else np.nan
        for k in range(i, j):
            if not usable[k]:
                continue
            if hp.name_on:
                a = nw.setdefault(perm[k], [0.0, 0.0])
                a[0] = a[0] * dn + 1.0
                a[1] = a[1] * dn + x[k]
            if ind[k] >= 0:
                a = iw.setdefault(ind[k], [0.0, 0.0, d])
                fi = np.exp(-lam * (d - a[2]))
                a[0], a[1], a[2] = a[0] * fi + 1.0, a[1] * fi + x[k], d
            gw[0] += 1.0
            gw[1] += x[k]
            lp = xhat[k] + hp.gamma * ls2[k]
            if np.isfinite(lp):
                cw[0] += r[k] * r[k]
                cw[1] += np.exp(lp)
                cw[2] += abs(r[k])
                cw[3] += np.exp(lp / 2)
        i = j
    h["xhat"], h["w_name"], h["c2"], h["c1"] = xhat, wn_out, c2, c1
    h["lsig2"] = xhat + hp.gamma * ls2
    h["pred_var"] = c2 * np.exp(h["lsig2"])
    h["pred_abs"] = c1 * np.exp(h["lsig2"] / 2)
    h["z"] = r / np.exp(h["lsig2"] / 2)
    h["xres"] = x - xhat
    return h


def shape_pool(h: pd.DataFrame, year: int, n_nodes: int = 200) -> np.ndarray:
    """Quantile nodes of standardised moves z from announcements before 1 January ``year``."""
    z = h.loc[(h["day0"] < pd.Timestamp(f"{year}-01-01")) & np.isfinite(h["z"]), "z"].to_numpy()
    q = (np.arange(n_nodes) + 0.5) / n_nodes
    return np.quantile(z, q)


def model_price_shape(
    fwd: np.ndarray, k: np.ndarray, t_diff: np.ndarray, sd2: np.ndarray, sig: np.ndarray,
    znodes: np.ndarray,
) -> np.ndarray:
    """Straddle value with an empirical jump J = sig z (z over the nodes), forward-martingale,
    plus Black diffusion of variance sd2 * t_diff for the rest of the tenor."""
    jj = sig[:, None] * znodes[None, :]
    adj = np.log(np.exp(jj).mean(axis=1))
    out = np.zeros_like(fwd, dtype=float)
    for c in range(znodes.size):
        fk = fwd * np.exp(jj[:, c] - adj)
        out += black_straddle(fk, k, sd2 * t_diff)
    return out / znodes.size


def black_straddle(fwd: np.ndarray, k: np.ndarray, tv: np.ndarray) -> np.ndarray:
    """Undiscounted Black straddle per share for total log variance ``tv``."""
    sd = np.sqrt(np.maximum(tv, 1e-12))
    d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    call = fwd * norm.cdf(d1) - k * norm.cdf(d2)
    put = k * norm.cdf(-d2) - fwd * norm.cdf(-d1)
    return call + put


def model_price(
    fwd: np.ndarray,
    k: np.ndarray,
    t: np.ndarray,
    sd2: np.ndarray,
    s: np.ndarray,
    alpha: np.ndarray,
    beta: np.ndarray,
    *,
    posterior: bool = True,
) -> np.ndarray:
    """Model-fair front straddle under the market diffusive variance and the jump posterior."""
    base = sd2 * t
    if not posterior:
        em = beta / (alpha - 1)
        return black_straddle(fwd, k, base + np.maximum(em - 1, 0) * s * s)
    q = (np.arange(N_QUAD) + 0.5) / N_QUAD
    out = np.zeros_like(fwd, dtype=float)
    for qq in q:
        m = invgamma.ppf(qq, alpha, scale=beta)
        out += black_straddle(fwd, k, base + np.maximum(m - 1, 0) * s * s)
    return out / N_QUAD


# ── scoring ─────────────────────────────────────────────────────────────────


def cell_delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell treated-minus-control differences."""
    num = den = 0.0
    for v in np.unique(c):
        m = c == v
        k = int((f & m).sum())
        if k >= MIN_SIDE and int((~f & m).sum()) >= MIN_SIDE:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def score_flag(
    y: np.ndarray, f: np.ndarray, c: np.ndarray, dates: pd.Series
) -> dict:
    """Within-cell residual value of a treated flag: delta, date-clustered CI, t, cell null."""
    keys = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    delta = cell_delta(y, f, c)
    rng = np.random.default_rng(SEED)
    uniq, inv = np.unique(keys, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(uniq.size)]
    boot = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate([members[k] for k in rng.integers(0, uniq.size, uniq.size)])
        boot[b] = cell_delta(y[idx], f[idx], c[idx])
    groups = [np.flatnonzero(c == v) for v in np.unique(c)]
    counts = [int(f[g].sum()) for g in groups]
    null = np.empty(N_BOOT)
    for b in range(N_BOOT):
        g2 = np.zeros_like(f)
        for g, k in zip(groups, counts, strict=True):
            if k:
                g2[rng.choice(g, k, replace=False)] = True
        null[b] = cell_delta(y, g2, c)
    sd = np.nanstd(boot, ddof=1)
    return {
        "delta": float(delta),
        "lo": float(np.nanpercentile(boot, 2.5)),
        "hi": float(np.nanpercentile(boot, 97.5)),
        "t": float(delta / sd) if sd > 0 else float("nan"),
        "null_pct": float(100.0 * (null[np.isfinite(null)] < delta).mean()),
        "n": int(len(y)),
        "n_treated": int(f.sum()),
    }


def level(x: np.ndarray, dates: pd.Series) -> tuple[float, float, float]:
    ci = date_clustered_ci(x, dates, stat=np.mean)
    return ci.point, ci.low, ci.high


def log_trial(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def causal_bins(v: np.ndarray, dates: pd.Series, n_bins: int, min_prior: int = 200) -> np.ndarray:
    """Bin 0..n_bins-1 from quantiles of strictly earlier dates; -1 if unassigned."""
    v = np.asarray(v, float)
    dd = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    out = np.full(v.size, -1, int)
    order = np.argsort(dd, kind="stable")
    qs = np.linspace(0, 1, n_bins + 1)[1:-1]
    seen: list[float] = []
    i = 0
    while i < order.size:
        j = i
        while j < order.size and dd[order[j]] == dd[order[i]]:
            j += 1
        idx = order[i:j]
        if len(seen) >= min_prior:
            cuts = np.quantile(np.asarray(seen), qs)
            for k in idx:
                if np.isfinite(v[k]):
                    out[k] = int(np.searchsorted(cuts, v[k], side="right"))
        seen.extend(float(x) for x in v[idx] if np.isfinite(x))
        i = j
    return out
