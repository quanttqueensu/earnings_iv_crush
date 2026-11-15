"""
build_features.py
Lane E2: build the entry-session flow signals for one block. Reads flow files and the entry
session's 15:59 chain only (for the strike diagnostic); never reads a reaction-session price.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/build_features.py --block discovery
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import lib


def _one(rec: dict) -> dict:
    try:
        f = lib.flow_features(rec["path"], rec["entry_date"])
    except Exception as exc:  # noqa: BLE001 - counted in the funnel, never treated as empty
        f = {"status": f"error:{type(exc).__name__}"}
    out = {**rec, **f}
    if f.get("status") == "ok":
        ks = lib.chain_strikes(rec["ticker"], rec["entry_date"], f["expiry"])
        f50 = f["f_flow_1550"]
        if ks.size and np.isfinite(f50):
            out["strike_nearest_1550"] = float(ks[np.argmin(np.abs(ks - f50))])
        else:
            out["strike_nearest_1550"] = np.nan
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    ev = lib.events(a.block)
    recs = ev.to_dict("records")
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(_one, recs, chunksize=8))
    d = pd.DataFrame(rows)
    print("funnel: feature status", d["status"].value_counts().to_dict())
    ok = d[d["status"] == "ok"]
    print(f"funnel: signed contracts >= {lib.MIN_SIGNED} in window: "
          f"{int((ok['n_signed'] >= lib.MIN_SIGNED).sum())} of {len(ok)}")
    late = ok["first_ts"].dt.tz_convert(lib.TZ).dt.time > pd.Timestamp("15:00").time()
    print(f"diagnostic: files whose first record is after 15:00: {int(late.sum())}")
    same = (ok["strike_nearest_1550"] == ok["strike"]).mean()
    print(f"diagnostic: share of events whose 15:59 strike is also nearest the 15:50 forward: "
          f"{same:.3f} (N={int(ok['strike_nearest_1550'].notna().sum())})")
    d.drop(columns=["first_ts"]).to_parquet(lib.HERE / f"features_{a.block}.parquet")
    print(f"wrote features_{a.block}.parquet, {len(d)} rows")


if __name__ == "__main__":
    main()
