"""
b2_mvdelta.py
L2 idea B2: Hull and White (2017) minimum-variance delta at the first hedging close of the hedged
hold. Declared in diagnosis.log entry [10].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b2_mvdelta.py --fit
    python outputs/research/2026-11-14-slate-tests/L2-execution/b2_mvdelta.py --block 2013-18

``--fit`` regresses, on the 2013-18 events' entry and reaction-day 15:59 chains (the only
same-contract price pairs on disk), dV - delta dF on (vega / sqrt(T)) (dF / F) (1, delta,
delta^2) for calls and puts separately, and writes ``b2_coefficients.json``. ``--block`` applies
the fitted adjustment at the reaction close through ``hedge_ratios`` and scores the change.

References
----------
Hull, J. and White, A. (2017) Optimal delta hedging for options. Journal of Banking and Finance
82, 180-190.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

import l2lib as L  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

CHAINS = L.ROOT / "data" / "cache" / "backfill_chains"
COEF = L.HERE / "b2_coefficients.json"
DELTA_RANGE = (0.05, 0.95)  # HW's moneyness range for the fit
MIN_T_DAYS = 14  # HW drop options with under 14 days to expiry
STRIKE_BAND = 0.30  # strikes within 30% of the forward, to bound the IV solves


def _chain(ticker: str, day: pd.Timestamp) -> pd.DataFrame | None:
    p = CHAINS / f"{ticker}_{pd.Timestamp(day).date()}.parquet"
    if not p.exists():
        return None
    return _parse_chain(pd.read_parquet(p).reset_index())


def _pairs(job: tuple[str, pd.Timestamp, pd.Timestamp, pd.Timestamp]) -> list[tuple]:
    """(right, y, x0) rows of one event: the regression inputs of every eligible option."""
    ticker, entry, react, front = job
    c0, c1 = _chain(ticker, entry), _chain(ticker, react)
    if c0 is None or c1 is None:
        return []
    out = []
    for e in sorted(c0["expiry"].unique()):
        if e <= front or (e - entry).days < MIN_T_DAYS:
            continue
        q0, q1 = hh.atm_quote(c0, e, entry), hh.atm_quote(c1, e, react)
        if q0 is None or q1 is None:
            continue
        f0, f1, t = q0.fwd, q1.fwd, hh.year_frac(entry, e)
        a = c0[(c0["expiry"] == e) & ((c0["strike"] / f0 - 1).abs() <= STRIKE_BAND)]
        b = c1[c1["expiry"] == e].set_index(["strike", "right"])["mid"]
        for k, r, v0 in zip(a["strike"], a["right"], a["mid"], strict=True):
            v1 = b.get((k, r))
            if v1 is None or not np.isfinite(v1):
                continue
            iv = hh.option_iv(float(v0), f0, float(k), t, str(r))
            if not np.isfinite(iv):
                continue
            sd = iv * np.sqrt(t)
            d1 = (np.log(f0 / k) + 0.5 * sd * sd) / sd
            dc = float(norm.cdf(d1))
            delta = dc if r == "C" else dc - 1.0
            if not DELTA_RANGE[0] <= abs(delta) <= DELTA_RANGE[1]:
                continue
            vega = f0 * float(norm.pdf(d1)) * np.sqrt(t)
            df = f1 - f0
            out.append((r, float(v1) - float(v0) - delta * df, vega / np.sqrt(t) * df / f0, delta))
    return out


def fit(workers: int) -> None:
    d = L.load_base()
    d = d[(d["block"] == "2013-18") & (d["h_status"] == "ok")]
    jobs = list(zip(d["ticker"], d["entry_date"], d["exit_date"], d["expiry"], strict=True))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_pairs, jobs, chunksize=20))
    n_ev = sum(1 for r in res if r)
    rows = [x for r in res for x in r]
    print(f"events with pairs {n_ev} of {len(jobs)}; option pairs {len(rows)}")
    out: dict = {"n_events": n_ev, "fit_block": "2013-18"}
    for right in "CP":
        z = np.array([(y, x, dl) for r, y, x, dl in rows if r == right])
        y, x, dl = z[:, 0], z[:, 1], z[:, 2]
        xm = np.column_stack([x, x * dl, x * dl * dl])
        coef, *_ = np.linalg.lstsq(xm, y, rcond=None)
        resid = y - xm @ coef
        sse_bs, sse_mv = float(np.sum(y * y)), float(np.sum(resid * resid))
        out[right] = {
            "a": float(coef[0]),
            "b": float(coef[1]),
            "c": float(coef[2]),
            "n_options": int(y.size),
            "gain_in_sse": 1.0 - sse_mv / sse_bs,
        }
        print(right, out[right])
    L.write_json(COEF, out)


def _g(cf: dict, delta: float) -> float:
    return cf["a"] + cf["b"] * delta + cf["c"] * delta * delta


def adjusted_ratios(kw: dict, coef: dict) -> tuple[np.ndarray, float]:
    """Black-Scholes hedge sequence with the Hull-White adjustment added at close 0."""
    h, _ = L.hedge_sequence(kw)
    s, k = float(kw["closes"][0]), float(kw["strike"])
    tau, sig = float(kw["taus"][0]), float(kw["sigmas"][0])
    if tau <= 0 or sig <= 0:
        return h, 0.0
    sd = sig * np.sqrt(tau)
    d1 = (np.log(s / k) + 0.5 * sd * sd) / sd
    dc = float(norm.cdf(d1))
    vega = s * float(norm.pdf(d1)) * np.sqrt(tau)
    call_live = kw.get("call_assigned_at") != 0
    put_live = kw.get("put_assigned_at") != 0
    g = (_g(coef["C"], dc) if call_live else 0.0) + (_g(coef["P"], dc - 1.0) if put_live else 0.0)
    adj = vega / (s * np.sqrt(tau)) * g
    h = h.copy()
    h[0] += adj
    return h, adj


def score(block: str) -> None:
    coef = json.loads(COEF.read_text())
    d = L.load_base()
    d = d[(d["block"] == block) & (d["h_status"] == "ok")].reset_index(drop=True)
    paths = L.load_paths()
    new, adjs, comp = [], [], []
    for _, r in d.iterrows():
        kw = paths[(r["ticker"], r["entry_date"])]["kw"]
        if kw is None:
            new.append(r["H_corr"])
            adjs.append(0.0)
            comp.append((0.0, 0.0))
            continue
        h0, _ = L.hedge_sequence(kw)
        same = hh.hedged_short_straddle(**kw, hedge_ratios=h0).net_pnl / r["m0"]
        if abs(same - r["H_corr"]) > 1e-12:
            raise AssertionError("hedge_ratios with the BS sequence does not reproduce H_corr")
        h, adj = adjusted_ratios(kw, coef)
        res = hh.hedged_short_straddle(**kw, hedge_ratios=h)
        new.append(res.net_pnl / r["m0"])
        adjs.append(adj)
        comp.append((res.hedge_pnl / r["m0"] - r["c_hedge"], -res.equity_cost / r["m0"] - r["c_equity_cost"]))
    d["H_B2"], d["adj"] = new, adjs
    c = np.array(comp)
    dates = d["exit_date"]
    dh = d["H_B2"] - d["H_corr"]
    hedged = d["n_hedge"] > 0
    out = {
        "block": block,
        "n": len(d),
        "n_hedged": int(hedged.sum()),
        "coefficients": coef,
        "mean_adjustment_shares": float(d.loc[hedged, "adj"].mean()),
        "mean_abs_adjustment_shares": float(d.loc[hedged, "adj"].abs().mean()),
        "var_ratio": L.iv_dict(L.var_ratio_ci(d["H_B2"], d["H_corr"], dates), 1.0),
        "paired_mean": L.iv_dict(L.mean_ci(dh, dates)),
        "sd_H_corr": float(d["H_corr"].std() * 100),
        "sd_H_B2": float(d["H_B2"].std() * 100),
        "decomposition_mean": {
            "hedge": float(c[:, 0].mean() * 100),
            "equity_cost": float(c[:, 1].mean() * 100),
        },
    }
    for k, v in out.items():
        print(k, v)
    L.write_json(L.HERE / f"b2_{block}.json", out)
    L.record_view(block, "execution_min_variance_delta", "L2-execution b2_mvdelta.py")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--block", choices=L.BLOCKS)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    if a.fit:
        fit(a.workers)
    if a.block:
        score(a.block)


if __name__ == "__main__":
    main()
