"""s02_build.py: lane G panel. Index ETF term structure, causal reporter weights, trade outcomes.

For every SPY, QQQ and IWM session 2016-2026 in the approved Databento cache
(`data/cache/index_chains/`, 15:59 ET snapshots), the ATM straddle of every listed expiry within
ten calendar days is located (two-sided legs only, strike minimising |C mid - P mid|) and each
leg is inverted under Black on the parity forward to a total implied variance w = sigma^2 T.
Two expiries that both contain the night give the jump-diffusion split w(E) = a n(E) + J
(Dubinsky, Johannes, Kaeck and Seeger 2019, applied to the index), with n(E) the NYSE sessions
from t to E. J is the ex-ante implied variance concentrated on the coming night.

Reporter weights are causal: a 252-session OLS of QQQ (and SPY) daily returns on the eight
mega-caps' returns, window ending at t-1's close. W(t) is the summed weight of names with an
after-close release on t; V_pred(t) = sum w_i^2 m_i^2 with m_i the name's mean absolute
earnings reaction over strictly earlier releases in the calendar. Release dates are announced
weeks ahead, so the flag is known before the 15:59 entry.

Trade outcomes are joined from the frozen index study's priced trades (front expiry after t+1,
15:59 entry, 15:59 or 10:00 exit) and the next-day-expiry study's trades (settle at intrinsic).

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneG-index-event-vol/s02_build.py

References
----------
Dubinsky, Johannes, Kaeck and Seeger (2019), Option pricing of earnings announcement risks, RFS.
Muravyev and Ni (2020), Why do option returns change sign from day to night?, JFE.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from earnings_iv_crush.engine.stats import nyse_sessions

# ── paths and constants ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CHAINS = ROOT / "data" / "cache" / "index_chains"
MEGACAP = ROOT / "data" / "cache" / "index_events" / "megacap_amc_releases_2016_2026.csv"
MACRO = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
PRICED = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"
NDE = ROOT / "outputs" / "research" / "2026-11-02-next-day-expiry-settle" / "trades.parquet"
TICKERS = ("QQQ", "SPY", "IWM")
NAMES = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO")
START, END = pd.Timestamp("2016-01-04"), pd.Timestamp("2026-10-30")
WEIGHT_WINDOW = 252  # sessions of daily returns in the causal weight regression
MIN_PRIOR_RELEASES = 3  # before a name's own mean reaction replaces the pooled prior mean
COMMISSION = 0.0065  # USD per share per leg per side (frozen index study)
SETTLE_COST_BP = 5.0  # disposal of exercised shares (frozen next-day-expiry study)
MARGIN_SPOT_FRAC = 0.15  # broad-based ETF short straddle (frozen index study)
SESSIONS = nyse_sessions(START, END + pd.Timedelta(days=20))
SPOS = {d: i for i, d in enumerate(SESSIONS)}


# ── Black inversion ──────────────────────────────────────────────────────────
def _black(f: np.ndarray, k: np.ndarray, s: np.ndarray, call: np.ndarray) -> np.ndarray:
    d1 = np.log(f / k) / s + s / 2
    d2 = d1 - s
    c = f * ndtr(d1) - k * ndtr(d2)
    return np.where(call, c, c - f + k)


def implied_s(price: np.ndarray, f: np.ndarray, k: np.ndarray, call: np.ndarray) -> np.ndarray:
    """Total implied standard deviation sigma*sqrt(T) by bisection (undiscounted Black)."""
    lo = np.full(price.shape, 1e-5)
    hi = np.full(price.shape, 1.5)
    intrinsic = np.where(call, np.maximum(f - k, 0), np.maximum(k - f, 0))
    bad = ~(price > intrinsic + 1e-6)
    for _ in range(60):
        mid = (lo + hi) / 2
        v = _black(f, k, mid, call)
        hi = np.where(v > price, mid, hi)
        lo = np.where(v > price, lo, mid)
    out = (lo + hi) / 2
    out[bad] = np.nan
    return out


# ── term structure per snapshot ──────────────────────────────────────────────
def term_structure(job: tuple[str, pd.Timestamp]) -> list[dict[str, object]]:
    tk, t = job
    p = CHAINS / f"{tk}_{t.date()}_1559.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    if df.empty:
        return []
    df = df.sort_values("ts_recv").groupby("symbol", as_index=False).last()
    sym = df["symbol"].astype(str)
    q = pd.DataFrame(
        {
            "expiry": pd.to_datetime(sym.str[6:12], format="%y%m%d"),
            "cp": sym.str[12],
            "strike": sym.str[13:21].astype(int) / 1000.0,
            "bid": df["bid_px_00"].astype(float),
            "ask": df["ask_px_00"].astype(float),
        }
    )
    q = q[(q["bid"] > 0) & (q["ask"] >= q["bid"]) & np.isfinite(q["ask"])]
    q = q[q["expiry"] > t]
    out: list[dict[str, object]] = []
    for exp, g in q.groupby("expiry"):
        piv = g.pivot_table(index="strike", columns="cp", values=["bid", "ask"]).dropna()
        if piv.empty or ("bid", "C") not in piv.columns or ("bid", "P") not in piv.columns:
            continue
        cm = (piv[("bid", "C")] + piv[("ask", "C")]) / 2
        pm = (piv[("bid", "P")] + piv[("ask", "P")]) / 2
        k = float((cm - pm).abs().idxmin())
        f = k + float(cm.loc[k] - pm.loc[k])
        if exp not in SPOS:
            continue
        n = SPOS[exp] - SPOS[t]
        sc = implied_s(np.array([cm.loc[k]]), np.array([f]), np.array([k]), np.array([True]))[0]
        sp = implied_s(np.array([pm.loc[k]]), np.array([f]), np.array([k]), np.array([False]))[0]
        s_atm = np.nanmean([sc, sp]) if np.isfinite([sc, sp]).any() else np.nan
        out.append(
            {
                "ticker": tk,
                "entry": t,
                "expiry": exp,
                "n_sess": n,
                "cal_days": int((exp - t).days),
                "strike": k,
                "fwd": f,
                "strad_mid": float(cm.loc[k] + pm.loc[k]),
                "strad_bid": float(piv.loc[k, ("bid", "C")] + piv.loc[k, ("bid", "P")]),
                "strad_ask": float(piv.loc[k, ("ask", "C")] + piv.loc[k, ("ask", "P")]),
                "w": float(s_atm**2) if np.isfinite(s_atm) else np.nan,
            }
        )
    return out


def build_term_structure() -> pd.DataFrame:
    path = HERE / "term_structure.parquet"
    if path.exists():
        return pd.read_parquet(path)
    sess = [d for d in SESSIONS if START <= d <= END]
    jobs = [(tk, d) for tk in TICKERS for d in sess]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = [r for lst in ex.map(term_structure, jobs, chunksize=64) for r in lst]
    ts = pd.DataFrame(rows)
    ts.to_parquet(path)
    return ts


def jump_split(ts: pd.DataFrame) -> pd.DataFrame:
    """Per session: a and J from the two shortest expiries with distinct n (both after t)."""
    rows = []
    for (tk, t), g in ts.dropna(subset=["w"]).groupby(["ticker", "entry"]):
        g = g.sort_values("n_sess").drop_duplicates("n_sess")
        rec: dict[str, object] = {"ticker": tk, "entry": t, "n_exp": len(g)}
        if len(g) >= 2:
            (n1, w1), (n2, w2) = g[["n_sess", "w"]].to_numpy()[:2]
            a = (w2 - w1) / (n2 - n1)
            rec.update({"n1": n1, "n2": n2, "w1": w1, "w2": w2, "a": a, "J": w1 - a * n1})
        if len(g) >= 1:
            rec.update({"w_front": g["w"].iloc[0], "n_front": g["n_sess"].iloc[0]})
        rows.append(rec)
    return pd.DataFrame(rows)


# ── causal weights and expected moves ────────────────────────────────────────
def causal_weights(px: pd.DataFrame, etf: str) -> pd.DataFrame:
    """Rolling OLS loadings of the ETF on the eight names, window ending at t-1."""
    cols = [f"adj_{n}" for n in NAMES]
    r = np.log(px[[f"adj_{etf}", *cols]]).diff().dropna()
    y = r[f"adj_{etf}"].to_numpy()
    x = r[cols].to_numpy()
    idx = r.index
    out = []
    for i in range(WEIGHT_WINDOW, len(r)):
        xs, ys = x[i - WEIGHT_WINDOW : i], y[i - WEIGHT_WINDOW : i]  # rows strictly before i
        b = np.linalg.lstsq(np.column_stack([np.ones(len(ys)), xs]), ys, rcond=None)[0][1:]
        out.append([idx[i], *b])  # loading usable on day idx[i] (window ends at idx[i-1])
    w = pd.DataFrame(out, columns=["date", *NAMES]).set_index("date")
    return w.clip(lower=0.0)


def expected_moves(px: pd.DataFrame, mc: pd.DataFrame) -> pd.DataFrame:
    """Each release's realised reaction and the causal expected |move| from earlier releases."""
    dates = px.index
    rows = []
    for r in mc.itertuples():
        d = pd.Timestamp(r.release_date)
        if d not in dates:
            continue
        i = dates.get_loc(d)
        if i + 1 >= len(dates):
            continue
        p0, p1 = px[f"adj_{r.ticker}"].iloc[i], px[f"adj_{r.ticker}"].iloc[i + 1]
        rows.append({"ticker": r.ticker, "release_date": d, "react": float(np.log(p1 / p0))})
    ev = pd.DataFrame(rows).sort_values("release_date").reset_index(drop=True)
    exp_m = []
    for j, r in ev.iterrows():
        prior = ev[(ev["release_date"] < r["release_date"])]
        own = prior[prior["ticker"] == r["ticker"]]["react"].abs()
        if len(own) >= MIN_PRIOR_RELEASES:
            exp_m.append(float(own.mean()))
        elif len(prior) >= MIN_PRIOR_RELEASES:
            exp_m.append(float(prior["react"].abs().mean()))
        else:
            exp_m.append(np.nan)
    ev["m_hat"] = exp_m
    return ev


