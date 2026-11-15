"""
ibclock.py
Does the monthly-expiry effect of pilot B reach the clocks of the IB-tradable vehicles? For each
monthly Friday and its three controls, the BTC move over the window an IB short straddle would
hold, in units of the Deribit straddle-implied standard deviation scaled to that window:

    CME   Thursday 16:00 London to Friday 16:00 London (BRR fixing; Friday weekly options)
    IBIT  Thursday 16:00 New York to Friday 16:00 New York (IBIT close; Friday weekly options)

BTC prices are Deribit BTC-PERPETUAL hourly closes. The implied sd comes from the Deribit
straddle at Thursday 09:00 UTC (pilot B's entry), per hour of its life, times the window's
hours. This is realised-only for the IB clocks: no CME or IBIT option price enters it.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/ibclock.py --pull
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/ibclock.py \
        --block discovery --trial 2357   (CME clock takes the trial, IBIT the next)
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from n10lib import CACHE, HERE, delivery_prices, mean_ci, straddle
from pull_deribit import LIVE, _get
from score_pilot_b import BLOCKS, CONTROL_WEEKS, EXPIRY_HOUR, last_fridays

CLOCKS = {"CME": "Europe/London", "IBIT": "America/New_York"}
CLOSE_HOUR = 16


def pull() -> None:
    start = pd.Timestamp("2019-12-15", tz="UTC")
    end = pd.Timestamp.now(tz="UTC").floor("h")
    parts = []
    t = start
    while t < end:
        hi = min(t + pd.Timedelta(hours=1000), end)
        r = _get(
            LIVE,
            "get_tradingview_chart_data",
            instrument_name="BTC-PERPETUAL",
            start_timestamp=int(t.timestamp() * 1000),
            end_timestamp=int(hi.timestamp() * 1000),
            resolution="60",
        )
        parts.append(pd.DataFrame({"ts": r["ticks"], "close": r["close"]}))
        t = hi
    df = pd.concat(parts).drop_duplicates("ts").sort_values("ts")
    df.to_parquet(CACHE / "btc_perp_1h_full.parquet")
    print(f"  {len(df)} hourly closes {df['ts'].min()} to {df['ts'].max()}")


def window_z(
    fri: pd.Timestamp, s: pd.Series, deliv: pd.Series, tz: str
) -> tuple[float | None, str]:
    exp = fri + pd.Timedelta(hours=EXPIRY_HOUR)
    entry = exp - pd.Timedelta(hours=23)
    r, why = straddle("BTC", entry, deliv, expiry=exp)
    if r is None:
        return None, why
    var_per_h = r["implied_var"] / r["hours_to_expiry"]
    day = fri.tz_localize(None).normalize()
    t1 = pd.Timestamp(day + pd.Timedelta(hours=CLOSE_HOUR), tz=tz).tz_convert("UTC")
    t0 = t1 - pd.Timedelta(days=1)
    hours = (t1 - t0).total_seconds() / 3600
    p0, p1 = s.asof(t0), s.asof(t1)
    if pd.isna(p0) or pd.isna(p1) or t1 > s.index[-1]:
        return None, "no price"
    return abs(float(np.log(p1 / p0))) / np.sqrt(var_per_h * hours), "ok"


def main() -> None:
    ap = argparse.ArgumentParser(description="pilot B effect on IB clocks")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--block", choices=list(BLOCKS))
    ap.add_argument("--trial", type=int)
    args = ap.parse_args()
    if args.pull:
        pull()
    if not args.block:
        return
    d = pd.read_parquet(CACHE / "btc_perp_1h_full.parquet")
    s = pd.Series(d["close"].to_numpy(), index=pd.to_datetime(d["ts"], unit="ms", utc=True))
    deliv = delivery_prices("btc_usd")
    lo, hi = BLOCKS[args.block]
    rows = []
    for f in last_fridays(lo, hi):
        rec: dict[str, object] = {"event_date": f.date()}
        for clock, tz in CLOCKS.items():
            ze, _ = window_z(f, s, deliv, tz)
            zc = [window_z(f - pd.Timedelta(weeks=w), s, deliv, tz)[0] for w in CONTROL_WEEKS]
            zc_ok = [z for z in zc if z is not None]
            rec[f"{clock}_diff"] = ze - float(np.mean(zc_ok)) if ze is not None and zc_ok else None
        rows.append(rec)
    r = pd.DataFrame(rows)
    out = []
    for clock in CLOCKS:
        v = r.dropna(subset=[f"{clock}_diff"])
        pt, lo_, h, n = mean_ci(v[f"{clock}_diff"].to_numpy(), pd.to_datetime(v["event_date"]))
        print(
            f"  {args.block} {clock} clock: |move| in implied sd, event minus control "
            f"{pt:+.3f} [{lo_:+.3f}, {h:+.3f}] N={n}"
        )
        out.append((clock, n, pt, lo_, h))
    if args.trial:
        f = HERE / "trials.csv"
        with f.open("a", newline="") as fh:
            w = csv.writer(fh)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            for i, (clock, n, pt, lo_, h) in enumerate(out):
                verdict = "PASS short" if h < 0 else ("PASS long" if lo_ > 0 else "FAIL")
                w.writerow(
                    [
                        args.trial + i,
                        "N10",
                        "B on IB clock",
                        f"{args.block}_{clock}_clock",
                        args.block,
                        n,
                        "mean |move| in Deribit-implied sd on the IB vehicle's window, "
                        "event minus control (negative favours the short); realised only",
                        round(pt, 6),
                        round(lo_, 6),
                        round(h, 6),
                        verdict,
                        "realised-only transfer check",
                        now,
                    ]
                )


if __name__ == "__main__":
    main()
