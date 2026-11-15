"""s04_rebuild_cboe.py: compliant rebuild of the realised side from Cboe price history, rescored.

The original realised side (s01_build.py) read GLD and SLV closes from the Yahoo chart API, whose
robots.txt disallows automated clients; those files were hashed and deleted (diagnosis.log entry
4). This script rebuilds the same panel and events from Cboe's public daily price history
(cdn-api.cboe.com delayed_quotes/charts/historical, raw/cboe_px/), reusing s01_build.py's logic
unchanged by replacing only its price loader, then scores both blocks with s02_score.score.

Trials (exploratory, held-out already read): 2,418 GLD pooled, 2,419 SLV pooled, 2,420 to 2,422
GLD FOMC, CPI, payrolls. Outputs carry a _cboe suffix; frozen files are not touched.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s04_rebuild_cboe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(ROOT))
import s01_build  # noqa: E402
import s02_score  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402

PX = HERE / "raw" / "cboe_px"


def _cboe(sym: str) -> pd.DataFrame:
    rows = json.loads((PX / f"{sym}_hist.json").read_text(encoding="utf-8"))["data"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    dup = df[df["date"].duplicated(keep=False)]
    if not dup.empty:
        # Only byte-identical duplicate rows may be collapsed; anything else is a data conflict.
        if dup.drop_duplicates().shape[0] != dup["date"].nunique():
            raise RuntimeError(f"{sym}: conflicting duplicate dates {sorted(dup['date'].unique())}")
        print(f"{sym}: collapsed identical duplicate rows on {sorted(set(dup['date'].dt.date))}")
        df = df.drop_duplicates()
    df = df.set_index("date").sort_index()
    sess = set(pd.DatetimeIndex(nyse_sessions("2015-12-01", "2026-11-13")))
    span = df.loc["2015-12-01":"2026-11-13"]
    extra = [d.date() for d in span.index if d not in sess]
    if extra:
        print(f"{sym}: dropping {len(extra)} non-NYSE-session dates: {extra}")
    df = df[~((df.index >= "2015-12-01") & (df.index <= "2026-11-13") & ~df.index.isin(list(sess)))]
    return df[["close", "open"]].astype(float)


def main() -> None:
    s01_build._yahoo = _cboe  # the only change: the price loader
    s01_build.OUT = HERE / "panel_cboe.parquet"
    s01_build.EVENTS_OUT = HERE / "events_cboe.parquet"
    s01_build.main()
    ev = pd.read_parquet(HERE / "events_cboe.parquet")
    sets = {
        2418: ("GLD", lambda k: k != "", "GLD pooled (Cboe prices)"),
        2419: ("SLV", lambda k: k != "", "SLV pooled (Cboe prices)"),
        2420: ("GLD", lambda k: "fomc" in k, "GLD FOMC (Cboe prices)"),
        2421: ("GLD", lambda k: k == "cpi", "GLD CPI (Cboe prices)"),
        2422: ("GLD", lambda k: k == "nfp", "GLD payrolls (Cboe prices)"),
    }
    out = {}
    for block in ("discovery", "heldout"):
        for tid, (sym, sel, label) in sets.items():
            sub = ev[(ev["block"] == block) & (ev["sym"] == sym) & ev["kind"].map(sel)]
            r = s02_score.score(sub)
            out[f"{tid}_{block}"] = {"label": label, "block": block, **r}
            print(f"trial {tid} {label} [{block}] N={r['n']}: mean S {r['S_mean']:+.3f} "
                  f"[{r['S_lo']:+.3f}, {r['S_hi']:+.3f}]; eQ/u {r['eQ_u_mean']:+.3f}, "
                  f"eP/u {r['eP_u_mean']:+.3f}; pi_1 {r['pi_1']:+.4f}")
    (HERE / "results_cboe_rebuild.json").write_text(json.dumps(out, indent=2, default=float),
                                                    encoding="utf-8")
    old = pd.read_parquet(HERE / "events.parquet")
    m = old.merge(ev, on=["date", "sym"], suffixes=("_old", "_new"))
    print(f"events matched old/new {len(m)} of old {len(old)}, new {len(ev)}; "
          f"max |r diff| {np.abs(m['r_old'] - m['r_new']).max():.5f}")


if __name__ == "__main__":
    main()
