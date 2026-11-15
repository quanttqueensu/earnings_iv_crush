"""
b8_strangle.py
L2 idea B8: set the strangle's width from the 1,623 move forecast and value it with the netted
hedged strangle. Declared in diagnosis.log entry [17].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b8_strangle.py --forecast
    python outputs/research/2026-11-14-slate-tests/L2-execution/b8_strangle.py --build
    python outputs/research/2026-11-14-slate-tests/L2-execution/b8_strangle.py --block 2016-18

``--forecast`` runs the closed 1,623 study's walk-forward (imported) and caches yhat_m0, yhat_m1.
``--build`` picks both strangles on every hedged CRSP event's 15:59 entry chain and values them on
the recorded stock path. ``--block`` scores 2016-18 or 2019-24.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pickle
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2lib as L  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED_NET  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

MF = L.ROOT / "research" / "selection" / "2026-11-12-move-forecast-and-sizing" / "study.py"
CHAINS = L.ROOT / "data" / "cache" / "backfill_chains"
FC = L.HERE / "_cache" / "b8_forecast.parquet"
BUILT = L.HERE / "_cache" / "b8_built.parquet"
HALF = 0.5  # the IM/2 construction of 1,815 and 1,826
BLOCKS8 = {"2016-18": (2016, 2018), "2019-24": (2019, 2024)}


def forecast() -> None:
    spec = importlib.util.spec_from_file_location("move_forecast_study", MF)
    assert spec is not None and spec.loader is not None
    mf = importlib.util.module_from_spec(spec)
    sys.modules["move_forecast_study"] = mf
    spec.loader.exec_module(mf)
    ev = mf.add_history(mf.attach_chars(mf.load_events()))
    ev, last = mf.walk_forward(ev)
    out = ev[["ticker", "entry_date", "im", "yhat_m0", "yhat_m1", "m1_defined"]].copy()
    print(f"forecast rows {len(out)}; m1 defined OOS {int(out['yhat_m1'].notna().sum())}")
    tmp = FC.with_suffix(".tmp.parquet")
    out.to_parquet(tmp)
    tmp.replace(FC)


def _legs(ch: pd.DataFrame, expiry: pd.Timestamp, target: float, right: str) -> dict | None:
    d = ch[(ch["expiry"] == expiry) & (ch["right"] == right) & (ch["bid_px_00"] > 0)]
    if d.empty:
        return None
    i = int(np.argmin(np.abs(d["strike"].to_numpy(float) - target)))
    r = d.iloc[i]
    return {"k": float(r["strike"]), "bid": float(r["bid_px_00"]), "mid": float(r["mid"])}


def strangle(kw: dict, ch: pd.DataFrame, expiry: pd.Timestamp, fwd: float, w: float) -> dict:
    c = _legs(ch, expiry, fwd * np.exp(w), "C")
    p = _legs(ch, expiry, fwd * np.exp(-w), "P")
    if c is None or p is None:
        return {"status": "no_leg"}
    if p["k"] > c["k"]:
        return {"status": "crossed_strikes"}
    sig = np.asarray(kw["sigmas"], float)
    r = hh.hedged_short_strangle(
        sale_price=c["bid"] + p["bid"],
        sale_mid=c["mid"] + p["mid"],
        call_strike=c["k"],
        put_strike=p["k"],
        fwd=fwd,
        closes=kw["closes"],
        rets=kw["rets"],
        taus=kw["taus"],
        call_sigmas=sig,
        put_sigmas=sig,
        half_spreads=kw["half_spreads"],
        settle_close=kw["settle_close"],
        cfg=HEDGED_NET,
    )
    return {
        "status": "ok",
        "kc": c["k"],
        "kp": p["k"],
        "sale": c["bid"] + p["bid"],
        "net": r.net_pnl,
        "premium": c["bid"] + p["bid"],
        "settlement": r.settlement,
        "hedge": r.hedge_pnl,
        "equity_cost": r.equity_cost,
    }


_W: dict[str, Any] = {}


def _init() -> None:
    _W["paths"] = L.load_paths()


def _one(job: dict) -> dict:
    key = (job["ticker"], pd.Timestamp(job["entry_date"]))
    out: dict = {"ticker": key[0], "entry_date": key[1]}
    kw = _W["paths"][key]["kw"]
    if kw is None:
        return {**out, "b8_status": "settles_on_reaction"}
    p = CHAINS / f"{key[0]}_{key[1].date()}.parquet"
    ch = _parse_chain(pd.read_parquet(p).reset_index()) if p.exists() else None
    if ch is None:
        return {**out, "b8_status": "no_entry_chain"}
    # reconciliation: equal strikes and the straddle's sale give the straddle on H_net
    kwn = {**kw, "cfg": HEDGED_NET, "financing": None, "call_assigned_at": None}
    st = hh.hedged_short_straddle(**kwn)
    eq = hh.hedged_short_strangle(
        sale_price=kw["sale_price"],
        sale_mid=kw["sale_mid"],
        call_strike=kw["strike"],
        put_strike=kw["strike"],
        fwd=kw["fwd"],
        closes=kw["closes"],
        rets=kw["rets"],
        taus=kw["taus"],
        call_sigmas=kw["sigmas"],
        put_sigmas=kw["sigmas"],
        half_spreads=kw["half_spreads"],
        settle_close=kw["settle_close"],
        cfg=HEDGED_NET,
    )
    out["recon_gap_usd"] = abs(st.net_pnl - eq.net_pnl)
    out["straddle_net"] = st.net_pnl
    w0 = HALF * job["im"]
    w1 = HALF * job["im"] * float(np.exp(job["yhat_m1"] - job["yhat_m0"]))
    exp = pd.Timestamp(job["expiry"])
    a0 = strangle(kw, ch, exp, kw["fwd"], w0)
    a1 = strangle(kw, ch, exp, kw["fwd"], w1)
    if a0["status"] != "ok" or a1["status"] != "ok":
        return {**out, "b8_status": f"w0_{a0['status']}_w1_{a1['status']}"}
    out.update({f"s0_{k}": v for k, v in a0.items() if k != "status"})
    out.update({f"s1_{k}": v for k, v in a1.items() if k != "status"})
    out.update(b8_status="ok", w0=w0, w1=w1)
    return out


def build(workers: int) -> None:
    d = L.load_base()
    d = d[(d["src"] == "crsp") & (d["h_status"] == "ok") & (d["year"] >= 2016)]
    f = pd.read_parquet(FC)
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    m = d[["ticker", "entry_date", "expiry", "m0", "year"]].merge(
        f, on=["ticker", "entry_date"], how="left", validate="one_to_one"
    )
    miss = m["yhat_m1"].isna() | m["yhat_m0"].isna()
    print(f"events 2016-24 {len(m)}; no out-of-sample M1 forecast {int(miss.sum())}")
    jobs = [dict(r) for _, r in m[~miss].iterrows()]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        res = list(ex.map(_one, jobs, chunksize=20))
    b = pd.DataFrame(res).merge(
        m[["ticker", "entry_date", "m0", "year"]], on=["ticker", "entry_date"]
    )
    print("funnel:", dict(Counter(b["b8_status"]).most_common()))
    print(f"straddle reconciliation, max gap {b['recon_gap_usd'].max():.2e} USD per share")
    tmp = BUILT.with_suffix(".tmp.parquet")
    b.to_parquet(tmp)
    tmp.replace(BUILT)
    _ = pickle


def score(block: str) -> None:
    b = pd.read_parquet(BUILT)
    base = L.load_base()[["ticker", "entry_date", "exit_date", "H_net"]]
    b = b.merge(base, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    lo, hi = BLOCKS8[block]
    b = b[(b["year"] >= lo) & (b["year"] <= hi)]
    funnel = dict(Counter(b["b8_status"]).most_common())
    ok = b[b["b8_status"] == "ok"].reset_index(drop=True)
    gap = (ok["straddle_net"] / ok["m0"] - ok["H_net"]).abs().max()
    if gap > 1e-9:
        raise AssertionError(f"straddle on recorded path misses H_net by {gap:.2e}")
    m0, dates = ok["m0"], ok["exit_date"]
    s0, s1 = ok["s0_net"] / m0, ok["s1_net"] / m0
    res: dict = {"block": block, "funnel": funnel, "n": len(ok)}
    res["primary_forecast_minus_im2"] = L.iv_dict(L.mean_ci(s1 - s0, dates))
    res["forecast_minus_straddle"] = L.iv_dict(L.mean_ci(s1 - ok["H_net"], dates))
    res["im2_minus_straddle"] = L.iv_dict(L.mean_ci(s0 - ok["H_net"], dates))
    res["level_straddle_H_net"] = L.iv_dict(L.mean_ci(ok["H_net"], dates))
    res["level_forecast_strangle"] = L.iv_dict(L.mean_ci(s1, dates))
    res["width_ratio_median"] = float((ok["w1"] / ok["w0"]).median())
    res["share_different_strikes"] = float(
        ((ok["s1_kc"] != ok["s0_kc"]) | (ok["s1_kp"] != ok["s0_kp"])).mean()
    )
    res["decomposition_forecast_minus_im2"] = {
        c: float(
            ((ok[f"s1_{c}"] - ok[f"s0_{c}"]) / m0).mean()
            * 100
            * (1 if c in ("premium", "hedge") else -1)
        )
        for c in ("premium", "settlement", "hedge", "equity_cost")
    }
    for k, v in res.items():
        print(k, v)
    L.write_json(L.HERE / f"b8_{block}.json", res)
    L.record_view(block, "execution_strangle_width_forecast", "L2-execution b8_strangle.py")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--forecast", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--block", choices=tuple(BLOCKS8))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    if a.forecast:
        forecast()
    if a.build:
        build(a.workers)
    if a.block:
        score(a.block)


if __name__ == "__main__":
    main()
