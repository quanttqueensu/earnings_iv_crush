"""build_tick_panel.py: per-event straddle quotes at fixed clocks and package prints, from cached ticks.

Reads the two-contract tick files under data/cache/flow (broad 2025-26, megacap 2023-24) and writes
one row per event: leg quotes and sizes at entry-day and reaction-day clocks, the late-window
package prints, strike, expiry and the parity forward. Real data (Databento cmbp-1 cache), no spend.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane4-structure/build_tick_panel.py
"""
from __future__ import annotations

from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FLOW = ROOT / "data" / "cache" / "flow"
OUT = Path(__file__).resolve().parent
BLOCKS = ("broad_2025_2026", "megacap_2023_2024")
ENTRY_CLOCKS = ("15:00", "15:30", "15:35", "15:40", "15:45", "15:50", "15:55", "15:59")
EXIT_CLOCKS = ("15:01", "15:15", "15:30", "15:45", "15:55", "15:59")
PAIR_NS = 1_000_000
COLS = ["ts_event", "publisher_id", "action", "price", "size", "bid_px_00", "ask_px_00",
        "bid_sz_00", "ask_sz_00", "symbol"]


def _quotes(d: pd.DataFrame, day: pd.Timestamp, clocks: tuple[str, ...], tag: str) -> dict:
    rec: dict = {}
    for right, g in d.groupby("right"):
        for t in clocks:
            ts = day + pd.Timedelta(t + ":00")
            q = g[g.index <= ts]
            k = f"{tag}_{right}_{t}"
            if q.empty:
                rec[k + "_bid"] = rec[k + "_ask"] = rec[k + "_bsz"] = rec[k + "_asz"] = np.nan
                continue
            last = q.iloc[-1]
            rec[k + "_bid"], rec[k + "_ask"] = float(last["bid_px_00"]), float(last["ask_px_00"])
            rec[k + "_bsz"], rec[k + "_asz"] = float(last["bid_sz_00"]), float(last["ask_sz_00"])
    return rec


def _packages(d: pd.DataFrame, day: pd.Timestamp, start: str, tag: str) -> dict:
    """Late-window call+put prints on one venue, same size, within 1 ms; location in the summed quote."""
    t = d[(d["action"] == "T") & (d.index >= day + pd.Timedelta(start + ":00"))
          & (d["bid_px_00"] > 0) & (d["ask_px_00"] > d["bid_px_00"])]
    c = t[t["right"] == "C"].sort_values("ts_event")
    p = t[t["right"] == "P"].sort_values("ts_event")
    out = {f"{tag}_pk_n": 0}
    if c.empty or p.empty:
        return out
    m = pd.merge_asof(c.reset_index(drop=True), p.reset_index(drop=True).reset_index(names="pi"),
                      on="ts_event", by=["publisher_id", "size"], direction="nearest",
                      tolerance=pd.Timedelta(PAIR_NS, "ns"), suffixes=("_c", "_p")).dropna(subset=["pi"])
    m = m.drop_duplicates("pi")
    if m.empty:
        return out
    bid = m["bid_px_00_c"] + m["bid_px_00_p"]
    ask = m["ask_px_00_c"] + m["ask_px_00_p"]
    px = m["price_c"] + m["price_p"]
    mid = (bid + ask) / 2
    lc = (m["price_c"] - m["bid_px_00_c"]) / (m["ask_px_00_c"] - m["bid_px_00_c"])
    lp = (m["price_p"] - m["bid_px_00_p"]) / (m["ask_px_00_p"] - m["bid_px_00_p"])
    m = m.assign(loc=(px - bid) / (ask - bid), cost=(mid - px) / mid, hs=(ask - bid) / (2 * mid),
                 synth=(lc - lp).abs() > 0.8)
    m = m[~m["synth"]]
    out[f"{tag}_pk_n"] = len(m)
    for side, sel in (("sell", m["loc"] < 0.45), ("buy", m["loc"] > 0.55), ("mid", (m["loc"] >= 0.45) & (m["loc"] <= 0.55))):
        g = m[sel]
        out[f"{tag}_pk_{side}_n"] = len(g)
        if len(g):
            out[f"{tag}_pk_{side}_cost"] = float(g["cost"].abs().mean())  # share of mid, away from mid
            out[f"{tag}_pk_{side}_loc"] = float(g["loc"].mean())
            out[f"{tag}_pk_{side}_hs"] = float(g["hs"].mean())  # quoted half-spread at the prints
            out[f"{tag}_pk_{side}_size_med"] = float(g["size"].median())
            out[f"{tag}_pk_{side}_size_sum"] = float(g["size"].sum())
    return out


def _load(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=COLS)
    d.index = d.index.tz_convert("America/New_York")
    d["right"] = d["symbol"].str.strip().str[-9]
    return d


def one(args: tuple[str, str, str]) -> dict:
    block, ticker, date = args
    rec: dict = {"block": block, "ticker": ticker, "entry_date": date, "status": "ok"}
    try:
        pre = _load(FLOW / block / f"{ticker}_{date}_pre.parquet")
        day = pd.Timestamp(date, tz="America/New_York")
        pre = pre[pre.index >= day]
        syms = sorted(pre["symbol"].str.strip().unique())
        if pre["right"].nunique() != 2 or len(syms) != 2:
            rec["status"] = "pre_not_two_legs"
            return rec
        s = syms[0]
        rec["strike"] = int(s[-8:]) / 1000.0
        rec["expiry"] = pd.Timestamp("20" + s[-15:-9]).strftime("%Y-%m-%d")
        rec.update(_quotes(pre, day, ENTRY_CLOCKS, "en"))
        rec.update(_packages(pre, day, "15:30", "en"))
        # time-weighted mean of the summed bid, 15:30-15:45, sampled each minute
        tw = []
        for mnt in range(30, 46):
            ts = day + pd.Timedelta(f"15:{mnt}:00")
            b = 0.0
            for _, g in pre.groupby("right"):
                q = g[g.index <= ts]
                b += float(q["bid_px_00"].iloc[-1]) if len(q) else np.nan
            tw.append(b)
        rec["en_twab_1530_1545"] = float(np.nanmean(tw)) if np.isfinite(tw).all() else np.nan
        ex = _load(FLOW / block / f"{ticker}_{date}_exit.parquet")
        xday = ex.index.max().normalize()
        ex = ex[ex.index >= xday]
        rec["exit_date"] = xday.strftime("%Y-%m-%d")
        if ex["right"].nunique() != 2:
            rec["status"] = "exit_not_two_legs"
            return rec
        rec.update(_quotes(ex, xday, EXIT_CLOCKS, "ex"))
        rec.update(_packages(ex, xday, "15:00", "ex"))
    except Exception as e:  # recorded, counted in the funnel, never silent
        rec["status"] = f"error:{type(e).__name__}:{e}"[:120]
    return rec


def main() -> None:
    jobs = []
    for b in BLOCKS:
        for f in sorted((FLOW / b).glob("*_pre.parquet")):
            tk, dt = f.stem.split("_")[:2]
            jobs.append((b, tk, dt))
    with Pool(6) as pool:
        rows = pool.map(one, jobs, chunksize=8)
    r = pd.DataFrame(rows)
    print("funnel:", r.groupby("block")["status"].value_counts().to_string())
    r.to_parquet(OUT / "tick_panel.parquet", index=False)


if __name__ == "__main__":
    main()