# ── trade outcomes ───────────────────────────────────────────────────────────
def trades(px: pd.DataFrame) -> pd.DataFrame:
    p = pd.read_parquet(PRICED)
    comm = 4 * COMMISSION
    p["long_touch_net"] = p["long_touch"] - comm / p["p0"]
    p["debit"] = p["c0a"] + p["p0a"]
    p["long_touch_net_debit"] = (p["c1b"] + p["p1b"] - p["debit"] - comm) / p["debit"]
    keep = ["ticker", "entry", "exit", "dte", "p0", "fwd0", "fwd1", "short_touch_net",
            "short_touch_net_rom", "long_touch_net", "long_touch_net_debit", "short_mid",
            "c0b", "c0a", "p0b", "p0a"]
    wide = []
    for snap, tag in (("1559", "d"), ("1000", "o")):
        s = p[p["exit_snap"] == snap][keep].copy()
        ren = {c: f"{c}_{tag}" for c in keep if c not in ("ticker", "entry")}
        wide.append(s.rename(columns=ren).set_index(["ticker", "entry"]))
    out = wide[0].join(wide[1], how="outer")
    # next-day expiry, settled at intrinsic on the Yahoo close of t+1 (frozen NDE rules)
    n = pd.read_parquet(NDE)
    n = n[n["status"] == "ok"].copy()
    s1 = []
    for r in n.itertuples():
        col = f"close_{r.ticker}"
        s1.append(float(px[col].get(r.exit, np.nan)))
    n["S1"] = s1
    intr = (n["S1"] - n["strike"]).abs()
    settle_cost = SETTLE_COST_BP / 1e4 * n["S1"] * (n["S1"] != n["strike"])
    ask_sum = 2 * n["p0"] - n["sale"]
    n["nde_short_net"] = n["N"]
    n["nde_long_net"] = (intr - ask_sum - 2 * COMMISSION - settle_cost) / n["p0"]
    n["nde_long_net_debit"] = (intr - ask_sum - 2 * COMMISSION - settle_cost) / ask_sum
    n["nde_short_rom"] = n["N_rom"]
    n["nde_p0"] = n["p0"]
    nn = n.set_index(["ticker", "entry"])[
        ["nde_short_net", "nde_short_rom", "nde_long_net", "nde_long_net_debit", "nde_p0",
         "half_spread"]
    ]
    return out.join(nn, how="outer").reset_index()


