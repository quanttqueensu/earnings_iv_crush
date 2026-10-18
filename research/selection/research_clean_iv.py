"""
research_clean_iv.py
Does the event-stripped ("clean") implied volatility forecast where post-event IV settles?

The event-cleaning method separates front-month implied variance into a diffusive baseline
and a one-off announcement jump, and claims the baseline is where implied volatility
converges once the event has passed. That claim is testable on the marked panel without
any selection rule: the post-event IV of the contract the book actually sold is observed at
exit, so each candidate baseline can be scored as a forecast of it.

Three things are measured, none of which sorts events on a candidate signal (that is the
section 2.1 pre-registration's job and must not be informed by a sort here):

1. Construction. The panel's ``event_var = (f^2 - b^2) t_f`` treats the back expiry as
   event-free, but the back expiry is the first listed at least 21 days beyond the front
   and so always lies after the announcement. With both expiries carrying the same jump
   variance E and the same diffusive variance s^2,

       f^2 t_f = s^2 t_f + E,    b^2 t_b = s^2 t_b + E
       E   = (f^2 - b^2) t_f t_b / (t_b - t_f)
       s^2 = (b^2 t_b - f^2 t_f) / (t_b - t_f)

   so the panel's E is low by the tenor-dependent factor t_b / (t_b - t_f). The section
   reports how far the corrected ratio's ranking departs from the one already tested.
   At-entry quantities only, both blocks.
2. Convergence. Five forecasts of exit IV (front IV unchanged, back IV, the corrected
   two-expiry baseline s, a history-cleaned baseline built from the name's own prior
   announcement moves, and trailing realised vol), scored on bias, dispersion and a
   Mincer-Zarnowitz regression. Discovery block only.
3. Drivers. Return on margin decomposed into premium, gap, residual value and cost, and
   regressed on the event surprise (realised over implied move) and the diffusive surprise
   (exit IV over the clean baseline), to say which of the two carries the P&L. Discovery
   block only.

The history-cleaned baseline follows the method as practised, with two deliberate
departures. Event size is the close-to-close move across the announcement rather than a
Parkinson range, because a range estimator sees only the trading session and an earnings
move is mostly the overnight gap. Prior events are averaged in variance space, because
variance is the additive quantity and averaging volatilities biases the jump down
(Jensen's inequality).

The back tenor is not stored on the panel. It is taken as ``t_f + 21/365``, the minimum the
expiry selector allows, which gives the largest correction; for a back expiry 28 days out
the factor is smaller by at most (t_f + 28)/(t_f + 21) * 21/28 in variance.

Usage:
    python research/selection/research_clean_iv.py
    python research/selection/research_clean_iv.py --n-boot 2000

References
----------
Dubinsky, A. and Johannes, M. (2006). Fundamental Uncertainty, Earnings Announcements and
Equity Options. Working paper, Columbia University.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option Pricing of Earnings
Announcement Risks. *Review of Financial Studies* 32(2), 646-687.
Mincer, J. and Zarnowitz, V. (1969). The Evaluation of Economic Forecasts. In *Economic
Forecasts and Expectations*, NBER.
Patell, J. M. and Wolfson, M. A. (1979). Anticipated Information Releases Reflected in Call
Option Prices. *Journal of Accounting and Economics* 1(2), 117-140.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402

PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
OUT = Path("outputs/research/clean_iv")

DISCOVERY = "discovery_2019_2024"
BACK_GAP_YEARS = 21 / 365  # GlobalConfig.back_month_min_gap_days, the minimum back gap
TRADING_DAYS = 252
HALF_LIFE_EVENTS = 4.0  # recency weighting of prior events, about one year of quarters
MIN_PRIOR_EVENTS = 3  # same floor as reverse_alpha_panel.trailing_name_move
SHRINK_K = 4.0  # pseudo-events of cross-sectional prior in the shrunk denominator
NEAR_ATM = 0.01  # |log(S_exit / K)| at which the sold strike's exit IV is ATM IV
N_BOOT = 5000
SEED = 0


# ── construction ─────────────────────────────────────────────────────────────


def two_expiry_split(f: np.ndarray, b: np.ndarray, t_f: np.ndarray) -> tuple:
    """Jump variance and diffusive vol from two expiries that both contain the event.

    Returns ``(E, s)``. E is clipped at zero (an inverted structure prices no jump, it does
    not price negative variance); s is NaN where the implied diffusive variance is
    non-positive, which happens when the front is so rich that no flat baseline fits both.
    """
    t_b = t_f + BACK_GAP_YEARS
    e = np.maximum(f**2 - b**2, 0.0) * t_f * t_b / (t_b - t_f)
    s2 = (b**2 * t_b - f**2 * t_f) / (t_b - t_f)
    s = np.where(s2 > 0, np.sqrt(np.where(s2 > 0, s2, 1.0)), np.nan)
    return e, s


def history_jump_var(df: pd.DataFrame) -> pd.DataFrame:
    """Per-event history of the name's own prior announcement moves, strictly causal.

    Columns returned:

    ``hist_jump_var``  recency-weighted mean of excess event variance, ``move^2`` less one
                       normal session of trailing realised variance, half-life
                       ``HALF_LIFE_EVENTS`` prior events.
    ``hist_rms``       unweighted root-mean-square prior move (variance-space denominator).
    ``hist_n``         number of prior events used.
    """
    d = df.sort_values("announce_date")
    move2 = pd.to_numeric(d["realised_move"], errors="coerce").to_numpy(dtype=float) ** 2
    rv = pd.to_numeric(d["trailing_rv"], errors="coerce").to_numpy(dtype=float)
    excess = move2 - np.nan_to_num(rv) ** 2 / TRADING_DAYS
    tick = d["ticker"].to_numpy()
    dates = d["announce_date"].to_numpy()

    jump = np.full(len(d), np.nan)
    rms = np.full(len(d), np.nan)
    n_used = np.zeros(len(d), dtype=int)
    for i in range(len(d)):
        m = (tick == tick[i]) & (dates < dates[i]) & np.isfinite(move2)
        if m.sum() < MIN_PRIOR_EVENTS:
            continue
        x = excess[m][::-1]  # most recent first
        w = 0.5 ** (np.arange(len(x)) / HALF_LIFE_EVENTS)
        jump[i] = float(np.sum(w * x) / np.sum(w))
        rms[i] = float(np.sqrt(np.mean(move2[m])))
        n_used[i] = int(m.sum())
    out = pd.DataFrame({"hist_jump_var": jump, "hist_rms": rms, "hist_n": n_used}, index=d.index)
    return out.reindex(df.index)


def shrunk_rms(df: pd.DataFrame) -> np.ndarray:
    """Name RMS move shrunk toward the cross-section of strictly earlier events.

    ``w = n / (n + SHRINK_K)`` on the name's own RMS, the remainder on the RMS of every
    event announced before this one across all names. ``SHRINK_K`` is fixed, not fitted.
    """
    d = df.sort_values("announce_date")
    move2 = pd.to_numeric(d["realised_move"], errors="coerce").to_numpy(dtype=float) ** 2
    dates = d["announce_date"].to_numpy()
    own = d["hist_rms"].to_numpy(dtype=float)
    n = d["hist_n"].to_numpy(dtype=float)
    out = np.full(len(d), np.nan)
    for i in range(len(d)):
        pool = move2[(dates < dates[i]) & np.isfinite(move2)]
        if pool.size < 20 or not np.isfinite(own[i]):
            continue
        w = n[i] / (n[i] + SHRINK_K)
        out[i] = float(np.sqrt(w * own[i] ** 2 + (1 - w) * pool.mean()))
    return pd.Series(out, index=d.index).reindex(df.index).to_numpy()


def build(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach every construction to the full panel (at-entry quantities only)."""
    d = panel.copy()
    d["announce_date"] = pd.to_datetime(d["announce_date"])
    f = pd.to_numeric(d["front_atm_iv"], errors="coerce").to_numpy(dtype=float)
    b = pd.to_numeric(d["back_atm_iv"], errors="coerce").to_numpy(dtype=float)
    t_f = pd.to_numeric(d["t_entry"], errors="coerce").to_numpy(dtype=float)

    e_dj, s_dj = two_expiry_split(f, b, t_f)
    d["event_var_dj"] = e_dj
    d["implied_jump_dj"] = np.sqrt(e_dj)
    d["base_iv_dj"] = s_dj
    d["dj_correction"] = (t_f + BACK_GAP_YEARS) / BACK_GAP_YEARS

    d = d.join(history_jump_var(d))
    clean2 = f**2 - d["hist_jump_var"].to_numpy() / t_f
    d["base_iv_hist"] = np.where(clean2 > 0, np.sqrt(np.where(clean2 > 0, clean2, 1.0)), np.nan)
    d["hist_exceeds_market"] = np.isfinite(d["hist_jump_var"]) & (clean2 <= 0)

    d["shrunk_rms"] = shrunk_rms(d)
    hm = d["name_move_hist"].to_numpy(dtype=float)
    d["richness_dj_mean"] = np.where(hm > 0, d["implied_jump_dj"] / hm, np.nan)
    d["richness_dj_rms"] = np.where(d["hist_rms"] > 0, d["implied_jump_dj"] / d["hist_rms"], np.nan)
    d["richness_dj_shrunk"] = np.where(
        d["shrunk_rms"] > 0, d["implied_jump_dj"] / d["shrunk_rms"], np.nan
    )
    return d


