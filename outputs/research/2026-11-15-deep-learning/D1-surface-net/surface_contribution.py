"""
surface_contribution.py
Lane D1: the surface's own contribution to the held-out log score, each frozen network minus
its frozen no-surface twin on the same events (declared in ``diagnosis.log`` entry 4, before any
held-out read). Reads the cards written once by ``score_heldout.py``; fits nothing.

Basis: nats per event, H_net space, date-clustered 95% on announcement dates.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/surface_contribution.py 2019-24
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import d1eval
import d1lib  # noqa: F401  (imports pyarrow before torch)
import pandas as pd

from earnings_iv_crush.research.protocol import log_block_view

HERE = Path(__file__).resolve().parent
PAIRS = {
    "D1b (primary minus control_primary)": ("primary", "control_primary"),
    "D1a (secondary minus control_secondary)": ("secondary", "control_secondary"),
}
KEYS = ["ticker", "entry_date"]


def main(block: str) -> None:
    stamp = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    log_block_view(
        HERE / "blocks_viewed.csv",
        panel="D1 held-out cards",
        period=block,
        outcome_family="H_net_log_density_and_book",
        feature_family="dl_surface_network",
        viewed_by=f"D1 surface_contribution (loaded {stamp})",
        kind="trial",
    )
    out: dict = {"block": block}
    for lab, (a, b) in PAIRS.items():
        ca = pd.read_parquet(HERE / "heldout" / f"cards_{a}_{block}.parquet")
        cb = pd.read_parquet(HERE / "heldout" / f"cards_{b}_{block}.parquet")
        m = ca[KEYS + ["log_score", "announce_date", "year", "decide"]].merge(
            cb[KEYS + ["log_score", "decide"]], on=KEYS, validate="one_to_one", suffixes=("", "_ns")
        )
        if len(m) != len(ca) or len(m) != len(cb):
            raise ValueError(f"{lab}: cards do not match one to one")
        r = d1eval.log_score_gain(
            m["log_score"].to_numpy(),
            m["log_score_ns"].to_numpy(),
            m["announce_date"].to_numpy(),
            m["year"].to_numpy(),
        )
        r["decision_agreement"] = round(float((m["decide"] == m["decide_ns"]).mean()), 4)
        out[lab] = r
        print(lab, json.dumps(r))
    (HERE / f"surface_contribution_{block}.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1])
