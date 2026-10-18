"""
research_crush_forecast.py
Forecast the implied-volatility crush and sell the events where it is largest.

Every one of the 1,476 recorded trials on this book asked which events to short, and all
of them are threshold rules on a selection variable. This asks a different question. The
driver attribution (``run_driver_attribution.py``) establishes that vega is the largest
positive leg, and the crush IS the vega leg, so the quantity worth forecasting is the
crush itself rather than a proxy for it.

Mechanism. The crush is not mechanical. A clean in-line print lets the event premium bleed
out and the short vega is paid in full; a result that re-rates forward uncertainty leaves
the back month elevated and the surface shifts rather than collapses, handing the vega
back. How much event premium is priced (``implied_move``), how fat-tailed the risk-neutral
distribution is (``bkm_kurt``), how rich implied sits to realised (``vol_premium``), the
term shape (``iv_term_spread``) and recent realised volatility (``trailing_rv``) are all
observable at entry and jointly forecast which regime the print lands in.

Phases, each with a kill gate that is checked before the next runs:

  1  scale     refit the expanding-window crush forecast on ~6,600 pooled events rather
               than the prototype's 126. Kill if the out-of-sample R-squared against the
               prevailing-mean benchmark does not stay positive.
  2  orthog    ``iv_term_spread`` is one of the five features, so the forecast could be
               the frozen term gate re-expressed. Residualise the forecast on the term
               spread and refit with the term spread dropped entirely. Kill if the tercile
               ordering does not survive. This runs BEFORE the holdout so a good holdout
               cannot excuse a failed orthogonality check.
  3  holdout   fit on 2019-2024, freeze every coefficient and breakpoint, apply without
               refitting to the 1,130-event 2013-2018 block. That block is the right test
               precisely because the frozen spec failed on it (per-trade Sharpe -0.005337).

Marking basis. ``build_ledger`` prices both legs from the event table's own implied
volatilities under Black-Scholes, so the levels are model marks, not traded fills. Absolute
Sharpes from this path are inflated and only the RELATIVE ordering across terciles should
be read. Costs are charged two ways and both are reported: the ``CostModel`` stack, and the
project's measured 11.6%-of-premium round-trip break-even.

Inference. Bootstrap confidence intervals resample whole announcement dates, because names
reporting on one day share the tape and are not independent draws.

Usage:
    python research/selection/research_crush_forecast.py
    python research/selection/research_crush_forecast.py --phase 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.pnl import build_ledger  # noqa: E402

OUT = Path("outputs/research")

DISCOVERY = {
    "broad_2024": OUT / "events_broad_full.parquet",
    "broad_2025": OUT / "events_broad_oos_2025.parquet",
    "broad_v2": OUT / "events_broad_v2.parquet",
    "megacap_v2": OUT / "events_megacap_v2.parquet",
}
HOLDOUT = Path("data/processed/events_megacap_quotes_2013_2018.parquet")

# Tables excluded and why. `events_megacap_databento` and its _oos twin report iv_exit
# ABOVE iv_entry on 62.6% of events (median 0.563 against 0.477), against this project's
# own established 98.1% fall, and their crush correlates -0.65 with the absolute move.
# Since the straddle return is also a function of the move, any sort on a crush computed
# from them is a sort on the move and is circular. The defect is in the Databento chain
# source rather than in `real_events.build_execution_events`, which produces the correct
# sign on every other table, so repairing them means rebuilding exit IVs from the raw OPRA
# chains. Excluded rather than patched.
EXCLUDED = {
    "events_megacap_databento.parquet": "iv_exit > iv_entry on 62.6% of events",
    "events_megacap_databento_oos.parquet": "same defect, 65.7%",
    "events_megacap_full.parquet": "IV falls on only 25.3% of events",
}

# A table must show the crush falling on at least this fraction of events to be used.
# The project's headline is 98.1%; anything near or below a coin flip is not measuring
# a crush.
MIN_FRAC_IV_FELL = 0.80

# At-entry only. Nothing here is observable after the print.
FEATURES = ["implied_move", "bkm_kurt", "vol_premium", "iv_term_spread", "trailing_rv"]
MIN_HIST = 30  # strictly-earlier events required before the forecast predicts
N_BUCKETS = 3
N_BOOT = 10000
SEED = 0
PREMIUM_COST = 0.116  # measured round-trip break-even as a fraction of premium

CARRY = [*FEATURES, "announce_date", "realised_move"]


# ── data ─────────────────────────────────────────────────────────────────────


def load_book(path: Path, label: str, costs: CostModel | None) -> pd.DataFrame:
    """Price every event in a table, ungated, and carry its at-entry features through.

    Deliberately ungated. The prototype fit its forecast on a book the term and skew gates
    had already selected, which makes the forecast's own contribution impossible to read.
    """
    ev = pd.read_parquet(path)
    ev = ev.dropna(subset=["iv_entry", "iv_exit", "spot_entry", "spot_exit", "strike"])
    have = [c for c in CARRY if c in ev.columns]
    led = build_ledger(ev, costs=costs)
    if led.empty:
        raise RuntimeError(f"{label}: build_ledger returned nothing")
    keys = ["ticker", "entry_date"]
    led = led.merge(ev[[*keys, *have]].drop_duplicates(keys), on=keys, how="left")
    led["source"] = label

    iv_e = pd.to_numeric(led["iv_entry"], errors="coerce")
    iv_x = pd.to_numeric(led["iv_exit"], errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        led["crush"] = np.where(iv_e > 0, (iv_e - iv_x) / iv_e, np.nan)

    # Cost is charged EXACTLY ONCE. ``build_ledger`` is called commission-only
    # (costs=None) and the measured 11.6%-of-premium round-trip break-even is then
    # subtracted here. Passing a CostModel as well would charge the spread twice and
    # manufacture a negative; that mistake was made and caught on the first run.
    if "entry_credit" in led.columns and "pnl" in led.columns:
        cred = pd.to_numeric(led["entry_credit"], errors="coerce")
        led["ret_prem"] = np.where(
            cred > 0, pd.to_numeric(led["pnl"], errors="coerce") / cred, np.nan
        )
        led["net_prem"] = led["ret_prem"] - PREMIUM_COST
    led["announce_date"] = pd.to_datetime(led["announce_date"], errors="coerce")

    # Sanity gate. Refuse a table whose crush does not behave like a crush, rather than
    # letting it into the pool and discovering afterwards that the result was circular.
    cr = led["crush"].dropna()
    frac_fell = float((cr > 0).mean()) if len(cr) else float("nan")
    mv = pd.to_numeric(led.get("realised_move"), errors="coerce").abs()
    pair = pd.DataFrame({"c": led["crush"], "m": mv}).dropna()
    corr_mv = float(pair.corr().iloc[0, 1]) if len(pair) > 2 else float("nan")
    flag = "" if frac_fell >= MIN_FRAC_IV_FELL else "   <-- REJECTED"
    print(
        f"  {label:18s} {len(led):5d} trades  {led['ticker'].nunique():4d} names  "
        f"IVfell={frac_fell:.3f}  corr(crush,|mv|)={corr_mv:+.3f}{flag}"
    )
    if frac_fell < MIN_FRAC_IV_FELL:
        raise ValueError(
            f"{label}: IV falls on only {frac_fell:.1%} of events, below the "
            f"{MIN_FRAC_IV_FELL:.0%} floor. This table is not measuring a crush."
        )
    return led


# ── forecast ─────────────────────────────────────────────────────────────────


def expanding_forecast(
    df: pd.DataFrame, features: list[str], min_hist: int = MIN_HIST
) -> tuple[pd.DataFrame, float, float]:
    """Expanding-window OLS forecast of the crush from strictly earlier events.

    Mirrors ``scripts/prototypes/crush_completeness.predict_crush_expanding``: for each
    event only rows strictly before it in announcement order enter the fit, and the
    out-of-sample R-squared is measured against the prevailing mean rather than zero, so a
    model that merely reproduces the unconditional average scores zero rather than well.
    """
    d = df.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    y = pd.to_numeric(d["crush"], errors="coerce").to_numpy(dtype=float)
    x = d[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)

    n = len(d)
    pred = np.full(n, np.nan)
    naive = np.full(n, np.nan)
    for i in range(n):
        prior = np.arange(i)
        ok = np.isfinite(y[prior]) & np.isfinite(x[prior]).all(axis=1)
        idx = prior[ok]
        if len(idx) < min_hist or not np.isfinite(x[i]).all():
            continue
        design = np.column_stack([np.ones(len(idx)), x[idx]])
        beta, *_ = np.linalg.lstsq(design, y[idx], rcond=None)
        pred[i] = float(beta[0] + x[i] @ beta[1:])
        naive[i] = float(y[idx].mean())

    d["pred_crush"] = pred
    scored = np.isfinite(pred) & np.isfinite(y) & np.isfinite(naive)
    if scored.sum() < 2:
        return d, float("nan"), float("nan")
    sse_m = float(np.sum((y[scored] - pred[scored]) ** 2))
    sse_n = float(np.sum((y[scored] - naive[scored]) ** 2))
    r2 = 1.0 - sse_m / sse_n if sse_n > 0 else float("nan")
    corr = float(np.corrcoef(pred[scored], y[scored])[0, 1])
    return d, r2, corr


def fit_frozen(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    """One OLS fit over the whole frame, for freezing and applying elsewhere."""
    y = pd.to_numeric(df["crush"], errors="coerce").to_numpy(dtype=float)
    x = df[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(y) & np.isfinite(x).all(axis=1)
    design = np.column_stack([np.ones(ok.sum()), x[ok]])
    beta, *_ = np.linalg.lstsq(design, y[ok], rcond=None)
    return beta


# ── inference ────────────────────────────────────────────────────────────────


def date_clustered_ci(vals: pd.Series, dates: pd.Series, n_boot: int = N_BOOT) -> tuple:
    """Resample whole announcement dates; same-day names share the tape."""
    g = [v.to_numpy() for _, v in vals.groupby(dates)]
    if len(g) < 3:
        return float("nan"), float("nan"), len(g)
    rng = np.random.default_rng(SEED)
    idx = np.arange(len(g))
    means = np.array(
        [
            np.concatenate([g[i] for i in rng.choice(idx, len(idx), replace=True)]).mean()
            for _ in range(n_boot)
        ]
    )
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), len(g)


def tercile_report(df: pd.DataFrame, sig: str, ret_col: str, label: str) -> pd.DataFrame:
    """Sort on ``sig`` into terciles within announcement quarter and score each."""
    d = df.dropna(subset=[sig, ret_col, "announce_date"]).copy()
    if d.empty:
        return pd.DataFrame()
    q = d["announce_date"].dt.to_period("Q")
    d["bucket"] = d.groupby(q)[sig].transform(
        lambda s: (
            pd.qcut(s, N_BUCKETS, labels=False, duplicates="drop")
            if s.notna().sum() >= 12
            else np.nan
        )
    )
    d = d.dropna(subset=["bucket"])
    rows = []
    for b, g in d.groupby("bucket"):
        v = g[ret_col]
        lo, hi, k = date_clustered_ci(v, g["announce_date"])
        rows.append(
            {
                "label": label,
                "bucket": int(b),
                "n": len(g),
                "n_dates": k,
                "mean": v.mean(),
                "hit": float((v > 0).mean()),
                "sharpe": v.mean() / v.std(ddof=1) if v.std(ddof=1) > 0 else np.nan,
                "ci_lo": lo,
                "ci_hi": hi,
                "mean_crush": g["crush"].mean(),
            }
        )
    return pd.DataFrame(rows)


def show(tbl: pd.DataFrame) -> None:
    if tbl.empty:
        print("  (empty)")
        return
    cols = ["bucket", "n", "n_dates", "mean", "hit", "sharpe", "ci_lo", "ci_hi", "mean_crush"]
    print(tbl[cols].to_string(index=False, float_format=lambda v: f"{v:+.4f}"))


def monotone(tbl: pd.DataFrame) -> bool:
    """Does mean return rise across buckets?"""
    if tbl.empty or len(tbl) < 2:
        return False
    m = tbl.sort_values("bucket")["mean"].to_numpy()
    return bool(np.all(np.diff(m) > 0))


# ── phases ───────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="all", choices=["all", "1", "2", "3"])
    ap.add_argument("--ret", default="net_prem", help="return column to score")
    args = ap.parse_args()

    # commission-only; the 11.6% premium round trip is charged in load_book
    costs = None
    print("=== loading and pricing (ungated, commission-only + 11.6% premium cost) ===")
    books = [load_book(p, k, costs) for k, p in DISCOVERY.items()]
    disc = pd.concat(books, ignore_index=True)
    disc = disc.dropna(subset=["crush", *FEATURES])
    print(f"  DISCOVERY POOLED    {len(disc):5d} trades  {disc['ticker'].nunique():4d} names")

    results = {}

    # ── Phase 1 ──
    print("\n=== PHASE 1: scale the forecast ===")
    scored, r2, corr = expanding_forecast(disc, FEATURES)
    print(f"  OOS R-squared vs prevailing mean : {r2:+.4f}")
    print(f"  predicted vs realised crush corr : {corr:+.4f}")
    print(f"  events scored                    : {int(scored['pred_crush'].notna().sum())}")
    t1 = tercile_report(scored, "pred_crush", args.ret, "phase1_pred_crush")
    print(f"\n  return column: {args.ret} (net of the 11.6% premium round trip)")
    show(t1)
    results["phase1"] = t1
    if not np.isfinite(r2) or r2 <= 0:
        print("\n  KILL GATE FAILED: OOS R-squared is not positive at scale.")
        print("  The n=126 prototype result does not survive. Stopping.")
        _save(results)
        return
    print(f"\n  kill gate PASSED (R2={r2:+.4f} > 0); monotone terciles: {monotone(t1)}")
    if args.phase == "1":
        _save(results)
        return

    # ── Phase 2 ──
    print("\n=== PHASE 2: is it just the term gate? ===")
    no_term = [f for f in FEATURES if f != "iv_term_spread"]
    s2, r2b, corrb = expanding_forecast(disc, no_term)
    print(f"  forecast WITHOUT iv_term_spread : R2={r2b:+.4f}  corr={corrb:+.4f}")
    t2a = tercile_report(s2, "pred_crush", args.ret, "phase2_no_term_feature")
    show(t2a)

    # residualise the full forecast on the term spread
    s3 = scored.dropna(subset=["pred_crush", "iv_term_spread"]).copy()
    xt = pd.to_numeric(s3["iv_term_spread"], errors="coerce").to_numpy(dtype=float)
    yp = s3["pred_crush"].to_numpy(dtype=float)
    ok = np.isfinite(xt) & np.isfinite(yp)
    b = np.polyfit(xt[ok], yp[ok], 1)
    s3["pred_orth"] = np.nan
    s3.loc[ok, "pred_orth"] = yp[ok] - np.polyval(b, xt[ok])
    print("\n  forecast RESIDUALISED on iv_term_spread:")
    t2b = tercile_report(s3, "pred_orth", args.ret, "phase2_orthogonalised")
    show(t2b)
    results["phase2_no_term"] = t2a
    results["phase2_orth"] = t2b

    surv = monotone(t2a) or monotone(t2b)
    print(f"\n  monotone without term feature : {monotone(t2a)}")
    print(f"  monotone after residualising  : {monotone(t2b)}")
    if not surv:
        print("\n  KILL GATE FAILED: the ordering does not survive removing the term")
        print("  component. This is the frozen gate re-expressed, i.e. trial 1,477. Stopping.")
        _save(results)
        return
    print("  kill gate PASSED: the forecast carries information beyond the term spread.")
    if args.phase == "2":
        _save(results)
        return

    # ── Phase 3 ──
    print("\n=== PHASE 3: frozen application to the 2013-2018 block ===")
    fit_src = disc  # every sane discovery table; the megacap Databento set is excluded
    beta = fit_frozen(fit_src, FEATURES)
    print(f"  fitted on {len(fit_src)} events (2019-2024 megacap); coefficients frozen")
    print(
        "  " + ", ".join(f"{n}={v:+.4f}" for n, v in zip(["const", *FEATURES], beta, strict=False))
    )

    hold = load_book(HOLDOUT, "megacap_2013_2018", costs)
    hold = hold.dropna(subset=["crush", *FEATURES])
    xh = hold[FEATURES].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    hold["pred_crush"] = beta[0] + xh @ beta[1:]
    print(f"  applied to {len(hold)} holdout events, nothing refitted")

    realised_corr = float(
        np.corrcoef(hold["pred_crush"], pd.to_numeric(hold["crush"], errors="coerce"))[0, 1]
    )
    print(f"  frozen forecast vs realised crush correlation: {realised_corr:+.4f}")
    t3 = tercile_report(hold, "pred_crush", args.ret, "phase3_holdout_2013_2018")
    show(t3)
    results["phase3_holdout"] = t3

    print(f"\n  monotone on the untouched block: {monotone(t3)}")
    _save(results)


def _save(results: dict[str, pd.DataFrame]) -> None:
    if not results:
        return
    out = pd.concat([v for v in results.values() if not v.empty], ignore_index=True)
    path = OUT / "crush_forecast.csv"
    out.to_csv(path, index=False)
    print(f"\nwrote {path.resolve()}")
    print("Model-marked levels are inflated; read the ORDERING across terciles, not the level.")


if __name__ == "__main__":
    main()
