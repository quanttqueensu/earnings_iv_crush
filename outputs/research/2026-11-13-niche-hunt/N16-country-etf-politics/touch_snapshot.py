"""
touch_snapshot.py
Half-spread of the at-the-money straddle on country ETF options, from one Cboe delayed-quote
snapshot (cdn.cboe.com delayed_quotes JSON, free and public, about fifteen minutes late).

For each underlying and each listed expiry between 2 and 70 calendar days, take the strike
nearest spot, require a two-sided quote on both legs, and report the straddle mid, the
straddle half-spread (sum of the two legs' half-spreads) and the half-spread as a share of the
mid. One snapshot is one market state; it is a level check, not a history.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N16-country-etf-politics/touch_snapshot.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SNAP_DIRS = [HERE / "raw" / "cboe_quotes", HERE / "raw" / "cboe_quotes_2"]
# Cboe regenerates the JSON for less-watched symbols rarely; a quote stamped outside the US
# regular session of the snapshot day is an after-hours state and is flagged, not used.
SESSION_UTC = (pd.Timestamp("2026-11-13 14:30"), pd.Timestamp("2026-11-13 21:00"))
OUT = HERE / "touch_snapshot.csv"
MIN_DAYS, MAX_DAYS = 2, 70  # weekly to roughly two-month tenors
_OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")


def _parse(path: Path) -> tuple[pd.DataFrame, float, pd.Timestamp]:
    body = json.loads(path.read_text())
    data = body["data"]
    spot = float(data["current_price"])
    ts = pd.Timestamp(body["timestamp"])
    rows: list[dict] = []
    for o in data["options"]:
        m = _OCC.match(o["option"])
        if m is None:
            raise ValueError(f"unparsed option symbol {o['option']}")
        if m.group(1) != data["symbol"]:
            continue  # non-standard roots (adjusted or special-settlement series)
        rows.append(
            {
                "expiry": pd.Timestamp("20" + m.group(2)),
                "right": m.group(3),
                "strike": int(m.group(4)) / 1000.0,
                "bid": float(o["bid"]),
                "ask": float(o["ask"]),
                "iv": float(o["iv"]),
            }
        )
    return pd.DataFrame(rows), spot, ts


def straddle_touch(path: Path) -> pd.DataFrame:
    sym = path.stem
    chain, spot, ts = _parse(path)
    asof = ts.normalize()
    out = []
    for expiry, g in chain.groupby("expiry"):
        days = (expiry - asof).days
        if not MIN_DAYS <= days <= MAX_DAYS:
            continue
        k = g.loc[(g["strike"] - spot).abs().idxmin(), "strike"]
        legs = g[g["strike"] == k].set_index("right")
        if not {"C", "P"} <= set(legs.index):
            continue
        c, p = legs.loc["C"], legs.loc["P"]
        if min(c.bid, p.bid) <= 0 or min(c.ask, p.ask) <= 0:
            continue  # a one-sided quote never becomes a mid
        mid = (c.bid + c.ask + p.bid + p.ask) / 2
        half = ((c.ask - c.bid) + (p.ask - p.bid)) / 2
        out.append(
            {
                "symbol": sym,
                "snapshot_dir": path.parent.name,
                "snapshot_utc": ts,
                "in_session": SESSION_UTC[0] <= ts <= SESSION_UTC[1],
                "spot": spot,
                "expiry": expiry.date(),
                "cal_days": days,
                "strike": k,
                "straddle_mid": round(mid, 4),
                "straddle_half_spread": round(half, 4),
                "half_spread_pct_of_mid": round(100 * half / mid, 3),
                "atm_iv_call": c.iv,
            }
        )
    if not out:
        raise RuntimeError(f"{sym}: no two-sided ATM straddle in {MIN_DAYS}-{MAX_DAYS} days")
    return pd.DataFrame(out)


def main() -> None:
    paths = sorted(p for d in SNAP_DIRS for p in d.glob("*.json"))
    df = pd.concat([straddle_touch(p) for p in paths], ignore_index=True)
    df.to_csv(OUT, index=False)
    pd.set_option("display.width", 160)
    live = df[df["in_session"] & (df["cal_days"] <= 40)]
    print(live.drop(columns=["snapshot_utc"]).to_string(index=False))
    stale = sorted(set(df.loc[~df["in_session"], "symbol"]))
    print(f"after-hours (not used): {stale}")


if __name__ == "__main__":
    main()
