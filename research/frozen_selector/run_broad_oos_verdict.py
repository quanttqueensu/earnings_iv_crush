"""
run_broad_oos_verdict.py
Read the 2025-2026 broad block against the locked gate and report significance.

The Databento baseline (2019-2024 mega-cap, term gate at q=0.80) is N=198, per-trade
Sharpe +0.087393, one-sided p 0.110, and would need N=356 to clear a one-sided 95%
bar. The figure previously carried here, +0.115773 on N=192, is superseded: it
requires the intrinsic mark repair to be disabled and an event file since corrected
by the GE/LIN session fix. The distance between the two is entirely exit marks below
the intrinsic floor, so the apparent significance was an artefact of the marks. See
_private/remark_findings.md section 1 for the reconstruction. This script scores
the out-of-sample block built by ``build_broad_oos_2025.py`` on the SAME locked
specification and reports the block alone, the pooled sample, and whether the
pooled result crosses.

THE GATE IS NOT RE-TUNED. ``Q`` and ``K_MIN`` are imported from the strategy
module and the broad per-name gate respectively. Re-optimising either on this block
would convert an out-of-sample test into trial family sixteen, which is what drove
the deflated Sharpe to ~0 in the first place.

HISTORY SEEDING. The per-name gate is an expanding percentile needing ``K_MIN``
strictly-earlier events per name. The block spans about six quarters, so seeding
history from the block alone would make only ~49% of its events gate-eligible and
would start every name cold, which the mega-cap book never did. Instead the
trailing history is seeded from the 2024 portion of ``events_broad_full.parquet``:
those events supply each name's prior term-spread distribution and are NEVER traded
and NEVER enter the ledger. The percentile remains strictly backward-looking, so
this adds power without look-ahead. The seed's comparability to the fresh pull is
checked on the overlap and reported, not assumed.

BASIS. Alpaca serves bar closes, so bid equals ask and every number here is GROSS
at the mid. Nothing in this output may be quoted net. Costs are measured separately
on the Databento NBBO sample (11.6% round-trip break-even) and are not re-derived
here.

Run: ``python research/frozen_selector/run_broad_oos_verdict.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.pnl import build_ledger  # noqa: E402
from earnings_iv_crush.strategy.filters import TERM_SPREAD_PCTL  # noqa: E402
from research.frozen_selector.broad_pername_gate import K_MIN, _per_name_gate  # noqa: E402

BLOCK = Path("outputs/research/events_broad_oos_2025.parquet")
SEED = Path("outputs/research/events_broad_full.parquet")
OUT = Path("outputs/research/broad_oos_2025_verdict.csv")

BLOCK_START = "2025-01-01"
SEED_END = "2024-12-31"  # 2024 events are history only, never traded

# Databento baseline, for pooling. Repaired marks on the session-corrected event file;
# reconstruction in _private/remark_findings.md section 1. The superseded +0.115773 on
# N=192 is not the comparison and must not be restored here.
BASE_N = 198
BASE_SHARPE = 0.087393


def _sharpe_z(s: float, n: int) -> float:
    """z on a per-trade Sharpe under the iid approximation (Lo 2002)."""
    return s / np.sqrt((1.0 + s**2 / 2.0) / n)


def _clustered_bootstrap(rom: pd.Series, clusters: pd.Series, n_boot: int = 5000) -> tuple:
    """Bootstrap CI on the per-trade Sharpe, resampling whole clusters.

    Events sharing an announcement date share a market-wide shock, so resampling
    individual trades would understate the interval. Clusters here are announcement
    dates, matching the convention used throughout the project.
    """
    rng = np.random.default_rng(0)
    keys = clusters.unique()
    groups = {k: rom[clusters == k].to_numpy() for k in keys}
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(keys, size=len(keys), replace=True)
        sample = np.concatenate([groups[k] for k in pick])
        draws[b] = sample.mean() / sample.std() if sample.std() > 0 else np.nan
    draws = draws[~np.isnan(draws)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> None:
    if not BLOCK.exists():
        raise SystemExit(f"{BLOCK} not found. Run scripts/build/build_broad_oos_2025.py first.")

    block = pd.read_parquet(BLOCK)
    block["announce_date"] = pd.to_datetime(block["announce_date"])
    block = block[block["announce_date"] >= BLOCK_START]

    seed = pd.DataFrame()
    if SEED.exists():
        seed = pd.read_parquet(SEED)
        seed["announce_date"] = pd.to_datetime(seed["announce_date"])
        seed = seed[seed["announce_date"] <= SEED_END]

    # ── seed comparability check ────────────────────────────────────────────
    # Both files should price identically (same adapter, same BS inversion). If
    # they do not, the seeded history is not on the same scale as the traded
    # events and the percentile is meaningless. Checked, not assumed.
    if not seed.empty:
        full = pd.read_parquet(SEED)
        full["announce_date"] = pd.to_datetime(full["announce_date"])
        ov = block.merge(
            full[["ticker", "announce_date", "iv_term_spread"]],
            on=["ticker", "announce_date"],
            suffixes=("", "_ref"),
        ).dropna(subset=["iv_term_spread", "iv_term_spread_ref"])
        if len(ov) >= 20:
            d = (ov["iv_term_spread"] - ov["iv_term_spread_ref"]).abs()
            corr = ov["iv_term_spread"].corr(ov["iv_term_spread_ref"])
            print(
                f"Seed comparability on {len(ov)} overlapping events: "
                f"corr {corr:.4f}, median |diff| {d.median():.5f}, p95 {d.quantile(0.95):.5f}"
            )
            if corr < 0.99:
                raise SystemExit(
                    f"HALT: seed and block price iv_term_spread inconsistently "
                    f"(corr {corr:.4f} < 0.99, p95 |diff| {d.quantile(0.95):.4f}). The "
                    "seeded percentile is off-scale, so the gated sample is not the "
                    "locked specification applied to unseen data. This was a warning in "
                    "the first version and the run proceeded to produce a headline "
                    "number that could not be trusted; a check that can invalidate the "
                    "result must halt, not advise. Rerun without seeding, or reconcile "
                    "the two pricings first."
                )
        else:
            print(f"Seed comparability: only {len(ov)} overlapping events, check skipped.")

    # ── locked gate, history-seeded ─────────────────────────────────────────
    seed_hist = seed.assign(_traded=False) if not seed.empty else pd.DataFrame()
    pool = pd.concat([seed_hist, block.assign(_traded=True)], ignore_index=True)
    pool = pool[pool["iv_exit"] != pool["iv_entry"]]
    pool = pool.sort_values(["ticker", "announce_date"]).reset_index(drop=True)

    gated_all = _per_name_gate(pool)
    gated = gated_all[gated_all["pername_passes"] & gated_all["_traded"]].reset_index(drop=True)

    print(
        f"\nBlock: {len(block)} events, {block['ticker'].nunique()} names, from {BLOCK_START}.\n"
        f"History seed: {len(seed)} events from 2024 (never traded).\n"
        f"Gate-eligible traded events: {int((gated_all['pername_qualifies'] & gated_all['_traded']).sum())}\n"
        f"Passing the locked per-name q={TERM_SPREAD_PCTL:.2f} gate (K_MIN={K_MIN}): {len(gated)}"
    )
    if gated.empty:
        raise SystemExit("No events passed the gate. Nothing to score.")

    led = build_ledger(gated, costs=CostModel())
    rom = pd.to_numeric(led["return_on_margin"], errors="coerce").dropna()
    n = len(rom)
    s = float(rom.mean() / rom.std())
    z = _sharpe_z(s, n)

    # build_ledger does not carry announce_date, but entry is one business day
    # before the announcement, so entry_date groups the same events.
    clusters = pd.to_datetime(led.loc[rom.index, "entry_date"]).dt.normalize()
    lo, hi = _clustered_bootstrap(rom, clusters)

    print("\n── Block alone (GROSS, at the mid; not a net result) ──")
    print(f"  N (sized trades)      {n}")
    print(f"  Hit rate              {(rom > 0).mean():.1%}")
    print(f"  Mean return on margin {rom.mean():+.4f}")
    print(f"  Per-trade Sharpe      {s:+.4f}  (unannualised)")
    print(f"  z / one-sided p       {z:+.2f} / {1 - sps.norm.cdf(z):.4f}")
    print(f"  Clustered 95% CI      [{lo:+.3f}, {hi:+.3f}] (by announcement date)")

    # ── pooled with the Databento headline ──────────────────────────────────
    # Pooled on an N-weighted Sharpe, which assumes comparable per-trade vol
    # across the two samples. Stated as an approximation, not a fitted result.
    pooled_n = BASE_N + n
    pooled_s = (BASE_SHARPE * BASE_N + s * n) / pooled_n
    pooled_z = _sharpe_z(pooled_s, pooled_n)

    print(f"\n── Pooled with Databento 2019-2024 (N={BASE_N}, S={BASE_SHARPE:+.4f}) ──")
    print(f"  Pooled N              {pooled_n}")
    print(f"  Pooled Sharpe (N-wtd) {pooled_s:+.4f}")
    print(f"  z / one-sided p       {pooled_z:+.2f} / {1 - sps.norm.cdf(pooled_z):.4f}")
    verdict = (
        "CROSSES the one-sided 95% bar"
        if pooled_z > 1.645
        else "still short of the one-sided 95% bar"
    )
    print(f"  Verdict               {verdict}")
    print(
        "\n  Basis: gross, marked at the mid on Alpaca bar closes with BS-inverted IV.\n"
        "  Not comparable to a net result and not a cost read. The two samples are\n"
        "  priced by different vendors, so the pooled figure is an approximation whose\n"
        "  main use is direction and magnitude, not a third decimal place."
    )

    pd.DataFrame(
        [
            {
                "block_n": n,
                "block_sharpe": s,
                "block_z": z,
                "block_ci_low": lo,
                "block_ci_high": hi,
                "block_hit_rate": float((rom > 0).mean()),
                "base_n": BASE_N,
                "base_sharpe": BASE_SHARPE,
                "pooled_n": pooled_n,
                "pooled_sharpe": pooled_s,
                "pooled_z": pooled_z,
                "crosses_one_sided_95": bool(pooled_z > 1.645),
                "basis": "gross_at_mid_alpaca_bs_inverted",
            }
        ]
    ).to_csv(OUT, index=False)
    print(f"\nwritten: {OUT.resolve()}")


if __name__ == "__main__":
    main()