def construction_table(d: pd.DataFrame) -> pd.DataFrame:
    """How far each corrected ratio's ranking departs from the tested ``jump_richness``."""
    rows = []
    for block, g in d.groupby("block"):
        for col in ("richness_dj_mean", "richness_dj_rms", "richness_dj_shrunk"):
            m = g[["jump_richness", col, "term_rank"]].dropna()
            top_old = m["jump_richness"] >= m["jump_richness"].quantile(0.8)
            top_new = m[col] >= m[col].quantile(0.8)
            rows.append(
                {
                    "block": block,
                    "variable": col,
                    "n": len(m),
                    "spearman_vs_jump_richness": stats.spearmanr(m["jump_richness"], m[col])[0],
                    "spearman_vs_term_rank": stats.spearmanr(m["term_rank"], m[col])[0],
                    "top_quintile_jaccard": (top_old & top_new).sum() / (top_old | top_new).sum(),
                }
            )
    return pd.DataFrame(rows)


# ── convergence ──────────────────────────────────────────────────────────────

FORECASTS = {
    "front_iv_unchanged": "front_atm_iv",
    "back_iv": "back_atm_iv",
    "base_iv_two_expiry": "base_iv_dj",
    "base_iv_history": "base_iv_hist",
    "trailing_rv": "trailing_rv",
}


