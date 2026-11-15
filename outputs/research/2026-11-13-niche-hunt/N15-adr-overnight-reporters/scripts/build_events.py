"""
build_events.py
Build the per-event table for lane N15 from the cached 15:59 OPRA chains: every pair of
consecutive NYSE sessions with a chain on both, the front ATM straddle's touch at entry, the same
contract's touch at exit, the parity forwards, implied vols and the net short-straddle return B.

The specification is the pre-registration in ``diagnosis.log`` entry [2]. One block per call so
the held-out block is built only by the held-out scorer.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N15-adr-overnight-reporters/scripts/build_events.py --year 2025
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

LANE = Path(__file__).resolve().parents[1]
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
FEE = 0.65 / 100.0  # USD per share per leg: config HEDGED.fee_per_contract_leg over 100 shares
MARGIN_SPOT_FRAC = 0.20  # the project's Reg-T approximation, m0 = 0.20 fwd + sale price

# ── groups, fixed in diagnosis.log [2] before any outcome ────────────────────
OVS = set("DB ALC FER CCEP FLUT".split())
FUS = set("CHKP CYBR GRAB CPNG ICLR AER NXPI FERG CRH".split())
CAN = set("AEM B BAM BCE BMO BN BNS CCJ CM CNI CNQ CP CVE EMA ENB FNV FTS GFL GIB IMO".split())


def group(t: str) -> str:
    return "OVS" if t in OVS else "FUS" if t in FUS else "CAN" if t in CAN else "US"


def pairs(year: int) -> pd.DataFrame:
    by: dict[str, set[pd.Timestamp]] = defaultdict(set)
    for f in os.listdir(CHAINS):
        if not f.endswith(".parquet"):
            continue
        t, d = f[:-8].rsplit("_", 1)
        by[t].add(pd.Timestamp(d))
    sess = nyse_sessions(pd.Timestamp(f"{year - 1}-12-01"), pd.Timestamp(f"{year + 1}-01-31"))
    nxt = {sess[i]: sess[i + 1] for i in range(len(sess) - 1)}
    rows = [
        (t, d, nxt[d])
        for t, ds in by.items()
        for d in sorted(ds)
        if d.year == year and d in nxt and nxt[d] in ds
    ]
    e = pd.DataFrame(rows, columns=["ticker", "d1", "d2"])
    e["grp"] = e["ticker"].map(group)
    return e


def _raw_leg(raw: pd.DataFrame, strike: float, expiry: pd.Timestamp, right: str) -> tuple:
    """Last 15:59 record of one leg read raw, so a zero bid is kept and only the ask matters."""
    d = raw[(raw["expiry"] == expiry) & np.isclose(raw["strike"], strike) & (raw["right"] == right)]
    if d.empty:
        return np.nan, np.nan
    r = d.sort_values("ts_recv").iloc[-1]
    return float(r["bid_px_00"]), float(r["ask_px_00"])


def _raw(df: pd.DataFrame) -> pd.DataFrame:
    d = df.reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    return d


def _parity_fwd(chain: pd.DataFrame, expiry: pd.Timestamp) -> float:
    d = chain[chain["expiry"] == expiry]
    w = d.pivot_table(index="strike", columns="right", values="mid", aggfunc="last").dropna()
    if w.empty or not {"C", "P"} <= set(w.columns):
        return float("nan")
    k = float((w["C"] - w["P"]).abs().idxmin())
    return float(k + w.loc[k, "C"] - w.loc[k, "P"])


def one(t: str, d1: pd.Timestamp, d2: pd.Timestamp) -> dict:
    raw1 = pd.read_parquet(CHAINS / f"{t}_{d1.date()}.parquet")
    c1 = _parse_chain(raw1)
    if c1 is None:
        return {"status": "entry_chain_empty"}
    c1 = c1.reset_index(drop=True)
    exps = sorted(pd.Timestamp(x) for x in c1["expiry"].unique())
    e1 = next((e for e in exps if e.normalize() >= d2.normalize()), None)
    if e1 is None:
        return {"status": "no_front_expiry"}
    q = hh.atm_quote(c1, e1, d1)
    if q is None or not q.bid > 0:
        return {"status": "no_entry_bid"}
    raw2 = _raw(pd.read_parquet(CHAINS / f"{t}_{d2.date()}.parquet"))
    bc, ac = _raw_leg(raw2, q.strike, e1, "C")
    bp, ap = _raw_leg(raw2, q.strike, e1, "P")
    c2 = _parse_chain(pd.read_parquet(CHAINS / f"{t}_{d2.date()}.parquet"))
    if not (np.isfinite(ac) and np.isfinite(ap)):
        # Attrition variant (diagnosis.log [5]): value an unquoted leg at its intrinsic on the
        # exit parity forward plus one nickel tick, as the ask a taker would face at best.
        fx = _parity_fwd(c2, e1) if c2 is not None else float("nan")
        if not np.isfinite(fx) and c2 is not None:
            other = sorted(pd.Timestamp(x) for x in c2["expiry"].unique() if pd.Timestamp(x) > e1)
            fx = _parity_fwd(c2, other[0]) if other else float("nan")
        fill = np.nan
        if np.isfinite(fx):
            ac_f = ac if np.isfinite(ac) else max(fx - q.strike, 0.0) + 0.05
            ap_f = ap if np.isfinite(ap) else max(q.strike - fx, 0.0) + 0.05
            m0f = MARGIN_SPOT_FRAC * q.fwd + q.bid
            fill = (q.bid - ac_f - ap_f - 4 * FEE) / m0f
        return {
            "status": "no_exit_leg",
            "expiry": e1,
            "iv1": q.iv,
            "im": q.mid / q.fwd,
            "tenor_days": int((e1 - d2).days),
            "hs_share": (q.ask - q.bid) / (2 * q.mid),
            "rm": abs(fx / q.fwd - 1.0) if np.isfinite(fx) else np.nan,
            "B_fill": fill,
        }
    fwd2 = _parity_fwd(c2, e1) if c2 is not None else float("nan")
    if not np.isfinite(fwd2) and c2 is not None:
        other = sorted(pd.Timestamp(x) for x in c2["expiry"].unique() if pd.Timestamp(x) > e1)
        fwd2 = _parity_fwd(c2, other[0]) if other else float("nan")
    two_sided = min(bc, bp) > 0 and min(ac, ap) > 0
    mid2 = (bc + ac + bp + ap) / 2 if two_sided else np.nan
    t2 = hh.year_frac(d2, e1)
    iv2 = (
        hh.straddle_iv(mid2, fwd2, q.strike, t2)
        if (two_sided and t2 > 0 and np.isfinite(fwd2))
        else np.nan
    )
    ask2 = ac + ap
    b_ok = ac > 0 and ap > 0
    m0 = MARGIN_SPOT_FRAC * q.fwd + q.bid
    return {
        "status": "ok",
        "expiry": e1,
        "tenor_days": int((e1 - d2).days),
        "strike": q.strike,
        "fwd1": q.fwd,
        "bid1": q.bid,
        "mid1": q.mid,
        "ask1": q.ask,
        "iv1": q.iv,
        "hs_share": (q.ask - q.bid) / (2 * q.mid),
        "im": q.mid / q.fwd,
        "fwd2": fwd2,
        "ask2": ask2,
        "mid2": mid2,
        "iv2": iv2,
        "b_defined": bool(b_ok),
        "m0": m0,
        "B": (q.bid - ask2 - 4 * FEE) / m0 if b_ok else np.nan,
        "B_fill": (q.bid - ask2 - 4 * FEE) / m0 if b_ok else np.nan,
        "B_mid": (q.mid - mid2) / m0 if two_sided else np.nan,
        "B_prem": (q.bid - ask2 - 4 * FEE) / q.bid if b_ok else np.nan,
        "rm": abs(fwd2 / q.fwd - 1.0) if np.isfinite(fwd2) else np.nan,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()
    e = pairs(a.year)
    print(f"pairs {a.year}: {len(e)}; by group {dict(Counter(e['grp']))}")
    out = []
    for i, r in enumerate(e.itertuples(index=False)):
        try:
            rec = one(r.ticker, r.d1, r.d2)
        except Exception as exc:  # recorded per event and counted in the funnel
            rec = {"status": f"error:{type(exc).__name__}"}
        out.append({"ticker": r.ticker, "d1": r.d1, "d2": r.d2, "grp": r.grp, **rec})
        if (i + 1) % 500 == 0:
            print(f"  built {i + 1}/{len(e)}", flush=True)
    d = pd.DataFrame(out)
    print("funnel:")
    print(d.groupby(["grp", "status"]).size().unstack(fill_value=0).to_string())
    p = LANE / "cache" / f"events_{a.year}.parquet"
    d.to_parquet(p)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
