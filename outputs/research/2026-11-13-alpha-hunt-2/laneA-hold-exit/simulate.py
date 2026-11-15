"""
simulate.py
Per-event outcomes of every lane-A post-announcement variant of the hedged event hold, on the
CRSP block 2013-24, in units of m0 = 0.20 x entry forward + 15:59 entry bid premium, net at the
touch. Each variant changes only what happens at or after the reaction-session close; entry, strike,
expiry and m0 are the frozen hedged-hold ones (`outputs/research/2026-11-02-hedged-event-hold`).

Columns written (all per trade, unit m0, net at the touch unless named otherwise):

- ``H_re``      the base hold re-simulated here; must reconcile to the stored ``H``.
- ``band05/10/20``  hedge rebalanced only when the target delta drifts more than the band.
- ``freq2/5``   hedge rebalanced every 2nd / 5th session.
- ``rvdelta``   hedge ratio from a causal HAR realised-vol forecast instead of implied vol.
- ``mixdelta``  hedge ratio from the mean of implied and HAR forecast vols.
- ``oto``       close the in-the-money leg at its ask at the reaction close, hold the other leg
                hedged (``ito``: the reverse).
- ``stop05/10/20``  modelled stop: buy back at a Black-Scholes mark (reaction-close implied vol,
                plus the reaction-close relative half-spread) the first close at which the
                post-reaction hedged loss exceeds the stated share of m0. Modelled exit, not a
                quoted one.
- ``rv_f``      causal HAR realised-vol forecast (annualised, decimal) over the remaining life,
                from CRSP log returns up to and including the entry date with every earlier
                reaction day of the name set to missing. Known before the reaction close.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneA-hold-exit/simulate.py --years 2013 2018
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
from scipy.stats import norm  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    har_annual_variance,
    straddle_delta,
    straddle_value,
    year_frac,
)

HERE = Path(__file__).resolve().parent
HOLD = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEAT = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"

FEE = HEDGED.fee_per_contract_leg / 100.0
FLOOR = HEDGED.equity_cost_floor_bps / 1e4
DISP = HEDGED.disposal_bps / 1e4
BANDS = (0.05, 0.10, 0.20)  # straddle-delta units; 0.10 is about one strike-width drift on a 1-day hold
FREQS = (2, 5)  # every other session, weekly
STOPS = (0.05, 0.10, 0.20)  # post-reaction hedged loss, share of m0; H's per-event sd is about 0.15
HAR_LOOKBACK = 756  # three years of sessions, enough for har_min_rows = 500


# ── option helpers ──────────────────────────────────────────────────────────


def leg_delta(s: float, k: float, t: float, sig: float, right: str) -> float:
    if t <= 0 or sig <= 0:
        if right == "C":
            return float(s > k)
        return -float(s < k)
    sd = sig * np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * sd * sd) / sd
    return float(norm.cdf(d1) if right == "C" else norm.cdf(d1) - 1.0)


def hedge_path(
    deltas: np.ndarray, closes: np.ndarray, rets: np.ndarray, hs: np.ndarray, settle: float
) -> tuple[float, float]:
    """Hedge P&L and equity cost for a given per-close hedge holding (shares per straddle)."""
    hs = np.maximum(hs, FLOOR)
    h_prev, pnl, cost = 0.0, 0.0, 0.0
    for i in range(len(closes)):
        h = deltas[i]
        cost += abs(h - h_prev) * closes[i] * hs[i]
        pnl += h * closes[i] * rets[i]
        h_prev = h
    cost += abs(h_prev) * settle * hs[-1]
    return pnl, cost


def banded(target: np.ndarray, band: float) -> np.ndarray:
    out = np.empty_like(target)
    h = target[0]
    for i, x in enumerate(target):
        if i == 0 or abs(x - h) > band:
            h = x
        out[i] = h
    return out


def every(target: np.ndarray, f: int) -> np.ndarray:
    out = np.empty_like(target)
    h = target[0]
    for i, x in enumerate(target):
        if i % f == 0:
            h = x
        out[i] = h
    return out


# ── data ────────────────────────────────────────────────────────────────────


def load_crsp() -> dict[int, pd.DataFrame]:
    c = pd.read_parquet(CRSP)
    for col in ("prc", "ret", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c["date"] = pd.to_datetime(c["date"])
    return {int(k): g.set_index("date").sort_index() for k, g in c.groupby("permno")}


def rv_forecast(
    g: pd.DataFrame, entry: pd.Timestamp, react_days: set[pd.Timestamp], h: int
) -> float:
    hist = g.loc[:entry].tail(HAR_LOOKBACK)
    lr = np.log1p(hist["ret"].to_numpy(float))
    mask = np.array([d in react_days for d in hist.index])
    lr[mask] = np.nan
    v = har_annual_variance(lr, max(h, 1))
    return float(np.sqrt(v)) if np.isfinite(v) and v > 0 else float("nan")


# ── one event ───────────────────────────────────────────────────────────────


def simulate(r: pd.Series, g: pd.DataFrame, react_days: set[pd.Timestamp]) -> dict:
    t1, exp, k = pd.Timestamp(r["exit_date"]), pd.Timestamp(r["expiry"]), float(r["strike"])
    sess = nyse_sessions(t1, exp)
    p = g.reindex(sess)
    closes_all = p["prc"].to_numpy(float)
    settle = float(closes_all[-1])
    n = len(closes_all) - 1
    s0, m0 = float(r["s0"]), float(r["m0"])
    intr = abs(settle - k)
    disp = DISP * settle if intr > 0 else 0.0
    out: dict = {"ticker": r["ticker"], "entry_date": r["entry_date"], "n_hedge": n}
    rvf = rv_forecast(g, pd.Timestamp(r["entry_date"]), react_days, n)
    out["rv_f"] = rvf
    if n == 0:
        base = (s0 - intr - 2 * FEE - disp) / m0
        for c in (
            ["H_re", "rvdelta", "mixdelta", "oto", "ito"]
            + [f"band{int(b * 100):02d}" for b in BANDS]
            + [f"freq{f}" for f in FREQS]
            + [f"stop{int(x * 100):02d}" for x in STOPS]
        ):
            out[c] = base
        out["oto"] = out["ito"] = np.nan  # nothing to choose on an expiry-day reaction
        out["stopped"] = False
        return out
    cl, rets = closes_all[:-1], p["ret"].to_numpy(float)[1:]
    hs = ((p["ask"] - p["bid"]) / 2 / p["prc"]).to_numpy(float)[:-1]
    taus = np.array([year_frac(d, exp) for d in sess[:-1]])
    sig = float(r["sigma"])

    def book(deltas: np.ndarray) -> float:
        pnl, cost = hedge_path(deltas, cl, rets, hs, settle)
        return (s0 - intr + pnl - cost - 2 * FEE - disp) / m0

    tgt = np.array([straddle_delta(cl[i], k, taus[i], sig) for i in range(n)])
    out["H_re"] = book(tgt)
    for b in BANDS:
        out[f"band{int(b * 100):02d}"] = book(banded(tgt, b))
    for f in FREQS:
        out[f"freq{f}"] = book(every(tgt, f))
    if np.isfinite(rvf):
        out["rvdelta"] = book(np.array([straddle_delta(cl[i], k, taus[i], rvf) for i in range(n)]))
        mix = 0.5 * (sig + rvf)
        out["mixdelta"] = book(np.array([straddle_delta(cl[i], k, taus[i], mix) for i in range(n)]))
    else:
        out["rvdelta"] = out["mixdelta"] = np.nan

    # partial unwind at the reaction close: buy one leg back at its ask, hold the other hedged
    fx = float(r["fwd_x"]) if np.isfinite(r["fwd_x"]) else float(cl[0])
    itm = "C" if fx > k else "P"
    for name, close_leg in (("oto", itm), ("ito", "P" if itm == "C" else "C")):
        hold_leg = "P" if close_leg == "C" else "C"
        ask_close = float(r[f"ask_{close_leg}"])
        sig_h = float(r[f"iv_{hold_leg}"]) if np.isfinite(r[f"iv_{hold_leg}"]) else sig
        # a short leg is hedged with +delta_leg shares (short call: long stock; short put: short)
        d = np.array([leg_delta(cl[i], k, taus[i], sig_h, hold_leg) for i in range(n)])
        pnl, cost = hedge_path(d, cl, rets, hs, settle)
        pay = max(settle - k, 0.0) if hold_leg == "C" else max(k - settle, 0.0)
        dsp = DISP * settle if pay > 0 else 0.0
        out[name] = (s0 - ask_close - pay + pnl - cost - 3 * FEE - dsp) / m0

    # modelled stop: mark the short straddle at BS(sigma) each close after the reaction close
    rel_hs = float(r["rel_hs"])
    v0 = straddle_value(cl[0], k, taus[0], sig)
    for x in STOPS:
        h_prev, pnl, cost, res = 0.0, 0.0, 0.0, None
        for i in range(n):
            if i > 0:
                vi = straddle_value(cl[i], k, taus[i], sig)
                mtm = (v0 - vi) + pnl - cost
                if mtm < -x * m0:
                    cost += abs(h_prev) * cl[i] * max(hs[i], FLOOR)
                    buy = vi * (1 + rel_hs)
                    res = (s0 - buy + pnl - cost - 4 * FEE) / m0
                    break
            h = tgt[i]
            cost += abs(h - h_prev) * cl[i] * max(hs[i], FLOOR)
            pnl += h * cl[i] * rets[i]
            h_prev = h
        out[f"stop{int(x * 100):02d}"] = out["H_re"] if res is None else res
        if x == 0.10:
            out["stopped"] = res is not None
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, nargs=2, required=True)
    a = ap.parse_args(argv)
    y0, y1 = a.years
    ev = pd.read_parquet(HOLD / "events.parquet")
    ev = ev[ev["status"] == "ok"].copy()
    ev["yr"] = pd.to_datetime(ev["exit_date"]).dt.year
    ev = ev[(ev["yr"] >= y0) & (ev["yr"] <= y1)]
    st = pd.read_parquet(HERE / "state.parquet")
    f = pd.read_parquet(FEAT)[["ticker", "entry_date", "s2_iv", "permno", "exit_date"]]
    for c in ("entry_date", "exit_date"):
        f[c] = pd.to_datetime(f[c])
    react = f.dropna(subset=["permno"]).groupby("permno")["exit_date"].apply(set).to_dict()
    ev = ev.merge(st, on=["ticker", "entry_date"], how="left", validate="1:1")
    ev = ev.merge(
        f[["ticker", "entry_date", "s2_iv", "permno"]].drop_duplicates(["ticker", "entry_date"]),
        on=["ticker", "entry_date"],
        how="left",
        validate="1:1",
    )
    # hedge vol exactly as the hold study: reaction-close straddle mid IV, else s2_iv
    ev["sigma"] = ev["iv_mid"].where(np.isfinite(ev["iv_mid"]), ev["s2_iv"])
    two = ev["two_sided"].astype(bool)
    rel = (ev["exit_ask"] - ev["exit_mid"]) / ev["exit_mid"]
    med = float(rel[two].median())
    ev["rel_hs"] = rel.where(two, med)
    print(f"events {y0}-{y1}: {len(ev)}; one-sided reaction quote {int((~two).sum())} "
          f"(stop half-spread set to the block median {med:.4f})")
    crsp = load_crsp()
    t0 = time.time()
    rows, bad = [], Counter()
    for i, (_, r) in enumerate(ev.iterrows()):
        pm = int(r["permno"])
        try:
            rows.append(simulate(r, crsp[pm], react.get(r["permno"], set())))
        except Exception as e:  # counted and printed, never silently dropped
            bad[type(e).__name__] += 1
            if sum(bad.values()) <= 5:
                print(f"  fail {r['ticker']} {r['entry_date']}: {e!r}")
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{len(ev)} {time.time() - t0:.0f}s", flush=True)
    print("failures:", dict(bad))
    s = pd.DataFrame(rows)
    keep = [
        "ticker", "entry_date", "exit_date", "expiry", "m0", "s0", "mid0", "H", "B", "exit_ask",
        "exit_mid", "abs_move", "hold_days", "sigma", "s2_iv", "iv_mid", "iv_ask", "iv_bid",
        "extr_mid", "extr_ask", "intr_x", "fwd_x", "two_sided", "rel_hs", "bid_C", "ask_C",
        "bid_P", "ask_P", "iv_C", "iv_P",
    ]
    s = ev[keep].merge(s.drop(columns=[]), on=["ticker", "entry_date"], how="left")
    err = (s["H_re"] - s["H"]).abs()
    print(f"reconcile H_re vs stored H: N {err.notna().sum()}, MAE {err.mean():.2e}, "
          f"max {err.max():.2e}")
    s.to_parquet(HERE / f"sim_{y0}_{y1}.parquet")
    print(f"wrote sim_{y0}_{y1}.parquet {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
