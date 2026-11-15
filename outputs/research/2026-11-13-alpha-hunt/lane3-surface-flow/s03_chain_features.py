"""
s03_chain_features.py
Per-event surface features from the cached 15:59:00 ET consolidated-quote chain on the entry day
(``data/cache/backfill_chains``). Every feature is stamped 15:59:00 ET on the entry session, the
same instant as the entry mark. No outcome is read here.

Features (front expiry = the expiry actually sold, strike = the strike actually sold):
  wing_curv    mean OTM IV one implied move either side of the forward over ATM IV, minus 1
  wing_skew    put-side minus call-side OTM IV at one implied move, over ATM IV
  wing_spread  mean relative quoted spread of the four bracketing wing options
  depth_imb    (bid size - ask size) / (bid size + ask size) summed over the two held legs
  depth_tot    displayed contracts at the touch, both sides, both held legs
  traded_frac  share of front-expiry contracts within one implied move that printed on the day
  atm_stale_h  hours since the older of the two held legs last printed (NaN if never)
  last_vs_mid  (last print - 15:59 mid) / half-spread, mean of legs that printed in the last hour
  n_strikes    two-sided strikes on the front expiry within two implied moves

Usage
-----
    python s03_chain_features.py [--workers 8]
"""

from __future__ import annotations

import argparse
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy.stats import norm

import lib

CHAINS = lib.ROOT / "data" / "cache" / "backfill_chains"
WING_MULT = 1.0  # wings measured one implied move from the forward
MIN_BID = 0.05  # a wing quote below this bid is not used


def _iv(price: np.ndarray, fwd: float, k: np.ndarray, t: float, is_call: np.ndarray) -> np.ndarray:
    """Black implied vol on the forward by bisection; NaN outside the no-arbitrage range."""
    lo = np.full(price.shape, 1e-3)
    hi = np.full(price.shape, 8.0)

    def val(s: np.ndarray) -> np.ndarray:
        sd = s * np.sqrt(t)
        d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
        d2 = d1 - sd
        c = fwd * norm.cdf(d1) - k * norm.cdf(d2)
        return np.where(is_call, c, c - fwd + k)

    bad = (val(lo) > price) | (val(hi) < price)
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        up = val(mid) < price
        lo = np.where(up, mid, lo)
        hi = np.where(up, hi, mid)
    out = 0.5 * (lo + hi)
    out[bad] = np.nan
    return out


