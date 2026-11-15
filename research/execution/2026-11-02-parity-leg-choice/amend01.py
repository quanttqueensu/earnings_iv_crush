"""
amend01.py
Amendment 01 of the parity leg choice: the two-call construction is chosen from 15:59 information
only (put half-spread wider than the call's); 2025-26 shares at the as-traded close.

Usage
-----
    python research/execution/2026-11-02-parity-leg-choice/amend01.py

References
----------
Cremers, M. and Weinbaum, D. (2010) Deviations from put-call parity and stock return
predictability. JFQA 45(2), 335-367.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import year_frac  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "amendment_01_no_lookahead.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}-amendment-01.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
SMILE = ROOT / "research" / "execution" / "2026-11-02-smile-strike-hedged-hold" / "study.py"

_s = importlib.util.spec_from_file_location("smile", SMILE)
assert _s is not None and _s.loader is not None
sm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(sm)

BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
YAHOO_HALF_SPREAD = 3e-4
QUOTE_TOL = 0.01
DIV_TOL = 1e-6
ATTRITION_TOL = 0.005


def _yahoo(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2024-10-01",
        end="2026-11-01",
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out = {}
    for t in tickers:
        try:
            g = raw[t].dropna(subset=["Close"]).copy()
        except KeyError:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = g
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    import yfinance as yf

    irx = (
        yf.download(
            "^IRX", start="2012-06-01", end="2026-11-01", progress=False, auto_adjust=False
        )["Close"]
        .iloc[:, 0]
        .dropna()
    )
    irx.index = pd.to_datetime(irx.index).tz_localize(None).normalize()

    a = pd.read_parquet(HH / "events.parquet")
    c = pd.read_parquet(HH / "events_confirm_2025_26.parquet")
    a, c = a[a["status"] == "ok"].copy(), c[c["status"] == "ok"].copy()
    a["src"], c["src"] = "crsp", "yahoo"
    d = pd.concat([a, c], ignore_index=True)
    for col in ("entry_date", "exit_date", "expiry"):
        d[col] = pd.to_datetime(d[col])
    f = pd.read_parquet(FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = d.merge(
        f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )

    cr = pd.read_parquet(CRSP)
    cr["date"] = pd.to_datetime(cr["date"])
    for col in ("prc", "ret", "bid", "ask"):
        cr[col] = pd.to_numeric(cr[col], errors="coerce").astype(float)
    cr["prc"] = cr["prc"].abs()
    crsp = {int(k): g.set_index("date").sort_index() for k, g in cr.groupby("permno")}
    yh = _yahoo(sorted(c["ticker"].unique()))

    rows, funnel = [], Counter()
    for _, e in d.iterrows():
        t0, exp, k = e["entry_date"], e["expiry"], float(e["strike"])
        ch = sm.chain(e["ticker"], t0, exp)
        if ch is None:
            funnel["no_chain"] += 1
            continue
        q = ch[np.isclose(ch["strike"], k)].set_index("right")
        if not {"C", "P"} <= set(q.index):
            funnel["no_leg"] += 1
            continue
        cb, pb = float(q.loc["C", "bid"]), float(q.loc["P", "bid"])
        ca, pa = float(q.loc["C", "ask"]), float(q.loc["P", "ask"])
        if abs(cb + pb - e["s0"]) > QUOTE_TOL:
            funnel["quote_mismatch"] += 1
            rows.append({"key": (e["ticker"], t0), "status": "quote_mismatch"})
            continue
        if e["src"] == "crsp":
            g = crsp.get(int(e["permno"])) if pd.notna(e["permno"]) else None
            if g is None or t0 not in g.index:
                funnel["no_stock"] += 1
                continue
            s_ask = float(g.loc[t0, "ask"])
            w = g.loc[(g.index > t0) & (g.index <= exp)]
            pr = w["prc"] / g["prc"].shift(1).reindex(w.index) - 1
            div = bool(((w["ret"] - pr).abs() > DIV_TOL).any())
        else:
            g = yh.get(e["ticker"])
            if g is None or t0 not in g.index:
                funnel["no_stock"] += 1
                continue
            sp = g.get("Stock Splits", pd.Series(0.0, index=g.index)).replace(0.0, 1.0).fillna(1.0)
            after = float(sp[sp.index > t0].prod())
            s_ask = float(g.loc[t0, "Close"]) * after * (1 + YAHOO_HALF_SPREAD)
            w = g.loc[(g.index > t0) & (g.index <= exp)]
            div = bool((w.get("Dividends", pd.Series(0.0)).fillna(0) > 0).any())
        if not np.isfinite(s_ask) or s_ask <= 0:
            funnel["no_stock"] += 1
            continue
        r = irx.asof(t0) / 100.0
        tau = year_frac(t0, exp)
        adv = (cb - pb) - (s_ask - k) - s_ask * r * tau
        status = "dividend" if div else "ok"
        funnel[status] += 1
        rows.append(
            {
                "key": (e["ticker"], t0),
                "status": status,
                "adv": adv,
                "adv_pos": (adv if (pa - pb) > (ca - cb) else 0.0) / e["m0"],
                "chosen_calls": (pa - pb) > (ca - cb),
                "hs_put_minus_call": ((pa - pb) - (ca - cb)) / 2 / e["m0"],
                "extra_notional_m0": s_ask / e["m0"],
            }
        )
    print("funnel:", dict(funnel))
    z = pd.DataFrame(rows)
    d["key"] = list(zip(d["ticker"], d["entry_date"], strict=True))
    d = d.merge(z, on="key", how="left", suffixes=("", "_p"))
    d["year"] = d["exit_date"].dt.year
    OUT.mkdir(parents=True, exist_ok=True)
    d.drop(columns=["key"]).to_parquet(OUT / "events_amend01.parquet")

    res: dict = {"funnel": dict(funnel)}
    for name, (y0, y1) in BLOCKS.items():
        blk = d[d["year"].between(y0, y1)]
        ok = blk[blk["status_p"] == "ok"].copy()
        exc = blk[blk["status_p"] != "ok"]
        ok["HP"] = ok["H"] + ok["adv_pos"]
        p1 = date_clustered_ci(ok["adv_pos"].to_numpy(float), ok["exit_date"], _mean)
        p2 = date_clustered_ci(ok["HP"].to_numpy(float), ok["exit_date"], per_trade_sharpe)
        res[name] = {
            "n_block": int(len(blk)),
            "n_ok": int(len(ok)),
            "n_excluded": int(len(exc)),
            "excluded_gap_H": float(exc["H"].mean() - ok["H"].mean()) if len(exc) else 0.0,
            "P1_mean_adv_pos": [p1.point, p1.low, p1.high],
            "share_calls_chosen": float(ok["chosen_calls"].mean()),
            "mean_adv_all": float((ok["adv"] / ok["m0"]).mean()),
            "P2_sharpe_HP": [p2.point, p2.low, p2.high],
            "sharpe_H_same": per_trade_sharpe(ok["H"]),
            "mean_H_same": float(ok["H"].mean()),
            "mean_HP": float(ok["HP"].mean()),
            "mean_hs_put_minus_call": float(ok["hs_put_minus_call"].mean()),
            "median_extra_notional_m0": float(ok["extra_notional_m0"].median()),
            "adv_pos_by_year": ok.groupby("year")["adv_pos"].mean().round(5).to_dict(),
        }
    dsc, val, con = res["discovery"], res["validation"], res["confirmation"]
    lever = (
        dsc["P1_mean_adv_pos"][1] > 0
        and val["P1_mean_adv_pos"][1] > 0
        and (con["P1_mean_adv_pos"][0] > 0)
    )
    book = (
        lever
        and val["P2_sharpe_HP"][1] > 0
        and dsc["P2_sharpe_HP"][0] > 0
        and (con["P2_sharpe_HP"][0] > 0)
    )
    res["verdict"] = (
        ("PARITY LEVER" if lever else "NO LEVER") + "; " + ("BOOK PASS" if book else "BOOK FAIL")
    )
    res["attrition_flag"] = [k for k in BLOCKS if abs(res[k]["excluded_gap_H"]) > ATTRITION_TOL]
    (OUT / "results_amend01.json").write_text(
        json.dumps(res, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"], "attrition flags:", res["attrition_flag"])


if __name__ == "__main__":
    main()
