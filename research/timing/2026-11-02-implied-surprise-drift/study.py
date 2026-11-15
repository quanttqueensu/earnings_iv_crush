"""
study.py
Post-announcement drift after reactions larger than the option-implied move, SPY-hedged, 20 sessions.
Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-implied-surprise-drift/study.py

References
----------
Brandt, M., Kishore, R., Santa-Clara, P. and Venkatachalam, M. (2008) Earnings announcements are full
of surprises. Working paper, Duke University.
Bernard, V. and Thomas, J. (1989) Post-earnings-announcement drift. JAR 27, 1-36.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
COST = 12e-4
H_MAIN = 20
H_SIDE = (5, 60)
BLOCKS = {"2013-18": (2013, 2018), "2019-24": (2019, 2024), "2025-26": (2025, 2026)}


def closes(tickers: list[str]) -> dict[str, pd.Series]:
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2013-01-01",
        end="2026-11-01",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out = {}
    for t in tickers:
        try:
            g = raw[t]["Adj Close"].dropna()
        except KeyError:
            continue
        if g.empty:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = g
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def summ(x: pd.DataFrame, col: str) -> dict:
    x = x[np.isfinite(x[col])]
    if len(x) < 5:
        return {"n": int(len(x))}
    a = date_clustered_ci(x[col].to_numpy(float), x["exit_date"], _mean)
    b = date_clustered_ci(
        x[col].to_numpy(float), x["exit_date"].dt.to_period("M").astype(str), _mean
    )
    return {
        "n": int(len(x)),
        "mean": a.point,
        "ci_date": [a.low, a.high],
        "ci_month": [b.low, b.high],
        "ci_wider": [min(a.low, b.low), max(a.high, b.high)],
        "sharpe": per_trade_sharpe(x[col]),
    }


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = pd.read_parquet(EVENTS)[["ticker", "entry_date", "exit_date", "block", "implied_move"]]
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    px = closes(sorted(ev["ticker"].unique()) + ["SPY"])
    spy = px["SPY"]
    rows, funnel = [], Counter()
    for _, e in ev.iterrows():
        g = px.get(e["ticker"])
        if not np.isfinite(e["implied_move"]) or e["implied_move"] <= 0:
            funnel["no_implied"] += 1
            continue
        if g is None:
            funnel["no_name"] += 1
            continue
        t0, t1 = e["entry_date"], e["exit_date"]
        if t0 not in g.index or t1 not in g.index or t1 not in spy.index:
            funnel["no_session"] += 1
            continue
        i1 = g.index.get_loc(t1)
        r = g.loc[t1] / g.loc[t0] - 1
        row = {
            "ticker": e["ticker"],
            "exit_date": t1,
            "block": e["block"],
            "R": r,
            "z": abs(r) / e["implied_move"],
        }
        for h in (H_MAIN, *H_SIDE):
            if i1 + h >= len(g):
                row[f"net{h}"] = np.nan
                continue
            th = g.index[i1 + h]
            if th not in spy.index:
                row[f"net{h}"] = np.nan
                continue
            sr = g.iloc[i1 + h] / g.iloc[i1] - 1
            mr = spy.loc[th] / spy.loc[t1] - 1
            row[f"net{h}"] = np.sign(r) * (sr - mr) - COST
        funnel["ok" if np.isfinite(row[f"net{H_MAIN}"]) else "short_history"] += 1
        rows.append(row)
    print("funnel:", dict(funnel))
    d = pd.DataFrame(rows)
    d["year"] = d["exit_date"].dt.year
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")
    sel, uns = d[d["z"] > 1], d[d["z"] <= 1]
    col = f"net{H_MAIN}"
    res: dict = {"funnel": dict(funnel)}
    res["primary"] = {k: summ(sel[sel["year"].between(*v)], col) for k, v in BLOCKS.items()}
    res["secondary"] = {
        "pooled_selected": summ(sel, col),
        "unselected": {k: summ(uns[uns["year"].between(*v)], col) for k, v in BLOCKS.items()},
        "by_block": {b: summ(g, col) for b, g in sel.groupby("block")},
        "up": summ(sel[sel["R"] > 0], col),
        "down": summ(sel[sel["R"] < 0], col),
        "h5": summ(sel, "net5"),
        "h60": summ(sel, "net60"),
    }
    p = res["primary"]
    ok = all(p[k].get("ci_wider", [0])[0] > 0 for k in ("2013-18", "2019-24")) and (
        p["2025-26"].get("mean", 0) > 0
    )
    res["verdict"] = "PASS" if ok else "FAIL"
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
