"""score_discovery.py: H1 and its secondaries on the 2016-2020 discovery block.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N05-treasuries-macro/scripts/score_discovery.py
"""

from __future__ import annotations

import json

from vx_lib import CFG, LANE, build_events, load_panel, summarise

if __name__ == "__main__":
    panel = load_panel()
    s, e = CFG.disc_start, CFG.disc_end
    out = {}
    ev = build_events(panel, s, e, "y")
    out["2202_H1_pooled"] = summarise(ev, "2202 H1 pooled, normalised (discovery)")
    for k, tid in (("nfp", 2203), ("cpi", 2204), ("fomc", 2205)):
        sub = ev[ev["kinds"].str.contains(k)]
        out[f"{tid}_S1_{k}"] = summarise(sub, f"{tid} S1 {k} (discovery)")
    raw = build_events(panel, s, e, "y_raw")
    raw["d"] = raw["d"] * 1e4  # percent-squared units, comparable with Wright (2020) Table 5
    out["2206_S2_raw_pct2"] = summarise(raw, "2206 S2 un-normalised, pct^2 (discovery)")
    st = build_events(panel, s, e, "s")
    out["2207_S3_straddle_share"] = summarise(st, "2207 S3 straddle share at the index mark (discovery)")
    ev.to_csv(LANE / "logs" / "discovery_events.csv", index=False)
    (LANE / "logs" / "discovery_results.json").write_text(json.dumps(out, indent=2, default=str))