def main() -> None:
    px = pd.read_parquet(HERE / "prices_yahoo.parquet")
    px.index = pd.to_datetime(px.index).tz_localize(None)
    vix = pd.read_parquet(HERE / "vix_fred.parquet").set_index("date")["vix"]
    mc = pd.read_csv(MEGACAP, parse_dates=["release_date"])
    macro = pd.read_csv(MACRO, parse_dates=["date"])
    macro_days = set(macro["date"])

    ts = build_term_structure()
    print("term structure rows", len(ts), ts.groupby("ticker").size().to_dict())
    js = jump_split(ts)

    ev = expected_moves(px, mc)
    ev.to_parquet(HERE / "releases.parquet")
    wq = causal_weights(px, "QQQ")
    ws = causal_weights(px, "SPY")
    print("QQQ causal loadings, yearly mean (sanity against published weights):")
    print(wq.groupby(wq.index.year).mean().round(3).to_string())
    print("SPY causal loadings, yearly mean:")
    print(ws.groupby(ws.index.year).mean().round(3).to_string())

    tr = trades(px)
    panel = tr.merge(js, on=["ticker", "entry"], how="left")
    # event features for each ETF
    feats = []
    for tk, wts in (("QQQ", wq), ("SPY", ws), ("IWM", wq * 0.0)):
        sub = panel[panel["ticker"] == tk]
        for t in sub["entry"].unique():
            t = pd.Timestamp(t)
            rel = ev[ev["release_date"] == t]
            wrow = wts.loc[t] if t in wts.index else None
            if wrow is None:
                feats.append({"ticker": tk, "entry": t, "W": np.nan})
                continue
            w_i = np.array([wrow[n] for n in rel["ticker"]]) if len(rel) else np.array([])
            m_i = rel["m_hat"].to_numpy() if len(rel) else np.array([])
            r_i = rel["react"].to_numpy() if len(rel) else np.array([])
            feats.append(
                {
                    "ticker": tk,
                    "entry": t,
                    "n_rep": int(len(rel)),
                    "reporters": ",".join(rel["ticker"]),
                    "W": float(w_i.sum()),
                    "V_pred": float(np.nansum(w_i**2 * m_i**2)),
                    "V_pred_corr": float(np.nansum(w_i * m_i) ** 2),
                    "contrib_real": float(np.nansum(w_i * r_i)),
                }
            )
    fe = pd.DataFrame(feats)
    panel = panel.merge(fe, on=["ticker", "entry"], how="left")
    vprev = vix.shift(1)  # close of t-1: known before the 15:59 entry on t
    panel["vix_prev"] = panel["entry"].map(vprev)
    panel["exit_macro"] = panel["exit_d"].isin(macro_days) | panel["exit_o"].isin(macro_days)
    panel["weekday"] = panel["entry"].dt.weekday
    panel["block"] = np.select(
        [panel["entry"] < "2019-01-01", panel["entry"] < "2025-01-01"], ["P", "M"], "C"
    )
    panel["move_d"] = np.log(panel["fwd1_d"] / panel["fwd0_d"])
    panel.to_parquet(HERE / "panel.parquet")
    print("panel", panel.shape)
    print(panel.groupby(["ticker", "block"]).agg(n=("entry", "size"),
                                                  ev=("n_rep", lambda s: int((s > 0).sum())),
                                                  J_ok=("J", lambda s: int(s.notna().sum())))
          .to_string())


if __name__ == "__main__":
    main()
