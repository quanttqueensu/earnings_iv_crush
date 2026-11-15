"""
s02_event_richness.py
Round 1b: richness measured on the event component only.

Round 1 showed that richness against the jump_share forecast is jump_share with the sign
flipped (rank correlation -1.00) and therefore long tenor (rank correlation +0.83 with days to
expiry). This variant strips the diffusive part first: the implied event move is the square root
of the two-expiry jump variance, and it is compared with the name's own mean log move over its
last eight events (at least four), all closed before entry.

Usage
-----
    python s02_event_richness.py [--block 2016 2019] [--log]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib

ap = argparse.ArgumentParser()
ap.add_argument("--block", nargs=2, type=int, default=[2016, 2019])
ap.add_argument("--log", action="store_true")
a = ap.parse_args()
blk = (a.block[0], a.block[1])

d = pd.read_parquet(lib.HERE / "richness_events.parquet")
jv = d["jsplit_jump_var"].where(d["jsplit_valid"].astype(bool) & (d["jsplit_jump_var"] > 0))
d["log_sj"] = 0.5 * np.log(jv)
d["rich_event"] = d["log_sj"] - d["hist_move"]
print(f"funnel: jump split valid {int(jv.notna().sum())}, rich_event defined {int(d['rich_event'].notna().sum())}")
m = d["year"].between(*blk)
print(d.loc[m, ["rich_event", "log_im", "jump_share", "dte", "log_sj"]].corr(method="spearman").round(2).to_string())
hyp = "R5 top tercile of log implied event move (two-expiry jump) minus own mean log move"
mech = (
    "with the diffusive part stripped, an implied event move above the name's own realised "
    "history is premium the event does not earn back, at any tenor"
)
tr, df = lib.top_bin(d, "rich_event", 3)
res = lib.score(d, tr, df & d["rich_event"].notna(), blk)
print(lib.bins_table(d, "rich_event", blk, 3).to_string())
print(lib.bins_table(d, "rich_event", blk, 3, by="tenor").to_string())
if a.log:
    ok = res.get("ci_low", -1) > 0 and res.get("null_pct", 0) >= 95 and res.get("t", 0) >= 3
    lib.log_trial(1694, hyp, mech, res, "pass discovery" if ok else "fail discovery")
d.to_parquet(lib.HERE / "richness_events.parquet")
