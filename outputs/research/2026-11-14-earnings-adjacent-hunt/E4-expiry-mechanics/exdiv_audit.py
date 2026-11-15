"""
exdiv_audit.py
E4 part (b), descriptive (not a trial): how often an ex-dividend date falls inside the hedged
hold while the short call is in the money, and the dividend the model credits to the writer that
an optimally exercising holder would take by exercising on the last cum-dividend day.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/exdiv_audit.py

Dividends are recovered from CRSP total and price returns: D_t = (1 + ret_t) |prc_{t-1}| - |prc_t|
on sessions with an unchanged cfacpr. The hedged-hold model (hedged_short_straddle) holds the
short call to expiry and credits the hedge with the dividend, so relative to early assignment on
the last cum-dividend day it gains D minus the time value the holder surrenders. Early exercise is
taken as optimal when D exceeds the Black-Scholes put value at the strike on the ex-dividend open
(zero rate, the event's post-event implied volatility s2_iv), the standard American-call condition
for a short-dated option (Roll 1977; Hao, Kalay and Mayhew 2010 eq. 1-4). Reads stock data, strikes
and m0 only; it does not read any P&L outcome.
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

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
MIN_DIV = 0.005  # USD per share; below this the recovered amount is CRSP rounding noise


def bs_put(s: float, k: float, t: float, sig: float) -> float:
    if t <= 0 or sig <= 0:
        return max(k - s, 0.0)
    v = sig * np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * v * v) / v
    return float(k * norm.cdf(-d1 + v) - s * norm.cdf(-d1))


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def main() -> None:
    c = pd.read_parquet(CRSP)
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "cfacpr"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c = c.sort_values(["permno", "date"])
    g = c.groupby("permno")
    c["prc_prev"] = g["prc"].shift(1)
    c["cf_prev"] = g["cfacpr"].shift(1)
    c["div"] = (1 + c["ret"]) * c["prc_prev"] - c["prc"]
    c.loc[c["cfacpr"] != c["cf_prev"], "div"] = np.nan
    exd = c[c["div"] > MIN_DIV][["permno", "date", "div", "prc_prev"]]
    print(f"ex-dividend sessions recovered: {len(exd)} over {exd['permno'].nunique()} permnos")

    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno", "s2_iv"])
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    out, res = [], {}
    for panel, fname in (("broad", "events.parquet"), ("megacap", "events_megacap.parquet")):
        ev = pd.read_parquet(HH / fname)
        ev = ev[ev["status"] == "ok"].copy()
        for col in ("entry_date", "exit_date", "expiry"):
            ev[col] = pd.to_datetime(ev[col])
        ev = ev.merge(f, on=["ticker", "entry_date"], how="left")
        ev["panel"] = panel
        m = ev.merge(exd, on="permno", how="left")
        inside = (m["date"] > m["entry_date"]) & (m["date"] <= m["expiry"])
        m = m[inside].copy()
        # cum-dividend close is prc_prev (the session before the ex-date)
        m["itm"] = m["prc_prev"] > m["strike"]
        t_after = (m["expiry"] - m["date"]).dt.days / 365.0
        m["put_ex"] = [
            bs_put(s - dv, k, t, sg) if np.isfinite(sg) else np.nan
            for s, dv, k, t, sg in zip(m["prc_prev"], m["div"], m["strike"], t_after, m["s2_iv"])
        ]
        m["optimal"] = m["itm"] & (m["div"] > m["put_ex"])
        m["credit_ub"] = np.where(m["itm"], m["div"], 0.0) / m["m0"]
        m["credit"] = np.where(m["optimal"], m["div"] - m["put_ex"], 0.0) / m["m0"]
        m["exdate_is_reaction"] = m["date"] == m["exit_date"]
        per = m.groupby(["ticker", "entry_date"])[["credit_ub", "credit"]].sum()
        ev = ev.merge(per.reset_index(), on=["ticker", "entry_date"], how="left")
        ev[["credit_ub", "credit"]] = ev[["credit_ub", "credit"]].fillna(0.0)
        ev["year"] = ev["entry_date"].dt.year
        for blk, (y0, y1) in {"2013-18": (2013, 2018), "2019-24": (2019, 2024)}.items():
            b = ev[ev["year"].between(y0, y1)]
            mb = m[m["entry_date"].dt.year.between(y0, y1)]
            dts = b["exit_date"]
            iv = date_clustered_ci(b["credit"].to_numpy(float), dts, _mean)
            ub = date_clustered_ci(b["credit_ub"].to_numpy(float), dts, _mean)
            res[f"{panel} {blk}"] = {
                "events": int(len(b)),
                "events_with_exdate_in_hold": int(mb[["ticker", "entry_date"]].drop_duplicates()
                                                  .shape[0]),
                "of_which_call_itm_on_cum_day": int(mb.loc[mb["itm"], ["ticker", "entry_date"]]
                                                    .drop_duplicates().shape[0]),
                "of_which_exercise_optimal": int(mb.loc[mb["optimal"], ["ticker", "entry_date"]]
                                                 .drop_duplicates().shape[0]),
                "exdate_on_reaction_session": int(mb["exdate_is_reaction"].sum()),
                "mean_div_over_m0_when_optimal": float((mb.loc[mb["optimal"], "div"]
                                                        / mb.loc[mb["optimal"], "m0"]).mean())
                if mb["optimal"].any() else None,
                "book_mean_credit_m0": [iv.point, iv.low, iv.high],
                "book_mean_credit_upper_bound_m0": [ub.point, ub.low, ub.high],
            }
        out.append(m)
    pd.concat(out).to_parquet(HERE / "exdiv_events.parquet")
    (HERE / "results_exdiv.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
