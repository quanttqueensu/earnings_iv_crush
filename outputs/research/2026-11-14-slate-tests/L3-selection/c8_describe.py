"""c8_describe.py: logged descriptive counts behind the C8 text; no outcome is read.

Counts the broad-panel events on names with cached Alpaca daily option bars (why C8 runs on the
megacap panel), the attrition funnel of each block, and on the discovery block the residual tenor
and calendar year of trial 2,953's selected events. Imports ``c8_score.build`` unchanged.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c8_describe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import c8_score  # noqa: E402
import lib  # noqa: E402


def main() -> None:
    names = sorted(
        p.name[len("options_") : -len("_1d.parquet")]
        for p in c8_score.ALPACA.glob("options_*_1d.parquet")
    )
    b = lib.load_base()
    on = b[b["ticker"].isin(names) & b["year"].between(2013, 2024)]
    out: dict = {
        "alpaca_names": len(names),
        "broad_events_on_alpaca_names_2013_24": int(len(on)),
        "broad_names_hit": int(on["ticker"].nunique()),
    }
    mega = pd.read_parquet(HERE / "c8_megacap_corrected.parquet")
    out["megacap_valued"] = int(len(mega))
    d = c8_score.build()
    for blk in ("2013-18", "2019-24"):
        g = d[d["block"] == blk]
        out[f"funnel_{blk}"] = {
            "events": int(len(g)),
            "with_os_d1": int(np.isfinite(g["os_d1"]).sum()),
            "binned": int((g["bin"] >= 0).sum()),
            "selected": int((g["bin"] == c8_score.N_BINS - 1).sum()),
        }
    g = d[(d["block"] == "2013-18") & (d["bin"] >= 0)]
    days = (pd.to_datetime(g["expiry"]) - pd.to_datetime(g["exit_date"])).dt.days
    sel = g["bin"] == c8_score.N_BINS - 1
    out["disc_sel_days_mean"] = float(days[sel].mean())
    out["disc_sel_days_range"] = [int(days[sel].min()), int(days[sel].max())]
    out["disc_sel_by_year"] = {int(k): int(v) for k, v in g.loc[sel, "year"].value_counts().items()}
    out["disc_unsel_by_year"] = {
        int(k): int(v) for k, v in g.loc[~sel, "year"].value_counts().items()
    }
    print(json.dumps(out, indent=2))
    (HERE / "c8_describe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
