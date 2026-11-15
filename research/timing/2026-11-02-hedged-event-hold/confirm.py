"""
confirm.py
Amendment 01 of the hedged event hold: the 2025-26 confirmation block on free Yahoo Finance stock
bars, after checking the Yahoo data path against CRSP on the 2024 events.

Usage
-----
    python research/timing/2026-11-02-hedged-event-hold/confirm.py
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
RECORD = ROOT / "outputs" / "research" / "prereg_2026-11-02-hedged-event-hold-amendment-01.json"
OUT = ROOT / "outputs" / "research" / HERE.name

_spec = importlib.util.spec_from_file_location("hedged_event_hold_study", HERE / "study.py")
assert _spec is not None and _spec.loader is not None
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)

# ── frozen constants (amendment 01) ─────────────────────────────────────────

YAHOO_HALF_SPREAD = 3e-4  # 90th percentile of CRSP 2024 closing half-spreads is 2.93 bp
CHECK_MAE, CHECK_CORR = 0.0025, 0.98  # data-path tolerance on H, unit m0
CONF_START = pd.Timestamp("2025-01-01")


def yahoo_paths(tickers: list[str]) -> dict[int, pd.DataFrame]:
    """CRSP-shaped frames (prc, ret, bid, ask, cfacpr) keyed by a per-ticker integer id."""
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2023-11-01",
        end="2026-11-01",
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out: dict[int, pd.DataFrame] = {}
    missing = []
    for i, t in enumerate(tickers):
        try:
            g = raw[t].dropna(subset=["Close"])
        except KeyError:
            missing.append(t)
            continue
        if g.empty:
            missing.append(t)
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        sp = g.get("Stock Splits", pd.Series(0.0, index=g.index)).replace(0.0, 1.0).fillna(1.0)
        # factor after d: product of split ratios with ex-date strictly after d
        after = sp[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        prc = g["Close"] * after
        out[i] = pd.DataFrame(
            {
                "prc": prc,
                "ret": g["Adj Close"].pct_change(),
                "bid": prc * (1 - YAHOO_HALF_SPREAD),
                "ask": prc * (1 + YAHOO_HALF_SPREAD),
                "cfacpr": after,
            }
        )
    print(f"  yahoo: {len(out)} of {len(tickers)} tickers with bars; missing {missing[:20]}")
    return out


def build(rows: pd.DataFrame, paths: dict[int, pd.DataFrame], ids: dict[str, int]) -> pd.DataFrame:
    st.CRSP_END = pd.Timestamp("2026-12-31")
    out = []
    for _, r in rows.iterrows():
        r = r.copy()
        r["permno"] = float(ids.get(r["ticker"], -1))
        out.append(st.build_event(r, paths))
    return pd.DataFrame(out)


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def main() -> None:
    print(f"amendment verified, sha256 {verify_prereg(AMEND, RECORD)[:12]}")
    f = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    crsp_built = pd.read_parquet(OUT / "events.parquet")
    chk_keys = crsp_built[
        (crsp_built["status"] == "ok") & (pd.to_datetime(crsp_built["entry_date"]).dt.year == 2024)
    ][["ticker", "entry_date", "H"]]
    conf = f[f["entry_date"] >= CONF_START]
    chk = f.merge(chk_keys[["ticker", "entry_date"]], on=["ticker", "entry_date"])
    tickers = sorted(set(conf["ticker"]) | set(chk["ticker"]))
    ids = {t: i for i, t in enumerate(tickers)}
    paths = yahoo_paths(tickers)

    # data-path check on 2024
    yb = build(chk, paths, ids)
    m = chk_keys.reset_index(drop=True).join(yb[["status", "H"]].add_prefix("y_"))
    m = m[m["y_status"] == "ok"]
    mae = float((m["H"] - m["y_H"]).abs().mean())
    corr = float(m["H"].corr(m["y_H"]))
    passed = mae <= CHECK_MAE and corr >= CHECK_CORR
    print(
        f"  data-path check 2024: N={len(m)} of {len(chk_keys)}, MAE {mae:.5f}, corr {corr:.4f}, "
        f"{'PASS' if passed else 'FAIL'}"
    )

    d = build(conf, paths, ids)
    d.to_parquet(OUT / "events_confirm_2025_26.parquet")
    print("funnel 2025-26:")
    for k, v in Counter(d["status"]).most_common():
        print(f"  {k:24s} {v}")
    ok = d[d["status"] == "ok"].copy()
    ok["b_defined"] = ok["b_defined"].astype(bool)
    pb = ok[ok["b_defined"]]
    res = {
        "data_path_check": {"n": int(len(m)), "mae": mae, "corr": corr, "passed": passed},
        "funnel": dict(Counter(d["status"])),
        "n_ok": int(len(ok)),
        "n_paired": int(len(pb)),
    }
    for name, x, dates, stat in (
        ("P1_mean_H_minus_B", pb["H"] - pb["B"], pb["exit_date"], _mean),
        ("P2_sharpe_H", ok["H"], ok["exit_date"], per_trade_sharpe),
        ("P2_mean_H", ok["H"], ok["exit_date"], _mean),
        ("B_sharpe", pb["B"], pb["exit_date"], per_trade_sharpe),
        ("B_mean", pb["B"], pb["exit_date"], _mean),
    ):
        iv = date_clustered_ci(x.to_numpy(float), dates, stat)
        res[name] = {
            "point": iv.point,
            "low": iv.low,
            "high": iv.high,
            "n": iv.n,
            "clusters": iv.clusters,
        }
    res["H_mid_mean"] = float(ok["H_mid"].mean())
    p1, p2 = res["P1_mean_H_minus_B"], res["P2_sharpe_H"]
    if not passed:
        verdict = "DATA PATH NOT VALIDATED (verdict not read)"
    else:
        lever = p1["point"] > 0 and p1["low"] > 0
        book = p2["point"] > 0 and p2["low"] > 0
        verdict = (
            ("exit lever CONFIRMED" if lever else "exit lever NOT confirmed")
            + "; "
            + ("book CONFIRMED" if book else "book not confirmed")
        )
    res["verdict"] = verdict
    (OUT / "results_confirm_2025_26.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
