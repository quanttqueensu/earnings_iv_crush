"""
validate_screen.py
Check the pivot screening harness against the settled IV-crush book.

The screen is about to score candidates whose results nobody can eyeball for
plausibility. Before that, it has to reproduce a number that is already known and
already adjudicated: the pooled 2013-2024 quote-marked book on the frozen
specification, per-trade Sharpe +0.0560 with a clustered 95% interval of
[-0.0421, +0.1803] over N=391.

If ``engine.screen`` disagrees with that, the harness is wrong, not the old result.
This runs entirely off cached data and costs nothing.

Run: ``python scripts/validate_screen.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.market_validate as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.screen import score_signal  # noqa: E402
from scripts.run_extension_verdict import EXTENSION, Q  # noqa: E402
from scripts.validate_skew_oos import expanding_high_term_mask  # noqa: E402

# Published verdict, from paper/iv_crush_verdict.tex and outputs/research/extension_verdict.csv.
EXPECTED_N = 391
EXPECTED_SHARPE = 0.0560
EXPECTED_CI = (-0.0421, 0.1803)

SHARPE_TOL = 0.002  # point estimate must match to well inside a rounding step
CI_TOL = 0.030  # interval is bootstrap-seeded; require the same story, not the same bits


def _block(events_path: str) -> pd.DataFrame:
    """Per-trade rows for one block on the frozen specification."""
    events, _ = mv._prepare(events_path, chain_path=dq.cache_path)
    mask = np.asarray(expanding_high_term_mask(events, Q), dtype=bool)
    ledger = mv._ledger(
        events[mask].reset_index(drop=True), defined_risk=False, costs=mv.MEGACAP_COST
    )
    out = ledger[["entry_date", "return_on_margin"]].copy()
    out["return_on_margin"] = pd.to_numeric(out["return_on_margin"], errors="coerce")
    return out.dropna(subset=["return_on_margin"]).reset_index(drop=True)


def main() -> int:
    print("Rebuilding the settled book from cached quote marks (frozen spec, q=0.80)...")
    blocks = [_block(mv.EVENTS_FULL), _block(EXTENSION)]
    pooled = pd.concat(blocks, ignore_index=True).sort_values("entry_date").reset_index(drop=True)

    entry = pd.to_datetime(pooled["entry_date"])
    result = score_signal(
        pooled["return_on_margin"],
        entry,
        "iv-crush pooled 2013-2024",
        cadence="event",
        cluster_keys=entry.dt.normalize(),
        basis="per-trade",
        gross=False,
        n_boot=5000,
        seed=0,
    )

    print()
    print(result.summary())
    print()

    checks: list[tuple[str, bool, str]] = [
        ("N", result.n == EXPECTED_N, f"{result.n} vs expected {EXPECTED_N}"),
        (
            "per-trade Sharpe",
            abs(result.sharpe - EXPECTED_SHARPE) <= SHARPE_TOL,
            f"{result.sharpe:+.6f} vs expected {EXPECTED_SHARPE:+.4f}",
        ),
        (
            "CI low",
            abs(result.ci_low - EXPECTED_CI[0]) <= CI_TOL,
            f"{result.ci_low:+.4f} vs expected {EXPECTED_CI[0]:+.4f}",
        ),
        (
            "CI high",
            abs(result.ci_high - EXPECTED_CI[1]) <= CI_TOL,
            f"{result.ci_high:+.4f} vs expected {EXPECTED_CI[1]:+.4f}",
        ),
        (
            "interval contains zero",
            result.interval_contains_zero,
            "verdict unchanged" if result.interval_contains_zero else "VERDICT CHANGED",
        ),
        (
            "basis is per-trade",
            result.sharpe_basis == "per-trade",
            result.sharpe_basis,
        ),
    ]

    width = max(len(name) for name, _, _ in checks)
    ok = True
    for name, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name:<{width}}  {detail}")
        ok &= passed

    print()
    if ok:
        print("Harness reproduces the settled book. Safe to score unknown candidates.")
        return 0
    print("Harness does NOT reproduce the settled book. Fix the screen before using it.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
