"""
confirm.py
Amendment 01 of the smile-strike study: the 2025-26 confirmation block on Yahoo stock paths.

Usage
-----
    python research/execution/2026-11-02-smile-strike-hedged-hold/confirm.py
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

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
AMEND = HERE / "amendment_01_confirmation.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}-amendment-01.json"
CONF = (
    ROOT
    / "outputs"
    / "research"
    / "2026-11-02-hedged-event-hold"
    / "events_confirm_2025_26.parquet"
)


def _load(name: str, path: Path):
    s = importlib.util.spec_from_file_location(name, path)
    assert s is not None and s.loader is not None
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


sm = _load("smile_study", HERE / "study.py")
cf = _load(
    "hh_confirm", ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "confirm.py"
)


def main() -> None:
    print(f"amendment verified, sha256 {verify_prereg(AMEND, RECORD)[:12]}")
    ev = pd.read_parquet(CONF)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    tickers = sorted(ev["ticker"].unique())
    ids = {t: i for i, t in enumerate(tickers)}
    paths = cf.yahoo_paths(tickers)
    ev["permno"] = ev["ticker"].map(ids).astype(float)
    print(f"  H events {len(ev)}")
    g = pd.DataFrame([sm.build_g(e, paths) for _, e in ev.iterrows()])
    funnel = dict(Counter(g["status"]))
    print("funnel:", funnel)
    d = ev.merge(g, on=["ticker", "entry_date"], how="left", suffixes=("", "_g"))
    d.to_parquet(sm.OUT / "events_confirm_2025_26.parquet")
    ok = d[d["status_g"] == "ok"]
    p1 = date_clustered_ci(ok["G"].to_numpy(float), ok["exit_date"], per_trade_sharpe)
    p2 = sm._sr_diff_ci(ok["G"].to_numpy(float), ok["H"].to_numpy(float), ok["exit_date"])
    bins = pd.cut(ok["move_ratio"], [0, 0.5, 1, 1.5, 2, np.inf])
    gap = float(ok["H"].mean() - d["H"].mean())
    res = {
        "funnel": funnel,
        "n_h": int(len(d)),
        "n_g": int(len(ok)),
        "P1_sharpe_G": [p1.point, p1.low, p1.high],
        "P2_sharpe_G_minus_H": [p2.point, p2.low, p2.high],
        "sharpe_H_same": per_trade_sharpe(ok["H"]),
        "mean_G": float(ok["G"].mean()),
        "mean_G_mid": float(ok["G_mid"].mean()),
        "mean_H_same": float(ok["H"].mean()),
        "attrition_gap": gap,
        "fallback_share": float((ok["src"] == "entry_iv_fallback").mean()),
        "G_half_spread_frac_med": float(ok["G_half_spread_frac"].median()),
        "G_minus_H_by_move_ratio": {
            str(k): [float(v.mean()), int(len(v))]
            for k, v in (ok["G"] - ok["H"]).groupby(bins, observed=True)
        },
    }
    res["verdict"] = ("CONFIRMED" if p2.low > 0 else "NOT CONFIRMED") + (
        "; attrition-biased" if gap > sm.ATTRITION_TOL else ""
    )
    (sm.OUT / "results_confirm_2025_26.json").write_text(
        json.dumps(res, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
