"""
study.py
Follow reaction-day gaps larger than the implied move in the most liquid broad names, open to close.
Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-gap-continuation-size/study.py

References
----------
Gao, L., Han, Y., Li, S. Z. and Zhou, G. (2018) Market intraday momentum. JFE 129(2), 394-414.
Berkman, H., Koch, P., Tuttle, L. and Zhang, Y. (2012) Paying attention. JFQA 47(4), 715-741.
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

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
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
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
COST = 10e-4
ADV_WIN, ADV_MIN = 60, 50
N_BINS, MIN_PRIOR = 5, 200
SPLITS = {"2013-18": (2013, 2018), "2019-24": (2019, 2024), "2025-26": (2025, 2026)}


def bars(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2012-06-01",
        end="2026-11-01",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out = {}
    for t in tickers:
        try:
            g = raw[t].dropna(subset=["Open", "Close"])
        except KeyError:
            continue
        if g.empty:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        g = g[["Open", "Close", "Volume"]].copy()
        g["dv"] = g["Close"] * g["Volume"]
        out[t] = g
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def summ(x: pd.DataFrame, col: str = "net") -> dict:
    if len(x) < 5:
        return {"n": int(len(x))}
    ci = date_clustered_ci(x[col].to_numpy(float), x["exit_date"], _mean)
    return {
        "n": int(len(x)),
        "mean": [ci.point, ci.low, ci.high],
        "sharpe": per_trade_sharpe(x[col]),
    }


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = pd.read_parquet(EVENTS)[["ticker", "entry_date", "exit_date", "block", "implied_move"]]
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    seen = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ]
    )
    seen = seen[seen["status"] == "ok"][["ticker", "entry_date"]].drop_duplicates()
    seen["entry_date"] = pd.to_datetime(seen["entry_date"])
    ev = ev.merge(seen, on=["ticker", "entry_date"])
    print(f"  broad events {len(ev)}")
    px = bars(sorted(ev["ticker"].unique()) + ["SPY"])
    spy = px["SPY"]
    rows, funnel = [], Counter()
    for _, e in ev.iterrows():
        g = px.get(e["ticker"])
        t0, t1 = e["entry_date"], e["exit_date"]
        if g is None:
            funnel["no_name"] += 1
            continue
        if t0 not in g.index or t1 not in g.index or t1 not in spy.index:
            funnel["no_session"] += 1
            continue
        if not np.isfinite(e["implied_move"]) or e["implied_move"] <= 0:
            funnel["no_implied"] += 1
            continue
        past = g.loc[g.index < t0, "dv"].tail(ADV_WIN).dropna()
        adv = float(past.mean()) if len(past) >= ADV_MIN else np.nan
        c0, o1, c1 = g.loc[t0, "Close"], g.loc[t1, "Open"], g.loc[t1, "Close"]
        gap = o1 / c0 - 1
        oc = c1 / o1 - 1
        m_oc = spy.loc[t1, "Close"] / spy.loc[t1, "Open"] - 1
        s = np.sign(gap)
        funnel["ok" if np.isfinite(adv) else "ok_no_adv"] += 1
        rows.append(
            {
                "ticker": e["ticker"],
                "exit_date": t1,
                "gap": gap,
                "ratio": abs(gap) / e["implied_move"],
                "adv": adv,
                "net": s * oc - COST,
                "net_mkt": s * (oc - m_oc) - COST,
                "up": gap > 0,
            }
        )
    print("funnel:", dict(funnel))
    d = pd.DataFrame(rows).sort_values("exit_date").reset_index(drop=True)
    d["q"] = causal_bins(d["adv"].to_numpy(float), d["exit_date"], N_BINS, MIN_PRIOR)
    d["year"] = d["exit_date"].dt.year
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")
    big = d[(d["ratio"] > 1) & (d["q"] >= 0)]
    sel = big[big["q"] == N_BINS - 1]
    res: dict = {"funnel": dict(funnel), "n_big_assigned": int(len(big))}
    res["primary"] = summ(sel)
    res["splits"] = {k: summ(sel[sel["year"].between(*v)]) for k, v in SPLITS.items()}
    res["by_quintile"] = {int(k): summ(g) for k, g in big.groupby("q")}
    res["secondary"] = {
        "spy_adjusted": summ(sel, "net_mkt"),
        "gap_up": summ(sel[sel["up"]]),
        "gap_down": summ(sel[~sel["up"]]),
    }
    pm = res["primary"]["mean"]
    pos = sum(1 for v in res["splits"].values() if v.get("mean", [0])[0] > 0)
    res["verdict"] = "PASS" if (pm[1] > 0 and res["primary"]["sharpe"] > 0 and pos >= 2) else "FAIL"
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
