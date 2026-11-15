"""score_discovery_2208.py: the straddle-return metric (trials 2208-2211) on discovery 2016-2020.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N05-treasuries-macro/scripts/score_discovery_2208.py
"""

from __future__ import annotations

import json

from vx_lib import CFG, LANE, build_events, load_panel, summarise

if __name__ == "__main__":
    panel = load_panel()
    print(f"[check] straddle return sample {panel['straddle'].describe().round(4).to_dict()}")
    ev = build_events(panel, CFG.disc_start, CFG.disc_end, "straddle")
    out = {"2208_pooled": summarise(ev, "2208 straddle pooled (discovery)")}
    for k, tid in (("nfp", 2209), ("cpi", 2210), ("fomc", 2211)):
        out[f"{tid}_{k}"] = summarise(ev[ev["kinds"].str.contains(k)], f"{tid} straddle {k} (discovery)")
    x = ev[(ev["date"] < "2020-02-15") | (ev["date"] > "2020-06-30")]
    print(f"[diagnostic, not a trial] excluding 2020-02-15..2020-06-30: mean d {x['d'].mean():+.4f}, N={len(x)}")
    print(f"[diagnostic] share of events with d > 0: {(ev['d'] > 0).mean():.3f}; worst 3 d: "
          f"{ev.nsmallest(3, 'd')[['date', 'kinds', 'd']].to_dict('records')}")
    ev.to_csv(LANE / "logs" / "discovery_events_2208.csv", index=False)
    (LANE / "logs" / "discovery_results_2208.json").write_text(json.dumps(out, indent=2, default=str))
