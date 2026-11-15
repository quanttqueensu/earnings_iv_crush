"""
study.py
<One line: what this study tests.>

Scores the pre-registration in ``prereg.md`` exactly as frozen. Develop and debug on blinded
outcomes (the default); run ``--unblind`` once, after the pre-freeze review says go and the
freeze records this file and its inputs (``docs/PROTOCOL.md`` P16 to P21). Blocks are scored in
order and scoring stops at the first failed stage, so a failed trial has no later-block numbers.

Usage
-----
    python research/<line>/<slug>/study.py            # blinded development run
    python research/<line>/<slug>/study.py --unblind  # the one real run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    blind,
    date_clustered_ci,
    date_clustered_pvalue,
    log_block_view,
    matched_random_null,
    staged_scoring,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
LEDGER = ROOT / "research" / "ledger" / "blocks.csv"

# ── frozen parameters (copy every number from the prereg, with its derivation) ──
BLOCKS = ("discovery", "validation", "confirmation")  # scored in this order
PANEL, OUTCOME_FAMILY, FEATURE_FAMILY = "<panel>", "<outcome family>", "<feature family>"


def load_events() -> pd.DataFrame:
    """Every declared block, one row per event, with ``block``, ``announce_date``, outcome."""
    raise NotImplementedError("load the declared blocks here and print a funnel")


def select(events: pd.DataFrame) -> np.ndarray:
    """The pre-registered rule, as a boolean mask over ``events``."""
    raise NotImplementedError("the frozen rule goes here")


def score_block(events: pd.DataFrame, block: str) -> dict[str, Any]:
    """Primary statistic, interval, p-value and matched null for one block."""
    blk = events[events["block"] == block]
    mask = select(blk)
    y = blk["outcome"].to_numpy(float)
    sel = date_clustered_ci(y[mask], blk.loc[mask, "announce_date"])
    p = date_clustered_pvalue(y[mask], blk.loc[mask, "announce_date"])
    null = matched_random_null(y, mask)
    print(f"{block}: {int(mask.sum())} of {len(blk)} selected; {sel}; p {p:.4f}; {null}")
    return {
        "n": int(mask.sum()),
        "stat": [sel.point, sel.low, sel.high],
        "p": p,
        "null_pct": null.percentile,
    }


def passes(res: dict[str, Any]) -> bool:
    """The frozen success criterion for one stage."""
    raise NotImplementedError("copy the prereg's stage criterion here")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unblind", action="store_true", help="the one real run")
    ap.add_argument("--rerun-reason", default=None, help="required for a second real run")
    args = ap.parse_args(argv)
    sha = verify_prereg(PREREG, RECORD, unblind=args.unblind, rerun_reason=args.rerun_reason)
    print(
        f"pre-registration verified, sha256 {sha[:12]}; {'UNBLINDED' if args.unblind else 'blind'}"
    )
    events = load_events()
    if not args.unblind:
        events = events.assign(outcome=blind(events["outcome"], events["announce_date"]))
    res = staged_scoring(BLOCKS, lambda b: score_block(events, b), passes)
    print(f"stopped at: {res['stopped_at']}; passed all stages: {res['passed']}")
    if args.unblind:
        for b in res["blocks"]:
            log_block_view(
                LEDGER,
                panel=PANEL,
                period=b,
                outcome_family=OUTCOME_FAMILY,
                feature_family=FEATURE_FAMILY,
                viewed_by=HERE.name,
            )
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
