"""
research_realised_move.py
Stage 1: forecast the realised earnings-announcement move out of sample on the
WRDS event panel. Stage 2: apply the frozen forecaster to the 192-trade Databento
option book as a ranking signal (``richness = implied_move / E_hat[realised_move]``)
and compare it against the existing term-structure gate.

The project's term-structure gate (``iv_term_spread`` trailing-percentile filter)
forecasts only the implied side of a short straddle's edge (implied move minus
realised move). This script builds the missing half: a cross-sectional,
strictly ex-ante forecast of the realised move, fit once on 1996-2011 and frozen
before it ever sees the 2012-2024 holdout or the option book. Stage 1 is powered
(N ~ 99k holdout events); Stage 2 is not (N = 192) and is reported as exploratory
only, per the project's standing √252-annualisation and small-N-significance
failure modes (see repository CLAUDE.md).

Usage
-----
Run::

    python -m scripts.research_realised_move

Outputs (``outputs/research/``)
--------------------------------
``rmove_model.csv``        Frozen Stage-1 OLS coefficients, HC1 t-stats.
``rmove_oos.csv``           Stage-1 out-of-sample decile table + scalar OOS stats.
``rmove_straddle_rank.csv`` Stage-2 rank-correlation and top-quintile book stats.
``rmove.png``                Stage-1 calibration and rank-correlation figure.

References
----------
Bakshi, G., & Kapadia, N. (2003). Delta-hedged gains and the negative market
volatility risk premium. *Review of Financial Studies*, 16(2), 527-566.
Carr, P., & Wu, L. (2009). Variance risk premiums. *Review of Financial
Studies*, 22(3), 1311-1341.
Kandel, S., & Pearson, N. D. (1995). Differential interpretation of public
signals and trade in speculative markets. *Journal of Political Economy*,
103(4), 831-872.
Andersen, T. G., Bollerslev, T., Diebold, F. X., & Ebens, H. (2003). The
distribution of realized stock return volatility. *Journal of Financial
Economics*, 61(1), 43-76.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

from earnings_iv_crush.data.wrds_panel import FIT_END, HOLDOUT_START
from earnings_iv_crush.engine import event_study

# ── constants ─────────────────────────────────────────────────────────────────
OUT_DIR = Path("outputs/research")
PANEL_EVENTS = OUT_DIR / "panel_events.parquet"
PANEL_DAILY = OUT_DIR / "panel_daily.parquet"
HOLD_TO_EXPIRY = OUT_DIR / "hold_to_expiry.csv"
DATABENTO_EVENTS = OUT_DIR / "events_megacap_databento.parquet"

LOG_EPS = 1e-4  # additive offset so log(y) is defined at y=0 (right-skewed, non-negative target)
TRAILING_N = 4  # firm's own prior-announcement window for trailing_move_mean/std
VOL_WINDOW = 60  # trailing trading days for trailing_vol_60d
TRADING_DAYS_PER_YEAR = (
    252  # project convention (ACT/365, 252 trading days); also used for t_entry->trading-days
)
N_DECILES = 10
RICHNESS_QUINTILE = (
    0.80  # top-quintile threshold, matches the existing term-gate's own q=0.80 convention
)

PREDICTOR_COLS = [
    "log1p_disp",
    "log_numest",
    "log_mktcap",
    "log_adv60",
    "trailing_move_mean",
    "trailing_move_std",
    "log1p_abs_rev",
    "trailing_vol_60d",
]


def _elapsed(label: str, t0: float) -> None:
    print(f"  [{label}] {time.time() - t0:6.1f}s")


# ── Stage 1: data assembly ───────────────────────────────────────────────────
def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the WRDS event and daily panels (no I/O elsewhere in this module)."""
    events = pd.read_parquet(PANEL_EVENTS)
    daily = pd.read_parquet(PANEL_DAILY)
    return events, daily


