"""
dry_check.py
Lane L4: exercises the held-out scorer's statistics on 2013-18 only, before the freeze, so a bug
in ``score_heldout.py`` is found while it can still be fixed without breaking the freeze hash.
Only discovery events are passed to the model; nothing held out is read, and nothing is written
to the lane's trial or block records.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/dry_check.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402
import score_heldout as sh  # noqa: E402

from earnings_iv_crush.config import OnlineBayesConfig  # noqa: E402


def _cfg(best: dict) -> tuple[OnlineBayesConfig, str]:
    kw = {k: v for k, v in best.items() if k not in ("group_level", "score")}
    return replace(OnlineBayesConfig(), **kw), str(best["group_level"])


def main() -> None:
    d_all = l4iter.load_all()
    d = d_all[d_all["block"] == "2013-18"].reset_index(drop=True)
    D = l4iter.Design(d)
    best = json.loads((HERE / "search_best_H_corr.json").read_text(encoding="utf-8"))
    (mc, ml), (bc, bl) = _cfg(best["model"]), _cfg(best["baseline"])
    y = l4lib.target(d, "H_corr", mc)
    rm = D.run(mc, y, with_features=True, group_level=ml, quiet=False)
    rb = D.run(bc, y, with_features=False, group_level=bl, quiet=False)
    disc = l4iter.score(rm, d, l4iter.discovery_mask(d, D.usable, y))
    print(
        f"[dry] model discovery score {disc['mean_log_score']:+.5f} (search {best['model']['score']:+.5f})"
    )
    for blk in ("2013-18", "2015-18"):
        sh.score_block(d, rm, rb, blk, "H_corr")
    sh._gauge_summary(rb.gauge, "baseline intercept (dry, discovery only)")
    bm = sh._book_mean_gauge(rb, d, bc)
    print(f"[dry] book-mean gauge rows {len(bm)}; last {bm.iloc[-1].to_dict()}")
    print(f"[dry] coefficient path rows {len(rm.path)}, columns {list(rm.path.columns)[:4]} ...")
    print("[dry] DRY RUN ON DISCOVERY ONLY: no held-out block was read")


if __name__ == "__main__":
    main()
