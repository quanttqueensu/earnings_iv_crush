"""s01_build.py: daily panel of gold and silver implied and realised variance with event flags.

Joins the Cboe GVZ (30-day implied volatility of GLD options, VIX method) and VXSLV (the same on
SLV) closes with GLD and SLV daily closes (Yahoo chart API), computes the 30-day implied total
variance W, its one-session change dW and the close-to-close log return r, flags the sessions
carrying a CPI, payrolls or FOMC release (frozen project calendar), and attaches to each event
session its matched controls: non-event sessions with the same weekday and the same calendar gap
since the previous session, within 60 sessions either side. No outcome is summarised here; the
script prints a funnel only.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s01_build.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
RAW = HERE / "raw"
CAL = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
OUT = HERE / "panel.parquet"
EVENTS_OUT = HERE / "events.parquet"

START, END = "2016-01-04", "2026-10-30"  # the frozen calendar's span
HORIZON_DAYS = 30.0  # GVZ and VXSLV are 30-calendar-day constant-maturity indices
CONTROL_WINDOW = 60  # sessions either side for matched controls
MIN_CONTROLS = 5  # an event with fewer matched controls is dropped (funnel)


def _yahoo(sym: str) -> pd.DataFrame:
    body = json.loads((RAW / f"yahoo_{sym}.json").read_text(encoding="utf-8"))
    res = body["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {"date": ts.normalize().tz_localize(None), "close": q["close"], "open": q["open"]}
    )
    if "splits" in res.get("events", {}):
        raise RuntimeError(f"{sym}: split events present; unadjusted closes would be wrong")
    return df.dropna(subset=["close"]).drop_duplicates("date").set_index("date")


def _vol_index(name: str) -> pd.Series:
    df = pd.read_csv(RAW / f"{name}_History.csv")
    df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y")
    col = name if name in df.columns else "CLOSE"
    return df.set_index("DATE")[col].astype(float).rename(name)


def build_one(sym: str, vol: str) -> pd.DataFrame:
    # Returns, gaps and index changes are taken on the price series' own session calendar, so a
    # session whose previous session lacks an index print yields no dW (never a multi-day change).
    px = _yahoo(sym).sort_index()
    px = px.loc[(px.index >= pd.Timestamp(START) - pd.Timedelta(days=10)) & (px.index <= END)]
    iv = _vol_index(vol)
    df = px.join(iv, how="left")
    df.loc[~(df[vol] > 0), vol] = np.nan
    df["r"] = np.log(df["close"]).diff()
    df["gap"] = df.index.to_series().diff().dt.days
    df["W"] = (df[vol] / 100.0) ** 2 * HORIZON_DAYS / 365.0
    df["dW"] = df["W"].diff()  # NaN unless both this and the previous session have a print
    df["u"] = (df[vol].shift(1) / 100.0) ** 2 / 252.0  # ordinary implied trading-day variance at entry
    stale = df[vol].diff().eq(0)
    n_px, n_iv = len(df), int(df[vol].notna().sum())
    print(f"{sym}/{vol}: price sessions {n_px}, with index print {n_iv}, "
          f"with dW {int(df['dW'].notna().sum())}, unchanged index prints {int(stale.sum())}")
    df["r2"] = df["r"] ** 2
    df["weekday"] = df.index.weekday
    df["stale"] = stale
    df["sym"] = sym
    df = df.loc[df.index >= START].dropna(subset=["dW", "r", "u"])
    return df


def attach_events(df: pd.DataFrame) -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["date"])
    kinds = cal.groupby("date")["kind"].apply(lambda s: "+".join(sorted(set(s))))
    df = df.copy()
    df["kind"] = df.index.map(kinds).fillna("")
    df["is_event"] = df["kind"] != ""
    missing = sorted(set(kinds.index[(kinds.index >= START) & (kinds.index <= END)]) - set(df.index))
    print(f"  calendar event dates in span {int(((kinds.index >= START) & (kinds.index <= END)).sum())}, "
          f"not a session in the panel {len(missing)}: {[d.date().isoformat() for d in missing][:10]}")
    return df


def match_controls(df: pd.DataFrame) -> pd.DataFrame:
    pos = np.arange(len(df))
    rows = []
    ev = df[df["is_event"]]
    dropped_stale = 0
    for t in ev.index:
        i = df.index.get_loc(t)
        if bool(df.iloc[i]["stale"]):
            dropped_stale += 1
            continue
        lo, hi = max(0, i - CONTROL_WINDOW), min(len(df) - 1, i + CONTROL_WINDOW)
        win = df.iloc[lo : hi + 1]
        m = (
            (~win["is_event"])
            & (~win["stale"])
            & (win["weekday"] == df.iloc[i]["weekday"])
            & (win["gap"] == df.iloc[i]["gap"])
        )
        ctrl = win[m]
        rows.append(
            {
                "date": t,
                "sym": df.iloc[i]["sym"],
                "kind": df.iloc[i]["kind"],
                "n_ctrl": len(ctrl),
                "dW": df.iloc[i]["dW"],
                "r2": df.iloc[i]["r2"],
                "r": df.iloc[i]["r"],
                "u": df.iloc[i]["u"],
                "W_prev": df.iloc[i]["W"] - df.iloc[i]["dW"],
                "ctrl_dW_mean": ctrl["dW"].mean() if len(ctrl) else np.nan,
                "ctrl_r2_mean": ctrl["r2"].mean() if len(ctrl) else np.nan,
                "ctrl_u_mean": ctrl["u"].mean() if len(ctrl) else np.nan,
                "ctrl_dates": ",".join(d.date().isoformat() for d in ctrl.index),
            }
        )
    _ = pos
    out = pd.DataFrame(rows)
    few = out["n_ctrl"] < MIN_CONTROLS
    print(f"  event sessions {len(ev)}, dropped stale index print {dropped_stale}, "
          f"dropped fewer than {MIN_CONTROLS} controls {int(few.sum())}, kept {int((~few).sum())}; "
          f"median controls {out['n_ctrl'].median():.0f}")
    return out[~few].reset_index(drop=True)


def main() -> None:
    panels, events = [], []
    for sym, vol in (("GLD", "GVZ"), ("SLV", "VXSLV")):
        df = attach_events(build_one(sym, vol))
        panels.append(df.reset_index(names="date"))
        events.append(match_controls(df))
    pd.concat(panels).to_parquet(OUT, index=False)
    ev = pd.concat(events)
    ev["block"] = np.where(ev["date"] <= pd.Timestamp("2021-12-31"), "discovery", "heldout")
    ev.to_parquet(EVENTS_OUT, index=False)
    print(ev.groupby(["sym", "block"]).size().to_string())
    print(ev.groupby(["sym", "kind"]).size().to_string())


if __name__ == "__main__":
    main()
