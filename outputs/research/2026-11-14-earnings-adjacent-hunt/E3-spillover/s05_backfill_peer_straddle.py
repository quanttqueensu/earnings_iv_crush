"""
s05_backfill_peer_straddle.py
Trial 2753 (exploratory, descriptive, N about 20): a non-reporting peer's front ATM straddle on
the Databento 15:59 chains (data/cache/backfill_chains, cbbo-1m) that happen to exist for the peer
on both a same-SIC3 reporter's entry session and its reaction session.

Reports, per peer night: the straddle's quoted half-spread as a share of its mid at entry (the
per-side touch), and the long straddle's return bought at the entry ask and sold at the reaction
bid (net at the touch, before the USD 0.65 per contract fee), plus the same at the mid.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s05_backfill_peer_straddle.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

CACHE = lib.ROOT / "data" / "cache" / "backfill_chains"
MIN_DTE, MAX_DTE = 7, 60
FEE = 0.65  # USD per contract per side (brief rule 5)


def _chain(t: str, d: pd.Timestamp) -> pd.DataFrame | None:
    p = CACHE / f"{t}_{d:%Y-%m-%d}.parquet"
    if not p.exists():
        return None
    x = pd.read_parquet(p, columns=["ts_event", "symbol", "bid_px_00", "ask_px_00"])
    if x.empty:
        return None
    x = x.sort_values("ts_event").groupby("symbol").last().reset_index()
    s = x["symbol"].str.replace(" ", "", regex=False)
    m = s.str.extract(r"^(?P<root>[A-Z.]+)(?P<ymd>\d{6})(?P<cp>[CP])(?P<k>\d{8})$")
    x = pd.concat([x, m], axis=1).dropna(subset=["ymd"])
    x["expiry"] = pd.to_datetime(x["ymd"], format="%y%m%d")
    x["strike"] = x["k"].astype(int) / 1000
    x = x.rename(columns={"bid_px_00": "bid", "ask_px_00": "ask"})
    return x[(x["bid"] > 0) & (x["ask"] >= x["bid"])]


def _straddle(x: pd.DataFrame, e: pd.Timestamp, k: float) -> tuple[float, float] | None:
    y = x[(x["expiry"] == e) & (x["strike"] == k)]
    if sorted(y["cp"]) != ["C", "P"]:
        return None
    return float(y["bid"].sum()), float(y["ask"].sum())


def main() -> None:
    pn = pd.read_parquet(lib.HERE / "peer_nights.parquet").drop_duplicates(
        ["p_ticker", "entry_date", "exit_date"])
    rows, funnel = [], {"both_chains": 0, "no_atm": 0, "contract_missing_on_exit": 0, "ok": 0}
    for r in pn.itertuples(index=False):
        a, b = _chain(r.p_ticker, r.entry_date), _chain(r.p_ticker, r.exit_date)
        if a is None or b is None:
            continue
        funnel["both_chains"] += 1
        dte = (a["expiry"] - r.entry_date).dt.days
        f = a[(dte >= MIN_DTE) & (dte <= MAX_DTE)]
        if f.empty:
            funnel["no_atm"] += 1
            continue
        e = f["expiry"].min()
        y = f[f["expiry"] == e].assign(mid=lambda z: (z["bid"] + z["ask"]) / 2)
        c = y[y["cp"] == "C"].set_index("strike")["mid"]
        p = y[y["cp"] == "P"].set_index("strike")["mid"]
        ks = c.index.intersection(p.index)
        if not len(ks):
            funnel["no_atm"] += 1
            continue
        k = float((c[ks] - p[ks]).abs().idxmin())
        s0, s1 = _straddle(a, e, k), _straddle(b, e, k)
        if s0 is None or s1 is None:
            funnel["contract_missing_on_exit"] += 1
            continue
        funnel["ok"] += 1
        m0, m1 = sum(s0) / 2, sum(s1) / 2
        rows.append({
            "p_ticker": r.p_ticker, "exit_date": r.exit_date, "dte": int((e - r.entry_date).days),
            "hs_pct": (s0[1] - s0[0]) / (s0[0] + s0[1]) * 100,
            "long_touch_pct": ((s1[0] * 100 - FEE * 2) / (s0[1] * 100 + FEE * 2) - 1) * 100,
            "long_mid_pct": (m1 / m0 - 1) * 100,
        })
    print(f"funnel: {funnel}")
    d = pd.DataFrame(rows)
    if d.empty:
        raise SystemExit("no usable peer nights")
    print(f"N={len(d)} peer nights, {d['exit_date'].nunique()} dates, years "
          f"{sorted(d['exit_date'].dt.year.unique())}, dte median {d['dte'].median():.0f}")
    for c in ("hs_pct", "long_mid_pct", "long_touch_pct"):
        v = d[c].to_numpy()
        se = v.std(ddof=1) / np.sqrt(len(v))
        print(f"{c}: mean {v.mean():+.2f} median {np.median(v):+.2f} "
              f"(+/- 1.96 SE: [{v.mean() - 1.96 * se:+.2f}, {v.mean() + 1.96 * se:+.2f}])")
    d.to_csv(lib.HERE / "backfill_peer_straddle.csv", index=False)


if __name__ == "__main__":
    main()
