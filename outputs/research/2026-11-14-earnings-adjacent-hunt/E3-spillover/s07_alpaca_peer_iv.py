"""
s07_alpaca_peer_iv.py
Trial 2754 (exploratory, descriptive, sizes the seller's side before any pull): a non-reporting
peer's front ATM implied vol change across a same-SIC3 reporter's night, against the same peer's
ordinary consecutive sessions, on the Alpaca panel chains (2024 only, inside the peer-night
table). Alpaca serves daily last-trade closes stamped on both bid and ask, with a five-day
stale-close lookback, so this is gross, at last trade, and biased towards zero change on both
the event and control sides. It cannot measure the touch and cannot set direction.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s07_alpaca_peer_iv.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

sys.path.insert(0, str(lib.ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

PROC = lib.ROOT / "data" / "processed"
MIN_DTE, MAX_DTE = 7, 60
CTRL_NEAR, CTRL_FAR, N_CTRL = 6, 25, 3


def _chain(t: str, d: pd.Timestamp) -> pd.DataFrame | None:
    p = PROC / f"alpaca_chain_panel_{t}_{d:%Y-%m-%d}.parquet"
    if not p.exists():
        return None
    x = pd.read_parquet(p)
    if x.empty:
        return None
    x["expiry"] = pd.to_datetime(x["expiry"])
    return x[np.isfinite(x["iv"]) & (x["iv"] > 0) & (x["bid"] > 0)]


def _div(t: str, d0: pd.Timestamp, d1: pd.Timestamp) -> float | None:
    a, b = _chain(t, d0), _chain(t, d1)
    if a is None or b is None:
        return None
    dte = (a["expiry"] - d0).dt.days
    f = a[(dte >= MIN_DTE) & (dte <= MAX_DTE)]
    if f.empty:
        return None
    e = f["expiry"].min()
    y = f[f["expiry"] == e]
    c = y[y["right"].str.upper().str[0] == "C"].set_index("strike")
    p = y[y["right"].str.upper().str[0] == "P"].set_index("strike")
    ks = c.index.intersection(p.index)
    if not len(ks):
        return None
    k = (c.loc[ks, "bid"] - p.loc[ks, "bid"]).abs().idxmin()
    z = b[(b["expiry"] == e) & (b["strike"] == k)]
    if sorted(z["right"].str.upper().str[0]) != ["C", "P"]:
        return None
    return float((z["iv"].mean() - (c.loc[k, "iv"] + p.loc[k, "iv"]) / 2) * 100)


def main() -> None:
    sess = lib.sessions()
    spos = {d: i for i, d in enumerate(sess)}
    pn = pd.read_parquet(lib.HERE / "peer_nights.parquet")
    pn = pn[pn["exit_date"].dt.year == 2024].drop_duplicates(["p_ticker", "exit_date"])
    rep = lib.all_report_dates()
    t2p = dict(zip(pn["p_ticker"], pn["p_permno"], strict=False))
    busy = {}
    for p in set(pn["p_permno"]):
        r = rep[rep["permno"] == p]
        busy[p] = r
    react = set(zip(pn["sic3"], pn["exit_date"], strict=True))
    rows, funnel = [], {"peer_dates": len(pn), "event_iv": 0, "with_control": 0}
    for r in pn.itertuples(index=False):
        ev = _div(r.p_ticker, r.entry_date, r.exit_date)
        if ev is None:
            continue
        funnel["event_iv"] += 1
        i1 = spos[r.exit_date]
        ctl = []
        for k in [*range(CTRL_NEAR, CTRL_FAR + 1), *range(-CTRL_NEAR, -CTRL_FAR - 1, -1)]:
            j = i1 + k
            if j - 1 < 0 or j >= len(sess) or len(ctl) >= N_CTRL:
                continue
            d0, d1 = sess[j - 1], sess[j]
            if (r.sic3, d1) in react:
                continue
            br = busy[t2p[r.p_ticker]]
            if ((br["d1"] >= d0 - pd.Timedelta(days=3)) & (br["d0"] <= d1 + pd.Timedelta(days=7))).any():
                continue
            v = _div(r.p_ticker, d0, d1)
            if v is not None:
                ctl.append(v)
        if not ctl:
            continue
        funnel["with_control"] += 1
        rows.append({"p_ticker": r.p_ticker, "exit_date": r.exit_date, "ev": ev,
                     "ctl": float(np.mean(ctl))})
    print(f"funnel: {funnel}")
    d = pd.DataFrame(rows)
    d["diff"] = d["ev"] - d["ctl"]
    mean = lambda x: float(np.mean(x))  # noqa: E731
    for c in ("ev", "ctl", "diff"):
        print(f"{c} (vol points): {date_clustered_ci(d[c], d['exit_date'], stat=mean)}")
    d.to_csv(lib.HERE / "alpaca_peer_iv.csv", index=False)


if __name__ == "__main__":
    main()
