"""
study.py
Later expiry versus front expiry for the hedged event hold, paired on the same events. Scores the
frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-later-expiry-hedged-hold/study.py
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

from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402
from earnings_iv_crush.research.hedged_hold import atm_quote  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HHO = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
HH = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold"

_s = importlib.util.spec_from_file_location("hh_confirm", HH / "confirm.py")
assert _s is not None and _s.loader is not None
cf = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cf)
st = cf.st

MIN_GAP_DAYS, MAX_GAP_DAYS = 7, 60
BLOCKS = {"2013-18": (2013, 2018), "2019-24": (2019, 2024), "2025-26": (2025, 2026)}


def later_row(r: pd.Series) -> tuple[str, pd.Series | None]:
    p = st.CHAINS / f"{r['ticker']}_{pd.Timestamp(r['entry_date']).date()}.parquet"
    if not p.exists():
        return "no_entry_chain", None
    ch = _parse_chain(pd.read_parquet(p).reset_index())
    if ch is None:
        return "no_entry_chain", None
    fe = pd.Timestamp(r["front_expiry"])
    exps = sorted(
        e
        for e in ch["expiry"].unique()
        if fe + pd.Timedelta(days=MIN_GAP_DAYS) <= e <= fe + pd.Timedelta(days=MAX_GAP_DAYS)
    )
    if not exps:
        return "no_later_expiry", None
    q = atm_quote(ch, pd.Timestamp(exps[0]), pd.Timestamp(r["entry_date"]))
    if q is None or not q.bid > 0:
        return "no_two_sided_pair", None
    out = r.copy()
    out["front_expiry"], out["front_t"], out["front_fwd"] = q.expiry, q.t, q.fwd
    out["front_strike"], out["front_bid"], out["front_mid"] = q.strike, q.bid, q.mid
    out["front_ask"], out["front_iv"] = q.ask, q.iv
    return "ok", out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _sr_diff_ci(x: np.ndarray, y: np.ndarray, dates: pd.Series):
    idx = np.arange(len(x), dtype=float)

    def stat(ii: np.ndarray) -> float:
        k = ii.astype(int)
        return per_trade_sharpe(x[k]) - per_trade_sharpe(y[k])

    return date_clustered_ci(idx, dates, stat)


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    a = pd.read_parquet(HHO / "events.parquet")
    b = pd.read_parquet(HHO / "events_confirm_2025_26.parquet")
    a["src"], b["src"] = "crsp", "yahoo"
    h = pd.concat([a, b], ignore_index=True)
    h = h[h["status"] == "ok"].copy()
    h["entry_date"] = pd.to_datetime(h["entry_date"])
    f = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    j = h[["ticker", "entry_date", "src", "H", "m0", "s0"]].merge(
        f, on=["ticker", "entry_date"], how="left"
    )
    print(f"  arm-H events {len(j)}")

    crsp = st.load_crsp()
    y_t = sorted(j.loc[j["src"] == "yahoo", "ticker"].unique())
    y_ids = {t: i for i, t in enumerate(y_t)}
    ypaths = cf.yahoo_paths(y_t)

    rows, funnel = [], Counter()
    for i, (_, r) in enumerate(j.iterrows()):
        s, lr = later_row(r)
        if s != "ok" or lr is None:
            funnel[s] += 1
            continue
        if r["src"] == "crsp":
            st.CRSP_END = pd.Timestamp("2024-12-31")
            res = st.build_event(lr, crsp)
        else:
            st.CRSP_END = pd.Timestamp("2026-12-31")
            lr = lr.copy()
            lr["permno"] = float(y_ids[r["ticker"]])
            res = st.build_event(lr, ypaths)
        if res["status"] != "ok":
            funnel["L_" + res["status"]] += 1
            continue
        funnel["ok"] += 1
        h_usd = r["H"] * r["m0"]
        l_usd = res["H"] * res["m0"]
        mc = 0.20 * float(r["front_fwd"]) + max(float(r["s0"]), float(res["s0"]))
        rows.append(
            {
                "ticker": r["ticker"],
                "entry_date": r["entry_date"],
                "exit_date": r["exit_date"],
                "H": h_usd / mc,
                "L": l_usd / mc,
                "L_mid": res["H_mid"] * res["m0"] / mc,
                "entry_cost_L": (res["mid0"] - res["s0"]) / mc,
                "entry_cost_H": (float(r["front_mid"]) - float(r["s0"])) / mc,
                "days_L": res["hold_days"],
                "implied_move": float(r["front_mid"]) / float(r["front_fwd"]),
                "peak_hedge_L": res["peak_hedge_notional"] / mc,
            }
        )
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{len(j)}", flush=True)
    print("funnel:", dict(funnel))
    d = pd.DataFrame(rows)
    d["year"] = pd.to_datetime(d["entry_date"]).dt.year
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")

    res_all: dict = {"funnel": dict(funnel)}
    for name, (y0, y1) in BLOCKS.items():
        s = d[d["year"].between(y0, y1)]
        p1 = date_clustered_ci((s["L"] - s["H"]).to_numpy(float), s["exit_date"], _mean)
        p2 = _sr_diff_ci(s["L"].to_numpy(float), s["H"].to_numpy(float), s["exit_date"])
        res_all[name] = {
            "n": int(len(s)),
            "P1_mean_L_minus_H": [p1.point, p1.low, p1.high],
            "P2_sharpe_L_minus_H": [p2.point, p2.low, p2.high],
            "sharpe_L": per_trade_sharpe(s["L"]),
            "sharpe_H": per_trade_sharpe(s["H"]),
            "mean_L": float(s["L"].mean()),
            "mean_H": float(s["H"].mean()),
            "mean_L_mid": float(s["L_mid"].mean()),
            "extra_entry_cost": float((s["entry_cost_L"] - s["entry_cost_H"]).mean()),
            "median_days_L": float(s["days_L"].median()),
        }
    p = {k: res_all[k]["P1_mean_L_minus_H"] for k in BLOCKS}
    q = {k: res_all[k]["P2_sharpe_L_minus_H"] for k in BLOCKS}
    if (
        p["2013-18"][1] > 0
        and p["2019-24"][1] > 0
        and p["2025-26"][0] > 0
        and q["2013-18"][0] >= 0
        and q["2019-24"][0] >= 0
    ):
        v = "LATER EXPIRY"
    elif p["2013-18"][2] < 0 and p["2019-24"][2] < 0:
        v = "FRONT EXPIRY"
    else:
        v = "NO DIFFERENCE"
    res_all["verdict"] = v
    (OUT / "results.json").write_text(json.dumps(res_all, indent=2), encoding="utf-8")
    print(json.dumps(res_all, indent=2))
    print("VERDICT:", v)


if __name__ == "__main__":
    main()
