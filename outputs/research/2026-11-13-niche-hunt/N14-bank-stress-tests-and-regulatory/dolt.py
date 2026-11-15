"""dolt.py: DoltHub public SQL API helpers (no key) for lane N14, rate-limited to 1 request/s.

Every query pins an exact date (the option_chain key is date-led; ranged scans time out).
Chains are cached under chains/<T>_<date>.parquet with expiries up to 75 days out.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd
import requests

API_OLD = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"
API_NEW = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
# the two repositories hold identical rows where both have them (JPM 2024-06-26, 54 of 54);
# dolthub/options stops in late 2024, post-no-preference/options continues into 2026
SWITCH = pd.Timestamp("2024-11-30")
HERE = os.path.dirname(os.path.abspath(__file__))
CHAINS = os.path.join(HERE, "chains")
SNAP = os.path.join(HERE, "snap_cache.json")
os.makedirs(CHAINS, exist_ok=True)
_last = [0.0]
_snap: dict = json.load(open(SNAP)) if os.path.exists(SNAP) else {}


def q(sql: str, api: str = API_OLD) -> list[dict]:
    last = ""
    for attempt in range(6):
        wait = 1.05 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = requests.get(api, params={"q": sql}, timeout=90,
                             headers={"User-Agent": "research-client"})
            b = r.json()
            if b.get("query_execution_status") == "Success":
                return b.get("rows") or []
            last = b.get("query_execution_message", "")[:160]
        except Exception as exc:  # network errors are retried, then raised
            last = str(exc)[:160]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DoltHub failed after retries: {last} :: {sql[:160]}")


def api(d: pd.Timestamp) -> str:
    return API_OLD if d <= SWITCH else API_NEW


def has_snap(t: str, d: pd.Timestamp) -> bool:
    key = f"{t}|{d:%Y-%m-%d}"
    if key not in _snap:
        rows = q(f"select count(*) n from option_chain where date='{d:%Y-%m-%d}' "
                 f"and act_symbol='{t}'", api(d))
        _snap[key] = int(rows[0]["n"]) > 0
        json.dump(_snap, open(SNAP, "w"))
    return _snap[key]


def chain(t: str, d: pd.Timestamp) -> pd.DataFrame:
    path = os.path.join(CHAINS, f"{t}_{d:%Y-%m-%d}.parquet")
    if not os.path.exists(path):
        hz = (d + pd.Timedelta(days=75)).strftime("%Y-%m-%d")
        rows = q(f"select expiration, strike, call_put, bid, ask, vol, delta from option_chain "
                 f"where date='{d:%Y-%m-%d}' and act_symbol='{t}' and expiration >= "
                 f"'{d:%Y-%m-%d}' and expiration <= '{hz}'", api(d))
        if not rows:
            raise RuntimeError(f"snapshot listed but empty chain {t} {d:%Y-%m-%d}")
        pd.DataFrame(rows).to_parquet(path)
    c = pd.read_parquet(path)
    return c.assign(expiry=pd.to_datetime(c["expiration"]), strike=c["strike"].astype(float),
                    right=c["call_put"].str[0].str.upper(), bid=pd.to_numeric(c["bid"]),
                    ask=pd.to_numeric(c["ask"]), iv=pd.to_numeric(c["vol"]))[
        ["expiry", "strike", "right", "bid", "ask", "iv"]]


def cover(d: pd.Timestamp, names: list[str]) -> None:
    """Record snapshot presence for many symbols on one date with a single grouped query."""
    todo = [t for t in names if f"{t}|{d:%Y-%m-%d}" not in _snap]
    if not todo:
        return
    lst = ",".join(f"'{t}'" for t in todo)
    rows = q(f"select act_symbol, count(*) n from option_chain where date='{d:%Y-%m-%d}' "
             f"and act_symbol in ({lst}) group by act_symbol", api(d))
    have = {r["act_symbol"] for r in rows if int(r["n"]) > 0}
    for t in todo:
        _snap[f"{t}|{d:%Y-%m-%d}"] = t in have
    json.dump(_snap, open(SNAP, "w"))
