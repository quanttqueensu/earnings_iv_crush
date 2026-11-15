"""
round3b.py
Lane I (entry day), round 3 fix: a volatility-pegged resting offer.

T2031 and T2032 were picked off: a static price limit is crossed whenever the stock moves (the
straddle gains value) or implied vol rises, and the fill lands about 5% of m0 below the fill-day
mid. T2033 re-prices the offer every snapshot day at the entry-day implied vol (the D-k straddle
mid IV) on that day's forward and tenor, so a spot move alone no longer crosses it; it fills only
when the bid's implied vol reaches the entry IV. Same fill rule (end-of-day quote-through, D0
15:59 Databento last), same fallback to the S0 sale, same hedge.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/round3b.py --set discovery
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from analyse import pick_bin  # noqa: E402
from build import FEATURES, databento_chain, dolthub_atm, hold, simulate  # noqa: E402
from pull import cached, shift  # noqa: E402
from round3 import straddle_touch  # noqa: E402
from score import ci, log_trial, signflip_pct  # noqa: E402

from earnings_iv_crush.research.hedged_hold import straddle_value, year_frac  # noqa: E402


def vol_pegged(r: pd.Series, s0: pd.Series, f: pd.Series, crsp: dict, permno: float) -> dict:
    d0, exp, k = pd.Timestamp(r["entry_date"]), pd.Timestamp(r["expiry"]), float(r["strike"])
    sig_l = float(r["iv_entry"]) + float(r.get("vol_offset", 0.0))
    for j in range(int(r["k"]) - 1, -1, -1):
        day = shift(d0, -j)
        if j == 0:
            bid, mid = straddle_touch(databento_chain(r["ticker"], d0), exp, k)
            fwd = float(f["front_fwd"])
            src = "databento_d0"
        else:
            p = cached(r["ticker"], day)
            if p is None:
                continue
            bid, mid = straddle_touch(pd.read_parquet(p), exp, k)
            q = dolthub_atm(r["ticker"], day, exp)
            if isinstance(q, str) or not np.isfinite(bid):
                continue
            fwd = q["fwd"]
            src = "dolthub"
        if not np.isfinite(bid):
            continue
        limit = straddle_value(fwd, k, year_frac(day, exp), sig_l)
        if bid >= limit:
            st, g = hold.stock_path(crsp, permno, day, exp)
            if st != "ok" or g is None:
                return {"filled": True, "net_rest": np.nan, "src": f"path_{st}"}
            res = simulate(
                g=g,
                entry=day,
                hedge_from=day,
                d0=d0,
                t1=pd.Timestamp(r["exit_date"]),
                expiry_last=g.index[-1],
                expiry=exp,
                k=k,
                fwd=fwd,
                bid=limit,
                mid=mid,
                sig_pre=sig_l,
                sig_post=r["sig_post"],
            )
            return {
                "filled": True,
                "net_rest": res["net"] / r["m0"],
                "src": src,
                "below_mid_m0": (limit - mid) / r["m0"],
            }
    return {"filled": False, "net_rest": s0["net_m0"], "src": "none"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Lane I round 3b")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    d = pd.read_parquet(HERE / f"arms_{a.set}.parquet")
    ok = d[d["status"] == "ok"]
    s0 = ok[ok["arm"] == "S0"].set_index(["ticker", "entry_date"])
    e = pick_bin(ok, 7, 10).reset_index(drop=True)
    feats = pd.read_parquet(FEATURES)
    feats["entry_date"] = pd.to_datetime(feats["entry_date"])
    feats = feats.drop_duplicates(["ticker", "entry_date"]).set_index(["ticker", "entry_date"])
    crsp = hold.load_crsp()
    rows = []
    for _, r in e.iterrows():
        key = (r["ticker"], r["entry_date"])
        rows.append(vol_pegged(r, s0.loc[key], feats.loc[key], crsp, feats.loc[key, "permno"]))
    x = pd.concat([e, pd.DataFrame(rows)], axis=1)
    x["net_s0"] = [s0.loc[(t, dt), "net_m0"] for t, dt in zip(x["ticker"], x["entry_date"])]
    print(f"  fill sources {x['src'].value_counts().to_dict()}")
    x = x.dropna(subset=["net_rest"])
    dd = x["net_rest"] - x["net_s0"]
    c = ci(dd, x["exit_date"])
    pct = signflip_pct(dd, x["exit_date"])
    lvl = ci(x["net_rest"], x["exit_date"])
    fl = x[x["filled"].astype(bool)]
    cf = ci(fl["net_rest"] - fl["net_s0"], fl["exit_date"])
    print(
        f"T2033 vol-pegged resting: N={c['n']} fill rate {x['filled'].mean():.3f}; book minus S0 "
        f"{c['point']:+.4f} [{c['low']:+.4f}, {c['high']:+.4f}] t={c['t']:+.2f} flip {pct:.1f}; "
        f"level {lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}] vs S0 "
        f"{x['net_s0'].mean():+.4f}\n    filled: N={cf['n']} diff {cf['point']:+.4f} "
        f"[{cf['low']:+.4f}, {cf['high']:+.4f}]; sale minus fill-day mid "
        f"{fl['below_mid_m0'].mean():+.4f} m0"
    )
    log_trial(
        {
            "trial_id": 2033,
            "hypothesis": "Rest a straddle offer from the k7-10 entry day pegged to the entry IV "
            "(re-priced daily on forward and tenor), fill on EOD quote-through, else S0; beats S0",
            "mechanism": "vol pegging removes the spot-move pick-off of a static limit, leaving "
            "time to collect the half-spread",
            "block": f"{a.set} (k7-10 bin, 2019-24)",
            "n": c["n"],
            "effect": round(c["point"], 5),
            "ci_low": round(c["low"], 5),
            "ci_high": round(c["high"], 5),
            "t": round(c["t"], 2),
            "null_pct": round(pct, 1),
            "basis": "per trade, standard m0, net (fill at the vol-pegged limit, else 15:59 bid), "
            "paired minus S0; modelled quote-through fills",
            "verdict": f"exploratory, modelled fills; fill rate {x['filled'].mean():.3f}; level "
            f"{lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}]",
        }
    )
    x.to_parquet(HERE / f"round3b_{a.set}.parquet")


if __name__ == "__main__":
    main()
