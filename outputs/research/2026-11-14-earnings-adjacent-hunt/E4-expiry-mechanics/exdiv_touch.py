"""
exdiv_touch.py
E4 part (b), descriptive (not a trial): what a small writer receives at the touch for a deep
in-the-money call sold on the last cum-dividend day, and the share of open interest that must fail
to exercise for the covered write to break even.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/exdiv_touch.py

Sample: every CRSP-inferred ex-dividend date whose previous session (the last cum-dividend day) has
a cached 15:59 chain in data/cache/backfill_chains (entry or reaction sessions of the earnings
book). Calls on any listed expiry after the ex-date for which early exercise is optimal (dividend
above the Black-Scholes put value at the strike on the ex-dividend open, zero rate, the strike's
own put mid IV when quoted, else the call's), two-sided at 15:59.

Covered write per share: buy stock at the CRSP close plus its half-spread (floored at 1 bp), sell
the call at the 15:59 bid, USD 0.0065 commission per share per option trade. Assigned (the holder
exercises): deliver the stock at K. Not assigned: collect D, buy the call back next morning at
parity plus remaining time value plus today's call half-spread, sell the stock at its half-spread.
    E = gamma - hs_s - fee + u * (D - tv - hs_c - hs_s - fee),  gamma = C_bid - (S - K)
u is the writer's chance of not being assigned. Breakeven u* = -(gamma - hs_s - fee) / (D - tv -
hs_c - hs_s - fee). A writer profits only if the share of open interest left unexercised, after
the dividend play dilutes it, exceeds u*.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

from earnings_iv_crush.research.hedged_hold import option_iv  # noqa: E402

HERE = Path(__file__).resolve().parent
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
FEE = 0.65 / 100.0  # USD per share per option trade
EQ_FLOOR = 1e-4
MAX_DTE = 60  # calendar days after the ex-date; the play concentrates in short-dated series


def bs_put(s: float, k: float, t: float, sig: float) -> float:
    if t <= 0 or not np.isfinite(sig) or sig <= 0:
        return max(k - s, 0.0)
    v = sig * np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * v * v) / v
    return float(k * norm.cdf(-d1 + v) - s * norm.cdf(-d1))


def main() -> None:
    ex = pd.read_parquet(HERE / "exdiv_events.parquet", columns=["ticker", "permno"])
    tick = ex.drop_duplicates("permno").set_index("permno")["ticker"]
    c = pd.read_parquet(ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet")
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "cfacpr", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c = c.sort_values(["permno", "date"])
    g = c.groupby("permno")
    c["cum_date"] = g["date"].shift(1)
    c["S"] = g["prc"].shift(1)
    c["hs_s"] = (((g["ask"].shift(1) - g["bid"].shift(1)) / 2) / c["S"]).clip(lower=EQ_FLOOR)
    c["div"] = (1 + c["ret"]) * c["S"] - c["prc"]
    c.loc[c["cfacpr"] != g["cfacpr"].shift(1), "div"] = np.nan
    exd = c[(c["div"] > 0.005)].copy()
    # map permno to the ticker used by the chain cache (any ticker of the earnings book)
    f = pd.read_parquet(ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet",
                        columns=["ticker", "permno"]).dropna().drop_duplicates("permno")
    exd = exd.merge(f, on="permno", how="inner")
    rows, funnel = [], {"exdates": len(exd), "with_cum_chain": 0}
    for _, e in exd.iterrows():
        p = CHAINS / f"{e['ticker']}_{e['cum_date'].date()}.parquet"
        if not p.exists():
            continue
        funnel["with_cum_chain"] += 1
        d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00", "ts_recv"]).reset_index()
        body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
        d["right"] = body.str[6]
        d["K"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
        d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
        d = d.sort_values("ts_recv").groupby(["expiry", "K", "right"], as_index=False).last()
        d = d[(d["bid_px_00"] > 0) & (d["ask_px_00"] > 0)]
        d = d[(d["expiry"] >= e["date"]) & ((d["expiry"] - e["date"]).dt.days <= MAX_DTE)]
        S, D, hs_s = float(e["S"]), float(e["div"]), float(e["hs_s"])
        calls = d[(d["right"] == "C") & (d["K"] < S)]
        puts = d[d["right"] == "P"].set_index(["expiry", "K"])
        for _, q in calls.iterrows():
            t_cum = max((q["expiry"] - e["cum_date"]).days, 1) / 365.0
            t_ex = max((q["expiry"] - e["date"]).days, 0) / 365.0
            key = (q["expiry"], q["K"])
            if key in puts.index:
                pm = float((puts.loc[key, "bid_px_00"] + puts.loc[key, "ask_px_00"]) / 2)
                sig = option_iv(pm, S - D, float(q["K"]), t_cum, "P")
            else:
                cm = float((q["bid_px_00"] + q["ask_px_00"]) / 2)
                sig = option_iv(cm, S - D, float(q["K"]), t_cum, "C")
            tv = bs_put(S - D, float(q["K"]), t_ex, sig)
            if not D > tv:
                continue
            hs_c = float(q["ask_px_00"] - q["bid_px_00"]) / 2
            gamma = float(q["bid_px_00"]) - (S - float(q["K"]))
            den = D - tv - hs_c - hs_s * S - FEE
            num = -(gamma - hs_s * S - FEE)
            rows.append({
                "ticker": e["ticker"], "cum_date": e["cum_date"], "expiry": q["expiry"],
                "K": q["K"], "S": S, "D": D, "tv": tv, "hs_c": hs_c, "hs_s_usd": hs_s * S,
                "gamma": gamma, "den": den,
                "u_star": num / den if den > 0 else np.inf,
            })
    r = pd.DataFrame(rows)
    r.to_parquet(HERE / "exdiv_touch.parquet")
    res = {"funnel": funnel, "series": int(len(r)),
           "names_days": int(r[["ticker", "cum_date"]].drop_duplicates().shape[0]) if len(r) else 0}
    if len(r):
        q = r["u_star"].replace(np.inf, np.nan)
        res.update(
            share_den_nonpositive=float((r["den"] <= 0).mean()),
            gamma_over_D_median=float((r["gamma"] / r["D"]).median()),
            hs_c_over_D_median=float((r["hs_c"] / r["D"]).median()),
            share_bid_below_parity=float((r["gamma"] < 0).mean()),
            u_star_quantiles={str(k): float(v) for k, v in q.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).items()},
            share_u_star_below_0p40=float((r["u_star"] < 0.40).mean()),
            share_u_star_below_0p10=float((r["u_star"] < 0.10).mean()),
            D_over_S_median=float((r["D"] / r["S"]).median()),
        )
    (HERE / "results_exdiv_touch.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