def _ci(vals: np.ndarray, keys: np.ndarray, fn, n_boot: int) -> tuple[float, float]:
    idx = np.arange(len(vals), dtype=float)
    return cluster_bootstrap_ci(idx, keys, lambda i: fn(i.astype(int)), n_boot=n_boot, seed=SEED)


def convergence_table(d: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    """Score every baseline as a forecast of exit IV on one common subsample."""
    cols = list(FORECASTS.values())
    m = d[["iv_exit", "entry_date", *cols]].apply(pd.to_numeric, errors="coerce")
    m["entry_date"] = d["entry_date"]
    m = m[(m[cols + ["iv_exit"]] > 0).all(axis=1)].dropna()
    y = np.log(m["iv_exit"].to_numpy())
    keys = m["entry_date"].astype(str).to_numpy()

    rows = []
    for label, col in FORECASTS.items():
        x = np.log(m[col].to_numpy())
        err = y - x
        mz = stats.linregress(x, y)
        bias_ci = _ci(err, keys, lambda i, e=err: float(e[i].mean()), n_boot)
        slope_ci = _ci(err, keys, lambda i, x=x: float(stats.linregress(x[i], y[i]).slope), n_boot)
        rows.append(
            {
                "forecast": label,
                "n": len(m),
                "n_dates": len(np.unique(keys)),
                "bias_log": float(err.mean()),
                "bias_ci_low": bias_ci[0],
                "bias_ci_high": bias_ci[1],
                "median_abs_log_err": float(np.median(np.abs(err))),
                "rmse_log": float(np.sqrt(np.mean(err**2))),
                "mz_intercept": float(mz.intercept),
                "mz_slope": float(mz.slope),
                "mz_slope_ci_low": slope_ci[0],
                "mz_slope_ci_high": slope_ci[1],
                "mz_r2": float(mz.rvalue**2),
            }
        )
    return pd.DataFrame(rows)


# ── drivers ──────────────────────────────────────────────────────────────────


def decompose(d: pd.DataFrame) -> pd.DataFrame:
    """Per-event return on margin split into its four additive components.

    Raises if the components fail to rebuild the stored return, since a decomposition
    that does not reconcile cannot be used to attribute anything.
    """
    k = d["contracts"] * 100 / d["margin"]
    out = pd.DataFrame(index=d.index)
    out["premium"] = d["credit_mkt"] * k
    out["gap"] = -d["intr_exit"] * k
    out["residual_value"] = -(d["exit_mkt"] - d["intr_exit"]) * k
    out["cost"] = -d["cost_frozen"] / d["margin"]
    gap = (out.sum(axis=1) - d["return_on_margin"]).abs().max()
    if not np.isfinite(gap) or gap > 1e-6:
        raise ValueError(f"decomposition does not reconcile to return_on_margin (max {gap:.2e})")
    return out


def driver_table(d: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    """Standardised regression of each P&L component on the two surprises."""
    comp = decompose(d)
    s = d["base_iv_dj"]
    frame = (
        pd.DataFrame(
            {
                "event_surprise": d["realised_move"] / d["implied_move"],
                "diffusive_surprise": np.log(d["iv_exit"] / s),
                "entry_date": d["entry_date"].astype(str),
                "rom": d["return_on_margin"],
                **{c: comp[c] for c in comp.columns},
            }
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    keys = frame["entry_date"].to_numpy()
    z = frame[["event_surprise", "diffusive_surprise"]]
    x = ((z - z.mean()) / z.std(ddof=1)).to_numpy()
    xc = np.column_stack([np.ones(len(x)), x])

    def betas(idx: np.ndarray, yv: np.ndarray) -> np.ndarray:
        return np.linalg.lstsq(xc[idx], yv[idx], rcond=None)[0]

    rows = []
    for target in ("rom", "gap", "residual_value", "premium"):
        yv = frame[target].to_numpy()
        full = betas(np.arange(len(yv)), yv)
        r2 = 1 - np.sum((yv - xc @ full) ** 2) / np.sum((yv - yv.mean()) ** 2)
        for j, name in enumerate(("event_surprise", "diffusive_surprise"), start=1):
            ci = _ci(yv, keys, lambda i, j=j, yv=yv: float(betas(i, yv)[j]), n_boot)
            r2_alone = stats.pearsonr(x[:, j - 1], yv)[0] ** 2
            rows.append(
                {
                    "target": target,
                    "regressor": name,
                    "n": len(yv),
                    "beta_per_sd": float(full[j]),
                    "ci_low": ci[0],
                    "ci_high": ci[1],
                    "r2_alone": float(r2_alone),
                    "r2_joint": float(r2),
                    "spearman": float(stats.spearmanr(z.iloc[:, j - 1], yv)[0]),
                }
            )
    return pd.DataFrame(rows)


# ── entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(PANEL)
    d = build(panel)

    print("\n== 1. construction (at-entry only, both blocks)")
    print(
        "  dj_correction t_b/(t_b - t_f): median "
        f"{d['dj_correction'].median():.3f}, p10 {d['dj_correction'].quantile(0.1):.3f}, "
        f"p90 {d['dj_correction'].quantile(0.9):.3f} (variance units)"
    )
    print(f"  history exceeds market (clean IV undefined): {int(d['hist_exceeds_market'].sum())}")
    print(f"  two-expiry baseline undefined: {int(d['base_iv_dj'].isna().sum())}")
    ct = construction_table(d)
    ct.to_csv(OUT / "richness_construction.csv", index=False)
    print(ct.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    disc = d[d["block"] == DISCOVERY].copy()
    if disc.empty:
        raise SystemExit("discovery block missing from panel - refusing to score an empty frame")

    # Exit IV is the IV of the strike sold, not post-event ATM IV. After a gap that strike
    # sits away from the money days from expiry, where the smile and an unstable inversion
    # on intrinsic-heavy contracts dominate. Only events finishing within NEAR_ATM of the
    # strike measure the quantity the convergence claim is about. The restriction conditions
    # on the realised move, so it measures the target; it is not a tradeable subset.
    mny = np.abs(np.log(disc["spot_exit"] / disc["strike"]))
    near = disc[mny <= NEAR_ATM]
    print(f"\n== 2. convergence of exit IV, discovery block (panel N={len(disc)})")
    tables = []
    for label, frame in (("all_events", disc), (f"exit_within_{NEAR_ATM:.0%}_of_strike", near)):
        cv = convergence_table(frame, args.n_boot)
        cv.insert(0, "sample", label)
        tables.append(cv)
        print(f"  -- {label}")
        print(cv.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    pd.concat(tables).to_csv(OUT / "convergence.csv", index=False)

    print("\n== 3. P&L drivers, discovery block")
    dt = driver_table(disc, args.n_boot)
    dt.to_csv(OUT / "drivers.csv", index=False)
    print(dt.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    d.to_parquet(OUT / "panel_clean_iv.parquet")
    print(f"\n  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
