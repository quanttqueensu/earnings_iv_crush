"""fetch_windows.py: find DoltHub entry/exit snapshots and cache chains for event and control windows.

For each event (events.csv) the event window is [latest snapshot in D-5..D-1, earliest snapshot
in D+1..D+5] (calendar days). Controls shift D by -28 and -56 days and are fetched only for
events whose own window is priceable. lookback is never applied silently: dates are found by an
explicit per-symbol query and a window with no snapshot on either side is recorded as missing.

Output: windows.csv (one row per window with snapshot dates and status), chains/<T>_<date>.parquet.
"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd
import requests

API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"
SHIFTS = [0, -28, -56]
NOW = pd.Timestamp.now


def q(sql: str) -> list[dict]:
    last = ""
    for attempt in range(6):
        try:
            r = requests.get(API, params={"q": sql}, timeout=90,
                             headers={"User-Agent": "research-client"})
            b = r.json()
            if b.get("query_execution_status") == "Success":
                return b.get("rows") or []
            last = b.get("query_execution_message", "")[:120]
        except Exception as exc:
            last = str(exc)[:120]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DoltHub failed after retries: {last} :: {sql[:120]}")


def has_snap(t: str, d: pd.Timestamp) -> bool:
    # a ranged date scan times out server-side and returns a partial result; pin every date
    rows = q(f"select count(*) n from option_chain where date='{d:%Y-%m-%d}' and act_symbol='{t}'")
    return int(rows[0]["n"]) > 0


def snap_dates(t: str, a: pd.Timestamp, b: pd.Timestamp, latest: bool) -> list[pd.Timestamp]:
    days = [d for d in pd.date_range(a, b) if d.weekday() < 5]
    for d in (reversed(days) if latest else days):
        if has_snap(t, d):
            return [d]
    return []


def chain(t: str, d: pd.Timestamp) -> str:
    path = f"chains/{t}_{d:%Y-%m-%d}.parquet"
    if os.path.exists(path):
        return path
    hz = (d + pd.Timedelta(days=75)).strftime("%Y-%m-%d")
    rows = q(f"select expiration, strike, call_put, bid, ask, vol, delta from option_chain where "
             f"date='{d:%Y-%m-%d}' and act_symbol='{t}' and expiration >= '{d:%Y-%m-%d}' "
             f"and expiration <= '{hz}'")
    if not rows:
        raise RuntimeError(f"snapshot listed but empty chain {t} {d}")
    pd.DataFrame(rows).to_parquet(path)
    return path


def window(t: str, d: pd.Timestamp) -> dict:
    pre = snap_dates(t, d - pd.Timedelta(days=5), d - pd.Timedelta(days=1), latest=True)
    post = snap_dates(t, d + pd.Timedelta(days=1), d + pd.Timedelta(days=5), latest=False) \
        if pre else []
    out = {"entry": pre[-1] if pre else pd.NaT, "exit": post[0] if post else pd.NaT}
    if pre and post:
        chain(t, out["entry"])
        chain(t, out["exit"])
        out["status"] = "ok"
    else:
        out["status"] = "no_entry" if not pre else "no_exit"
    return out


def main() -> None:
    ev = pd.read_csv("events.csv", parse_dates=["event_date"])
    done = pd.read_csv("windows.csv", parse_dates=["event_date", "entry", "exit"]) \
        if os.path.exists("windows.csv") else pd.DataFrame()
    have = set(zip(done.get("event_id", []), done.get("shift", [])))
    recs = done.to_dict("records") if len(done) else []
    for i, e in ev.iterrows():
        if e["event_date"] > pd.Timestamp("2024-11-08") or e["event_date"] < pd.Timestamp("2019-01-07"):
            continue
        ok0 = None
        for s in SHIFTS:
            if (e["event_id"], s) in have:
                ok0 = ok0 if s else next(r["status"] for r in recs
                                         if r["event_id"] == e["event_id"] and r["shift"] == 0)
                continue
            if s != 0 and ok0 != "ok":
                break
            d = e["event_date"] + pd.Timedelta(days=s)
            try:
                w = window(e["ticker"], d)
            except RuntimeError as exc:
                print("ERROR", e["event_id"], s, exc, flush=True)
                w = {"entry": pd.NaT, "exit": pd.NaT, "status": "error"}
            if s == 0:
                ok0 = w["status"]
            recs.append({"event_id": e["event_id"], "ticker": e["ticker"], "shift": s,
                         "event_date": d, **w})
            pd.DataFrame(recs).to_csv("windows.csv", index=False)
        print(f"{i+1}/{len(ev)} {e['event_id']} {e['ticker']} {e['event_date']:%Y-%m-%d} {ok0}",
              flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
