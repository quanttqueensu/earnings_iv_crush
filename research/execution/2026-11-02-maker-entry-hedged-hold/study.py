"""
study.py
Resting entry (15:00 mid, cancel and cross at 15:59:00) combined with the hedged event hold, on the
2025-26 broad ledger contracts. Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/execution/2026-11-02-maker-entry-hedged-hold/study.py
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

import research.execution.research_flow_liquidity as f1  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold"
CONF = (
    ROOT
    / "outputs"
    / "research"
    / "2026-11-02-hedged-event-hold"
    / "events_confirm_2025_26.parquet"
)

_s = importlib.util.spec_from_file_location("hh_confirm", HH / "confirm.py")
assert _s is not None and _s.loader is not None
cf = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cf)
st = cf.st

SCHEDULE, RULE = "penny", "strict"
ATTRITION_TOL = 0.005


def fills(e: pd.Series) -> dict:
    """Per-leg 15:59:00 bid, limit and fill under the frozen policy."""
    pre = f1._frame(
        f1._path(
            {
                "block": "broad_2025_2026",
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "kind": "pre",
            }
        )
    )
    if pre is None:
        return {"status": "no_tick_file"}
    day = pd.Timestamp(e["entry_date"]).normalize()
    if f1.is_early_close(day):
        return {"status": "early_close"}
    t15 = (day + pd.Timedelta(hours=15)).tz_localize(f1.TZ)
    t1559 = (day + pd.Timedelta(hours=15, minutes=59)).tz_localize(f1.TZ)
    out: dict = {"status": "ok", "bid": 0.0, "mid": 0.0, "improve": 0.0, "legs_filled": 0}
    for r in "CP":
        leg = pre[pre["right"] == r]
        q15 = f1._quote_at(leg, t15)
        qx = f1._quote_at(leg, t1559)
        if q15 is None or qx is None:
            return {"status": "leg_unquoted"}
        limit = f1._round_limit(sum(q15) / 2, "sell", SCHEDULE)
        tf = f1._first_fill(leg, t15, t1559, limit, "sell", RULE)
        out["bid"] += qx[0]
        out["mid"] += (qx[0] + qx[1]) / 2
        if tf is not None:
            out["improve"] += limit - qx[0]
            out["legs_filled"] += 1
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    led = pd.read_csv(
        ROOT / "outputs/research/oos_2026_ledger.csv",
        parse_dates=["entry_date", "exit_date", "expiry"],
    )
    conf = pd.read_parquet(CONF)
    conf["entry_date"] = pd.to_datetime(conf["entry_date"])
    conf_ok = conf[conf["status"] == "ok"]
    feat = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        feat[c] = pd.to_datetime(feat[c])
    j = led.merge(conf_ok[["ticker", "entry_date"]], on=["ticker", "entry_date"])
    j = j.merge(feat, on=["ticker", "entry_date"], suffixes=("", "_feat"))
    print(f"  ledger {len(led)}, confirmation ok {len(conf_ok)}, joined {len(j)}")

    tickers = sorted(j["ticker"].unique())
    ids = {t: i for i, t in enumerate(tickers)}
    paths = cf.yahoo_paths(tickers)
    st.CRSP_END = pd.Timestamp("2026-12-31")

    rows, funnel = [], Counter()
    for _, e in j.iterrows():
        fl = fills(e)
        if fl["status"] != "ok":
            funnel[fl["status"]] += 1
            continue
        r = e.copy()
        r["exit_date"] = e["exit_date"]
        r["front_expiry"], r["front_strike"] = e["expiry"], float(e["strike"])
        r["front_bid"], r["front_mid"] = fl["bid"], fl["mid"]
        r["permno"] = float(ids[e["ticker"]])
        b = st.build_event(r, paths)
        if b["status"] != "ok":
            funnel["hh_" + b["status"]] += 1
            continue
        funnel["ok"] += 1
        rows.append(
            {
                **b,
                "improve": fl["improve"] / b["m0"],
                "legs_filled": fl["legs_filled"],
                "implied_move": e["implied_move"],
            }
        )
    print("funnel:", dict(funnel))
    d = pd.DataFrame(rows)
    d["HM"] = d["H"] + d["improve"]
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")

    p1 = date_clustered_ci(d["improve"].to_numpy(float), d["exit_date"], _mean)
    p2 = date_clustered_ci(d["HM"].to_numpy(float), d["exit_date"], per_trade_sharpe)
    h_sr = date_clustered_ci(d["H"].to_numpy(float), d["exit_date"], per_trade_sharpe)
    joined_h = float(d["H"].mean())
    all_h = float(conf_ok["H"].mean())
    biased = joined_h - all_h > ATTRITION_TOL
    res = {
        "funnel": dict(funnel),
        "n": int(len(d)),
        "P1_mean_HM_minus_H": [p1.point, p1.low, p1.high],
        "P2_sharpe_HM": [p2.point, p2.low, p2.high],
        "sharpe_H_same_events": [h_sr.point, h_sr.low, h_sr.high],
        "mean_HM": float(d["HM"].mean()),
        "mean_H_joined": joined_h,
        "mean_H_all_confirmation": all_h,
        "attrition_biased": bool(biased),
        "fill_rate_both_legs": float((d["legs_filled"] == 2).mean()),
        "fill_rate_any_leg": float((d["legs_filled"] >= 1).mean()),
        "improve_by_implied_tercile": d.groupby(pd.qcut(d["implied_move"], 3, labels=False))[
            "improve"
        ]
        .mean()
        .to_dict(),
    }
    if biased:
        res["imputed_book_mean"] = all_h + p1.point
    pass1 = p1.point > 0 and p1.low > 0
    pass2 = p2.point > 0 and p2.low > 0
    res["verdict"] = (
        ("P1 PASS" if pass1 else "P1 FAIL")
        + "; "
        + ("P2 not read (ledger attrition)" if biased else ("P2 PASS" if pass2 else "P2 FAIL"))
        + "; conditional on a block partly seen"
    )
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
