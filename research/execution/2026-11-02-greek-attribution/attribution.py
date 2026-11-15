"""
attribution.py
Descriptive Greek attribution of the one-night short front straddle (entry 15:59 before the
announcement, exit 15:59 on the reaction session, same strike and expiry). Selects nothing and
tests no rule, so it is not a trial; it says which Greek carries the P&L and where a mispricing
could live.

Sequential full revaluation of a long Black-Scholes straddle on the forward, zero rate:

    theta   = V(S0, t1, s0) - V(S0, t0, s0)
    vega    = V(S0, t1, s1) - V(S0, t1, s0)
    delta   = D(S0, t1, s1) * (S1 - S0)
    convex  = V(S1, t1, s1) - V(S0, t1, s1) - delta
    resid   = exit_mid - V(S1, t1, s1)

with S0 the entry parity forward, S1 the reaction-session parity forward, s0 and s1 the straddle
implied volatilities at the two marks. The short's P&L at the mid is minus the sum; touch costs are
the entry and exit half-spreads. The reverse order (spot before volatility) is reported too, since
a sequential split depends on its order.

Usage
-----
    python research/execution/2026-11-02-greek-attribution/attribution.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    straddle_delta,
    straddle_iv,
    straddle_value,
    year_frac,
)
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "research" / HERE.name
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
MARGIN_SPOT_FRAC = 0.20
COMPONENTS = ("theta", "vega", "delta", "convex", "resid")


def _chain(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> pd.DataFrame | None:
    p = CHAINS / f"{ticker}_{day.date()}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d[(d["expiry"] == expiry) & (d["bid_px_00"] > 0) & (d["ask_px_00"] > 0)]
    if d.empty:
        return None
    d = d.sort_values("ts_recv").groupby(["strike", "right"], as_index=False).last()
    d["mid"] = (d["bid_px_00"] + d["ask_px_00"]) / 2
    return d


def one(r: pd.Series) -> dict:
    exp, t1d = pd.Timestamp(r["front_expiry"]), pd.Timestamp(r["exit_date"])
    k = float(r["front_strike"])
    t1 = year_frac(t1d, exp)
    if t1 <= 0:
        return {"status": "expires_on_exit"}
    d = _chain(r["ticker"], t1d, exp)
    if d is None:
        return {"status": "no_exit_chain"}
    w = d.pivot(index="strike", columns="right", values="mid").dropna()
    if w.empty or not {"C", "P"} <= set(w.columns) or k not in w.index:
        return {"status": "no_exit_pair"}
    kk = float((w["C"] - w["P"]).abs().idxmin())
    s1_fwd = float(kk + w.loc[kk, "C"] - w.loc[kk, "P"])
    legs = d[d["strike"] == k].set_index("right")
    x_mid = float(legs["mid"].sum())
    x_ask = float(legs["ask_px_00"].sum())
    s0f, t0, sig0 = float(r["front_fwd"]), float(r["front_t"]), float(r["front_iv"])
    sig1 = straddle_iv(x_mid, s1_fwd, k, t1)
    if not (np.isfinite(sig0) and np.isfinite(sig1)):
        return {"status": "iv_not_bracketed"}
    v00 = straddle_value(s0f, k, t0, sig0)
    a = straddle_value(s0f, k, t1, sig0)
    b = straddle_value(s0f, k, t1, sig1)
    c = straddle_value(s1_fwd, k, t1, sig1)
    dl = straddle_delta(s0f, k, t1, sig1) * (s1_fwd - s0f)
    # reverse order: spot first at the old vol, then vol at the new spot
    ar = straddle_value(s1_fwd, k, t1, sig0)
    dl_r = straddle_delta(s0f, k, t1, sig0) * (s1_fwd - s0f)
    m0 = MARGIN_SPOT_FRAC * s0f + float(r["front_bid"])
    sh = -1.0 / m0  # short position, per unit margin
    return {
        "status": "ok",
        "m0": m0,
        "entry_resid": (float(r["front_mid"]) - v00) * sh,
        "theta": (a - v00) * sh,
        "vega": (b - a) * sh,
        "delta": dl * sh,
        "convex": (c - b - dl) * sh,
        "resid": (x_mid - c) * sh,
        "vega_rev": (c - ar) * sh,
        "spot_rev": (ar - a) * sh,
        "delta_rev": dl_r * sh,
        "entry_cost": (float(r["front_mid"]) - float(r["front_bid"])) / m0,
        "exit_cost": (x_ask - x_mid) / m0,
        "mid_pnl": (float(r["front_mid"]) - x_mid) / m0,
        "touch_pnl": (float(r["front_bid"]) - x_ask) / m0,
        "dvol_pts": (sig1 - sig0) * 100,
        "move": s1_fwd / s0f - 1,
        "implied_move": float(r["front_mid"]) / s0f,
    }


def main() -> None:
    f = pd.read_parquet(FEATURES)
    f = f[f["has_entry_chain"] & f["has_exit_chain"] & (f["front_bid"] > 0)].copy()
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    print(f"  events with both chains and an entry bid: {len(f)}")
    rows = []
    for i, (_, r) in enumerate(f.iterrows()):
        rows.append({"ticker": r["ticker"], "exit_date": r["exit_date"], **one(r)})
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{len(f)}", flush=True)
    d = pd.DataFrame(rows)
    print(d["status"].value_counts().to_string())
    ok = d[d["status"] == "ok"].copy()
    ok["year"] = ok["exit_date"].dt.year
    # the forward-vs-spot gap and the sequential split leave a residual; check it closes
    recon = ok[list(COMPONENTS)].sum(axis=1) - ok["mid_pnl"]
    print(f"  mid reconciliation max |err| {recon.abs().max():.2e}")
    OUT.mkdir(parents=True, exist_ok=True)
    ok.to_parquet(OUT / "attribution.parquet")

    def ci(col: str, s: pd.DataFrame) -> str:
        iv = date_clustered_ci(s[col], s["exit_date"], lambda a: float(np.mean(a)))
        return f"{iv.point * 100:+.3f}% [{iv.low * 100:+.3f}, {iv.high * 100:+.3f}]"

    cols = [
        "theta",
        "vega",
        "delta",
        "convex",
        "resid",
        "mid_pnl",
        "entry_cost",
        "exit_cost",
        "touch_pnl",
        "vega_rev",
        "spot_rev",
    ]
    for lab, s in (
        ("2013-18", ok[ok["year"] <= 2018]),
        ("2019-24", ok[ok["year"].between(2019, 2024)]),
        ("2025-26", ok[ok["year"] >= 2025]),
        ("all", ok),
    ):
        print(f"\n== {lab}  N={len(s)}  (mean per trade, short, unit m0 = 0.20 fwd + entry bid)")
        for c in cols:
            print(f"  {c:11s} {ci(c, s)}")
    # by realised move relative to the implied move: where does convexity overwhelm vega?
    ok["move_ratio"] = ok["move"].abs() / ok["implied_move"]
    ok["mr_bin"] = pd.cut(ok["move_ratio"], [0, 0.5, 1.0, 1.5, 2.0, np.inf])
    g = ok.groupby("mr_bin", observed=True)[
        ["vega", "convex", "theta", "mid_pnl", "touch_pnl", "exit_cost", "dvol_pts"]
    ].mean()
    g["n"] = ok.groupby("mr_bin", observed=True).size()
    print("\n== by |move| / implied move (all years; P&L per m0, dvol in vol points)")
    print(g.round(4).to_string())
    g.to_csv(OUT / "by_move_ratio.csv")


if __name__ == "__main__":
    main()
