"""
smoke_synthetic.py
Lane D2: synthetic smoke run of the fold runner (SYNTHETIC data only; no real row is read).
Fits K=1 and K=2 Gaussian-mixture heads and the Student-t head on the 2016-18 rolling-origin
folds of a planted-effect synthetic panel and prints the gain over the constant benchmark.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/smoke_synthetic.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d2lib  # noqa: E402
import d2net  # noqa: E402
import numpy as np  # noqa: E402


def main() -> None:
    ev = d2lib.synthetic(n=4000, seed=1)
    for cfg in (d2net.Config(K=1), d2net.Config(K=2, hidden=(32, 32)), d2net.Config(head="t")):
        t0 = time.time()
        out, info = d2net.run(ev, d2lib.dev_folds(), cfg, (0, 1))
        l4 = ev["l4_model_log_score"].to_numpy()[out["row"].to_numpy()]
        g = out["d2_log_score"].to_numpy() - l4
        print(
            f"SYNTHETIC {cfg} gain over constant {np.nanmean(g):+.4f} "
            f"N {int(np.isfinite(g).sum())} epochs {[i['epochs'] for i in info]} "
            f"{time.time() - t0:.1f}s"
        )
        if cfg.head == "gm":
            print(
                "  mean pred_mean",
                float(out["pred_mean"].mean()),
                "mean h",
                float(ev["h"].to_numpy()[out["row"]].mean()),
            )


if __name__ == "__main__":
    main()
