"""
units_check.py
Lane D2, development only (rows entered before 2019): a units check requested by the team lead.
A no-feature Gaussian in z, fitted on each fold's full training window (mean and sd of z), is
scored on the 2016-18 fold events in the same % of m0 basis as D2, against the L4 baseline.
A gap near ln(100) = 4.6 nats would mean a units error; tails differ, so about 0.5 is the bar.
Fits no network; not a search configuration.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/units_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d2lib  # noqa: E402
import numpy as np  # noqa: E402


def main() -> None:
    ev = d2lib.load_real(heldout=False, note="units_check (no-feature Gaussian, 2016-18)")
    h, U = ev["h"].to_numpy(float), ev["U"].to_numpy(float)
    z = d2lib.to_z(np.where(np.isfinite(h), h, 0.0), U)
    tot_g, tot_b, n = 0.0, 0.0, 0
    for f in d2lib.dev_folds():
        m = d2lib.fold_masks(ev, f)
        mu, sd = z[m["full"]].mean(), z[m["full"]].std(ddof=1)
        rows = np.flatnonzero(m["score"])
        lp = -0.5 * np.log(2 * np.pi) - np.log(sd) - 0.5 * ((z[rows] - mu) / sd) ** 2
        g = d2lib.log_score_h(lp, h[rows], U[rows])
        sc = d2lib.scored_set(ev, rows, g)
        b = ev["l4_base_log_score"].to_numpy(float)[rows][sc]
        print(
            f"{f.label}: N {sc.sum()}; no-feature Gaussian {g[sc].mean():+.4f}; "
            f"L4 baseline {b.mean():+.4f}; gap {g[sc].mean() - b.mean():+.4f} nats"
        )
        tot_g += g[sc].sum()
        tot_b += b.sum()
        n += int(sc.sum())
    print(f"pooled: N {n}; gap {(tot_g - tot_b) / n:+.4f} nats (ln 100 = {np.log(100):.4f})")


if __name__ == "__main__":
    main()
