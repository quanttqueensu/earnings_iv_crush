"""
weekend_rv.py
Exploratory (trial 2,372): how much BTC variance falls while IBIT is closed, and how the one
live IBIT and Deribit snapshot (spread_snapshot.csv) price the window that spans this weekend.

BTC prices are Deribit BTC-PERPETUAL hourly closes (public chart endpoint, no key). The IBIT
clock is the NYSE session, 09:30 to 16:00 America/New_York; exchange holidays are ignored, so a
holiday Monday is counted as a weekday (a small bias towards a lower weekend share).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/weekend_rv.py --pull
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/weekend_rv.py
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from n10lib import CACHE, HERE, mean_ci
from pull_deribit import LIVE, _get

NY = "America/New_York"
START = pd.Timestamp("2024-11-18", tz="UTC")  # IBIT options listed 2024-11-19
K_ATM = float(np.sqrt(2 / np.pi))


def pull() -> None:
    end = pd.Timestamp.now(tz="UTC").floor("h")
    rows: list[pd.DataFrame] = []
    t = START - pd.Timedelta(days=7)
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
        rows.append(pd.DataFrame({"ts": r["ticks"], "close": r["close"]}))
        t = hi
    df = pd.concat(rows).drop_duplicates("ts").sort_values("ts")
    df.to_parquet(CACHE / "btc_perp_1h.parquet")
    print(f"  {len(df)} hourly closes")


def price_at(s: pd.Series, t: pd.Timestamp) -> float:
    return float(s.asof(t))


def main() -> None:
    ap = argparse.ArgumentParser(description="BTC variance while IBIT is closed")
    ap.add_argument("--pull", action="store_true")
    args = ap.parse_args()
    if args.pull:
        pull()
    d = pd.read_parquet(CACHE / "btc_perp_1h.parquet")
    s = pd.Series(d["close"].to_numpy(), index=pd.to_datetime(d["ts"], unit="ms", utc=True))
    days = pd.date_range(START.tz_convert(NY).normalize(), s.index[-1].tz_convert(NY), freq="D")
    sessions = [x for x in days if x.weekday() < 5]
    rows = []
    for a, b in zip(sessions[:-1], sessions[1:], strict=True):
        o_a = a + pd.Timedelta(hours=9, minutes=30)
        c_a = a + pd.Timedelta(hours=16)
        o_b = b + pd.Timedelta(hours=9, minutes=30)
        if o_b.tz_convert("UTC") > s.index[-1]:
            break
        p = [price_at(s, x.tz_convert("UTC")) for x in (o_a, c_a, o_b)]
        rows.append(
            {
                "date": a.date(),
                "weekend": b.weekday() == 0,
                "intraday": np.log(p[1] / p[0]) ** 2,
                "closed": np.log(p[2] / p[1]) ** 2,
            }
        )
    r = pd.DataFrame(rows)
    dates = pd.to_datetime(r["date"]).to_numpy()
    wk, wd = r[r["weekend"]], r[~r["weekend"]]
    print(f"  sessions {len(r)}, weekends {len(wk)}")
    for lbl, v, dt in [
        ("intraday (09:30-16:00 ET), per session", r["intraday"], dates),
        ("weekday overnight close-open", wd["closed"], pd.to_datetime(wd["date"]).to_numpy()),
        ("weekend Fri close-Mon open", wk["closed"], pd.to_datetime(wk["date"]).to_numpy()),
    ]:
        pt, lo, hi, n = mean_ci(v.to_numpy(), dt)
        print(f"  {lbl:40s} mean sq log return {pt:.6f} [{lo:.6f}, {hi:.6f}] N={n}")
    week = r["intraday"].mean() * 5 + wd["closed"].mean() * 4 + wk["closed"].mean()
    print(
        f"  weekend gap share of weekly BTC variance on the IBIT clock: "
        f"{wk['closed'].mean() / week:.3f}"
    )
    # realised variance over the snapshot's window: Friday 14:45 ET to Monday 16:00 ET
    real = []
    for f in [x for x in sessions if x.weekday() == 4]:
        t0 = (f + pd.Timedelta(hours=14, minutes=45)).tz_convert("UTC")
        t1 = (f + pd.Timedelta(days=3, hours=16)).tz_convert("UTC")
        if t1 > s.index[-1]:
            continue
        real.append({"date": f.date(), "rv": np.log(price_at(s, t1) / price_at(s, t0)) ** 2})
    rv = pd.DataFrame(real)
    pt, lo, hi, n = mean_ci(rv["rv"].to_numpy(), pd.to_datetime(rv["date"]).to_numpy())
    print(
        f"  realised Fri 14:45 ET - Mon 16:00 ET: {pt:.6f} [{lo:.6f}, {hi:.6f}] N={n}, "
        f"median {rv['rv'].median():.6f}"
    )
    snap = pd.read_csv(HERE / "spread_snapshot.csv")
    snap["impl_var"] = (snap["mid_over_spot"] / K_ATM) ** 2
    ib = snap[snap["venue"].str.startswith("IBIT")].sort_values("hours")
    de = snap[snap["venue"].str.startswith("Deribit")].sort_values("hours")
    mon = ib.iloc[1]
    dv = float(np.interp(mon["hours"], de["hours"], de["impl_var"]))
    print(
        f"  snapshot window to IBIT expiry {mon['expiry']} ({mon['hours']:.1f} h): IBIT implied "
        f"var {mon['impl_var']:.6f}, Deribit interpolated {dv:.6f}, IBIT/Deribit "
        f"{mon['impl_var'] / dv:.2f}; IBIT/mean realised {mon['impl_var'] / pt:.2f}; "
        f"Deribit/mean realised {dv / pt:.2f}"
    )
    for _, row in ib.iloc[2:].iterrows():
        dvi = float(np.interp(row["hours"], de["hours"], de["impl_var"]))
        print(
            f"  IBIT {row['expiry']} {row['hours']:.0f} h: IBIT/Deribit implied var "
            f"{row['impl_var'] / dvi:.2f}"
        )


if __name__ == "__main__":
    main()
