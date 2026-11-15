"""s00_base.py: build and describe the base event table (no selection, pool description only)."""

from __future__ import annotations

import pandas as pd

import lib

d = lib.load_events()
print(d.groupby("year").size().to_dict())
print(pd.crosstab(d.tenor, d.im_bin))
cols = ["im", "jump_share", "iv_term_spread", "entry_spread", "y", "r_meas", "y_gross", "mv_ratio"]
print(d[cols].describe().round(4))
print(d.groupby(pd.cut(d.year, [2012, 2015, 2019, 2024, 2026]))[["y", "r_meas", "y_gross"]].mean())
d.to_parquet(lib.HERE / "base_events.parquet")
