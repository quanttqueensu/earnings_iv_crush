"""
build.py
Lane B, contract choice under the hedged event hold: per-event P&L of alternative contracts on
the same events as the frozen arm H (front ATM straddle, hedged from the reaction close, settled
at intrinsic). Builds, per event, the straddle at the two listed strikes adjacent to the ATM
strike, and strangles at fractions of the implied move, all through the frozen builders of the
hedged event hold (``build_event``) and the smile-strike study (``build_g``), unchanged.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/build.py

Every alternative is re-priced on the entry chain's last 15:59 record (decision time 15:59 ET on
the entry session). The ATM strike is rebuilt too and must reproduce the stored H to 1e-9 per m0.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402
from earnings_iv_crush.research.hedged_hold import atm_quote, straddle_iv, year_frac  # noqa: E402

HERE = Path(__file__).resolve().parent
SMILE = ROOT / "research" / "execution" / "2026-11-02-smile-strike-hedged-hold" / "study.py"
H_EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"

_s = importlib.util.spec_from_file_location("smile_study", SMILE)
assert _s is not None and _s.loader is not None
sm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(sm)
st = sm.st  # the frozen hedged-event-hold study module

# ── per-event parquet cache (read-only; the frozen readers call pd.read_parquet) ──
_real_read = pd.read_parquet
_cache: dict[tuple, pd.DataFrame] = {}


def _cached_read(path, columns=None, **kw):  # noqa: ANN001
    key = (str(path), tuple(columns) if columns is not None else None)
    if key not in _cache:
        _cache[key] = _real_read(path, columns=columns, **kw)
    return _cache[key]


STRANGLE_WIDTHS = (0.5, 1.0)  # fractions of the implied move; 1.0 reproduces trial 1,557


def _usd(res: dict) -> float:
    return float(res["H"] * res["m0"]) if res.get("status") == "ok" else np.nan


def strike_table(ch: pd.DataFrame, expiry: pd.Timestamp) -> pd.DataFrame:
    """Two-sided straddle quotes per strike on one expiry (both legs bid > 0, ask > 0)."""
    d = ch[ch["expiry"] == expiry]
    c = d[d["right"] == "C"].set_index("strike")
    p = d[d["right"] == "P"].set_index("strike")
    k = c.index.intersection(p.index)
    t = pd.DataFrame(
        {
            "bid": c.loc[k, "bid_px_00"] + p.loc[k, "bid_px_00"],
            "ask": c.loc[k, "ask_px_00"] + p.loc[k, "ask_px_00"],
            "mid": c.loc[k, "mid"] + p.loc[k, "mid"],
            "bid_sz": np.minimum(c.loc[k, "bid_sz_00"], p.loc[k, "bid_sz_00"]),
        }
    ).sort_index()
    return t


def build_one(e: pd.Series, f: pd.Series, crsp: dict) -> dict:
    out: dict = {"ticker": e["ticker"], "entry_date": e["entry_date"], "status": "ok"}
    p = st.CHAINS / f"{e['ticker']}_{pd.Timestamp(e['entry_date']).date()}.parquet"
    if not p.exists():
        return {**out, "status": "no_entry_chain"}
    ch = _parse_chain(pd.read_parquet(p).reset_index())
    exp = pd.Timestamp(f["front_expiry"])
    tab = strike_table(ch, exp)
    k0 = float(f["front_strike"])
    fwd = float(f["front_fwd"])
    t0 = year_frac(pd.Timestamp(e["entry_date"]), exp)
    if k0 not in tab.index or abs(tab.loc[k0, "bid"] - float(e["s0"])) > 0.011:
        return {**out, "status": "k0_quote_mismatch"}
    ks = tab.index.to_numpy(float)
    i0 = int(np.searchsorted(ks, k0))
    out.update(fwd=fwd, k0=k0, t0=t0, m0=float(e["m0"]))
    # the ATM strike rebuilt (reconciliation) and its two listed neighbours
    for lab, j in (("k0", i0), ("km1", i0 - 1), ("kp1", i0 + 1)):
        if j < 0 or j >= len(ks):
            out[f"{lab}_status"] = "no_neighbour"
            continue
        k = float(ks[j])
        q = tab.loc[k]
        row = f.copy()
        row["front_strike"], row["front_bid"] = k, float(q["bid"])
        row["front_mid"], row["front_ask"] = float(q["mid"]), float(q["ask"])
        res = st.build_event(row, crsp)
        out[f"{lab}_status"] = res["status"]
        out[f"{lab}_K"] = k
        out[f"{lab}_bid"], out[f"{lab}_ask"], out[f"{lab}_mid"] = q["bid"], q["ask"], q["mid"]
        out[f"{lab}_bid_sz"] = float(q["bid_sz"])
        out[f"{lab}_bid_iv"] = straddle_iv(float(q["bid"]), fwd, k, t0)
        out[f"{lab}_mid_iv"] = straddle_iv(float(q["mid"]), fwd, k, t0)
        out[f"{lab}_usd"] = _usd(res)
        out[f"{lab}_usd_mid"] = float(res["H_mid"] * res["m0"]) if res["status"] == "ok" else np.nan
        out[f"{lab}_intrinsic"] = res.get("intrinsic", np.nan)
        out[f"{lab}_hedge_pnl"] = res.get("hedge_pnl", np.nan)
    # standard monthly expiry at least 7 days after the front, ATM by the frozen atm_quote
    mons = sorted(
        x
        for x in ch["expiry"].unique()
        if x >= exp + pd.Timedelta(days=7)
        and x <= exp + pd.Timedelta(days=60)
        and 15 <= pd.Timestamp(x).day <= 21
        and pd.Timestamp(x).weekday() in (3, 4, 5)
    )
    if not mons:
        out["mon_status"] = "no_monthly"
    else:
        q = atm_quote(ch, pd.Timestamp(mons[0]), pd.Timestamp(e["entry_date"]))
        if q is None or not q.bid > 0:
            out["mon_status"] = "no_two_sided_pair"
        else:
            row = f.copy()
            row["front_expiry"], row["front_t"], row["front_fwd"] = q.expiry, q.t, q.fwd
            row["front_strike"], row["front_bid"], row["front_mid"] = q.strike, q.bid, q.mid
            row["front_ask"], row["front_iv"] = q.ask, q.iv
            res = st.build_event(row, crsp)
            out["mon_status"] = res["status"]
            out["mon_expiry"] = q.expiry
            out["mon_bid"], out["mon_ask"], out["mon_mid"] = q.bid, q.ask, q.mid
            out["mon_usd"] = _usd(res)
            out["mon_usd_mid"] = (
                float(res["H_mid"] * res["m0"]) if res["status"] == "ok" else np.nan
            )
            out["mon_days"] = res.get("hold_days", np.nan)
    # strangles at fractions of the implied move (frozen build_g, wing width scaled)
    ee = e.copy()
    for w in STRANGLE_WIDTHS:
        sm.pick_wings = lambda c, fw, im, _w=w: _pick(c, fw, im * _w)
        g = sm.build_g(ee, crsp)
        lab = f"g{int(round(w * 100)):03d}"
        out[f"{lab}_status"] = g["status"]
        if g["status"] == "ok":
            out[f"{lab}_usd"] = float(g["G"] * g["mg"])
            out[f"{lab}_usd_mid"] = float(g["G_mid"] * g["mg"])
            out[f"{lab}_mg"] = float(g["mg"])
            out[f"{lab}_sale"] = float(g["sale"])
            out[f"{lab}_mid_sale"] = float(g["mid_sale"])
            out[f"{lab}_kc"], out[f"{lab}_kp"] = g["kc"], g["kp"]
            out[f"{lab}_call_settle"] = float(g["G_call_settle"] * g["mg"])
            out[f"{lab}_put_settle"] = float(g["G_put_settle"] * g["mg"])
    sm.pick_wings = _pick
    return out


_pick = sm.pick_wings


def main() -> None:
    ev = pd.read_parquet(H_EVENTS)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    f = f.drop_duplicates(["ticker", "entry_date"])
    ev = ev.merge(f[["ticker", "entry_date", "permno"]], on=["ticker", "entry_date"])
    fi = f.set_index(["ticker", "entry_date"], drop=False)
    print(f"H events (2013-24, status ok): {len(ev)}", flush=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        ev = ev.sample(limit, random_state=0)
    crsp = st.load_crsp()
    pd.read_parquet = _cached_read  # type: ignore[assignment]
    rows, t_start = [], time.time()
    for i, (_, e) in enumerate(ev.iterrows()):
        _cache.clear()
        rows.append(build_one(e, fi.loc[(e["ticker"], e["entry_date"])], crsp))
        if (i + 1) % 500 == 0:
            el = time.time() - t_start
            print(f"  {i + 1}/{len(ev)}  {el:.0f}s  eta {el / (i + 1) * (len(ev) - i - 1):.0f}s",
                  flush=True)
    pd.read_parquet = _real_read  # type: ignore[assignment]
    d = pd.DataFrame(rows)
    d = ev.merge(d, on=["ticker", "entry_date"], how="left", suffixes=("", "_b"))
    print("funnel:", dict(Counter(d["status_b"])))
    for lab in ("k0", "km1", "kp1", "mon", "g050", "g100"):
        print(f"  {lab}:", dict(Counter(d[f"{lab}_status"].fillna("not_built"))))
    rec = (d["k0_usd"] / d["m0"] - d["H"]).abs()
    print(f"reconciliation k0 vs stored H: n={int(rec.notna().sum())}, max abs diff {rec.max():.2e}")
    out = HERE / ("arms.parquet" if not limit else "arms_smoke.parquet")
    d.to_parquet(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
