"""
wings.py
Lane B, trial 1,821: the IM/2 strangle with each wing moved to the adjacent listed strike when
that strike's 15:59 quote is strictly narrower in volatility terms, dollar spread over Black-Scholes vega (candidates: the frozen IM/2 wing and
the listed strikes one step either side of it, call strikes kept above the forward and put
strikes below it). Hedge-held by the frozen ``build_g``.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/wings.py [LIMIT]
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import build as bd  # noqa: E402

sm, st = bd.sm, bd.st
WIDTH = 0.5


def _vega(price: float, fwd: float, k: float, t: float, right: str) -> float:
    """Black-Scholes vega per share (per unit of vol) at the leg's own mid IV, zero carry."""
    from scipy.stats import norm

    from earnings_iv_crush.research.hedged_hold import option_iv

    iv = option_iv(price, fwd, k, t, right)
    if not np.isfinite(iv) or t <= 0:
        return float("nan")
    sd = iv * np.sqrt(t)
    d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
    return float(fwd * norm.pdf(d1) * np.sqrt(t))


def _tight(cands: pd.DataFrame, base_k: float, fwd: float, t: float) -> pd.Series:
    """Narrowest quote in volatility terms (dollar spread over vega); the base wing wins ties."""
    c = cands.copy()
    c["vega"] = [
        _vega((b + a) / 2, fwd, k, t, r)
        for b, a, k, r in zip(c["bid"], c["ask"], c["strike"], c["right"])
    ]
    c["spr"] = (c["ask"] - c["bid"]) / c["vega"]
    b = c[np.isclose(c["strike"], base_k)].iloc[0]
    c = c[np.isfinite(c["spr"])]
    if c.empty or not np.isfinite(b["spr"]):
        return b
    best = c.loc[c["spr"].idxmin()]
    return best if best["spr"] < b["spr"] - 1e-12 else b


def wings_one(e: pd.Series, crsp: dict) -> dict:
    out: dict = {"ticker": e["ticker"], "entry_date": e["entry_date"]}
    exp, t0 = pd.Timestamp(e["expiry"]), pd.Timestamp(e["entry_date"])
    fwd0 = (e["m0"] - e["s0"]) / st.MARGIN_SPOT_FRAC
    im = e["mid0"] / fwd0
    c0 = sm.chain(e["ticker"], t0, exp)
    if c0 is None:
        return {**out, "wstatus": "no_entry_chain"}
    w = bd._pick(c0, fwd0, im * WIDTH)
    if w is None:
        return {**out, "wstatus": "no_wing"}
    cl0, pt0 = w
    w1 = bd._pick(c0, fwd0, im)  # the 1-IM wings, stored for vega matching of trial 1,823
    if w1 is not None:
        for tag, leg in (("oc", w1[0]), ("op", w1[1])):
            out[f"{tag}_k"], out[f"{tag}_bid"], out[f"{tag}_ask"] = (
                float(leg["strike"]),
                float(leg["bid"]),
                float(leg["ask"]),
            )
    two = c0[(c0["bid"] > 0) & (c0["ask"] > 0)]
    calls = two[(two["right"] == "C") & (two["strike"] > fwd0)].sort_values("strike")
    puts = two[(two["right"] == "P") & (two["strike"] < fwd0)].sort_values("strike")
    if not (cl0["ask"] > 0 and pt0["ask"] > 0):
        return {**out, "wstatus": "base_wing_one_sided"}

    def near(tab: pd.DataFrame, k: float) -> pd.DataFrame:
        ks = tab["strike"].to_numpy(float)
        i = int(np.argmin(np.abs(ks - k)))
        return tab.iloc[max(0, i - 1) : i + 2]

    cc = near(calls, float(cl0["strike"]))
    pp = near(puts, float(pt0["strike"]))
    if not (np.isclose(cc["strike"], cl0["strike"]).any() and np.isclose(pp["strike"], pt0["strike"]).any()):
        return {**out, "wstatus": "base_wing_not_two_sided"}
    t_e = (exp - t0).days / 365.0
    cl1 = _tight(cc, float(cl0["strike"]), fwd0, t_e)
    pt1 = _tight(pp, float(pt0["strike"]), fwd0, t_e)
    out["wstatus"] = "ok"
    for tag, leg in (("bc", cl0), ("bp", pt0), ("tc", cl1), ("tp", pt1)):
        out[f"{tag}_k"], out[f"{tag}_bid"], out[f"{tag}_ask"] = (
            float(leg["strike"]),
            float(leg["bid"]),
            float(leg["ask"]),
        )
    out["fwd"], out["t0"] = fwd0, (exp - t0).days / 365.0
    sm.pick_wings = lambda c, fw, i, _a=cl1, _b=pt1: (_a, _b)
    g = sm.build_g(e, crsp)
    sm.pick_wings = bd._pick
    out["tw_status"] = g["status"]
    if g["status"] == "ok":
        out["tw_usd"] = float(g["G"] * g["mg"])
        out["tw_usd_mid"] = float(g["G_mid"] * g["mg"])
        out["tw_mg"] = float(g["mg"])
        out["tw_sale"] = float(g["sale"])
    return out


def main() -> None:
    ev = pd.read_parquet(bd.H_EVENTS)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    ev = ev.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        ev = ev.sample(limit, random_state=0)
    print(f"events: {len(ev)}", flush=True)
    crsp = st.load_crsp()
    pd.read_parquet = bd._cached_read  # type: ignore[assignment]
    rows, t_start = [], time.time()
    for i, (_, e) in enumerate(ev.iterrows()):
        bd._cache.clear()
        rows.append(wings_one(e, crsp))
        if (i + 1) % 1000 == 0:
            el = time.time() - t_start
            print(f"  {i + 1}/{len(ev)}  {el:.0f}s  eta {el / (i + 1) * (len(ev) - i - 1):.0f}s",
                  flush=True)
    pd.read_parquet = bd._real_read  # type: ignore[assignment]
    d = pd.DataFrame(rows)
    print("funnel:", dict(Counter(d["wstatus"])))
    print("  tw:", dict(Counter(d.get("tw_status", pd.Series()).fillna("not_built"))))
    out = HERE / ("wings.parquet" if not limit else "wings_smoke.parquet")
    d.to_parquet(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
