"""
study.py
Fade reaction-day earnings gaps larger than the option-implied move, open to close, on events no
earlier stream observed. Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-implied-move-gap-fade/study.py

References
----------
Berkman, H., Koch, P., Tuttle, L. and Zhang, Y. (2012) Paying attention: overnight returns and the
hidden cost of buying at the open. JFQA 47(4), 715-741.
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
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
COST = 10e-4
SPLITS = {"2013-18": (2013, 2018), "2019-24": (2019, 2024), "2025-26": (2025, 2026)}


def bars(tickers: list[str]) -> dict[str, pd.DataFrame]:
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
            g = raw[t].dropna(subset=["Open", "Close"])
        except KeyError:
            continue
        if g.empty:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = g[["Open", "Close"]]
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def build(ev: pd.DataFrame, px: dict[str, pd.DataFrame], spy: pd.DataFrame) -> pd.DataFrame:
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
        c0, o1, c1 = g.loc[t0, "Close"], g.loc[t1, "Open"], g.loc[t1, "Close"]
        gap = o1 / c0 - 1
        oc = c1 / o1 - 1
        m_oc = spy.loc[t1, "Close"] / spy.loc[t1, "Open"] - 1
        s = -np.sign(gap)
        funnel["ok"] += 1
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": t0,
                "exit_date": t1,
                "block": e["block"],
                "gap": gap,
                "im": e["implied_move"],
                "ratio": abs(gap) / e["implied_move"],
                "net": s * oc - COST,
                "net_mkt": s * (oc - m_oc) - COST,
                "up": gap > 0,
            }
        )
    print("funnel:", dict(funnel))
    return pd.DataFrame(rows), dict(funnel)


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
    seen = seen[seen["status"] == "ok"][["ticker", "entry_date"]]
    seen["entry_date"] = pd.to_datetime(seen["entry_date"])
    seen["seen"] = True
    ev = ev.merge(seen.drop_duplicates(), on=["ticker", "entry_date"], how="left")
    ev["seen"] = ev["seen"].fillna(False).astype(bool)
    test = ev[~ev["seen"]]
    print(f"  events {len(ev)}, test (unseen) {len(test)}, seen {int(ev['seen'].sum())}")
    px = bars(sorted(ev["ticker"].unique()) + ["SPY"])
    spy = px["SPY"]
    d, funnel = build(test, px, spy)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "test_events.parquet")
    sel = d[d["ratio"] > 1]
    res: dict = {
        "funnel_test": funnel,
        "n_test_ok": int(len(d)),
        "selected_share": float((d["ratio"] > 1).mean()),
    }
    res["primary"] = summ(sel)
    d["year"] = d["exit_date"].dt.year
    sel = d[d["ratio"] > 1]
    res["splits"] = {k: summ(sel[sel["year"].between(*v)]) for k, v in SPLITS.items()}
    res["secondary"] = {
        "unconditional_fade": summ(d),
        "ratio_gt_2": summ(d[d["ratio"] > 2]),
        "selected_spy_adjusted": summ(sel, "net_mkt"),
        "selected_gap_up": summ(sel[sel["up"]]),
        "selected_gap_down": summ(sel[~sel["up"]]),
        "by_block": {b: summ(g) for b, g in sel.groupby("block")},
    }
    pm = res["primary"]["mean"]
    pos_splits = sum(1 for v in res["splits"].values() if v.get("mean", [0])[0] > 0)
    ok = pm[1] > 0 and res["primary"]["sharpe"] > 0 and pos_splits >= 2
    res["verdict"] = "PASS" if ok else "FAIL"
    # in-sample comparison on the stream-3 events, labelled as such
    s_ev = ev[ev["seen"]]
    ds, fs = build(s_ev, px, spy)
    res["in_sample_seen_events"] = {
        "funnel": fs,
        "selected": summ(ds[ds["ratio"] > 1]),
        "unconditional": summ(ds),
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
