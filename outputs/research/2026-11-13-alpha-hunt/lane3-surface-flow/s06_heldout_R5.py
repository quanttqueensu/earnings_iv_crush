"""s06_heldout_R5.py: the single held-out read of the frozen R5 spec (freeze_2026-11-13_R5.md)."""

from __future__ import annotations

import pandas as pd

import lib

d = pd.read_parquet(lib.HERE / "all_features.parquet")
tr, df = lib.top_bin(d, "rich_event", 3)
df &= d["rich_event"].notna()
hyp = "R5 frozen: top tercile of log implied event move minus own mean log move"
mech = "implied event move above own history lowers gap cost per unit of premium"
for tid, blk in ((1707, (2020, 2024)), (1708, (2025, 2026))):
    print(f"\n[{tid}] held-out {blk}")
    res = lib.score(d, tr, df, blk)
    ok = res["ci_low"] > 0 and res["null_pct"] >= 95 and res["t"] >= 3
    lib.log_trial(tid, hyp, mech, res, "pass held-out" if ok else "fail held-out")
    print(lib.bins_table(d, "rich_event", blk, 3).to_string())
    print(lib.bins_table(d, "rich_event", blk, 3, by="tenor").drop(columns=["y", "im"]).to_string())
    for col in ("gap_cost", "extrinsic"):
        r = lib.score(d, tr, df, blk, ycol=col, n_boot=1000, quiet=True)
        print(f"  {col:10s} {r['effect']:+.4f} [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}]")
