"""
corrections.py
Logged figures for the corrected 2026-11-12 tail-signal findings. Not a trial.

Records the attrition split and exact Fisher tests for the small cells quoted in ``findings.md``,
so every figure there traces to a file. The Fisher tests are descriptive: they come from trials
that failed discovery and cannot support a claim.

Usage
-----
    python research/selection/2026-11-12-tail-event-signals/corrections.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import numpy as np  # noqa: E402
import study as s  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

OUT = s.OUT / "corrections.json"


def main() -> None:
    res = json.loads((s.OUT / "results.json").read_text())
    out: dict[str, object] = {"label": "descriptive, from failed trials, not evidence"}
    cells = {"T1_peer_shock": "discovery", "T2_oscore": "validation"}
    for trial, blk in cells.items():
        r = res["trials"][trial][blk]
        tab = [
            [r["tails_treated"], r["treated"] - r["tails_treated"]],
            [r["tails_untreated"], r["defined"] - r["treated"] - r["tails_untreated"]],
        ]
        odds, p = fisher_exact(tab)
        out[f"{trial}_{blk}_fisher"] = {"table": tab, "odds_ratio": odds, "p_two_sided": p}
        print(f"{trial} {blk}: table {tab} Fisher p {p:.3f}")

    ch = s.load_chars()
    ev = s.attach_chars(s.load_events(), ch)
    yr = ev["entry_date"].dt.year
    m = (yr >= 2015) & (yr <= 2024)
    has = ev["chars_eom"].notna()
    for name, mask in (("with_chars", m & has), ("without_chars", m & ~has)):
        sub = ev[mask]
        out[f"attrition_{name}"] = {
            "n": int(len(sub)),
            "tail_rate": float(sub["tail"].mean()),
            "mean_B": float(np.nanmean(sub["B"])),
        }
        print(
            f"attrition {name}: N {len(sub)} tail {sub['tail'].mean():.3f} mean B "
            f"{np.nanmean(sub['B']):+.4f}"
        )
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
