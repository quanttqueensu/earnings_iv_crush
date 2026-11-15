"""c1_score.py: trial 2,952, exclude the top causal decile of option-implied borrow.

Scores one block of the corrected panel with lib.score_mask (residual value and H_corr side by
side, date-clustered, matched null). The held-out block is read only if ``freeze_c1.md`` exists
and its recorded hash of this file matches.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c1_score.py --block 2013-18
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import sha256_file  # noqa: E402

TRIAL = 2952
N_BINS = 10  # deciles: hard-to-borrow is a tail property
FEATURE_FAMILY = "implied_borrow"


def build() -> pd.DataFrame:
    """Panel with the causal decile of borrow on dividend-free windows; funnel printed."""
    b = lib.load_base()
    f = pd.read_parquet(HERE / "c1_borrow.parquet")
    d = b.merge(
        f[["ticker", "entry_date", "borrow", "b_status", "div_free"]],
        on=["ticker", "entry_date"],
        how="left",
        validate="one_to_one",
    )
    d["block"] = lib.block_of(d["year"])
    print(
        f"panel {len(d)}; borrow ok {(d['b_status'] == 'ok').sum()}; "
        f"div_free {(d['div_free'] == 1).sum()}"
    )
    x = np.where(d["div_free"] == 1, d["borrow"], np.nan)
    d["bin"] = causal_bins(x, d["entry_date"], N_BINS, lib.CFG.min_prior)
    return d


def freeze_ok(path: Path) -> bool:
    if not path.exists():
        return False
    return sha256_file(Path(__file__)) in path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True, choices=[n for n, _, _ in lib.CFG.blocks])
    a = ap.parse_args(argv)
    if a.block != "2013-18" and not freeze_ok(HERE / "freeze_c1.md"):
        raise SystemExit("held-out read refused: no freeze note recording this scorer's hash")
    d = build()
    pop = d[(d["block"] == a.block) & (d["b_status"] == "ok") & d["residual_value"].notna()]
    pop = pop.reset_index(drop=True)
    print(
        f"block {a.block}: scored {len(pop)}; H_corr NaN {pop['H_corr'].isna().sum()}; "
        f"div_free with a bin {(pop['bin'] >= 0).sum()}; top decile {(pop['bin'] == 9).sum()}"
    )
    sel = (pop["bin"] != N_BINS - 1).to_numpy()
    r = lib.score_mask(pop, sel)
    r.update(trial=TRIAL, block=a.block, passes=lib.passes(r))
    # descriptive: the excluded decile's mean borrow and where its H_corr shortfall sits
    ex = pop[~sel]
    comp = ["c_premium", "c_settlement", "c_hedge", "c_equity_cost", "c_fees", "c_financing"]
    r["excluded_mean_borrow"] = float(ex["borrow"].mean())
    r["components_sel_minus_excl"] = {
        c: float(100 * (pop.loc[sel, c].mean() - ex[c].mean())) for c in comp
    }
    for o in ("residual_value", "H_corr"):
        print(lib.fmt(r, o))
    print("passes:", r["passes"])
    print(json.dumps(r, indent=2, default=float))
    (HERE / f"c1_results_{a.block}.json").write_text(
        json.dumps(r, indent=2, default=float), encoding="utf-8"
    )
    for fam in ("residual_value", "hedged_hold"):
        lib.log_view(a.block, fam, FEATURE_FAMILY, "L3 c1_score.py trial 2,952", "trial")


if __name__ == "__main__":
    main()
