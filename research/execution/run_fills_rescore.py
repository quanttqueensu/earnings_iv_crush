"""
run_fills_rescore.py
Re-score the book charging measured fills instead of an assumed half-cross.

The cost model the verdict used, ``MEGACAP_COST``, assumes a 4% quoted width and charges
half of it per side, so 2% of premium each way. Two things about that are assumptions
rather than measurements, and they pull in opposite directions:

* the quoted width on this book was later measured at 5.14% median, wider than the 4%
  assumed, which makes the model optimistic;
* the model charges a full half-cross from mid to the touch, whereas real prints may land
  inside the touch, which makes it pessimistic.

``research_fills_study.py`` measures both from ``cmbp-1`` trade prints. This applies the
result. Three arms are scored on the identical frozen specification, changing only the cost:

    assumed    - MEGACAP_COST as the verdict used it
    quoted     - the measured quoted width, still charging a full half-cross
    effective  - the measured effective half-spread, i.e. where trades actually printed

The third arm is the honest execution ceiling. It is a ceiling and not an estimate for two
reasons that are printed with the result: the measurement covers 2023-2024 only, and a
resting order that captures price improvement is not guaranteed to fill at all, so the
improvement measured on completed prints is conditioned on having traded.

Run: ``python research/execution/run_fills_rescore.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

EXTENSION = "data/processed/events_megacap_quotes_2013_2018.parquet"
SUMMARY = Path("outputs/research/fills_study.csv")
OUT = Path("outputs/research/fills_rescore.csv")
Q = 0.80


def _score(events_path: str, cost: CostModel) -> dict:
    ev, _ = mv._prepare(events_path, chain_path=dq.cache_path)
    mask = np.asarray(expanding_high_term_mask(ev, Q), dtype=bool)
    led = mv._ledger(ev[mask].reset_index(drop=True), defined_risk=False, costs=cost)
    led = led.dropna(subset=["return_on_margin"])
    rom = pd.to_numeric(led["return_on_margin"], errors="coerce").dropna()
    if len(rom) < 2:
        return {"n": len(rom)}
    n = len(rom)
    s = float(rom.mean() / rom.std(ddof=1))
    se = float(np.sqrt((1 + s**2 / 2) / n))
    return {
        "n": n,
        "sharpe": s,
        "z": s / se,
        "p": float(1 - sps.norm.cdf(s / se)),
        "pnl": float(pd.to_numeric(led["pnl"], errors="coerce").sum()),
        "rom": rom,
        "entry": pd.to_datetime(led.loc[rom.index, "entry_date"]),
    }


def _clustered_ci(rom: pd.Series, clusters: pd.Series, n_boot: int = 5000) -> tuple[float, float]:
    """Percentile CI on the per-trade Sharpe, resampling whole announcement dates.

    Clustered because several names report on the same evening and their outcomes share
    that session's market move, so treating trades as independent would understate the
    interval. Identical to the resampling used for the headline verdict, so the corrected
    execution interval is comparable to it.
    """
    rng = np.random.default_rng(0)
    keys = pd.Index(clusters.unique())
    groups = {k: rom[clusters == k].to_numpy() for k in keys}
    draws = np.empty(n_boot)
    for b in range(n_boot):
        sample = np.concatenate([groups[k] for k in rng.choice(keys, size=len(keys), replace=True)])
        sd = sample.std(ddof=1)
        draws[b] = sample.mean() / sd if sd > 0 else np.nan
    draws = draws[np.isfinite(draws)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _trial_family() -> tuple[int, float]:
    """The recorded search family the DSR deflates against, taken from the panel."""
    p = pd.read_csv("outputs/research/performance_panel.csv").iloc[0]
    return int(p["n_trials"]), float(p["sr_trials_std"])


def _pooled(a: dict, b: dict) -> dict:
    rom = pd.concat([a["rom"], b["rom"]], ignore_index=True)
    entry = pd.concat([a["entry"], b["entry"]], ignore_index=True)
    n = len(rom)
    s = float(rom.mean() / rom.std(ddof=1))
    se = float(np.sqrt((1 + s**2 / 2) / n))
    span = max((entry.max() - entry.min()).days / 365.25, 1e-9)
    lo, hi = _clustered_ci(rom, entry.dt.normalize())
    n_trials, sr_std = _trial_family()
    dsr = float(deflated_sharpe_ratio(rom, n_trials=n_trials, sr_trials_std=sr_std))
    return {
        "n": n,
        "sharpe": s,
        "z": s / se,
        "p": float(1 - sps.norm.cdf(s / se)),
        "pnl": a["pnl"] + b["pnl"],
        "ann_sharpe": s * np.sqrt(n / span),
        "tpy": n / span,
        "ci_lo": lo,
        "ci_hi": hi,
        "dsr": dsr,
    }


def main() -> None:
    if not SUMMARY.exists():
        raise SystemExit(
            f"missing {SUMMARY}; run research/execution/research_fills_study.py --score first"
        )
    f = pd.read_csv(SUMMARY).iloc[0]
    quoted_half = float(f["quoted_half_median"])
    snap_half = float(f["snapshot_quoted_half_median"])
    eff_half = float(f["effective_half_median"])
    improvement = float(f["improvement_median"])

    print("Measured on cmbp-1, 15:30-16:00 America/New_York, 2023-03-28 onward:")
    print(f"  15:59 book, unconditional  {snap_half:.4%} of mid   <- the attainable arm")
    print(f"  trade-conditional quoted   {quoted_half:.4%} of mid   (selection-biased)")
    print(f"  effective half-spread      {eff_half:.4%} of mid")
    print(f"  price improvement          {improvement:.1%}")
    print(
        f"  assumed by MEGACAP_COST: {mv.MEGACAP_COST.bid_ask_pct*mv.MEGACAP_COST.cross_fraction:.4%}\n"
    )

    # Each arm carries its attainability, because the cheapest arm is the one a reader is
    # most likely to quote and the one a strategy cannot actually obtain. The metadata
    # travels in the CSV so the distinction survives being read without this docstring.
    arms = {
        "assumed_fixed_cost": (
            mv.MEGACAP_COST,
            "attainable_proxy",
            "none: modelling assumption, 4% quoted width charged as a half-cross",
            "yes",
        ),
        "measured_1559_snapshot": (
            CostModel(bid_ask_pct=snap_half * 2, cross_fraction=0.5),
            "best_empirical_basis",
            "none: the prevailing book at the mark, unconditional on a trade",
            "yes",
        ),
        "trade_conditional_print": (
            CostModel(bid_ask_pct=quoted_half * 2, cross_fraction=0.5),
            "selection_biased",
            "conditional on a print having occurred, which selects tight-spread states",
            "no",
        ),
    }

    rows = []
    for label, (cost, status, condition, recommended) in arms.items():
        a = _score(mv.EVENTS_FULL, cost)
        b = _score(EXTENSION, cost)
        p = _pooled(a, b)
        print(f"  {label}")
        print(f"    charged per side  {cost.bid_ask_pct*cost.cross_fraction:.4%} of premium")
        print(f"    2019-2024  N={a['n']}  Sharpe {a['sharpe']:+.6f}  p={a['p']:.4f}")
        print(f"    2013-2018  N={b['n']}  Sharpe {b['sharpe']:+.6f}  p={b['p']:.4f}")
        print(
            f"    POOLED     N={p['n']}  Sharpe {p['sharpe']:+.6f}  "
            f"ann {p['ann_sharpe']:+.3f} (x sqrt({p['tpy']:.1f}))  p={p['p']:.4f}  "
            f"P&L ${p['pnl']:,.0f}"
        )
        print(
            f"    clustered 95% CI  [{p['ci_lo']:+.4f}, {p['ci_hi']:+.4f}]   " f"DSR {p['dsr']:.4f}"
        )
        rows.append(
            {
                "cost_basis": label,
                "attainability_status": status,
                "selection_condition": condition,
                "recommended_for_inference": recommended,
                "charged_per_side": cost.bid_ask_pct * cost.cross_fraction,
                "n_2019": a["n"],
                "sharpe_2019": a["sharpe"],
                "p_2019": a["p"],
                "n_2013": b["n"],
                "sharpe_2013": b["sharpe"],
                "p_2013": b["p"],
                "n_pooled": p["n"],
                "sharpe_pooled": p["sharpe"],
                "ann_sharpe_pooled": p["ann_sharpe"],
                "p_pooled": p["p"],
                "ci_lo_pooled": p["ci_lo"],
                "ci_hi_pooled": p["ci_hi"],
                "dsr_pooled": p["dsr"],
                "pnl_pooled": p["pnl"],
            }
        )

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    rec = out[out["recommended_for_inference"] == "yes"]
    base = float(out.set_index("cost_basis").loc["assumed_fixed_cost", "sharpe_pooled"])
    head = float(out.set_index("cost_basis").loc["measured_1559_snapshot", "sharpe_pooled"])
    if float(rec["sharpe_pooled"].max()) < float(out["sharpe_pooled"].max()):
        print("\n  NOTE: the highest-Sharpe arm is NOT recommended for inference. See below.")
    print(
        f"\n  Headline: charging the measured 15:59 book moves pooled Sharpe "
        f"{base:+.6f} -> {head:+.6f} ({head-base:+.6f})."
    )
    print(
        "\n  The trade-conditional arm is a DIAGNOSTIC, not a ceiling the book can reach.\n"
        "  It conditions on a print having occurred, and prints cluster where the book is\n"
        "  tight, so it measures the spread in states a fixed-timestamp strategy cannot\n"
        "  select into. Both measured arms cover 2023-2024 only; transferring either to\n"
        "  earlier years is a cross-regime claim, since spreads tightened over the decade."
    )
    print(f"\nwritten: {OUT.resolve()}")


if __name__ == "__main__":
    main()
