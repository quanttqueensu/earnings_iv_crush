"""score_round2.py: discovery round 2 for N09 (T2329 to T2332), discovery blocks only.

Usage
-----
    python scripts/score_round2.py        # writes logs/discovery_round2.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import vxlib as V

VOL_LOOKBACK = 20  # sessions of daily front-month returns for the risk scale
RATIO_LOOKBACK = 252  # sessions for the trailing median of VIX9D/VIX


def front_daily_returns() -> pd.Series:
    """Short-F1 settle-to-settle return for every session (contract held fixed over the day)."""
    settle, expiry, days, _, _ = V.load()
    out = {}
    for d in days[1:]:
        w = V.short_window(settle, expiry, days, d, 1)
        if w is not None:
            out[d] = w[0] / w[1]
    return pd.Series(out).sort_index()


def scaled(t: pd.DataFrame, r: pd.Series, days: pd.DatetimeIndex) -> pd.DataFrame:
    sd = r.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std()
    sig = []
    for d in t["date"]:
        p = V.prev_day(days, d)
        sig.append(sd.get(p, np.nan))
    t = t.assign(sigma=sig).dropna(subset=["sigma"])
    t["net_ret"] = t["net_ret"] / t["sigma"]
    t["surplus"] = t["surplus"] / t["sigma"]
    return t


def main() -> None:
    res: dict = {}
    _, _, days, _, idx = V.load()
    # T2329
    t, f = V.event_table("fomc", V.DISC_FOMC, 1, V.COST.primary_rt, entry_lag=2)
    s = V.summarise(t, V.COST.primary_rt, V.COST.stress_rt)
    s.update(funnel=f, passed=V.passes(s))
    res["T2329"] = s
    t.to_csv(V.LANE / "logs/disc_T2329.csv", index=False)
    # T2330
    t, f = V.event_table("fomc", V.DISC_FOMC, 1, V.COST.primary_rt)
    r = front_daily_returns()
    ts = scaled(t, r, days)
    res["T2330"] = {
        "funnel": {**f, "with_sigma": len(ts)},
        "net_ret_per_sigma": V.ci(ts["net_ret"], ts["date"]),
        "surplus_per_sigma": V.ci(ts["surplus"], ts["date"]),
        "median_sigma": float(ts["sigma"].median()),
    }
    res["T2330"]["passed"] = bool(res["T2330"]["net_ret_per_sigma"]["low"] > 0
                                  and res["T2330"]["surplus_per_sigma"]["low"] > 0)
    ts.to_csv(V.LANE / "logs/disc_T2330.csv", index=False)
    # T2331
    ratio = (idx["VIX9D"] / idx["VIX"]).dropna()
    med = ratio.rolling(RATIO_LOOKBACK, min_periods=RATIO_LOOKBACK).median()
    keep = []
    for d in t["date"]:
        p = V.prev_day(days, d)
        keep.append(bool(p in ratio.index and np.isfinite(med.get(p, np.nan))
                         and ratio[p] > med[p]))
    sub = t[np.array(keep)]
    s = V.summarise(sub, V.COST.primary_rt, V.COST.stress_rt)
    s.update(funnel={"events": len(t), "eligible_rich": len(sub),
                     "note": "VIX9D starts 2011; 252-session median from 2012"},
             passed=V.passes(s))
    res["T2331"] = s
    # T2332
    parts = []
    for kind in ("fomc", "cpi", "nfp"):
        tk, fk = V.event_table(kind, V.DISC_MACRO, 1, V.COST.primary_rt)
        parts.append(tk.assign(kind=kind))
    pool = pd.concat(parts, ignore_index=True)
    s = V.summarise(pool, V.COST.primary_rt, V.COST.stress_rt)
    s.update(by_kind=pool.groupby("kind")[["net_ret", "surplus"]].mean().to_dict(),
             passed=V.passes(s))
    res["T2332"] = s
    for k, v in res.items():
        key_net = "net_ret" if "net_ret" in v else "net_ret_per_sigma"
        key_sur = "surplus" if "surplus" in v else "surplus_per_sigma"
        print(k, "n", v[key_net]["n"], "net", {a: round(v[key_net][a], 4) for a in
                                                ("point", "low", "high")},
              "surplus", {a: round(v[key_sur][a], 4) for a in ("point", "low", "high")},
              "pass", v["passed"])
    (V.LANE / "logs/discovery_round2.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
