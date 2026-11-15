"""
check_screens.py
Reviewer scratch check: the D1 and D2 tight-spread-per-date screens on identical inputs, their
half-spread sources, and a cross-recompute of each lane's selected-minus-screen point estimate
from the stored per-event files (held-out outputs already on disk; no scorer is re-run).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow  # noqa: F401
import pyarrow.parquet  # noqa: F401
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / "D1-surface-net"))
sys.path.insert(0, str(BASE / "D2-tabular"))
import d1eval  # noqa: E402
import d2lib  # noqa: E402

out = {}
d1 = pd.read_parquet(BASE / "D1-surface-net/heldout/cards_primary_2019-24.parquet")
d2 = pd.read_parquet(BASE / "D2-tabular/heldout_2019-24_events.parquet")
for d in (d1, d2):
    d["entry_date"] = pd.to_datetime(d["entry_date"]).dt.normalize()
m = d1.merge(d2, on=["ticker", "entry_date"], suffixes=("_1", "_2"), validate="one_to_one")
out["N_joined"] = len(m)
out["half_spread_maxabs_diff"] = float(np.nanmax(np.abs(m.half_spread_1 - m.half_spread_2)))
out["outcome_maxabs_diff_H_net"] = float(np.nanmax(np.abs(m.y - m.h)))
out["outcome_maxabs_diff_rv"] = float(np.nanmax(np.abs(m.rv_1 - m.rv_2)))
for name, sel_col, frame in (("D1_primary", "decide_1", m), ("D2_primary", "decide_2", m)):
    sel = frame[sel_col].to_numpy(bool)
    hs = frame["half_spread_1"].to_numpy(float)
    dates = frame["entry_date"].to_numpy()
    a = d1eval.tight_screen(sel, hs, dates)
    b = d2lib.tight_per_date(sel, hs, dates, frame["ticker"].to_numpy())
    ties = int(pd.DataFrame({"d": dates, "h": hs}).duplicated().sum())
    v = frame["y"].to_numpy(float)
    r = frame["rv_1"].to_numpy(float)
    out[name] = {
        "n_selected": int(sel.sum()),
        "screens_identical": bool((a == b).all()),
        "n_disagree": int((a != b).sum()),
        "same_count_per_date": bool(
            (pd.Series(a).groupby(dates).sum().values == pd.Series(sel).groupby(dates).sum().values).all()),
        "duplicate_date_spread_pairs": ties,
        "sel_minus_tight_H_net": round(float(v[sel].mean() - v[a].mean()), 4),
        "sel_minus_tight_rv": round(float(r[sel].mean() - r[a].mean()), 4),
        "overlap": round(float((sel & a).sum() / sel.sum()), 4),
    }
print(json.dumps(out, indent=1))
(HERE / "check_screens.json").write_text(json.dumps(out, indent=1) + "\n")
