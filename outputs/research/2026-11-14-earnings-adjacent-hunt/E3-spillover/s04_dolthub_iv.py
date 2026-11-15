"""
s04_dolthub_iv.py
Trial 2748 (exploratory, descriptive): a non-reporting peer's front ATM implied vol across a
same-SIC3 reporter's night, on exact-date DoltHub chains (data/cache/dolthub_runup, fetched with
lookback_days=0), and the peer straddle's quoted half-spread as a share of its mid.

Same expiry and strike on both days (the strike where call and put mids are closest on the entry
chain, front expiry 7 to 60 days out). Byte-identical chain pairs are dropped (the self-pairing
landmine). Gross, at the mid; the half-spread is the touch a taker pays per side.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s04_dolthub_iv.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

sys.path.insert(0, str(lib.ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

CACHE = lib.ROOT / "data" / "cache" / "dolthub_runup"
MIN_DTE, MAX_DTE = 7, 60


def _load(t: str, d: pd.Timestamp) -> tuple[pd.DataFrame | None, str]:
    p = CACHE / f"{t}_{d:%Y-%m-%d}.parquet"
    if not p.exists():
        return None, ""
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    x = pd.read_parquet(p)
    if x.empty:
        return None, h
    for c in ("strike", "bid", "ask", "iv"):
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x["expiry"] = pd.to_datetime(x["expiry"])
    return x, h


def _atm(x: pd.DataFrame, d: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    x = x[(x["bid"] > 0) & (x["ask"] >= x["bid"])].copy()
    dte = (x["expiry"] - d).dt.days
    x = x[(dte >= MIN_DTE) & (dte <= MAX_DTE)]
    if x.empty:
        return None
    e = x["expiry"].min()
    y = x[x["expiry"] == e]
    y = y.assign(mid=(y["bid"] + y["ask"]) / 2)
    c = y[y["right"].str.upper().str[0] == "C"].set_index("strike")["mid"]
    p = y[y["right"].str.upper().str[0] == "P"].set_index("strike")["mid"]
    k = c.index.intersection(p.index)
    if not len(k):
        return None
    gap = (c[k] - p[k]).abs()
    return e, float(gap.idxmin())


def _leg(x: pd.DataFrame, e: pd.Timestamp, k: float) -> dict | None:
    y = x[(x["expiry"] == e) & (x["strike"] == k) & (x["bid"] > 0) & (x["ask"] >= x["bid"])]
    r = y["right"].str.upper().str[0]
    if set(r) != {"C", "P"} or len(y) != 2:
        return None
    bid, ask = float(y["bid"].sum()), float(y["ask"].sum())
    return {"iv": float(y["iv"].mean()), "mid": (bid + ask) / 2, "hs": (ask - bid) / (bid + ask)}


def main() -> None:
    pn = pd.read_parquet(lib.HERE / "peer_nights.parquet")
    pn = pn.drop_duplicates(["p_ticker", "entry_date", "exit_date"])
    rows, funnel = [], {"peer_nights": len(pn), "both_files": 0, "identical": 0,
                        "no_atm": 0, "no_same_contract": 0, "ok": 0}
    for r in pn.itertuples(index=False):
        a, ha = _load(r.p_ticker, r.entry_date)
        b, hb = _load(r.p_ticker, r.exit_date)
        if a is None or b is None:
            continue
        funnel["both_files"] += 1
        if ha == hb:
            funnel["identical"] += 1
            continue
        atm = _atm(a, r.entry_date)
        if atm is None:
            funnel["no_atm"] += 1
            continue
        la, lb = _leg(a, *atm), _leg(b, *atm)
        if la is None or lb is None or not np.isfinite(la["iv"]) or not np.isfinite(lb["iv"]):
            funnel["no_same_contract"] += 1
            continue
        funnel["ok"] += 1
        rows.append({"p_ticker": r.p_ticker, "exit_date": r.exit_date, "dte": (atm[0] - r.entry_date).days,
                     "gap_days": (r.exit_date - r.entry_date).days,
                     "iv0": la["iv"], "iv1": lb["iv"], "hs0": la["hs"], "mid0": la["mid"],
                     "mid1": lb["mid"]})
    print(f"funnel: {funnel}")
    d = pd.DataFrame(rows)
    if len(d) < 10:
        raise SystemExit(f"only {len(d)} usable peer nights; nothing to describe")
    d["div_pts"] = (d["iv1"] - d["iv0"]) * 100
    d["rel_div"] = d["iv1"] / d["iv0"] - 1
    mean = lambda x: float(np.mean(x))  # noqa: E731
    c1 = date_clustered_ci(d["div_pts"], d["exit_date"], stat=mean)
    c2 = date_clustered_ci(d["rel_div"] * 100, d["exit_date"], stat=mean)
    c3 = date_clustered_ci(d["hs0"] * 100, d["exit_date"], stat=mean)
    print(f"years {sorted(d['exit_date'].dt.year.unique())}; dte median {d['dte'].median():.0f}; "
          f"calendar gap days {d['gap_days'].value_counts().to_dict()}")
    print(f"IV change, vol points: {c1}")
    print(f"IV change, % of entry IV: {c2}")
    print(f"straddle half-spread, % of mid (per side, entry): {c3}")
    print(f"median entry IV {d['iv0'].median():.3f}")
    d.to_parquet(lib.HERE / "dolthub_peer_iv.parquet", index=False)


if __name__ == "__main__":
    main()
