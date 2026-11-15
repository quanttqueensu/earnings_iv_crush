"""
extract.py
Lane E1, stage 1: last-hour quote grids for the held straddle on the reaction session and on the
sessions before the report, from the OPRA cmbp-1 files already on disk (no pull, no spend).

For every event in the three ``data/cache/flow`` blocks it reads the two legs (the call and put on
the strike sold at the 15:59 entry, front expiry) and writes, for each available session in
{D-2, D-1, D0, D+1}, the prevailing best bid and ask of each leg on a 5-second grid from 15:00:00
to 15:59:55 ET. A one-sided or crossed quote is stored as NaN, never as a mid. D+1 is the reaction
session (``exit_date``); D0 is the entry session; D-1 and D-2 are the sessions before it that the
pre file holds (the pull used weekday offsets, so a holiday can remove one).

Outputs (git-ignored binaries, derived from licensed quotes, not to be committed or shared):
    cache/events.parquet  one row per event: block, ticker, dates, strike, expiry, spot_entry,
                          s0 (sum of the 15:59:00 entry bids), m0 = 0.20 spot_entry + s0
    cache/grid.npz        float32 array [event, session(4), leg-side(4), 720] with leg-side
                          order (call bid, call ask, put bid, put ask)
    extract_funnel.json   attrition counts

Note: for broad_2025_2026 the ledger's spot_entry is a dividend-back-adjusted close, so the
m0 written here is understated on that block; correct_m0.py replaces it with the D0 15:59
parity forward (cache/events_m0fix.parquet). Use m0_fix for any m0-based figure.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/extract.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / "cache"
CACHE = ROOT / "data/cache/flow"
HOLD = ROOT / "outputs/research/2026-11-02-hedged-event-hold/events.parquet"
LEDGER = ROOT / "outputs/research/oos_2026_ledger.csv"
PANEL = ROOT / "outputs/research/reverse_alpha/panel.parquet"
TZ = "America/New_York"
CMBP_START = pd.Timestamp("2023-03-28")  # first cmbp-1 date the flow pull used
GRID_STEP = 5  # seconds; fine enough for a 30 s delta lag and 1-minute rebalancing
N_GRID = 3600 // GRID_STEP
SESSIONS = ("Dm2", "Dm1", "D0", "D1")
# NYSE 13:00 closes in the span; a 15:00-16:00 window does not exist on these days.
EARLY_CLOSE = {
    pd.Timestamp(d)
    for d in (
        "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24",
        "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24",
    )
}
COLS = ["ts_recv", "bid_px_00", "ask_px_00", "symbol"]


# ── events ──────────────────────────────────────────────────────────────────


def events() -> pd.DataFrame:
    """The three flow blocks' events with the traded contract and entry spot."""
    h = pd.read_parquet(HOLD)
    for c in ("entry_date", "exit_date", "expiry"):
        h[c] = pd.to_datetime(h[c])
    h = h[(h["entry_date"] >= CMBP_START) & (h["entry_date"] < "2025-01-01")]
    a = h.assign(block="broad_2023_2024", spot_entry=(h["m0"] - h["s0"]) / 0.20)[
        ["block", "ticker", "entry_date", "exit_date", "strike", "expiry", "spot_entry"]
    ]
    led = pd.read_csv(LEDGER, parse_dates=["entry_date", "exit_date", "expiry"])
    b = led.assign(block="broad_2025_2026")[a.columns]
    p = pd.read_parquet(PANEL)
    p = p[p["block"] == "discovery_2019_2024"].copy()
    for c in ("entry_date", "exit_date", "expiry_mkt"):
        p[c] = pd.to_datetime(p[c])
    p = p[p["entry_date"] >= CMBP_START]
    m = (
        p.drop(columns=["strike"])
        .rename(columns={"strike_mkt": "strike", "expiry_mkt": "expiry"})
        .assign(block="megacap_2023_2024")[a.columns]
    )
    ev = pd.concat([a, b, m], ignore_index=True)
    ev["exists"] = [
        (CACHE / r.block / f"{r.ticker}_{r.entry_date.date()}_exit.parquet").exists()
        and (CACHE / r.block / f"{r.ticker}_{r.entry_date.date()}_pre.parquet").exists()
        for r in ev.itertuples()
    ]
    return ev


# ── grids ───────────────────────────────────────────────────────────────────


def _local(day: pd.Timestamp, h: int, m: int, s: int = 0) -> pd.Timestamp:
    return (day.normalize() + pd.Timedelta(hours=h, minutes=m, seconds=s)).tz_localize(TZ)


