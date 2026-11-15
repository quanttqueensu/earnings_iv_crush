"""score_discovery.py: score the pre-registered N09 trials on the discovery blocks only.

Usage
-----
    python scripts/score_discovery.py            # writes logs/discovery_round1.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

import vxlib as V

OUT = V.LANE / "logs" / "discovery_round1.json"


def main() -> None:
    res: dict = {}
    specs = [
        ("T2322", "fomc", V.DISC_FOMC, 1),
        ("T2323", "fomc", V.DISC_FOMC, 2),
        ("T2324", "cpi", V.DISC_MACRO, 1),
        ("T2325", "nfp", V.DISC_MACRO, 1),
    ]
    for tid, kind, split, n in specs:
        t, funnel = V.event_table(kind, split, n, V.COST.primary_rt)
        s = V.summarise(t, V.COST.primary_rt, V.COST.stress_rt)
        s["funnel"] = funnel
        s["pass"] = V.passes(s)
        res[tid] = s
        t.to_csv(V.LANE / "logs" / f"disc_{tid}_{kind}_F{n}.csv", index=False)
        print(tid, kind, f"F{n}", json.dumps({k: s[k] for k in ("n", "net_ret", "surplus",
                                                                "pass")}, default=float))
    # T2326 / T2327: SOQ
    t, funnel = V.soq_table(V.DISC_FOMC)
    t.to_csv(V.LANE / "logs" / "disc_T2326_soq.csv", index=False)
    long_net = (t["gross_pts"] - V.COST.primary_entry_only) / t["entry_price"]
    short_net = (-t["gross_pts"] - V.COST.primary_entry_only) / t["entry_price"]
    res["T2326"] = {
        "funnel": funnel,
        "gross_ret_long": V.ci(t["gross_ret"], t["date"]),
        "net_long": V.ci(long_net, t["date"]),
        "net_short": V.ci(short_net, t["date"]),
        "next_contract_same_window_ret": V.ci(t["next_contract_ret"].dropna(),
                                              t.loc[t["next_contract_ret"].notna(), "date"]),
    }
    g = res["T2326"]["gross_ret_long"]
    res["T2326"]["pass"] = bool((res["T2326"]["net_long"]["low"] > 0)
                                or (res["T2326"]["net_short"]["low"] > 0))
    print("T2326 soq", json.dumps({"gross": g, "pass": res["T2326"]["pass"]}, default=float))
    lt = t.dropna(subset=["last_trade"])
    gap = (lt["soq"] - lt["last_trade"]) / lt["last_trade"]
    res["T2327"] = {"n": len(lt), "soq_minus_last_trade_ret": V.ci(gap, lt["date"])
                    if len(lt) > 2 else None, "diagnostic_only": True}
    print("T2327", json.dumps(res["T2327"], default=float))
    # T2328: VVIX
    t, funnel = V.index_event_change("fomc", V.DISC_FOMC, "VVIX")
    res["T2328"] = {"funnel": funnel, "vvix_logchg": V.ci(t["chg"], t["date"]),
                    "vvix_surplus": V.ci(t["surplus"], t["date"])}
    print("T2328", json.dumps(res["T2328"], default=float))
    # mechanism, not trials: VIX and VIX9D index log changes on event days
    mech = {}
    for kind, split in (("fomc", V.DISC_FOMC), ("cpi", V.DISC_MACRO), ("nfp", V.DISC_MACRO)):
        for col in ("VIX", "VIX9D"):
            t, f = V.index_event_change(kind, split, col)
            mech[f"{kind}_{col}"] = {"funnel": f, "chg": V.ci(t["chg"], t["date"]),
                                     "surplus": V.ci(t["surplus"], t["date"])}
    res["mechanism_indices"] = mech
    print("mechanism", json.dumps({k: (round(v["chg"]["point"], 4), round(v["surplus"]["point"], 4),
                                       round(v["surplus"]["low"], 4), round(v["surplus"]["high"], 4))
                                   for k, v in mech.items()}))
    OUT.write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    np.seterr(all="raise")
    sys.exit(main())
