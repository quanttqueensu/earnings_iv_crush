"""s04_intraday.py: index straddle held 10:00 to 15:59 within one session, every session 2016-2026.

Contract: at the 10:00 snapshot of session d, the shortest expiry strictly after d with a strike
whose call and put are both two-sided; strike minimising |C mid - P mid|. The same two contracts
are marked at d's 15:59 snapshot. Outcomes per unit of entry mid premium, net at the touch with
USD 0.0065 per share per leg per side, plus the 10:00 and 15:59 half-spreads actually quoted.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneG-index-event-vol/s04_intraday.py
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.engine.stats import nyse_sessions

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CHAINS = ROOT / "data" / "cache" / "index_chains"
TICKERS = ("QQQ", "SPY", "IWM")
COMMISSION = 0.0065
MARGIN_SPOT_FRAC = 0.15


def _load(tk: str, d: pd.Timestamp, snap: str) -> pd.DataFrame | None:
    p = CHAINS / f"{tk}_{d.date()}_{snap}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty:
        return None
    df = df.sort_values("ts_recv").groupby("symbol", as_index=False).last()
    sym = df["symbol"].astype(str)
    return pd.DataFrame(
        {
            "expiry": pd.to_datetime(sym.str[6:12], format="%y%m%d"),
            "cp": sym.str[12],
            "strike": sym.str[13:21].astype(int) / 1000.0,
            "bid": df["bid_px_00"].astype(float),
            "ask": df["ask_px_00"].astype(float),
        }
    )


def one(job: tuple[str, pd.Timestamp]) -> dict[str, object]:
    tk, d = job
    base: dict[str, object] = {"ticker": tk, "day": d}
    e, x = _load(tk, d, "1000"), _load(tk, d, "1559")
    if e is None or x is None:
        return {**base, "status": "no_snapshot"}
    e = e[(e["bid"] > 0) & (e["ask"] >= e["bid"]) & (e["expiry"] > d)]
    piv = e.pivot_table(index=["expiry", "strike"], columns="cp", values=["bid", "ask"]).dropna()
    if piv.empty or ("bid", "C") not in piv.columns or ("bid", "P") not in piv.columns:
        return {**base, "status": "no_pair"}
    exp = piv.index.get_level_values(0).min()
    sub = piv.loc[exp]
    cm = (sub[("bid", "C")] + sub[("ask", "C")]) / 2
    pm = (sub[("bid", "P")] + sub[("ask", "P")]) / 2
    k = float((cm - pm).abs().idxmin())
    leg = x[(x["expiry"] == exp) & (x["strike"] == k)].set_index("cp")
    if not {"C", "P"} <= set(leg.index):
        return {**base, "status": "no_exit_leg"}
    c1b, c1a, p1b, p1a = (float(leg.loc["C", "bid"]), float(leg.loc["C", "ask"]),
                          float(leg.loc["P", "bid"]), float(leg.loc["P", "ask"]))
    if not (c1b > 0 and p1b > 0 and c1a >= c1b and p1a >= p1b):
        return {**base, "status": "exit_not_two_sided"}
    c0b, c0a = float(sub.loc[k, ("bid", "C")]), float(sub.loc[k, ("ask", "C")])
    p0b, p0a = float(sub.loc[k, ("bid", "P")]), float(sub.loc[k, ("ask", "P")])
    p0 = (c0b + c0a + p0b + p0a) / 2
    p1 = (c1b + c1a + p1b + p1a) / 2
    fwd = k + float(cm.loc[k] - pm.loc[k])
    comm = 4 * COMMISSION
    return {
        **base,
        "status": "ok",
        "expiry": exp,
        "dte": int((exp - d).days),
        "strike": k,
        "p0": p0,
        "fwd0": fwd,
        "hs_entry": (c0a + p0a - c0b - p0b) / 2 / p0,
        "hs_exit": (c1a + p1a - c1b - p1b) / 2 / p0,
        "long_mid": (p1 - p0) / p0,
        "long_net_debit": (c1b + p1b - c0a - p0a - comm) / (c0a + p0a),
        "short_net_rom": (c0b + p0b - c1a - p1a - comm) / (p0 + MARGIN_SPOT_FRAC * fwd),
    }


def main() -> None:
    sess = nyse_sessions(pd.Timestamp("2016-01-04"), pd.Timestamp("2026-10-30"))
    jobs = [(tk, d) for tk in TICKERS for d in sess]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, jobs, chunksize=64))
    df = pd.DataFrame(rows)
    print(df.groupby(["ticker", "status"]).size().unstack().to_string())
    df.to_parquet(HERE / "intraday.parquet")


if __name__ == "__main__":
    main()
