"""
build_state.py
Reaction-close state of every ok hedged-hold event: per-leg 15:59 quotes at the frozen strike and
expiry, the parity forward, the straddle's implied vol at bid, mid and ask, and the remaining
extrinsic value. Everything here is observable at the reaction-session close (the decision time
of every lane-A rule). Reads the cached reaction-day chains only; no network.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneA-hold-exit/build_state.py [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import option_iv, straddle_iv, year_frac  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLD = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"


def _parse(p: Path) -> pd.DataFrame:
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    return d


def state(row: pd.Series) -> dict:
    t1, exp, k = pd.Timestamp(row["exit_date"]), pd.Timestamp(row["expiry"]), float(row["strike"])
    out: dict = {"ticker": row["ticker"], "entry_date": row["entry_date"]}
    p = CHAINS / f"{row['ticker']}_{t1.date()}.parquet"
    if not p.exists():
        return {**out, "st_status": "no_exit_chain"}
    d = _parse(p)
    e = d[d["expiry"] == exp]
    leg = e[np.isclose(e["strike"], k)].sort_values("ts_recv")
    for r in "CP":
        x = leg[leg["right"] == r]
        if x.empty:
            return {**out, "st_status": "no_exit_leg"}
        out[f"bid_{r}"] = float(x["bid_px_00"].iloc[-1])
        out[f"ask_{r}"] = float(x["ask_px_00"].iloc[-1])
    # parity forward exactly as the hold study (two-sided legs, strike with min |C - P|)
    w = e[(e["bid_px_00"] > 0) & (e["ask_px_00"] > 0)]
    w = w.sort_values("ts_recv").groupby(["strike", "right"], as_index=False).last()
    w["mid"] = (w["bid_px_00"] + w["ask_px_00"]) / 2
    pv = w.pivot(index="strike", columns="right", values="mid").dropna()
    fx = np.nan
    if not pv.empty and {"C", "P"} <= set(pv.columns):
        kk = float((pv["C"] - pv["P"]).abs().idxmin())
        fx = float(kk + pv.loc[kk, "C"] - pv.loc[kk, "P"])
    out["fwd_x"] = fx
    tau = year_frac(t1, exp)
    out["tau_x"] = tau
    two = min(out["bid_C"], out["bid_P"]) > 0 and min(out["ask_C"], out["ask_P"]) > 0
    out["two_sided"] = bool(two)
    ask = out["ask_C"] + out["ask_P"]
    bid = out["bid_C"] + out["bid_P"]
    mid = (ask + bid) / 2 if two else np.nan
    ok_f = np.isfinite(fx) and tau > 0
    out["iv_mid"] = straddle_iv(mid, fx, k, tau) if (two and ok_f) else np.nan
    out["iv_ask"] = straddle_iv(ask, fx, k, tau) if ok_f else np.nan
    out["iv_bid"] = straddle_iv(bid, fx, k, tau) if (ok_f and bid > 0) else np.nan
    if ok_f:
        intr = abs(fx - k)
        out["intr_x"] = intr
        out["extr_mid"] = mid - intr if two else np.nan
        out["extr_ask"] = ask - intr
        itm = "C" if fx > k else "P"
        out["itm"] = itm
        for r in "CP":
            b, a = out[f"bid_{r}"], out[f"ask_{r}"]
            m = (a + b) / 2 if (b > 0 and a > 0) else np.nan
            out[f"iv_{r}"] = option_iv(m, fx, k, tau, r) if np.isfinite(m) else np.nan
    out["st_status"] = "ok"
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    ev = pd.concat(
        [
            pd.read_parquet(HOLD / "events.parquet"),
            pd.read_parquet(HOLD / "events_confirm_2025_26.parquet"),
        ]
    )
    ev = ev[ev["status"] == "ok"].reset_index(drop=True)
    if a.limit:
        ev = ev.head(a.limit)
    print(f"events ok: {len(ev)}")
    t0 = time.time()
    rows = []
    for i, (_, r) in enumerate(ev.iterrows()):
        rows.append(state(r))
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{len(ev)}  {time.time() - t0:.0f}s", flush=True)
    s = pd.DataFrame(rows)
    print("funnel:", dict(Counter(s["st_status"])))
    out = HERE / ("state_test.parquet" if a.limit else "state.parquet")
    s.to_parquet(out)
    print(f"wrote {out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
