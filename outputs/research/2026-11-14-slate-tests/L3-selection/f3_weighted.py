"""f3_weighted.py: the expected per-trade mean of a randomly capped book against the uncapped one.

A uniform random cap of k per session keeps each event with probability min(1, k / n_session), so
its expected per-trade mean is the weighted mean with those weights. The capped-minus-uncapped
difference is given with a 95% interval resampling reaction-session dates. Exploratory: it reads
how the cap reweights sessions, not a selector.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/f3_weighted.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.protocol import N_BOOT, SEED  # noqa: E402

CAPS = (10, 5, 3)


def _wdiff(m: np.ndarray) -> float:
    h, w = m[:, 0], m[:, 1]
    return float((w * h).sum() / w.sum() - h.mean())


def main() -> None:
    b = lib.load_base()
    b["block"] = lib.block_of(b["year"])
    b = b[b["H_corr"].notna()]
    out: dict = {}
    for name, _, _ in lib.CFG.blocks:
        g = b[b["block"] == name]
        n = g.groupby("entry_date")["ticker"].transform("size").to_numpy(float)
        h = 100 * g["H_corr"].to_numpy(float)
        keys = g["exit_date"].dt.normalize().to_numpy()
        for cap in CAPS:
            w = np.minimum(1.0, cap / n)
            m = np.column_stack([h, w])
            lo, hi = cluster_bootstrap_ci(m, keys, _wdiff, n_boot=N_BOOT, seed=SEED)
            out[f"{name}_cap{cap}"] = {"diff": _wdiff(m), "lo": lo, "hi": hi, "N": int(len(g))}
            print(name, cap, {k: round(v, 3) for k, v in out[f"{name}_cap{cap}"].items()})
    (HERE / "f3_weighted.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
