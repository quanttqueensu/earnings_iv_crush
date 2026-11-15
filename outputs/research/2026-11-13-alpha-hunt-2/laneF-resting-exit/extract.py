"""
extract.py
Stage 1 of lane F: compact reaction-session ticks (15:00 to 16:00) and entry bids per event.

Reads the cmbp-1 files already on disk under ``data/cache/flow`` (no pull, no spend) for the two
blocks whose exit-day ticks exist and that are not the resting-entry confirmation block:
``broad_2025_2026`` (events of ``outputs/research/oos_2026_ledger.csv``) and
``megacap_2023_2024`` (``outputs/research/reverse_alpha/panel.parquet``, discovery block, entries
from 2023-03-28). Writes ``events.parquet`` (one row per event with the entry 15:59:00 bids and
m0) and ``ticks.parquet`` (every exit-day record of both legs, time in seconds after 15:00 ET).

m0 = 0.20 x spot_entry + S0, with S0 the sum of the two legs' 15:59:00 entry bids from the
ticks. Spot stands in for the forward (front expiries, a few days); this is the book's Reg-T
approximation.

Usage:
    python outputs/research/2026-11-13-alpha-hunt-2/laneF-resting-exit/extract.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
CACHE = ROOT / "data/cache/flow"
LEDGER = ROOT / "outputs/research/oos_2026_ledger.csv"
PANEL = ROOT / "outputs/research/reverse_alpha/panel.parquet"
TZ = "America/New_York"
CMBP_START = pd.Timestamp("2023-03-28")
# NYSE 13:00 closes in the span; a 15:00-16:00 window does not exist on these days.
EARLY_CLOSE = {
    pd.Timestamp(d)
    for d in (
        "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24",
        "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24",
    )
}
COLS = ["ts_recv", "action", "price", "size", "bid_px_00", "ask_px_00", "symbol"]


def _events() -> pd.DataFrame:
    led = pd.read_csv(LEDGER, parse_dates=["entry_date", "exit_date", "expiry", "announce_date"])
    b = led.assign(block="broad_2025_2026")[
        ["block", "ticker", "announce_date", "entry_date", "exit_date", "strike", "expiry",
         "spot_entry", "spot_exit", "implied_move"]
    ]
    p = pd.read_parquet(PANEL)
    p = p[p["block"] == "discovery_2019_2024"].copy()
    for c in ("entry_date", "exit_date", "announce_date", "expiry_mkt"):
        p[c] = pd.to_datetime(p[c])
    p = p[p["entry_date"] >= CMBP_START]
    # The panel also carries a model ``strike``; the traded contract is ``strike_mkt``.
    m = p.drop(columns=["strike"]).rename(columns={"strike_mkt": "strike", "expiry_mkt": "expiry"}).assign(
        block="megacap_2023_2024"
    )[b.columns]
    return pd.concat([b, m], ignore_index=True)


def _read(path: Path, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame | None:
    if not path.exists():
        return None
    d = ds.dataset(str(path))
    typ = pa.timestamp("ns", tz="UTC")
    flt = (ds.field("ts_recv") >= pa.scalar(lo.to_pydatetime(), type=typ)) & (
        ds.field("ts_recv") <= pa.scalar(hi.to_pydatetime(), type=typ)
    )
    t = d.to_table(columns=COLS, filter=flt).to_pandas(ignore_metadata=True)
    if t.empty:
        return t
    t["right"] = t["symbol"].astype(str).str.replace(" ", "").str[-9]
    return t


def _local(day: pd.Timestamp, h: int, m: int, s: int = 0) -> pd.Timestamp:
    return (day.normalize() + pd.Timedelta(hours=h, minutes=m, seconds=s)).tz_localize(TZ)


def main() -> None:
    ev = _events()
    rows, ticks, funnel = [], [], {"planned": len(ev)}
    t0 = time.time()
    for i, e in ev.iterrows():
        d_in, d_out = pd.Timestamp(e["entry_date"]), pd.Timestamp(e["exit_date"])
        if d_in in EARLY_CLOSE or d_out in EARLY_CLOSE:
            funnel["early_close"] = funnel.get("early_close", 0) + 1
            continue
        stem = CACHE / e["block"] / f"{e['ticker']}_{d_in.date()}"
        pre = _read(Path(f"{stem}_pre.parquet"), _local(d_in, 15, 50), _local(d_in, 15, 59))
        ex = _read(Path(f"{stem}_exit.parquet"), _local(d_out, 14, 59), _local(d_out, 16, 0))
        if pre is None or ex is None:
            funnel["no_file"] = funnel.get("no_file", 0) + 1
            continue
        s0 = {}
        for r in ("C", "P"):
            q = pre[(pre["right"] == r) & (pre["bid_px_00"] > 0) & (pre["ask_px_00"] > pre["bid_px_00"])]
            s0[r] = float(q["bid_px_00"].iloc[-1]) if len(q) else np.nan
        if not np.isfinite(s0["C"] + s0["P"]) or ex.empty:
            funnel["no_entry_bid_or_empty_exit"] = funnel.get("no_entry_bid_or_empty_exit", 0) + 1
            continue
        base = _local(d_out, 15, 0)
        sec = (pd.DatetimeIndex(ex["ts_recv"]).tz_convert(TZ) - base).total_seconds()
        ex = ex.assign(sec=np.asarray(sec), eid=i)
        ex = ex[ex["right"].isin(["C", "P"])]
        ticks.append(ex[["eid", "right", "sec", "action", "price", "size", "bid_px_00", "ask_px_00"]])
        m0 = 0.20 * float(e["spot_entry"]) + s0["C"] + s0["P"]
        rows.append({**e.to_dict(), "eid": i, "s0_c": s0["C"], "s0_p": s0["P"], "m0": m0})
        if len(rows) % 200 == 0:
            print(f"  {len(rows)} events, {time.time() - t0:.0f}s", flush=True)
    funnel["extracted"] = len(rows)
    print("  funnel:", funnel, flush=True)
    if not rows:
        raise SystemExit("nothing extracted")
    pd.DataFrame(rows).to_parquet(OUT / "events.parquet")
    tk = pd.concat(ticks, ignore_index=True)
    tk["action"] = tk["action"].astype(str)
    tk["right"] = tk["right"].astype(str)
    tk.to_parquet(OUT / "ticks.parquet")
    pd.Series(funnel).to_json(OUT / "extract_funnel.json")
    print(f"  wrote {len(rows)} events, {len(tk)} ticks, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    sys.exit(main())
