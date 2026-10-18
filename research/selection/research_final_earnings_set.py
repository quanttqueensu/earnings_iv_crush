"""
research_final_earnings_set.py
The final pre-registered test set for the single-name earnings straddle.

Tests T1 to T3 of ``research/selection/preregs/final_earnings_set_prereg.md``. Each test states the mechanism
by which it would work and carries a mechanism check; a pass whose mechanism check fails is
reported as unexplained.

    t1  causal spread gate on the 2025-2026 broad block, touch-basis P&L
    t2  risk-normalised sizing on all three blocks
    t3  retail ownership (one minus 13F institutional ownership) as the selector

Usage:
    python research/selection/research_final_earnings_set.py --test t2
    python research/selection/research_final_earnings_set.py --test t1
    python research/selection/research_final_earnings_set.py --test t3

References
----------
de Silva, T., So, E. C. and Smith, K. (2026). Losing is Optional: Retail Option Trading and
Expected Announcement Volatility. *Review of Finance* 30(2), 489-.
Muravyev, D. (2016). Order Flow and Expected Option Returns. *Journal of Finance* 71(2),
673-708.
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
from research.execution.research_spread_gate import gate, sharpe  # noqa: E402

PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
LEDGER = Path("outputs/research/oos_2026_ledger.csv")
CHAINS = Path("data/cache/backfill_chains")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/final_earnings_set")

ENTRY_HALF, EXIT_HALF = 0.012714, 0.030182  # measured 15:59 basis
REGT_SPOT = 0.20  # Reg-T straddle margin: 0.20 * spot + premium
MIN_NAME_PRIOR = 3
N_NULL = 1000
N_TRIALS = 1494
N_BOOT = 5000
SEED = 0


# ── shared ───────────────────────────────────────────────────────────────────


def _keys(dates: pd.Series) -> np.ndarray:
    return pd.to_datetime(dates).dt.strftime("%Y-%m-%d").to_numpy()


def sharpe_ci(x: np.ndarray, dates: pd.Series) -> tuple[float, float]:
    return cluster_bootstrap_ci(x, _keys(dates), sharpe, n_boot=N_BOOT, seed=SEED)


def _sr_std() -> float:
    return float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])


def megacap_blocks() -> dict[str, pd.DataFrame]:
    """Megacap panel per block with net return on the measured 15:59 basis."""
    p = pd.read_parquet(PANEL)
    k = p["contracts"] * 100
    cost = (ENTRY_HALF * p["credit_mkt"] + EXIT_HALF * p["exit_mkt"]) * k
    p["net_rom"] = ((p["credit_mkt"] - p["exit_mkt"]) * k - cost) / p["margin"]
    p["entry_date"] = pd.to_datetime(p["entry_date"])
    return {str(b): g.copy() for b, g in p.groupby("block")}


# ── T2 risk-normalised sizing ────────────────────────────────────────────────


def test_t2() -> pd.DataFrame:
    blocks = megacap_blocks()
    led = pd.read_csv(LEDGER, parse_dates=["entry_date", "announce_date"])
    blocks["broad_2025_2026"] = led
    sr_std = _sr_std()

    rows = []
    for name, g in blocks.items():
        g = g[np.isfinite(g["net_rom"]) & (g["implied_move"] > 0)].copy()
        m = g["implied_move"].to_numpy(dtype=float)
        r = m / (REGT_SPOT + m)
        w = (1 / r) / np.mean(1 / r)
        R = g["net_rom"].to_numpy(dtype=float)
        wr = w * R
        lo, hi = sharpe_ci(wr, g["entry_date"])
        ulo, uhi = sharpe_ci(R, g["entry_date"])

        def sharpe_gap(i: np.ndarray, wr: np.ndarray = wr, R: np.ndarray = R) -> float:
            j = i.astype(int)
            return sharpe(wr[j]) - sharpe(R[j])

        diff = cluster_bootstrap_ci(
            np.arange(len(R), dtype=float),
            _keys(g["entry_date"]),
            sharpe_gap,
            n_boot=N_BOOT,
            seed=SEED,
        )
        rows.append(
            {
                "block": name,
                "n": len(R),
                "sharpe_unweighted": sharpe(R),
                "unweighted_ci_low": ulo,
                "unweighted_ci_high": uhi,
                "sharpe_weighted": sharpe(wr),
                "weighted_ci_low": lo,
                "weighted_ci_high": hi,
                "diff_ci_low": diff[0],
                "diff_ci_high": diff[1],
                "mean_unweighted": float(R.mean()),
                "mean_weighted": float(wr.mean()),
                "return_per_risk_unweighted": float(R.sum() / r.sum()),
                "return_per_risk_weighted": float(wr.sum() / (w * r).sum()),
                "weight_max": float(w.max()),
                "dsr_weighted": float(
                    deflated_sharpe_ratio(pd.Series(wr), n_trials=N_TRIALS, sr_trials_std=sr_std)
                ),
            }
        )
    res = pd.DataFrame(rows)
    passed = bool((res["weighted_ci_low"] > 0).all())
    mech = bool(
        (res["return_per_risk_weighted"] >= res["return_per_risk_unweighted"] - 1e-12).all()
    )
    print(res.T.to_string(float_format=lambda v: f"{v:.4f}"))
    print(f"\n  T2 PRIMARY: {'PASS' if passed else 'FAIL'}   mechanism check: {mech}")
    return res


# ── T1 spread gate, broad block ──────────────────────────────────────────────


def _touch(ch: pd.DataFrame, strike: float, expiry: pd.Timestamp) -> tuple[float, float] | None:
    leg = ch[(ch["strike"] == strike) & (ch["expiry"] == expiry)]
    c, p = leg[leg["right"] == "C"], leg[leg["right"] == "P"]
    if c.empty or p.empty:
        return None
    bid = float(c["bid_px_00"].iloc[0] + p["bid_px_00"].iloc[0])
    ask = float(c["ask_px_00"].iloc[0] + p["ask_px_00"].iloc[0])
    return (bid, ask) if ask > bid > 0 else None


def broad_quotes() -> pd.DataFrame:
    """Ledger rows with entry and exit touch prices of the traded straddle."""
    from earnings_iv_crush.research.chains import _parse_chain

    led = pd.read_csv(LEDGER, parse_dates=["announce_date", "entry_date", "exit_date", "expiry"])
    cache: dict[tuple[str, str], pd.DataFrame | None] = {}

    def chain(t: str, d: pd.Timestamp) -> pd.DataFrame | None:
        key = (t, str(d.date()))
        if key not in cache:
            f = CHAINS / f"{t}_{key[1]}.parquet"
            cache[key] = _parse_chain(pd.read_parquet(f)) if f.exists() else None
        return cache[key]

    rows, dropped = [], 0
    for _, e in led.iterrows():
        ci, co = chain(e["ticker"], e["entry_date"]), chain(e["ticker"], e["exit_date"])
        qi = _touch(ci, e["strike"], e["expiry"]) if ci is not None else None
        qo = _touch(co, e["strike"], e["expiry"]) if co is not None else None
        if qi is None or qo is None:
            dropped += 1
            continue
        rows.append(
            {
                **e.to_dict(),
                "entry_bid": qi[0],
                "entry_ask": qi[1],
                "exit_bid": qo[0],
                "exit_ask": qo[1],
            }
        )
    print(
        f"  T1 funnel: ledger {len(led)}, touch-quoted on both sessions {len(rows)}, "
        f"dropped {dropped}"
    )
    if not rows:
        raise SystemExit("no ledger row could be touch-quoted - refusing to score")
    return pd.DataFrame(rows)


def test_t1() -> pd.DataFrame:
    d = broad_quotes().sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    d["entry_rel"] = (d["entry_ask"] - d["entry_bid"]) / (d["entry_ask"] + d["entry_bid"])
    d["exit_rel"] = (d["exit_ask"] - d["exit_bid"]) / (d["exit_ask"] + d["exit_bid"])
    prior = np.full(len(d), np.nan)
    for i in range(len(d)):
        m = (d["ticker"] == d.at[i, "ticker"]) & (d["exit_date"] < d.at[i, "entry_date"])
        if m.sum() >= MIN_NAME_PRIOR:
            prior[i] = float(d.loc[m, "exit_rel"].mean())
    d["cost_signal"] = d["entry_rel"] + prior
    d["rom_touch"] = (d["entry_bid"] - d["exit_ask"]) * 100 / d["margin"]

    elig_mask = np.isfinite(d["cost_signal"]).to_numpy()
    eligible = d[elig_mask]
    take = gate(d)[elig_mask]
    gated = eligible[take]
    print(f"  T1: eligible {len(eligible)}, gated {len(gated)}")
    if len(gated) < 3:
        raise SystemExit(f"gate selected {len(gated)} events - an empty slice, not a null")

    rng = np.random.default_rng(SEED)
    pool = eligible["rom_touch"].to_numpy()
    null = np.array([sharpe(rng.choice(pool, len(gated), replace=False)) for _ in range(N_NULL)])
    sr_std = _sr_std()

    rows = []
    for label, book in (("gated", gated), ("ungated", eligible)):
        x = book["rom_touch"].to_numpy()
        lo, hi = sharpe_ci(x, book["entry_date"])
        rows.append(
            {
                "book": label,
                "n": len(book),
                "mean_rom_touch": float(x.mean()),
                "sharpe_touch": sharpe(x),
                "ci_low": lo,
                "ci_high": hi,
                "hit_rate": float((x > 0).mean()),
                "mean_gross_mid": float(book["gross_rom"].mean()),
                "mean_cost_signal": float(book["cost_signal"].mean()),
                "null_median": float(np.median(null)) if label == "gated" else np.nan,
                "null_percentile": float((null < sharpe(x)).mean()) if label == "gated" else np.nan,
                "dsr": float(
                    deflated_sharpe_ratio(pd.Series(x), n_trials=N_TRIALS, sr_trials_std=sr_std)
                ),
            }
        )
    res = pd.DataFrame(rows)
    g, u = res.iloc[0], res.iloc[1]
    passed = bool(g["ci_low"] > 0 and g["sharpe_touch"] > g["null_median"])
    saving = (u["mean_cost_signal"] - g["mean_cost_signal"]) * 2  # half-spreads, two sessions
    mech = bool(g["mean_cost_signal"] < u["mean_cost_signal"])
    print(res.T.to_string(float_format=lambda v: f"{v:.4f}"))
    print(
        f"\n  T1 PRIMARY: {'PASS' if passed else 'FAIL'}   mechanism (cost lower): {mech}; "
        f"gross-at-mid change {g['mean_gross_mid'] - u['mean_gross_mid']:+.4f}, "
        f"cost-signal saving {saving:.4f} (relative units)"
    )
    return res


# ── entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--test", choices=["t1", "t2", "t3"], required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.test == "t2":
        test_t2().to_csv(OUT / "t2_risk_sizing.csv", index=False)
    elif args.test == "t1":
        test_t1().to_csv(OUT / "t1_spread_gate_broad.csv", index=False)
    else:
        from research.selection.research_retail_share import test_t3

        test_t3().to_csv(OUT / "t3_retail_share.csv", index=False)
    print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