def features(row: tuple) -> dict:
    ticker, entry, expiry, strike, fwd, t, im, atm_iv = row
    out: dict = {"ticker": ticker, "entry_date": entry, "chain_status": "ok"}
    path = CHAINS / f"{ticker}_{pd.Timestamp(entry):%Y-%m-%d}.parquet"
    if not path.exists():
        out["chain_status"] = "no_file"
        return out
    df = pd.read_parquet(path)
    sym = df["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    df = df.assign(
        right=sym.str[6],
        strike=pd.to_numeric(sym.str[7:], errors="coerce") / 1000.0,
        expiry=pd.to_datetime(sym.str[:6], format="%y%m%d", errors="coerce"),
    )
    d = df[df["expiry"] == pd.Timestamp(expiry)]
    if d.empty or not (np.isfinite(fwd) and np.isfinite(t) and t > 0 and np.isfinite(im)):
        out["chain_status"] = "no_front_expiry"
        return out
    snap = d.index.max()
    d = d.groupby(["strike", "right"], as_index=False).last()
    # ── held legs: depth and print recency ──
    legs = d[d["strike"] == strike]
    if len(legs) == 2:
        bs, as_ = float(legs["bid_sz_00"].sum()), float(legs["ask_sz_00"].sum())
        if bs + as_ > 0:
            out["depth_imb"] = float((bs - as_) / (bs + as_))
            out["depth_tot"] = float(bs + as_)
        te = pd.to_datetime(legs["ts_event"], utc=True)
        age = (snap - te).dt.total_seconds() / 3600.0
        same_day = te.dt.date == snap.date()
        out["atm_stale_h"] = float(age.max()) if te.notna().all() else np.nan
        recent = legs[(age <= 1.0).to_numpy() & same_day.to_numpy()]
        if len(recent):
            mid = (recent["bid_px_00"] + recent["ask_px_00"]) / 2
            half = (recent["ask_px_00"] - recent["bid_px_00"]) / 2
            ok = half > 0
            if ok.any():
                out["last_vs_mid"] = float(((recent["price"] - mid) / half)[ok].clip(-3, 3).mean())
    # ── activity near the money ──
    band = d[(d["strike"] >= fwd * (1 - im)) & (d["strike"] <= fwd * (1 + im))]
    if len(band):
        tb = pd.to_datetime(band["ts_event"], utc=True)
        out["traded_frac"] = float((tb.dt.date == snap.date()).mean())
    # ── wings on quotes ──
    q = d[(d["bid_px_00"] >= MIN_BID) & (d["ask_px_00"] > d["bid_px_00"])].copy()
    q["mid"] = (q["bid_px_00"] + q["ask_px_00"]) / 2
    q["rel_spread"] = (q["ask_px_00"] - q["bid_px_00"]) / q["mid"]
    otm = q[((q["right"] == "P") & (q["strike"] <= fwd)) | ((q["right"] == "C") & (q["strike"] > fwd))]
    otm = otm[(otm["strike"] >= fwd * (1 - 2.5 * im)) & (otm["strike"] <= fwd * (1 + 2.5 * im))]
    out["n_strikes"] = int(((otm["strike"] >= fwd * (1 - 2 * im)) & (otm["strike"] <= fwd * (1 + 2 * im))).sum())
    if len(otm) >= 4 and np.isfinite(atm_iv) and atm_iv > 0:
        k = otm["strike"].to_numpy(float)
        iv = _iv(otm["mid"].to_numpy(float), fwd, k, t, (otm["right"] == "C").to_numpy())
        good = np.isfinite(iv)
        k, iv, rs = k[good], iv[good], otm["rel_spread"].to_numpy(float)[good]
        kd, ku = fwd * (1 - WING_MULT * im), fwd * (1 + WING_MULT * im)
        # need a quoted strike on each side of each wing target, so the IV is interpolated
        if len(k) >= 4 and k.min() <= kd and k.max() >= ku and (k <= fwd).any() and (k > fwd).any():
            order = np.argsort(k)
            k, iv, rs = k[order], iv[order], rs[order]
            ivd, ivu = np.interp(kd, k, iv), np.interp(ku, k, iv)
            out["wing_curv"] = float(0.5 * (ivd + ivu) / atm_iv - 1.0)
            out["wing_skew"] = float((ivd - ivu) / atm_iv)
            out["wing_spread"] = float(0.5 * (np.interp(kd, k, rs) + np.interp(ku, k, rs)))
            out["wing_gap"] = float(max(np.min(np.abs(k - kd)), np.min(np.abs(k - ku))) / (fwd * im))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    ev = pd.read_parquet(lib.HERE / "base_events.parquet")
    rows = list(
        zip(
            ev["ticker"], ev["entry_date"], ev["expiry"], ev["strike"], ev["front_fwd"],
            ev["front_t"], ev["im"], ev["front_iv"], strict=True,
        )
    )
    with Pool(a.workers) as pool:
        res = pool.map(features, rows, chunksize=64)
    f = pd.DataFrame(res)
    print("funnel chain_status:", f["chain_status"].value_counts().to_dict())
    for c in f.columns[3:]:
        print(f"  {c}: defined {int(f[c].notna().sum())} of {len(f)}")
    f.to_parquet(lib.HERE / "chain_features.parquet", index=False)


if __name__ == "__main__":
    main()
