"""
research_ml_zoo_full.py
The model zoo and the nested walk-forward on the full 15:59-quote event set, 2013-2026.

Merges the 2013-2024 megacap panel, the 2013-2024 broad-universe events built from the Databento
pull (``build_broad_history_events.py`` shards), the 2025-2026 broad events rebuilt on 15:59 quotes,
and the July-August 2026 events, then re-derives every feature across the whole table (so per-name
histories span all blocks) and runs the zoo grid and the nested walk-forward on it.

Usage:
    python research/selection/research_ml_zoo_full.py --build
    python research/selection/research_ml_zoo_full.py --zoo [--workers 6]
    python research/selection/research_ml_nested.py --events outputs/research/ml_zoo/events_full.parquet
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = Path("outputs/research/ml_zoo")
FULL = OUT / "events_full.parquet"
KEEP = ["ticker", "announce_date", "entry_date", "exit_date", "rom", "realised_move", "block"]


def build() -> None:
    import research.selection.research_ml_zoo as zoo

    cur = pd.read_parquet(OUT / "events_1559.parquet")[KEEP + zoo.BASE]
    shards = sorted(glob.glob(str(OUT / "broad_history_events_shard*of6.parquet")))
    if len(shards) != 6:
        raise SystemExit(f"expected 6 history shards, found {len(shards)}")
    h = pd.concat([pd.read_parquet(p) for p in shards], ignore_index=True)
    h = h.assign(block="broad_hist")[KEEP + zoo.BASE]
    for c in ("announce_date", "entry_date", "exit_date"):
        h[c] = pd.to_datetime(h[c])
        cur[c] = pd.to_datetime(cur[c])
    base = pd.concat([cur, h], ignore_index=True).drop_duplicates(["ticker", "entry_date"])
    d = zoo.enrich(base)
    d.to_parquet(FULL, index=False)
    print(f"  wrote {len(d)} events -> {FULL}: {d['block'].value_counts().to_dict()}", flush=True)


def run_zoo(workers: int) -> None:
    os.environ["ZOO_EVENTS"] = str(FULL)
    import research.selection.research_ml_zoo as zoo

    zoo.EVENTS = FULL
    keep = {p: p.read_bytes() for p in (OUT / "zoo_results.csv", OUT / "zoo_predictions.parquet")}
    zoo.run(workers)
    (OUT / "zoo_results.csv").replace(OUT / "zoo_results_full.csv")
    (OUT / "zoo_predictions.parquet").replace(OUT / "zoo_predictions_full.parquet")
    for p, data in keep.items():
        p.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--zoo", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.build:
        build()
    if a.zoo:
        run_zoo(a.workers)


if __name__ == "__main__":
    main()
