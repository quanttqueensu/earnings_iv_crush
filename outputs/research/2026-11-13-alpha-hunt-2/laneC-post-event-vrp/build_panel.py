"""
build_panel.py
Lane C panel: per-event decomposition of the hedged event hold into the jump part and the
post-reaction diffusive part, plus volatility forecasts known at the reaction-session close.

Every feature is computable at the reaction session's 15:59-16:00 close (decision time of a
hold-or-close rule): the reaction-close straddle mid of the held contract, CRSP daily returns up to
and including the reaction session, and prior announcement dates. Outcomes use the stored stock
paths from the reaction close to expiry.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/build_panel.py

References
----------
Corsi, F. (2009) A simple approximate long-memory model of realized volatility. JFEC 7(2).
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. (2019) Option pricing of earnings
announcement risks. RFS 32(2).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLD = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
FEE = HEDGED.fee_per_contract_leg / 100.0
RV_WINDOW = 22  # trailing realised-vol window, trading days (one month, the HAR monthly lag)


# ── inputs ──────────────────────────────────────────────────────────────────


def load_crsp() -> dict[int, pd.DataFrame]:
    c = pd.read_parquet(CRSP)
    for col in ("prc", "ret", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c["date"] = pd.to_datetime(c["date"])
    return {int(k): g.set_index("date").sort_index() for k, g in c.groupby("permno")}


def load_events() -> pd.DataFrame:
    b = pd.read_parquet(HOLD / "events.parquet").assign(universe="broad")
    m = pd.read_parquet(HOLD / "events_megacap.parquet").assign(universe="megacap")
    d = pd.concat([b, m], ignore_index=True)
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c])
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno", "jsplit_sd2",
                                           "jsplit_valid", "front_iv", "front_t", "s2_iv"])
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = d.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                how="left")
    return d


# ── per-event features ──────────────────────────────────────────────────────


def har_pair(r_hist: np.ndarray, r1: float, h: int) -> tuple[float, float]:
    """HAR forecast of annualised variance over h days: ex the reaction day, and with it."""
    rv = r_hist ** 2
    coef, n = hh.har_fit(rv, HEDGED.har_lags)
    if n < HEDGED.har_min_rows or not np.isfinite(coef).all():
        return float("nan"), float("nan")
    ex = hh.har_forecast_sum(rv, coef, h, HEDGED.har_lags) / h * 252.0
    inc = hh.har_forecast_sum(np.append(rv, r1 ** 2), coef, h, HEDGED.har_lags) / h * 252.0
    return ex, inc


def one(row: pd.Series, crsp: dict[int, pd.DataFrame], excl: set) -> dict:
    out: dict = {}
    if not np.isfinite(row["permno"]) or int(row["permno"]) not in crsp:
        return {"lc_status": "no_permno"}
    g_all = crsp[int(row["permno"])]
    t1, exp = row["exit_date"], row["expiry"]
    sess = nyse_sessions(t1, exp)
    g = g_all.reindex(sess)
    if g["prc"].isna().any() or g["ret"].iloc[1:].isna().any():
        return {"lc_status": "missing_path"}
    spot1 = float(g["prc"].iloc[0])
    h = len(g) - 1
    rem = np.log1p(g["ret"].to_numpy(float)[1:])
    out["rv_rem"] = float(np.sum(rem ** 2) / h * 252.0)
    out["spot1"] = spot1
    out["moneyness1"] = float(np.log(spot1 / row["strike"]))
    t = hh.year_frac(t1, exp)
    out["iv_post"] = hh.straddle_iv(float(row["exit_mid"]), spot1, float(row["strike"]), t)
    out["vega1"] = (hh.straddle_vega(spot1, float(row["strike"]), t, out["iv_post"])
                    if np.isfinite(out["iv_post"]) else np.nan)
    out["extrinsic1"] = float(row["exit_mid"]) - abs(spot1 - float(row["strike"]))
    # history strictly before the reaction session, prior announcement days blanked
    hist = g_all[g_all.index < t1]
    r_hist = np.log1p(hist["ret"].to_numpy(float))
    r_hist[np.isin(hist.index.normalize(), list(excl))] = np.nan
    r1 = float(np.log1p(g_all.loc[t1, "ret"])) if t1 in g_all.index else np.nan
    out["r1"] = r1
    out["har_ex"], out["har_in"] = har_pair(r_hist, r1, h) if np.isfinite(r1) else (np.nan,) * 2
    tail = r_hist[np.isfinite(r_hist)][-RV_WINDOW:]
    out["rv22"] = float(np.mean(tail ** 2) * 252.0) if tail.size == RV_WINDOW else np.nan
    out["lc_status"] = "ok" if np.isfinite(out["iv_post"]) else "iv_not_bracketed"
    return out


def main() -> None:
    d = load_events()
    print(f"events loaded: {len(d)} ({d['universe'].value_counts().to_dict()})")
    print("upstream status:", dict(Counter(d["status"])))
    d = d[d["status"] == "ok"].copy()
    d["n_hedge"] = d["n_hedge"].astype(int)
    print(f"  status ok: {len(d)}")
    print(f"  of which expiry on the reaction session (no decision left): {(d['n_hedge'] == 0).sum()}")
    d = d[d["n_hedge"] >= 1]
    two = d["exit_mid"].notna()
    print(f"  n_hedge >= 1: {len(d)}; two-sided reaction quote: {int(two.sum())}; "
          f"one-sided: {int((~two).sum())}")
    print(f"    H mean two-sided {d.loc[two, 'H'].mean():+.4f}, one-sided {d.loc[~two, 'H'].mean():+.4f}"
          f"; abs_move {d.loc[two, 'abs_move'].mean():.4f} vs {d.loc[~two, 'abs_move'].mean():.4f}")
    excl_by = (pd.read_parquet(EVENTS, columns=["ticker", "exit_date"])
               .assign(exit_date=lambda x: pd.to_datetime(x["exit_date"]).dt.normalize())
               .groupby("ticker")["exit_date"].apply(set).to_dict())
    crsp = load_crsp()
    rows = []
    dd = d[two].reset_index(drop=True)
    for i, r in dd.iterrows():
        excl = {x for x in excl_by.get(r["ticker"], set()) if x < r["exit_date"]}
        rows.append(one(r, crsp, excl))
        if (i + 1) % 1000 == 0:
            print(f"  built {i + 1}/{len(dd)}", flush=True)
    p = pd.concat([dd, pd.DataFrame(rows)], axis=1)

    # ── decomposition, every term per unit of m0 ──
    p["J"] = (p["s0"] - p["exit_mid"]) / p["m0"]  # jump part: bid sold vs reaction-close mid
    p["D_mid"] = (p["exit_mid"] - p["intrinsic"] + p["hedge_pnl"]) / p["m0"]
    p["D_net"] = p["D_mid"] - (p["equity_cost"] + p["disposal"]) / p["m0"]
    p["recon"] = p["J"] + p["D_net"] - 2 * FEE / p["m0"] - p["H"]
    p["G"] = p["H"] - p["B"]  # hold minus buy-back, net at the touch
    p["exit_bid"] = 2 * p["exit_mid"] - p["exit_ask"]
    p["exit_half"] = (p["exit_ask"] - p["exit_mid"]) / p["m0"]
    p["D_vega"] = (p["exit_mid"] - p["intrinsic"] + p["hedge_pnl"]) / p["vega1"]  # vol points
    m_post = 0.20 * p["spot1"] + p["exit_bid"]
    p["A"] = (p["exit_bid"] - p["intrinsic"] + p["hedge_pnl"] - p["equity_cost"] - p["disposal"]
              - 2 * FEE) / m_post  # fresh sale of one more unit at the reaction-close bid
    fwd0 = (p["m0"] - p["s0"]) / 0.20  # m0 = 0.20 x entry forward + bid premium
    p["implied_move"] = p["mid0"] / fwd0  # entry straddle mid over forward, a move proxy
    p["gap_ratio"] = p["abs_move"] / p["implied_move"]
    p["year"] = p["entry_date"].dt.year
    print("lane status:", dict(Counter(p["lc_status"])))
    ok = p["lc_status"] == "ok"
    print(f"  reconciliation |J + D_net - fees - H| max {p.loc[ok, 'recon'].abs().max():.2e}")
    p.to_parquet(HERE / "panel.parquet", index=False)
    print(f"wrote {HERE / 'panel.parquet'} ({len(p)} rows, {int(ok.sum())} lane-ok)")


if __name__ == "__main__":
    main()
