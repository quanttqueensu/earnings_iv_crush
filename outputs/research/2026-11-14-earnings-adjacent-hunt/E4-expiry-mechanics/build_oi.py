"""
build_oi.py
E4 trial 2,773 inputs: per megacap hedged-hold event, the hedged hold at the ATM strike K0 and at
its two listed neighbours, valued by the frozen hedged-event-hold builder (megacap amendment 02,
unchanged) under both settlement conventions, plus a causal open-interest proxy per strike.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/build_oi.py

Proxy: cumulative Alpaca daily option volume (calls plus puts) at each strike of the front expiry
over sessions strictly before the entry date. Open interest is not on disk (see diagnosis.log).
K0 rebuilt under HEDGED must reproduce the stored megacap H to 1e-9 of m0 or the build stops.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED, HEDGED_NET  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402

HERE = Path(__file__).resolve().parent
MEGA = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "megacap.py"
STORED = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events_megacap.parquet"
ALPACA = ROOT / "data" / "cache" / "alpaca_legacy"
RECON_TOL = 1e-9

sys.path.insert(0, str(MEGA.parent))
_s = importlib.util.spec_from_file_location("hh_megacap", MEGA)
assert _s is not None and _s.loader is not None
mg = importlib.util.module_from_spec(_s)
_s.loader.exec_module(mg)
st = mg.st
st.exit_quotes, st.exit_fwd = mg.exit_quotes, mg.exit_fwd  # as megacap.main does

_last: dict[str, float] = {}


def _both(**kw: Any) -> hh.HedgedResult:
    """Value under the frozen convention (returned) and record the netted one."""
    old = hh.hedged_short_straddle(**kw, cfg=HEDGED)
    if kw.get("hedge", True):
        _last["net"] = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET).net_pnl
    return old


st.hedged_short_straddle = _both


# ── open-interest proxy ─────────────────────────────────────────────────────

_vol_cache: dict[str, pd.DataFrame] = {}


def volume_bars(ticker: str) -> pd.DataFrame | None:
    if ticker not in _vol_cache:
        p = ALPACA / f"options_{ticker}_1d.parquet"
        if not p.exists():
            return None
        d = pd.read_parquet(p, columns=["ts", "expiry", "opt_type", "strike", "volume"])
        d["ts"] = pd.to_datetime(d["ts"]).dt.tz_localize(None).dt.normalize()
        d["expiry"] = pd.to_datetime(d["expiry"])
        d["strike"] = d["strike"].astype(float).round(3)
        _vol_cache[ticker] = d
    return _vol_cache[ticker]


def strike_table(strip: pd.DataFrame, expiry: pd.Timestamp) -> pd.DataFrame:
    x = mg._two_sided(strip[strip["expiry"] == expiry])
    c = x[x["right"] == "C"].groupby("strike").last()
    p = x[x["right"] == "P"].groupby("strike").last()
    k = c.index.intersection(p.index)
    return pd.DataFrame(
        {
            "bid": c.loc[k, "bid_px_00"] + p.loc[k, "bid_px_00"],
            "ask": c.loc[k, "ask_px_00"] + p.loc[k, "ask_px_00"],
            "mid": c.loc[k, "mid"] + p.loc[k, "mid"],
        }
    ).sort_index()


def build_one(r: pd.Series, crsp: dict) -> dict:
    out: dict = {"ticker": r["ticker"], "entry_date": r["entry_date"], "exit_date": r["exit_date"]}
    fr = mg.front_row(r)
    if fr is None:
        return {**out, "status": "no_entry_front"}
    exp = pd.Timestamp(fr["front_expiry"])
    vb = volume_bars(r["ticker"])
    if vb is None:
        return {**out, "status": "no_alpaca_file"}
    x = vb[(vb["expiry"] == exp) & (vb["ts"] < pd.Timestamp(r["entry_date"]))]
    if x.empty:
        return {**out, "status": "no_prior_bars"}
    vol = x.groupby("strike")["volume"].sum()
    strip = mg._strip(r["ticker"], pd.Timestamp(r["entry_date"]))
    tab = strike_table(strip, exp)
    k0, fwd = float(fr["front_strike"]), float(fr["front_fwd"])
    ks = tab.index.to_numpy(float)
    if k0 not in tab.index:
        return {**out, "status": "k0_not_in_table"}
    i0 = int(np.searchsorted(ks, k0))
    t0 = float(fr["front_t"])
    out.update(status="ok", expiry=exp, fwd=fwd, k0=k0, t0=t0, permno=fr["permno"],
               vol_total=float(vol.sum()), n_vol_days=int(x["ts"].nunique()))
    for lab, j in (("k0", i0), ("km1", i0 - 1), ("kp1", i0 + 1)):
        if j < 0 or j >= len(ks):
            out[f"{lab}_status"] = "no_neighbour"
            continue
        k = float(ks[j])
        q = tab.loc[k]
        row = fr.copy()
        row["front_strike"], row["front_bid"] = k, float(q["bid"])
        row["front_mid"], row["front_ask"] = float(q["mid"]), float(q["ask"])
        _last.clear()
        res = st.build_event(row, crsp)
        out[f"{lab}_status"] = res["status"]
        out[f"{lab}_K"] = k
        out[f"{lab}_bid"], out[f"{lab}_ask"], out[f"{lab}_mid"] = q["bid"], q["ask"], q["mid"]
        out[f"{lab}_mid_iv"] = hh.straddle_iv(float(q["mid"]), fwd, k, t0)
        out[f"{lab}_V"] = float(vol.get(round(k, 3), 0.0))
        if res["status"] == "ok":
            m0 = float(res["m0"])
            out[f"{lab}_m0"] = m0
            out[f"{lab}_usd_old"] = float(res["H"] * m0)
            net = _last["net"] if "net" in _last else float(res["H"] * m0)
            out[f"{lab}_usd"] = float(net)
            out[f"{lab}_usd_mid"] = float(res["H_mid"] * m0)
            out[f"{lab}_settle"] = float(res["settle"])
            out[f"{lab}_intrinsic"] = float(res["intrinsic"])
            out[f"{lab}_n_hedge"] = int(res["n_hedge"])
    return out


def main() -> None:
    ev = pd.read_parquet(st.EVENTS)
    ev = ev[ev["block"] == "megacap"][["ticker", "entry_date", "exit_date"]].copy()
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno", "s2_iv"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    ev = ev.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                  how="left")
    stored = pd.read_parquet(STORED)
    stored = stored[stored["status"] == "ok"].copy()
    stored["entry_date"] = pd.to_datetime(stored["entry_date"])
    ev = ev.merge(stored[["ticker", "entry_date", "H", "m0", "strike"]],
                  on=["ticker", "entry_date"], how="inner")
    print(f"megacap events with stored status ok: {len(ev)}", flush=True)
    crsp = st.load_crsp()
    rows = []
    for i, (_, r) in enumerate(ev.iterrows()):
        rows.append(build_one(r, crsp))
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(ev)}", flush=True)
    d = pd.DataFrame(rows).merge(ev[["ticker", "entry_date", "H", "m0", "strike"]],
                                 on=["ticker", "entry_date"], suffixes=("", "_stored"))
    print("funnel:", dict(Counter(d["status"])))
    for lab in ("k0", "km1", "kp1"):
        print(f"  {lab}:", dict(Counter(d.get(f"{lab}_status", pd.Series()).fillna("not_built"))))
    ok = d["k0_status"].eq("ok")
    gap = (d.loc[ok, "k0_usd_old"] / d.loc[ok, "m0"] - d.loc[ok, "H"]).abs()
    kgap = int((d.loc[ok, "k0"] != d.loc[ok, "strike"]).sum())
    print(f"reconciliation K0 vs stored H: n={int(ok.sum())}, max abs gap {gap.max():.2e}, "
          f"strike mismatches {kgap}")
    if gap.max() > RECON_TOL or kgap:
        raise ValueError("K0 rebuild does not reproduce the stored megacap H; nothing is scored")
    d.to_parquet(HERE / "oi_arms.parquet")
    print("wrote oi_arms.parquet")


if __name__ == "__main__":
    main()
