"""
study.py
<One line: what this study tests.>

Scores the pre-registration in ``prereg.md`` exactly as frozen. Run once on the declared blocks;
every run is a trial.

Usage
-----
    python research/<line>/<slug>/study.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name


def load_events() -> pd.DataFrame:
    """The declared block, one row per event, with ``announce_date`` and the outcome column."""
    raise NotImplementedError("load the declared block here")


def select(events: pd.DataFrame) -> np.ndarray:
    """The pre-registered rule, as a boolean mask over ``events``."""
    raise NotImplementedError("the frozen rule goes here")


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    events = load_events()
    mask = select(events)
    print(f"funnel: {len(events)} events, {int(mask.sum())} selected")
    outcome = events["net_rom"].to_numpy()
    print("selected:", date_clustered_ci(outcome[mask], events.loc[mask, "announce_date"]))
    print("all:     ", date_clustered_ci(outcome, events["announce_date"]))
    print("null:    ", matched_random_null(outcome, mask))
    OUT.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
