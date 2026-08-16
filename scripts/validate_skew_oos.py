"""
validate_skew_oos.py
Does the 25-delta skew lever survive an honest out-of-sample test?

The in-sample scan found that, inside the term-gated book, preferring low 25-delta put
skew roughly doubled per-trade Sharpe on two samples. That was in-sample and the
term-by-skew sort is a new degree of freedom, so this re-runs it causally. Every gate
uses only past information:

* the move gate's fair move is an expanding-window walk-forward fit
  (`FairMoveModel.fit_predict_walk_forward`), no look-ahead;
* the term gate keeps an event only if its front-minus-back ATM term spread is at or
  above the expanding cross-sectional quantile of the term spread over events strictly
  earlier in time. This is the panel-free causal term gate: it reads the per-event
  `iv_term_spread` the assembler already stores, so it needs no trailing daily surface
  history. (On a metered provider that daily panel would cost ~$100+ to reconstruct for
  a 62-event sample; the in-sample run used the free Alpaca panel gate
  `passes_term_filter_panel`, which is still used here when a panel is supplied.)
* the skew gate (new) keeps an event only if its `skew_25d` is at or below the
  expanding cross-sectional quantile of skew over events strictly earlier in time -
  a low-skew filter built from the past alone.

Arms (control, term-only, term+skew, full stack) are scored frequency-neutral on the
common out-of-sample window. The best arm's Sharpe is discounted by a Deflated Sharpe
whose trial count is every configuration tried here, and the skew keep-fraction is swept
so the result is a plateau, not a lucky cut. Cached megacap only; no network.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.baseline.agent0 import run_agent0  # noqa: E402
from earnings_iv_crush.engine.backtester import (  # noqa: E402
    backtest,
    daily_return_series,
    frequency_neutral_stats,
)
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.pnl import ACCOUNT_SIZE, build_ledger  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.engine.structured_ledger import build_structured_ledger  # noqa: E402
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel  # noqa: E402
from earnings_iv_crush.strategy.filters import (  # noqa: E402
    passes_move_filter,
    passes_term_filter_panel,
)

EVENTS = "outputs/research/events_megacap_databento.parquet"
PANEL = "outputs/research/panel_megacap_databento.parquet"
OUT_DIR = Path("outputs/research")
MEMO_PATH = Path("notes/skew_validation.md")
MIN_HIST = 25  # prior events required before an event enters the OOS window
MOVE_RATIO = 1.20
TERM_PCTL = 0.75
SKEW_KEEP = 0.67  # keep the lowest-skew this fraction (causal, expanding)
SKEW_SWEEP = [0.50, 0.67, 0.80, 1.00]  # 1.00 = no skew gate (term-only)


def expanding_high_term_mask(events: pd.DataFrame, pctl: float) -> np.ndarray:
    """Causal term gate without a daily panel: keep event i if its `iv_term_spread`
    is at/above the `pctl` quantile of the term spread over all events with a
    strictly earlier announce_date (steep front-vs-back structure, past-only)."""
    dates = events["announce_date"].to_numpy()
    term = events["iv_term_spread"].to_numpy(dtype=float)
    keep = np.zeros(len(events), dtype=bool)
    for i in range(len(events)):
        prior = term[dates < dates[i]]
        prior = prior[np.isfinite(prior)]
        if len(prior) < MIN_HIST or not np.isfinite(term[i]):
            continue
        keep[i] = term[i] >= np.quantile(prior, pctl)
    return keep


def expanding_low_skew_mask(events: pd.DataFrame, keep_frac: float) -> np.ndarray:
    """Causal low-skew gate: keep event i if its skew is at/below the keep_frac
    quantile of skew over all events with a strictly earlier announce_date."""
    if keep_frac >= 1.0:
        return np.ones(len(events), dtype=bool)
    dates = events["announce_date"].to_numpy()
    skew = events["skew_25d"].to_numpy(dtype=float)
    keep = np.zeros(len(events), dtype=bool)
    for i in range(len(events)):
        prior = skew[dates < dates[i]]
        prior = prior[np.isfinite(prior)]
        if len(prior) < MIN_HIST or not np.isfinite(skew[i]):
            continue
        keep[i] = skew[i] <= np.quantile(prior, keep_frac)
    return keep


def _score(events: pd.DataFrame, mask: np.ndarray, ag0: pd.DataFrame, costs: CostModel) -> dict:
    led = build_ledger(events[mask], costs=costs)
    fn = frequency_neutral_stats(led, ag0, n_boot=2000, seed=0)
    ann = backtest(led, ACCOUNT_SIZE)
    return {"ledger": led, "fn": fn, "ann": ann}


def main(events_path: str = EVENTS, panel_path: str = PANEL) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not Path(events_path).exists():
        raise SystemExit(
            f"{events_path} not found - run build_databento_events.py --prefetch then --run first."
        )
    events = (
        pd.read_parquet(events_path).sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    )
    panel = pd.read_parquet(panel_path) if Path(panel_path).exists() else None
    costs = CostModel()

    # Causal fair move (expanding walk-forward) and the OOS window.
    fair = FairMoveModel().fit_predict_walk_forward(events, events["realised_move"], min_train=20)
    n_prior = np.arange(len(events))  # events are date-sorted, so index ~ prior count
    oos = (n_prior >= MIN_HIST) & fair.notna().to_numpy()
    eo = events[oos].reset_index(drop=True)
    fair_o = fair[oos].reset_index(drop=True)

    # Causal gates on the OOS frame. With a daily panel, use the per-name trailing
    # percentile gate; without one (metered provider), use the panel-free
    # cross-sectional term gate off the per-event term spread.
    if panel is not None:
        term_ok = passes_term_filter_panel(eo, panel, pctl=TERM_PCTL).fillna(False).to_numpy()
    else:
        term_ok = expanding_high_term_mask(eo, TERM_PCTL)
    move_ok = (
        passes_move_filter(eo["implied_move"], fair_o, ratio=MOVE_RATIO).fillna(False).to_numpy()
    )
    skew_ok = expanding_low_skew_mask(eo, SKEW_KEEP)

    ag0 = run_agent0(eo, seed=11, costs=costs)
    arms = {
        "term_only": term_ok,
        "term_plus_skew": term_ok & skew_ok,
        "full_stack": move_ok & term_ok & skew_ok,
    }

    rows, all_sharpe, ledgers = [], [ag0_ann := backtest(ag0, ACCOUNT_SIZE)["sharpe"]], {}
    for name, mask in arms.items():
        r = _score(eo, mask, ag0, costs)
        ledgers[name] = r["ledger"]
        # Per-period, not annualised: deflated_sharpe_ratio is handed a daily series
        # below, so the trial dispersion has to be on that same basis. backtest()
        # annualises by the rate it infers from the ledger (~sqrt(35) here), not by
        # sqrt(252), so undo it with the factor that arm actually used.
        all_sharpe.append(r["ann"]["sharpe"] / np.sqrt(r["ann"]["periods_per_year"]))
        rows.append(
            {
                "arm": name,
                "n_trades": len(r["ledger"]),
                "mean_rom": r["fn"]["mean_rom_strategy"],
                "per_trade_sharpe": r["fn"]["per_trade_sharpe_strategy"],
                "per_trade_sharpe_delta": r["fn"]["per_trade_sharpe_delta"],
                "size_matched_win_prob": r["fn"]["size_matched_win_prob"],
                "ci_low": r["fn"]["size_matched_delta_ci_low"],
                "ci_high": r["fn"]["size_matched_delta_ci_high"],
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT_DIR / "skew_oos_arms.csv", index=False)

    # Skew keep-fraction robustness on top of the term gate.
    sweep_rows = []
    for q in SKEW_SWEEP:
        mask = term_ok & expanding_low_skew_mask(eo, q)
        r = _score(eo, mask, ag0, costs)
        # Per-period, not annualised: deflated_sharpe_ratio is handed a daily series
        # below, so the trial dispersion has to be on that same basis. backtest()
        # annualises by the rate it infers from the ledger (~sqrt(35) here), not by
        # sqrt(252), so undo it with the factor that arm actually used.
        all_sharpe.append(r["ann"]["sharpe"] / np.sqrt(r["ann"]["periods_per_year"]))
        sweep_rows.append(
            {
                "skew_keep_frac": q,
                "n_trades": len(r["ledger"]),
                "per_trade_sharpe": r["fn"]["per_trade_sharpe_strategy"],
                "per_trade_sharpe_delta": r["fn"]["per_trade_sharpe_delta"],
                "ci_low": r["fn"]["size_matched_delta_ci_low"],
                "ci_high": r["fn"]["size_matched_delta_ci_high"],
            }
        )
    sweep = pd.DataFrame(sweep_rows)
    sweep.to_csv(OUT_DIR / "skew_oos_robustness.csv", index=False)

    # Deflated Sharpe of the best arm, discounted by every configuration tried.
    best = table.sort_values("per_trade_sharpe_delta", ascending=False).iloc[0]
    best_led = ledgers[best["arm"]]
    sr_arr = np.asarray(all_sharpe, dtype=float)
    n_trials = len(sr_arr)
    sr_std = float(np.std(sr_arr, ddof=1))
    dsr = deflated_sharpe_ratio(daily_return_series(best_led), n_trials, sr_std)

    # Best arm booked as a short calendar vs the naked straddle, on the same events.
    best_mask = arms[best["arm"]]
    gated = eo[best_mask].reset_index(drop=True)
    struct = {}
    for s in ("straddle", "calendar"):
        led = build_structured_ledger(gated, pd.Series([s] * len(gated)), costs=costs)
        if not led.empty:
            ror = led["return_on_risk"].astype(float)
            struct[s] = (float(ror.mean()), float(ror.mean() / ror.std(ddof=1)), len(led))

    # Equity curves (cumulative daily return) for control vs term vs term+skew.
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        daily_return_series(ag0).cumsum().to_numpy(), label=f"control (Agent 0) Sh {ag0_ann:.1f}"
    )
    for name in ("term_only", "term_plus_skew"):
        ax.plot(daily_return_series(ledgers[name]).cumsum().to_numpy(), label=name)
    ax.set_xlabel("OOS trading day index")
    ax.set_ylabel("cumulative return on account")
    ax.set_title("Out-of-sample equity curves: control vs term vs term+skew (megacap)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "skew_oos_equity.png", dpi=120)
    plt.close(fig)

    pd.set_option("display.width", 170)
    print(
        f"OOS window: {len(eo)} events from {eo['announce_date'].min()} ({eo['ticker'].nunique()} names)"
    )
    print(
        f"Control (Agent 0) per-trade Sharpe: {frequency_neutral_stats(ledgers['term_only'], ag0)['per_trade_sharpe_agent0']:.3f}\n"
    )
    print("OOS arms (frequency-neutral vs control):")
    print(table.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\nSkew keep-fraction robustness (on top of the term gate; 1.00 = term-only):")
    print(sweep.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(
        f"\nBest arm: {best['arm']} -> per-trade Sharpe delta {best['per_trade_sharpe_delta']:+.3f}, "
        f"size-matched 95% CI [{best['ci_low']:+.2f}, {best['ci_high']:+.2f}] on {int(best['n_trades'])} trades"
    )
    print(f"Deflated Sharpe of best arm (n_trials={n_trials}, sr_std={sr_std:.4f}): {dsr:.4f}")
    print("\nBest arm booked by structure (mean RoR / per-trade Sharpe / n):")
    for s, (m, sh, n) in struct.items():
        print(f"  {s:10s} {m:+.4f} / {sh:+.3f} / {n}")
    print(f"\nWrote skew_oos_arms.csv, skew_oos_robustness.csv, skew_oos_equity.png to {OUT_DIR}")
    _write_memo(eo, table, sweep, best, dsr, ag0_ann)
    print(f"Wrote verdict memo to {MEMO_PATH}")


def _write_memo(
    eo: pd.DataFrame,
    table: pd.DataFrame,
    sweep: pd.DataFrame,
    best: pd.Series,
    dsr: float,
    ctrl_sharpe: float,
) -> None:
    """Write the plain out-of-sample verdict on the term + skew gates."""
    t = table.set_index("arm")
    ci = (float(best["ci_low"]), float(best["ci_high"]))
    survives = ci[0] > 0
    # Plateau: every gated keep-fraction beats the ungated (1.00 = term-only) cut.
    ungated = float(sweep.loc[sweep["skew_keep_frac"] >= 1.0, "per_trade_sharpe_delta"].iloc[0])
    gated = sweep.loc[sweep["skew_keep_frac"] < 1.0, "per_trade_sharpe_delta"]
    plateau = bool((gated > ungated).all())
    lo_y = pd.Timestamp(eo["announce_date"].min()).year
    hi_y = pd.Timestamp(eo["announce_date"].max()).year
    # Absolute (not just vs-control) per-trade Sharpe: is any arm actually profitable?
    abs_sharpe = {a: float(t.loc[a, "per_trade_sharpe"]) for a in t.index}
    any_positive = any(v > 0 for v in abs_sharpe.values())
    lines = [
        f"# Skew lever - out-of-sample validation (Databento OPRA, {lo_y}-{hi_y})",
        "",
        "**Hypothesis.** The term and low-skew gates, tuned on the 2024-2026 sample, still",
        "separate good short-straddle events from bad ones on the pre-2024 OPRA sample - a",
        "different period (incl. the 2020 COVID shock and 2022 bear), so a genuine",
        "out-of-sample test.",
        "",
        f"**Sample.** {len(eo)} causal-window events, {eo['ticker'].nunique()} megacap names, "
        f"{pd.Timestamp(eo['announce_date'].min()).date()} to {pd.Timestamp(eo['announce_date'].max()).date()}.",
        "",
        "**Result (frequency-neutral vs the Agent-0 control).**",
        f"- term-only: per-trade Sharpe {abs_sharpe['term_only']:+.3f} "
        f"(delta vs control {t.loc['term_only','per_trade_sharpe_delta']:+.3f}) "
        f"on {int(t.loc['term_only','n_trades'])} trades.",
        f"- term+skew: per-trade Sharpe {abs_sharpe['term_plus_skew']:+.3f} "
        f"(delta {t.loc['term_plus_skew','per_trade_sharpe_delta']:+.3f}) "
        f"on {int(t.loc['term_plus_skew','n_trades'])} trades.",
        f"- best arm '{best['arm']}': size-matched 95% CI [{ci[0]:+.2f}, {ci[1]:+.2f}], "
        f"deflated Sharpe {dsr:.2f}.",
        f"- keep-fraction sweep {'IS' if plateau else 'is NOT'} a plateau "
        f"(gated cuts vs term-only).",
        "",
        "**Verdict.** "
        + (
            "Term+skew beats the control out of sample with a CI excluding zero"
            if survives
            else "The size-matched CI straddles zero, so the skew lever is NOT validated out of sample"
        )
        + (
            "; the edge holds across keep-fractions."
            if (survives and plateau)
            else "; treat as suggestive, not established."
        )
        + (
            ""
            if any_positive
            else " Moreover, every arm's absolute per-trade Sharpe is negative: on this "
            "2019-2023 sample the short-straddle book loses money per trade, and the gates "
            "only shrink the loss rather than turn it positive. The in-sample edge does not "
            "generalise to the COVID/2022 regimes - it is regime-dependent, not established."
        ),
        "",
        "**Caveats.** Pre-2023 marks are trade-based daily closes (no NBBO mid), so wing-strike",
        "skew is patchier than ATM; one liquid-megacap universe; bootstrap-only significance.",
        "The term gate here is the panel-free",
        "cross-sectional term-spread quantile, not the per-name trailing-day panel of the",
        "in-sample run (the daily OPRA panel is cost-prohibitive to reconstruct); the two are",
        "both causal but not identical. A longer multi-name history (WRDS/OptionMetrics) with the",
        "trailing-day panel remains the stronger test.",
    ]
    MEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMO_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=EVENTS, help="events parquet (default: Databento OOS)")
    ap.add_argument("--panel", default=PANEL, help="term panel parquet")
    args = ap.parse_args()
    main(args.events, args.panel)