def attach_target(events: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Attach ``ar01`` = |AR[0,+1]|, the realised announcement move.

    ``event_study.car`` expects ``events['day0']`` to be the trading-day
    *ordinal*; the panel stores the calendar date under that name and the
    ordinal under ``day0_ordinal``, so the columns are swapped only for this
    call (the panel's own ``day0``/``day0_ordinal`` are left untouched).
    """
    for_car = events.rename(columns={"day0": "day0_date", "day0_ordinal": "day0"})
    ar = event_study.car(daily, for_car, 0, 1, adjust="mkt")
    out = events.copy()
    out["ar_0_1"] = ar.to_numpy()
    out["ar01"] = out["ar_0_1"].abs()
    return out


def attach_trailing_vol(events: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Attach ``trailing_vol_60d``: the firm's own realised daily-return vol over
    the 60 trading days ending day0-2, annualised by sqrt(252) (correct here, this
    *is* a daily series, unlike the sparse event book elsewhere in this project).
    """
    d = daily.sort_values(["permno", "ordinal"]).copy()
    d["vol60"] = d.groupby("permno")["ret_adj"].transform(
        lambda s: s.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std()
    )
    lookup = d[["permno", "ordinal", "vol60"]].rename(columns={"ordinal": "day0_minus_2"})
    out = events.copy()
    out["day0_minus_2"] = out["day0_ordinal"] - 2
    out = out.merge(lookup, on=["permno", "day0_minus_2"], how="left")
    out["trailing_vol_60d"] = out["vol60"] * np.sqrt(TRADING_DAYS_PER_YEAR)
    return out.drop(columns=["day0_minus_2", "vol60"])


def attach_trailing_move(events: pd.DataFrame) -> pd.DataFrame:
    """Attach ``trailing_move_mean``/``trailing_move_std``: mean/std of the firm's
    own prior :data:`TRAILING_N` announcement moves, strictly excluding the
    current event (``shift(1)`` before the rolling window, no look-ahead).
    """
    out = events.sort_values(["permno", "day0_ordinal"]).copy()
    g = out.groupby("permno")["ar01"]
    out["trailing_move_mean"] = g.transform(
        lambda s: s.shift(1).rolling(TRAILING_N, min_periods=TRAILING_N).mean()
    )
    out["trailing_move_std"] = g.transform(
        lambda s: s.shift(1).rolling(TRAILING_N, min_periods=TRAILING_N).std()
    )
    return out


def build_design(events: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Attach the transformed predictor columns and full-sample sector dummies.

    Sector dummies are built once on the whole sample (not separately per
    fit/holdout split) purely so both slices share an identical, aligned column
    set, this is a bookkeeping choice, not a source of look-ahead, since each
    event's own ``siccd`` is static and known at day0.
    """
    out = events.copy()
    out["log1p_disp"] = np.log1p(out["disp"])
    out["log_numest"] = np.log(out["numest"])
    out["log_mktcap"] = np.log(out["mktcap"])
    out["log_adv60"] = np.log(out["adv60"])
    out["log1p_abs_rev"] = np.log1p(out["rev"].abs())
    sic1 = (out["siccd"] // 1000).astype(int).astype(str)
    dummies = pd.get_dummies(sic1, prefix="sic", drop_first=True, dtype=float)
    out = pd.concat([out, dummies], axis=1)
    return out, list(dummies.columns)


def funnel(events: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, list[str], dict]:
    """Assemble the Stage-1 estimation sample and print the row-count funnel."""
    fn: dict[str, int] = {"panel_events": len(events)}

    ev = attach_target(events, daily)
    fn["ar01_computed"] = int(ev["ar01"].notna().sum())
    ev = ev[ev["ar01"].notna()].copy()

    ev = attach_trailing_vol(ev, daily)
    fn["trailing_vol_available"] = int(ev["trailing_vol_60d"].notna().sum())
    ev = ev[ev["trailing_vol_60d"].notna()].copy()

    ev = attach_trailing_move(ev)
    has_trailing = ev["trailing_move_mean"].notna() & ev["trailing_move_std"].notna()
    fn[">=4 prior announcements"] = int(has_trailing.sum())
    ev = ev[has_trailing].copy()

    ev, sic_cols = build_design(ev)
    fn["final estimation sample"] = len(ev)

    ev["y_log"] = np.log(ev["ar01"] + LOG_EPS)
    fn["fit (<= " + FIT_END + ")"] = int((ev["anndats"] <= FIT_END).sum())
    fn["holdout (>= " + HOLDOUT_START + ")"] = int((ev["anndats"] >= HOLDOUT_START).sum())

    print("STAGE 1 FUNNEL")
    for k, v in fn.items():
        print(f"  {k:<40s} {v:>10,}")

    return ev, sic_cols, fn


# ── Stage 1: model ────────────────────────────────────────────────────────────
def fit_frozen_model(
    ev: pd.DataFrame, sic_cols: list[str]
) -> tuple[sm.regression.linear_model.RegressionResultsWrapper, list[str]]:
    """OLS on the fit half (<= FIT_END) only, HC1 robust covariance. Coefficients
    frozen here are never re-estimated on the holdout or the option book."""
    cols = PREDICTOR_COLS + sic_cols
    fit_mask = ev["anndats"] <= FIT_END
    X_fit = sm.add_constant(ev.loc[fit_mask, cols].astype(float))
    y_fit = ev.loc[fit_mask, "y_log"]
    model = sm.OLS(y_fit, X_fit).fit(cov_type="HC1")
    return model, cols


def score_all(
    ev: pd.DataFrame, model: sm.regression.linear_model.RegressionResultsWrapper, cols: list[str]
) -> pd.DataFrame:
    """Apply the frozen coefficients to every row (fit and holdout alike)."""
    out = ev.copy()
    X_all = sm.add_constant(out[cols].astype(float), has_constant="add")
    X_all = X_all[model.params.index]  # exact column order/order the model was fit on
    out["pred_log"] = model.predict(X_all)
    out["pred_ar01"] = np.exp(out["pred_log"]) - LOG_EPS
    return out


def oos_report(ev: pd.DataFrame, model, in_sample_r2: float) -> tuple[dict, pd.DataFrame]:
    """OOS R^2 (log scale), OOS Spearman rho, and the decile calibration table."""
    hold = ev[ev["anndats"] >= HOLDOUT_START].copy()
    y, yhat = hold["y_log"].to_numpy(), hold["pred_log"].to_numpy()
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2_oos = 1.0 - ss_res / ss_tot

    rho, pval = spearmanr(hold["pred_ar01"], hold["ar01"])

    hold["decile"] = pd.qcut(hold["pred_ar01"], N_DECILES, labels=False, duplicates="drop") + 1
    dec = (
        hold.groupby("decile")
        .agg(
            n=("ar01", "size"), mean_predicted=("pred_ar01", "mean"), mean_realised=("ar01", "mean")
        )
        .reset_index()
    )
    dec_rho, dec_pval = spearmanr(dec["decile"], dec["mean_realised"])

    summary = {
        "n_fit": int((ev["anndats"] <= FIT_END).sum()),
        "n_holdout": int(len(hold)),
        "in_sample_r2_log": in_sample_r2,
        "oos_r2_log": r2_oos,
        "oos_spearman_rho": float(rho),
        "oos_spearman_pvalue": float(pval),
        "decile_spearman_rho": float(dec_rho),
        "decile_spearman_pvalue": float(dec_pval),
    }
    for k, v in summary.items():
        dec[k] = v
    return summary, dec


def make_figure(dec: pd.DataFrame, hold: pd.DataFrame, summary: dict, path: Path) -> None:
    """Calibration (decile) panel + a downsampled predicted-vs-realised scatter."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    ax.plot(dec["decile"], dec["mean_predicted"], "o-", label="mean predicted |AR|")
    ax.plot(dec["decile"], dec["mean_realised"], "s-", label="mean realised |AR|")
    ax.set_xlabel("decile of predicted move (1 = smallest)")
    ax.set_ylabel("|AR[0,+1]|")
    ax.set_title(f"OOS calibration (decile Spearman={summary['decile_spearman_rho']:.2f})")
    ax.legend()

    ax = axes[1]
    rng = np.random.default_rng(0)
    n = len(hold)
    idx = rng.choice(n, size=min(20_000, n), replace=False)
    s = hold.iloc[idx]
    ax.scatter(s["pred_ar01"], s["ar01"], s=3, alpha=0.15)
    lim = float(np.nanpercentile(hold["ar01"], 99.5))
    ax.plot([0, lim], [0, lim], "r--", lw=1)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("predicted |AR[0,+1]|")
    ax.set_ylabel("realised |AR[0,+1]|")
    ax.set_title(
        f"OOS holdout (rho={summary['oos_spearman_rho']:.3f}, R2_log={summary['oos_r2_log']:.3f})"
    )

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ── Stage 2: option book application ─────────────────────────────────────────
def load_option_book() -> pd.DataFrame:
    """Join the 192-trade ledger to its per-event implied-move/term-spread source.

    ``hold_to_expiry.csv`` carries the realised straddle P&L (``rom_plus1``,
    ``rom_hold``) but not the implied move; ``events_megacap_databento.parquet``
    carries ``implied_move`` and ``iv_term_spread`` (the existing gate signal) for
    the same (ticker, entry_date) pairs. All 192 rows join 1:1 on that key.
    """
    hte = pd.read_csv(HOLD_TO_EXPIRY, parse_dates=["entry_date", "expiry"])
    edb = pd.read_parquet(DATABENTO_EVENTS)
    edb["announce_date"] = pd.to_datetime(edb["announce_date"])
    edb["entry_date"] = pd.to_datetime(edb["entry_date"])
    opt = hte.merge(edb, on=["ticker", "entry_date"], how="left")
    n_missing = int(opt["implied_move"].isna().sum())
    print(
        f"option book: {len(hte)} trades, {n_missing} missing implied_move/iv_term_spread after join"
    )
    return opt


def join_forecaster(opt: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    """Join the 192 option events to the frozen Stage-1 forecaster on
    (ibes_ticker, anndats) == (ticker, announce_date)."""
    lookup = scored[["ibes_ticker", "anndats", "permno", "pred_ar01"]].rename(
        columns={"ibes_ticker": "ticker", "anndats": "announce_date"}
    )
    joined = opt.merge(lookup, on=["ticker", "announce_date"], how="left")
    n_matched = int(joined["pred_ar01"].notna().sum())
    print(f"JOIN FUNNEL: {len(opt)} option events -> {n_matched} matched to the Stage-1 forecaster")
    if n_matched < 150:
        print(f"  WARNING: matched count {n_matched} < 150; proceeding with what matched.")
    return joined


def compute_richness(joined: pd.DataFrame) -> pd.DataFrame:
    """``richness = implied_move (2-day horizon) / E_hat[realised_move]``.

    ``implied_move`` is quoted over the option's own tenor (``t_entry``, years);
    ``pred_ar01`` is a 2-trading-day forecast. The conservative common-horizon
    choice: scale the implied move by sqrt(2 / dte_trading_days), with
    dte_trading_days = t_entry * 252 (the project's stated ACT/365, 252-trading-
    day convention), rather than rescale the realised-move side.
    """
    out = joined.copy()
    dte_trading_days = out["t_entry"] * TRADING_DAYS_PER_YEAR
    out["implied_move_2day"] = out["implied_move"] * np.sqrt(2.0 / dte_trading_days)
    out["richness"] = out["implied_move_2day"] / out["pred_ar01"]
    return out


def stage2_report(matched: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rank correlations (richness and the existing term gate) and top-quintile books."""
    rows = []
    for sig, label in [
        ("richness", "richness (Stage-1 forecaster)"),
        ("iv_term_spread", "term gate (benchmark)"),
    ]:
        rho_p1, p_p1 = spearmanr(matched[sig], matched["rom_plus1"])
        rho_h, p_h = spearmanr(matched[sig], matched["rom_hold"])
        thresh = matched[sig].quantile(RICHNESS_QUINTILE)
        top_q = matched[matched[sig] >= thresh]
        book = event_study.summarise_book(
            top_q["rom_plus1"], top_q["entry_date"], f"{sig}_top_quintile"
        )
        rows.append(
            {
                "signal": label,
                "spearman_rho_rom_plus1": rho_p1,
                "spearman_pvalue_rom_plus1": p_p1,
                "spearman_rho_rom_hold": rho_h,
                "spearman_pvalue_rom_hold": p_h,
                "quintile_threshold": thresh,
                **{f"quintile_{k}": v for k, v in book.items() if k != "label"},
            }
        )
    df = pd.DataFrame(rows)
    return df, {"n_matched": len(matched)}


# ── orchestration ──────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", type=Path, default=OUT_DIR, help="output directory for artefacts"
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("loading panel (ETA ~1-2 min: 27M-row daily panel + 199k-row event panel)")
    events, daily = load_panel()
    _elapsed("load", t0)

    t1 = time.time()
    ev, sic_cols, fn = funnel(events, daily)
    _elapsed("funnel/predictors", t1)

    t2 = time.time()
    model, cols = fit_frozen_model(ev, sic_cols)
    scored = score_all(ev, model, cols)
    _elapsed("fit + score", t2)

    coef_table = pd.DataFrame(
        {
            "predictor": model.params.index,
            "coef": model.params.values,
            "se_hc1": model.bse.values,
            "t_stat": model.tvalues.values,
            "p_value": model.pvalues.values,
        }
    )
    coef_path = args.out_dir / "rmove_model.csv"
    coef_table.to_csv(coef_path, index=False)

    summary, dec = oos_report(scored, model, float(model.rsquared))
    oos_path = args.out_dir / "rmove_oos.csv"
    dec.to_csv(oos_path, index=False)

    fig_path = args.out_dir / "rmove.png"
    make_figure(dec, scored[scored["anndats"] >= HOLDOUT_START], summary, fig_path)

    print("\nSTAGE 1 RESULT")
    for k, v in summary.items():
        print(f"  {k:<28s} {v}")
    print("\nOOS DECILE TABLE")
    print(dec[["decile", "n", "mean_predicted", "mean_realised"]].to_string(index=False))
    print("\nFROZEN COEFFICIENTS")
    print(coef_table.to_string(index=False))

    validated = summary["oos_spearman_rho"] >= 0.30 and summary["decile_spearman_rho"] >= 0.8
    print(
        f"\nSTAGE 1 ACCEPTANCE: {'PASS' if validated else 'FAIL'} "
        f"(rho={summary['oos_spearman_rho']:.3f} >= 0.30, decile_rho={summary['decile_spearman_rho']:.3f} >= 0.8)"
    )

    # ── Stage 2 ──
    t3 = time.time()
    opt = load_option_book()
    joined = join_forecaster(opt, scored)
    matched = compute_richness(joined[joined["pred_ar01"].notna()].copy())
    rank_table, meta = stage2_report(matched)
    rank_path = args.out_dir / "rmove_straddle_rank.csv"
    rank_table.to_csv(rank_path, index=False)
    _elapsed("stage 2", t3)

    print("\nSTAGE 2 RESULT (EXPLORATORY, N = {})".format(meta["n_matched"]))
    print(rank_table.to_string(index=False))

    print(f"\ntotal elapsed: {time.time() - t0:.1f}s")
    print(f"artefacts: {coef_path}, {oos_path}, {rank_path}, {fig_path}")


if __name__ == "__main__":
    main()