def _read(path: Path) -> pd.DataFrame:
    t = ds.dataset(str(path)).to_table(columns=COLS).to_pandas(ignore_metadata=True)
    t["right"] = t["symbol"].astype(str).str.replace(" ", "").str[-9]
    t["ts"] = pd.DatetimeIndex(t["ts_recv"]).tz_convert(TZ)
    return t.sort_values("ts")


def _grid(t: pd.DataFrame, day: pd.Timestamp) -> np.ndarray:
    """Prevailing (call bid, call ask, put bid, put ask) at each grid second of 15:00-16:00."""
    base = _local(day, 15, 0)
    times = base + pd.to_timedelta(np.arange(N_GRID) * GRID_STEP, unit="s")
    out = np.full((4, N_GRID), np.nan, dtype=np.float32)
    lo = _local(day, 9, 30)
    for j, r in enumerate(("C", "P")):
        q = t[(t["right"] == r) & (t["ts"] >= lo) & (t["ts"] < base + pd.Timedelta(hours=1))]
        if q.empty:
            continue
        idx = np.searchsorted(q["ts"].to_numpy(), times.to_numpy(), side="right") - 1
        ok = idx >= 0
        bid = q["bid_px_00"].to_numpy(float)
        ask = q["ask_px_00"].to_numpy(float)
        b = np.where(ok, bid[np.clip(idx, 0, None)], np.nan)
        a = np.where(ok, ask[np.clip(idx, 0, None)], np.nan)
        bad = ~((b > 0) & (a > b))  # one-sided or crossed: no usable quote
        b[bad], a[bad] = np.nan, np.nan
        out[2 * j], out[2 * j + 1] = b, a
    return out


def _s0(pre: pd.DataFrame, d0: pd.Timestamp) -> float:
    """Sum of the two legs' prevailing two-sided bids at 15:59:00 on the entry session."""
    cut = _local(d0, 15, 59)
    tot = 0.0
    for r in ("C", "P"):
        q = pre[(pre["right"] == r) & (pre["ts"] <= cut) & (pre["ts"] >= _local(d0, 9, 30))]
        q = q[(q["bid_px_00"] > 0) & (q["ask_px_00"] > q["bid_px_00"])]
        if q.empty:
            return float("nan")
        tot += float(q["bid_px_00"].iloc[-1])
    return tot


def main() -> None:
    ev = events()
    funnel: dict[str, int] = {"planned": len(ev), "files_missing": int((~ev["exists"]).sum())}
    ev = ev[ev["exists"]].drop(columns="exists")
    dup = ev.duplicated(["ticker", "entry_date"], keep="first")
    funnel["duplicate_across_blocks"] = int(dup.sum())
    ev = ev[~dup]
    early = ev["entry_date"].isin(EARLY_CLOSE) | ev["exit_date"].isin(EARLY_CLOSE)
    funnel["early_close"] = int(early.sum())
    ev = ev[~early].reset_index(drop=True)
    grids = np.full((len(ev), 4, 4, N_GRID), np.nan, dtype=np.float32)
    rows = []
    t0 = time.time()
    for i, e in ev.iterrows():
        stem = CACHE / e["block"] / f"{e['ticker']}_{e['entry_date'].date()}"
        pre, ex = _read(Path(f"{stem}_pre.parquet")), _read(Path(f"{stem}_exit.parquet"))
        d0, d1 = e["entry_date"], e["exit_date"]
        pre_days = sorted({d for d in pre["ts"].dt.normalize().dt.tz_localize(None).unique()
                           if d < d0})
        days = {"D0": d0, "D1": d1}
        if len(pre_days) >= 1:
            days["Dm1"] = pd.Timestamp(pre_days[-1])
        if len(pre_days) >= 2:
            days["Dm2"] = pd.Timestamp(pre_days[-2])
        for k, s in enumerate(SESSIONS):
            if s in days and days[s] not in EARLY_CLOSE:
                grids[i, k] = _grid(ex if s == "D1" else pre, days[s])
        rows.append({**e.to_dict(), "eid": i, "s0": _s0(pre, d0),
                     "dm1_date": days.get("Dm1"), "dm2_date": days.get("Dm2")})
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(ev)} events, {time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    out["m0"] = 0.20 * out["spot_entry"] + out["s0"]
    funnel["extracted"] = len(out)
    funnel["no_entry_bid"] = int(out["s0"].isna().sum())
    OUT.mkdir(exist_ok=True)
    out.to_parquet(OUT / "events.parquet", index=False)
    np.savez_compressed(OUT / "grid.npz", grid=grids)
    (HERE / "extract_funnel.json").write_text(json.dumps(funnel, indent=1))
    print("funnel:", funnel, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    sys.exit(main())
