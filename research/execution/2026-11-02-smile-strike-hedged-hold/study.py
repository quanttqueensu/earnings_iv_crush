"""
study.py
Hedged one-implied-move strangle against the hedged ATM straddle on the same earnings events.
Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/execution/2026-11-02-smile-strike-hedged-hold/study.py

References
----------
Alexiou, L., Goyal, A., Kostakis, A. and Rompolis, L. (2025) Pricing event risk: evidence from
concave implied volatility curves. Review of Finance.
Glasserman, P. and Pirjol, D. (2023) W-shaped implied volatility curves and the Gaussian mixture
model. Quantitative Finance 23(4).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research.hedged_hold import option_iv, year_frac  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"
H_EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"

_s = importlib.util.spec_from_file_location("hh_study", HH)
assert _s is not None and _s.loader is not None
st = importlib.util.module_from_spec(_s)
_s.loader.exec_module(st)

N_TRIALS, SR_TRIALS_STD = 1557, 0.127475
ATTRITION_TOL = 0.005
FEE = HEDGED.fee_per_contract_leg / 100.0


# ── chains ──────────────────────────────────────────────────────────────────


def chain(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> pd.DataFrame | None:
    """Last record per (strike, right) on one expiry, raw bids and asks (zeros kept)."""
    p = st.CHAINS / f"{ticker}_{pd.Timestamp(day).date()}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d[d["expiry"] == expiry].sort_values("ts_recv")
    d = d.groupby(["strike", "right"], as_index=False).last()
    return d.rename(columns={"bid_px_00": "bid", "ask_px_00": "ask"})[
        ["strike", "right", "bid", "ask"]
    ]


def pick_wings(c: pd.DataFrame, fwd: float, im: float) -> tuple[pd.Series, pd.Series] | None:
    calls = c[(c["right"] == "C") & (c["bid"] > 0) & (c["strike"] >= fwd * (1 + im))]
    puts = c[(c["right"] == "P") & (c["bid"] > 0) & (c["strike"] <= fwd * (1 - im))]
    if calls.empty or puts.empty:
        return None
    return calls.loc[calls["strike"].idxmin()], puts.loc[puts["strike"].idxmax()]


# ── valuation ───────────────────────────────────────────────────────────────


def leg_delta(spot: float, k: float, t: float, sigma: float, right: str) -> float:
    """Black-Scholes delta of one long option, zero carry; at expiry the exercise indicator."""
    if t <= 0 or sigma <= 0:
        itm = spot > k if right == "C" else spot < k
        return (1.0 if right == "C" else -1.0) if itm else 0.0
    sd = sigma * np.sqrt(t)
    d1 = (np.log(spot / k) + 0.5 * sd * sd) / sd
    return float(norm.cdf(d1)) if right == "C" else float(norm.cdf(d1) - 1.0)


def hedged_short_strangle(
    *,
    sale: float,
    kc: float,
    kp: float,
    closes: np.ndarray,
    rets: np.ndarray,
    taus: np.ndarray,
    sig_c: float,
    sig_p: float,
    half_spreads: np.ndarray,
    settle: float,
) -> dict:
    """Mirror of ``hedged_short_straddle`` for two strikes; equal strikes reproduce it."""
    floor = HEDGED.equity_cost_floor_bps / 1e4
    hs = np.maximum(np.asarray(half_spreads, float), floor)
    h_prev = hedge_pnl = cost = peak = 0.0
    for i in range(len(closes)):
        h = leg_delta(closes[i], kc, taus[i], sig_c, "C") + leg_delta(
            closes[i], kp, taus[i], sig_p, "P"
        )
        cost += abs(h - h_prev) * closes[i] * hs[i]
        hedge_pnl += h * closes[i] * rets[i]
        peak = max(peak, abs(h) * closes[i])
        h_prev = h
    if len(closes):
        cost += abs(h_prev) * settle * hs[-1]
    settlement = max(settle - kc, 0.0) + max(kp - settle, 0.0)
    disposal = HEDGED.disposal_bps / 1e4 * settle if settlement > 0 else 0.0
    net = sale - settlement + hedge_pnl - cost - 2 * FEE - disposal
    return {
        "net": net,
        "settlement": settlement,
        "hedge_pnl": hedge_pnl,
        "eq_cost": cost,
        "disposal": disposal,
        "peak": peak,
    }


# ── one event ───────────────────────────────────────────────────────────────


def build_g(e: pd.Series, crsp: dict) -> dict:
    base = {"ticker": e["ticker"], "entry_date": e["entry_date"]}
    exp, t0, t1 = pd.Timestamp(e["expiry"]), pd.Timestamp(e["entry_date"]), e["exit_date"]
    fwd0 = (e["m0"] - e["s0"]) / st.MARGIN_SPOT_FRAC
    im = e["mid0"] / fwd0
    c0 = chain(e["ticker"], t0, exp)
    if c0 is None:
        return {**base, "status": "no_entry_chain"}
    w = pick_wings(c0, fwd0, im)
    if w is None:
        return {**base, "status": "no_wing"}
    cl0, pt0 = w
    kc, kp = float(cl0["strike"]), float(pt0["strike"])
    sale = float(cl0["bid"] + pt0["bid"])
    two0 = cl0["ask"] > 0 and pt0["ask"] > 0
    mid_sale = float((cl0["bid"] + cl0["ask"] + pt0["bid"] + pt0["ask"]) / 2) if two0 else np.nan
    st_, g = st.stock_path(crsp, e["permno"], t1, exp)
    if st_ != "ok" or g is None:
        return {**base, "status": "path_" + st_}
    closes = g["prc"].to_numpy(float)
    hs = ((g["ask"] - g["bid"]) / 2 / g["prc"]).to_numpy(float)
    settle = float(closes[-1])
    n = len(closes) - 1
    src = "none"
    sig_c = sig_p = np.nan
    if n > 0:
        t_ex = year_frac(t1, exp)
        t_en = year_frac(t0, exp)
        c1 = chain(e["ticker"], t1, exp)
        fx = st.exit_fwd(e["ticker"], t1, exp) if c1 is not None else np.nan
        sigs = {}
        src = "exit_chain"
        for leg, k, r in ((cl0, kc, "C"), (pt0, kp, "P")):
            s = np.nan
            if c1 is not None and np.isfinite(fx):
                q = c1[(np.isclose(c1["strike"], k)) & (c1["right"] == r)]
                if not q.empty and q["bid"].iloc[0] > 0 and q["ask"].iloc[0] > 0:
                    s = option_iv(float(q[["bid", "ask"]].iloc[0].mean()), fx, k, t_ex, r)
            if not np.isfinite(s) and leg["ask"] > 0:
                s = option_iv(float((leg["bid"] + leg["ask"]) / 2), fwd0, k, t_en, r)
                src = "entry_iv_fallback"
            if not np.isfinite(s):
                return {**base, "status": "no_hedge_vol"}
            sigs[r] = s
        sig_c, sig_p = sigs["C"], sigs["P"]
    taus = np.array([year_frac(d, exp) for d in g.index[:-1]])
    r = hedged_short_strangle(
        sale=sale,
        kc=kc,
        kp=kp,
        closes=closes[:-1],
        rets=g["ret"].to_numpy(float)[1:],
        taus=taus,
        sig_c=sig_c,
        sig_p=sig_p,
        half_spreads=hs[:-1],
        settle=settle,
    )
    mg = st.MARGIN_SPOT_FRAC * fwd0 + sale
    s1 = closes[0]
    call_set = max(settle - kc, 0.0)
    put_set = max(kp - settle, 0.0)
    return {
        **base,
        "status": "ok",
        "src": src,
        "kc": kc,
        "kp": kp,
        "im": im,
        "sale": sale,
        "mid_sale": mid_sale,
        "mg": mg,
        "G": r["net"] / mg,
        "G_mid": (mid_sale - r["settlement"] + r["hedge_pnl"]) / mg,
        "G_call_settle": call_set / mg,
        "G_put_settle": put_set / mg,
        "G_call_bid": float(cl0["bid"]) / mg,
        "G_put_bid": float(pt0["bid"]) / mg,
        "G_half_spread_frac": (mid_sale - sale) / mid_sale if two0 else np.nan,
        "move_ratio": abs(s1 / fwd0 - 1.0) / im,
        "peak_g": r["peak"],
    }


# ── scoring ─────────────────────────────────────────────────────────────────


def _sr_diff_ci(a: np.ndarray, b: np.ndarray, dates: pd.Series):
    idx = np.arange(len(a), dtype=float)

    def stat(ii: np.ndarray) -> float:
        k = ii.astype(int)
        return per_trade_sharpe(a[k]) - per_trade_sharpe(b[k])

    return date_clustered_ci(idx, dates, stat)


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = pd.read_parquet(H_EVENTS)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    ev = ev.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])
    print(f"  H events {len(ev)}")
    crsp = st.load_crsp()
    rows = []
    for i, (_, e) in enumerate(ev.iterrows()):
        rows.append(build_g(e, crsp))
        if (i + 1) % 1000 == 0:
            print(f"  built {i + 1}/{len(ev)}", flush=True)
    g = pd.DataFrame(rows)
    funnel = dict(Counter(g["status"]))
    print("funnel:", funnel)
    d = ev.merge(g, on=["ticker", "entry_date"], how="left")
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")
    d["year"] = d["exit_date"].dt.year
    res: dict = {"funnel": funnel}
    for name, (y0, y1) in st.BLOCKS.items():
        blk = d[d["year"].between(y0, y1)]
        ok = blk[blk["status_y"] == "ok"] if "status_y" in blk else blk[blk["status"] == "ok"]
        p1 = date_clustered_ci(ok["G"].to_numpy(float), ok["exit_date"], per_trade_sharpe)
        p2 = _sr_diff_ci(ok["G"].to_numpy(float), ok["H"].to_numpy(float), ok["exit_date"])
        h_sr = per_trade_sharpe(ok["H"])
        bins = pd.cut(ok["move_ratio"], [0, 0.5, 1, 1.5, 2, np.inf])
        res[name] = {
            "n_h": int(len(blk)),
            "n_g": int(len(ok)),
            "P1_sharpe_G": [p1.point, p1.low, p1.high],
            "P2_sharpe_G_minus_H": [p2.point, p2.low, p2.high],
            "sharpe_H_same": h_sr,
            "mean_G": float(ok["G"].mean()),
            "mean_G_mid": float(ok["G_mid"].mean()),
            "mean_H_same": float(ok["H"].mean()),
            "mean_H_all": float(blk["H"].mean()),
            "attrition_gap": float(ok["H"].mean() - blk["H"].mean()),
            "call_bid_minus_settle": float((ok["G_call_bid"] - ok["G_call_settle"]).mean()),
            "put_bid_minus_settle": float((ok["G_put_bid"] - ok["G_put_settle"]).mean()),
            "G_half_spread_frac_med": float(ok["G_half_spread_frac"].median()),
            "skew_G": float(ok["G"].skew()),
            "fallback_share": float((ok["src"] == "entry_iv_fallback").mean()),
            "G_minus_H_by_move_ratio": {
                str(k): [float(v.mean()), int(len(v))]
                for k, v in (ok["G"] - ok["H"]).groupby(bins, observed=True)
            },
            "dsr_G": float(
                deflated_sharpe_ratio(ok["G"].reset_index(drop=True), N_TRIALS, SR_TRIALS_STD)
            ),
        }
    a, b = res["discovery"], res["validation"]
    biased = any(x["attrition_gap"] > ATTRITION_TOL for x in (a, b))
    book = b["P1_sharpe_G"][1] > 0 and a["P1_sharpe_G"][0] > 0
    lever = all(x["P2_sharpe_G_minus_H"][1] > 0 for x in (a, b))
    worse = all(x["P2_sharpe_G_minus_H"][2] < 0 for x in (a, b))
    res["attrition_biased"] = bool(biased)
    res["verdict"] = (
        ("BOOK not read (attrition)" if biased else ("BOOK PASS" if book else "BOOK FAIL"))
        + "; "
        + (
            "STRUCTURE LEVER"
            if lever
            else ("straddle is the better structure" if worse else "no structure difference")
        )
    )
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
