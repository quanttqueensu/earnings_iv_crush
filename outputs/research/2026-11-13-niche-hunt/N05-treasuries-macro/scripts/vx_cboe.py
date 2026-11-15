"""vx_cboe.py: re-score of the VXTLT pilot with a robots-compliant TLT price source (trials 2218-2221).

The frozen pilot (``vx_lib.py``) took TLT closes from Yahoo's chart API, whose robots.txt
disallows all agents; that file is deleted. This module rebuilds the same panel from Cboe's
public TLT daily history (split-adjusted, not dividend-adjusted) and blanks the first trading
day of each month on both event and control sides, a calendar proxy for TLT's ex-dividend day.
Every other definition is imported unchanged from ``vx_lib.py``. Held-out results here are
descriptive: the held-out block was read once already (``diagnosis.log`` entry 4).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N05-treasuries-macro/scripts/vx_cboe.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import vx_lib
from vx_lib import CFG, LANE, black_straddle, build_events, summarise

TLT_CBOE = LANE / "raw" / "cboe" / "TLT_daily.json"
CI_HELD = 0.975


def load_panel_cboe() -> pd.DataFrame:
    """Same fields as ``vx_lib.load_panel`` with Cboe TLT closes and ex-dividend proxy days blanked."""
    vx = pd.read_csv(vx_lib.VX_PATH)
    vx["date"] = pd.to_datetime(vx["DATE"], format="%m/%d/%Y")
    vx = vx.set_index("date")["VXTLT"].astype(float)
    raw = pd.DataFrame(json.loads(TLT_CBOE.read_text())["data"])
    tlt = raw.assign(date=pd.to_datetime(raw["date"])).set_index("date")["close"].astype(float)
    p = pd.concat({"vx": vx, "tlt": tlt}, axis=1, join="inner").dropna()
    if ((p["vx"] <= 0) | (p["tlt"] <= 0)).any():
        raise ValueError("non-positive rows in panel")
    tau = CFG.tau_days / CFG.year_days
    p["sig2"] = (p["vx"] / 100.0) ** 2
    p["delta"] = p.index.to_series().diff().dt.days / CFG.year_days
    p["r"] = np.log(p["tlt"] / p["tlt"].shift(1))
    s2_prev = p["sig2"].shift(1)
    p["e"] = s2_prev * tau - p["sig2"] * (tau - p["delta"])
    p["y"] = (p["e"] - p["r"] ** 2) / (s2_prev * p["delta"])
    f_prev = p["tlt"].shift(1)
    v0 = black_straddle(f_prev, f_prev, np.sqrt(s2_prev), tau)
    v1 = black_straddle(p["tlt"], f_prev, np.sqrt(p["sig2"]), tau - p["delta"])
    p["straddle"] = (v0 - v1) / v0
    month = p.index.to_period("M")
    first_day = pd.Series(month, index=p.index).ne(pd.Series(month, index=p.index).shift(1))
    gap = p["delta"] > 5 / CFG.year_days
    blank = first_day | gap
    print(f"[panel cboe] {int(first_day.sum())} first-of-month (ex-dividend proxy) and {int(gap.sum())} gap rows blanked")
    p.loc[blank, ["y", "e", "straddle"]] = np.nan
    return p.iloc[1:]


if __name__ == "__main__":
    panel = load_panel_cboe()
    out = {}
    d = build_events(panel, CFG.disc_start, CFG.disc_end, "straddle")
    out["2218_disc_pooled"] = summarise(d, "2218 straddle pooled, Cboe TLT (discovery)")
    out["2219_disc_fomc"] = summarise(d[d["kinds"].str.contains("fomc")], "2219 straddle FOMC, Cboe TLT (discovery)")
    h = build_events(panel, CFG.held_start, CFG.held_end, "straddle")
    for lab, sub, tid in (("pooled", h, 2220), ("FOMC", h[h["kinds"].str.contains("fomc")], 2221)):
        res = summarise(sub, f"{tid} straddle {lab}, Cboe TLT (held-out, descriptive, 95%)")
        from earnings_iv_crush.research.protocol import date_clustered_ci

        iv = date_clustered_ci(sub["d"], sub["month"], stat=np.mean, n_boot=CFG.n_boot, seed=CFG.seed, ci=CI_HELD)
        res["lo_975"], res["hi_975"] = iv.low, iv.high
        print(f"    97.5% interval [{iv.low:+.4f}, {iv.high:+.4f}]")
        out[f"{tid}_held_{lab}"] = res
    (LANE / "logs" / "cboe_rescore.json").write_text(json.dumps(out, indent=2, default=str))
