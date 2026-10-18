"""
research_conditional_hold.py
Pre-registered validation of the conditional hold-to-expiry exit on 2013-2018.

Test H of ``research/execution/preregs/cost_levers_prereg.md``. The rule holds the short straddle to its
front expiry unless the event's priced move is in the top 30% of strictly earlier events,
in which case it buys back at the next session close as the frozen book does. The 0.70 cut
was chosen in sample on 2019-2024 and is applied here once, unchanged.

Primary population: the frozen term-gated 2013-2018 book (193 trades), whose per-trade
entry credit, next-session exit mark and settlement intrinsic are stored in
``hold_decomposition_trades.csv``. The run aborts unless the measured cost basis reproduces
the stored next-session and hold Sharpes, so the inputs are the ones the earlier result used.

Secondary population, reported and not decisive: every 2013-2018 panel event, with
settlement recomputed from CRSP as-traded closes at the front expiry.

Holding to expiry replaces the exit spread with assignment of the in-the-money leg; the
shares are flattened at a charged 2 basis points of strike. Gap risk on assigned shares
between expiry close and the next open, and pin risk near the strike, are not modelled.

Usage:
    python research/timing/research_conditional_hold.py
    python research/timing/research_conditional_hold.py --skip-secondary

References
----------
Bailey, D. H. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of
Portfolio Management* 40(5), 94-107.
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-Based Improvements for
Inference with Clustered Errors. *Review of Economics and Statistics* 90(3), 414-427.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

TRADES = Path("outputs/research/hold_decomposition_trades.csv")
PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/cost_levers")

BLOCK_TRADES, BLOCK_PANEL = "2013-2018", "holdout_2013_2018"
CUT = 0.70  # frozen in sample, hold_holdout.csv chosen_cut_in_sample
MIN_HIST = 25
ENTRY_HALF, EXIT_HALF = 0.012714, 0.030182  # measured 15:59 basis, fills_rescore.csv
FLAT_ROUND_TRIP = 0.116
STOCK_FLATTEN = 0.0002  # 2 bp of strike per assigned share
N_TRIALS = 1491
N_BOOT = 5000
SEED = 0

# The measured basis must reproduce these before any new number is trusted.
HARNESS = {"plus1": 0.014297, "hold": -0.045105}


# ── helpers ──────────────────────────────────────────────────────────────────


def sharpe(x: pd.Series | np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else float("nan")


def clustered_ci(x: np.ndarray, keys: np.ndarray, fn=np.mean) -> tuple[float, float]:
    return cluster_bootstrap_ci(x, keys, lambda v: float(fn(v)), n_boot=N_BOOT, seed=SEED)


def causal_cut(panel_block: pd.DataFrame, dates: pd.Series) -> np.ndarray:
    """0.70 quantile of implied move over panel events announced strictly before each date."""
    ref = panel_block[["announce_date", "implied_move"]].dropna().sort_values("announce_date")
    ad = ref["announce_date"].to_numpy()
    im = ref["implied_move"].to_numpy(dtype=float)
    out = np.full(len(dates), np.nan)
    for i, d in enumerate(pd.to_datetime(dates).to_numpy()):
        prior = im[ad < d]
        if prior.size >= MIN_HIST:
            out[i] = float(np.quantile(prior, CUT))
    return out


def returns(g: pd.DataFrame, basis: str) -> tuple[pd.Series, pd.Series]:
    """Per-trade net return on margin for next-session exit and for hold to expiry."""
    mult, cr, ex, it = g["mult"], g["credit"], g["exit_mkt"], g["intrinsic"]
    flatten = np.where(it > 0, STOCK_FLATTEN * g["strike"] * mult, 0.0)
    if basis == "measured":
        plus1 = ((cr - ex) * mult - ENTRY_HALF * cr * mult - EXIT_HALF * ex * mult) / g["margin"]
        hold = ((cr - it) * mult - ENTRY_HALF * cr * mult - flatten) / g["margin"]
    else:
        plus1 = ((cr - ex) * mult - FLAT_ROUND_TRIP * cr * mult) / g["margin"]
        hold = ((cr - it) * mult - FLAT_ROUND_TRIP / 2 * cr * mult - flatten) / g["margin"]
    return plus1, hold


def harness_returns(g: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """The stored measured basis exactly as hold_decomposition.csv computed it."""
    mult, cr = g["mult"], g["credit"]
    plus1 = (cr - g["exit_mkt"]) * mult - ENTRY_HALF * cr * mult - EXIT_HALF * g["exit_mkt"] * mult
    hold = (cr - g["intrinsic"]) * mult - ENTRY_HALF * cr * mult
    return plus1 / g["margin"], hold / g["margin"]


def score(g: pd.DataFrame, exit_flag: np.ndarray, basis: str, label: str, sr_std: float) -> dict:
    plus1, hold = returns(g, basis)
    cond = np.where(exit_flag, plus1, hold)
    adv = cond - plus1.to_numpy()
    keys = pd.to_datetime(g["entry_date"]).dt.strftime("%Y-%m-%d").to_numpy()
    lo, hi = clustered_ci(adv, keys)
    s_lo, s_hi = clustered_ci(cond, keys, sharpe)
    return {
        "population": label,
        "basis": basis,
        "n": len(g),
        "n_held": int((~exit_flag).sum()),
        "sharpe_plus1": sharpe(plus1),
        "sharpe_hold_all": sharpe(hold),
        "sharpe_conditional": sharpe(cond),
        "sharpe_conditional_ci_low": s_lo,
        "sharpe_conditional_ci_high": s_hi,
        "hit_conditional": float((cond > 0).mean()),
        "mean_rom_conditional": float(np.mean(cond)),
        "mean_advantage": float(adv.mean()),
        "adv_ci_low": lo,
        "adv_ci_high": hi,
        "worst_rom_conditional": float(np.min(cond)),
        "dsr_conditional": float(
            deflated_sharpe_ratio(pd.Series(cond), n_trials=N_TRIALS, sr_trials_std=sr_std)
        ),
    }


# ── populations ──────────────────────────────────────────────────────────────


def primary(panel: pd.DataFrame) -> pd.DataFrame:
    """The frozen 2013-2018 book, joined to implied move and strike, with integrity checks."""
    t = pd.read_csv(TRADES)
    t = t[t["block"] == BLOCK_TRADES].copy()
    t["entry_date"] = pd.to_datetime(t["entry_date"])

    p1, h = harness_returns(t)
    got = {"plus1": round(sharpe(p1), 6), "hold": round(sharpe(h), 6)}
    if any(abs(got[k] - HARNESS[k]) > 1e-6 for k in HARNESS):
        raise SystemExit(f"harness failed: got {got}, expected {HARNESS}")
    print(f"  harness reproduced: {got}")

    pb = panel[panel["block"] == BLOCK_PANEL][
        ["ticker", "entry_date", "announce_date", "implied_move", "strike"]
    ].copy()
    pb["entry_date"] = pd.to_datetime(pb["entry_date"])
    m = t.merge(pb, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    lost = int(m["implied_move"].isna().sum())
    print(f"  funnel: {len(t)} trades, {lost} without a panel match")
    if lost:
        raise SystemExit("primary trades missing from the panel - refusing a partial book")
    bad = m["intrinsic"] > 0.5 * m["strike"]
    if bad.any():
        raise SystemExit(f"{int(bad.sum())} settlements exceed half the strike: split basis")
    return m


def secondary(panel: pd.DataFrame) -> pd.DataFrame:
    """Every 2013-2018 panel event, settled at CRSP as-traded closes on its front expiry."""
    from earnings_iv_crush.data import wrds_r2
    from earnings_iv_crush.data.equities import _permno_for_ticker

    pb = panel[panel["block"] == BLOCK_PANEL].copy()
    pb["entry_date"] = pd.to_datetime(pb["entry_date"])
    pb["expiry_mkt"] = pd.to_datetime(pb["expiry_mkt"])
    series: dict[str, pd.DataFrame] = {}
    for tkr in sorted(pb["ticker"].unique()):
        permno = _permno_for_ticker(tkr, pd.Timestamp("2013-01-01").date())
        if permno is None:
            continue
        df = wrds_r2.read_table(
            "crsp_a_stock",
            "dsf",
            columns=["date", "prc", "cfacpr"],
            filters=[
                ("permno", "=", permno),
                ("date", ">=", pd.Timestamp("2013-01-01").date()),
                ("date", "<=", pd.Timestamp("2019-01-31").date()),
            ],
        )
        if df.empty:
            continue
        df = df.assign(
            date=pd.to_datetime(df["date"]),
            close=pd.to_numeric(df["prc"], errors="coerce").astype(float).abs(),
            cfacpr=pd.to_numeric(df["cfacpr"], errors="coerce").astype(float),
        )
        series[tkr] = df.set_index("date").sort_index()

    # Amendment 01: a split between entry and expiry is detected from the CRSP adjustment
    # factor, not inferred from the size of the move, so a genuine extreme settlement stays in.
    rows = []
    reasons: dict[str, int] = {}

    def drop(why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    for _, e in pb.iterrows():
        s = series.get(e["ticker"])
        if s is None:
            drop("no CRSP history")
            continue
        window = s[(s.index >= e["entry_date"]) & (s.index <= e["expiry_mkt"])]
        if window.empty or (e["expiry_mkt"] - window.index[-1]).days > 4:
            drop("no close near expiry")
            continue
        if window["cfacpr"].nunique() > 1:
            drop("split between entry and expiry")
            continue
        settle = float(window["close"].iloc[-1])
        rows.append({**e.to_dict(), "intrinsic": abs(settle - float(e["strike"]))})
    print(f"  secondary funnel: {len(pb)} events, kept {len(rows)}, dropped {reasons}")
    m = pd.DataFrame(rows)
    m["credit"] = m["credit_mkt"]
    m["mult"] = m["contracts"] * 100
    return m


# ── entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--skip-secondary", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    panel = pd.read_parquet(PANEL)
    panel["announce_date"] = pd.to_datetime(panel["announce_date"])
    pb = panel[panel["block"] == BLOCK_PANEL]
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])

    print("\n== test H, primary: frozen 2013-2018 book")
    m = primary(panel)
    cut = causal_cut(pb, m["announce_date"])
    exit_causal = ~(np.isfinite(cut) & (m["implied_move"].to_numpy() < cut))
    exit_block = (m["implied_move"] >= m["implied_move"].quantile(CUT)).to_numpy()

    rows = []
    for basis in ("measured", "flat"):
        rows.append(score(m, exit_causal, basis, "primary_causal_cut", sr_std))
        rows.append(score(m, exit_block, basis, "primary_block_percentile", sr_std))

    if not args.skip_secondary:
        print("\n== test H, secondary: every 2013-2018 panel event")
        s = secondary(panel)
        cut_s = causal_cut(pb, s["announce_date"])
        exit_s = ~(np.isfinite(cut_s) & (s["implied_move"].to_numpy() < cut_s))
        for basis in ("measured", "flat"):
            rows.append(score(s, exit_s, basis, "secondary_all_events_causal", sr_std))

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "conditional_hold.csv", index=False)
    print(res.T.to_string(float_format=lambda v: f"{v:.4f}"))

    primary_row = res[(res["population"] == "primary_causal_cut") & (res["basis"] == "measured")]
    passed = bool((primary_row["adv_ci_low"] > 0).iloc[0])
    print(f"\n  PRIMARY CRITERION: {'PASS' if passed else 'FAIL'}")
    print(f"  wrote {(OUT / 'conditional_hold.csv').resolve()}")


if __name__ == "__main__":
    main()
