"""
study.py
Open hedge versus close hedge for the hedged event hold: does starting the stock hedge at the
reaction session's open beat waiting for its close? Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-open-hedge/study.py

References
----------
Berkman, H., Koch, P., Tuttle, L. and Zhang, Y. (2012) Paying attention: overnight returns and the
hidden cost of buying at the open. JFQA 47(4).
Liu, Hope and Hu (2023) Journal of Corporate Finance, overnight versus intraday earnings reactions.
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

from earnings_iv_crush.research.hedged_hold import straddle_delta, year_frac  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"

OPEN_HS, CLOSE_HS = 5e-4, 3e-4  # opening-auction and closing half-spreads, frozen
RATIO_BOUNDS = (0.5, 2.0)
BLOCKS = {"2013-18": (2013, 2018), "2019-24": (2019, 2024), "2025-26": (2025, 2026)}


def yahoo(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2013-01-01",
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
            g = raw[t].dropna(subset=["Close", "Open"])
        except KeyError:
            continue
        if g.empty:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        sp = g["Stock Splits"].replace(0.0, 1.0).fillna(1.0)
        after = sp[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        out[t] = pd.DataFrame(
            {
                "oc": g["Open"] / g["Close"],
                "close_at": g["Close"] * after,
                "gap": g["Open"] / g["Close"].shift(1) - 1,
            }
        )
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _sr_diff_ci(ho: np.ndarray, h: np.ndarray, dates: pd.Series):
    """Bootstrap the Sharpe difference by resampling event indices within whole dates."""
    idx = np.arange(len(ho), dtype=float)

    def stat(ii: np.ndarray) -> float:
        k = ii.astype(int)
        return per_trade_sharpe(ho[k]) - per_trade_sharpe(h[k])

    return date_clustered_ci(idx, dates, stat)


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    a = pd.read_parquet(HH / "events.parquet")
    b = pd.read_parquet(HH / "events_confirm_2025_26.parquet")
    a["src"], b["src"] = "crsp", "yahoo"
    d = pd.concat([a, b], ignore_index=True)
    d = d[d["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c])
    f = pd.read_parquet(FEATURES)[
        ["ticker", "entry_date", "permno", "jsplit_sd2", "jsplit_valid", "s1_iv", "front_iv"]
    ]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = d.merge(
        f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    ev = pd.read_parquet(EVENTS)[["ticker", "entry_date", "is_amc"]]
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    d = d.merge(
        ev.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    print(
        f"  hedged-hold ok events: {len(d)} (crsp {int((d.src == 'crsp').sum())}, "
        f"yahoo {int((d.src == 'yahoo').sum())})"
    )

    c = pd.read_parquet(CRSP)
    c["prc"] = pd.to_numeric(c["prc"], errors="coerce").astype(float).abs()
    c["date"] = pd.to_datetime(c["date"])
    crsp_close = c.set_index(["permno", "date"])["prc"]
    y = yahoo(sorted(d["ticker"].unique()))
    print(f"  yahoo bars for {len(y)} of {d['ticker'].nunique()} names")

    rows, funnel = [], Counter()
    for _, r in d.iterrows():
        g = y.get(r["ticker"])
        t1 = r["exit_date"]
        if g is None:
            funnel["no_yahoo_name"] += 1
            continue
        if t1 not in g.index:
            funnel["no_yahoo_session"] += 1
            continue
        oc = float(g.at[t1, "oc"])
        if not (RATIO_BOUNDS[0] <= oc <= RATIO_BOUNDS[1]):
            funnel["bad_ratio"] += 1
            continue
        if r["src"] == "crsp":
            key = (int(r["permno"]), t1)
            if key not in crsp_close.index:
                funnel["no_crsp_close"] += 1
                continue
            cl = float(crsp_close.loc[key])
        else:
            cl = float(g.at[t1, "close_at"])
        o = cl * oc
        if r.get("jsplit_valid") and np.isfinite(r["jsplit_sd2"]) and r["jsplit_sd2"] > 0:
            sig = float(np.sqrt(r["jsplit_sd2"]))
        elif np.isfinite(r.get("s1_iv", np.nan)):
            sig = float(r["s1_iv"])
        else:
            sig = float(r["front_iv"])
        tau = year_frac(t1, r["expiry"])
        d_o = straddle_delta(o, r["strike"], tau, sig)
        add = (d_o * (cl - o) - OPEN_HS * abs(d_o) * o - CLOSE_HS * abs(d_o) * cl) / r["m0"]
        funnel["ok"] += 1
        rows.append(
            {
                "ticker": r["ticker"],
                "entry_date": r["entry_date"],
                "exit_date": t1,
                "H": r["H"],
                "HO": r["H"] + add,
                "add": add,
                "d_o": d_o,
                "gap": float(g.at[t1, "gap"]),
                "is_amc": r["is_amc"],
            }
        )
    print("funnel:", dict(funnel))
    z = pd.DataFrame(rows)
    z["year"] = z["entry_date"].dt.year
    OUT.mkdir(parents=True, exist_ok=True)
    z.to_parquet(OUT / "events.parquet")

    disc = z[z["year"] <= 2018]
    cuts = np.quantile(disc["gap"].abs().dropna(), [1 / 3, 2 / 3])
    z["gap_t"] = np.digitize(z["gap"].abs(), cuts)
    res: dict = {"funnel": dict(funnel), "gap_cuts_2013_18": cuts.tolist()}
    for name, (y0, y1) in BLOCKS.items():
        s = z[z["year"].between(y0, y1)]
        p1 = date_clustered_ci(s["add"].to_numpy(float), s["exit_date"], _mean)
        p2 = _sr_diff_ci(s["HO"].to_numpy(float), s["H"].to_numpy(float), s["exit_date"])
        r = {
            "n": int(len(s)),
            "P1_mean_HO_minus_H": [p1.point, p1.low, p1.high],
            "P2_sharpe_HO_minus_H": [p2.point, p2.low, p2.high],
            "sharpe_H": per_trade_sharpe(s["H"]),
            "sharpe_HO": per_trade_sharpe(s["HO"]),
            "by_gap_tercile": {
                str(k): [int(len(g)), float(g["add"].mean())] for k, g in s.groupby("gap_t")
            },
            "by_gap_sign": {
                ("up" if k else "down"): [int(len(g)), float(g["add"].mean())]
                for k, g in s.groupby(s["gap"] > 0)
            },
            "by_amc": {
                str(k): [int(len(g)), float(g["add"].mean())] for k, g in s.groupby("is_amc")
            },
        }
        res[name] = r
    p = {k: res[k]["P1_mean_HO_minus_H"] for k in BLOCKS}
    if p["2013-18"][1] > 0 and p["2019-24"][1] > 0 and p["2025-26"][0] > 0:
        v = "OPEN HEDGE"
    elif p["2013-18"][2] < 0 and p["2019-24"][2] < 0 and p["2025-26"][0] < 0:
        v = "WAIT FOR THE CLOSE"
    else:
        q = [res[k]["P2_sharpe_HO_minus_H"] for k in ("2013-18", "2019-24")]
        if all(x[1] > 0 for x in q):
            v = "NO TIMING EFFECT; open hedge reduces risk (P2)"
        elif all(x[2] < 0 for x in q):
            v = "NO TIMING EFFECT; close hedge has the better Sharpe (P2)"
        else:
            v = "NO TIMING EFFECT"
    res["verdict"] = v
    (OUT / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(f"VERDICT: {v}")


if __name__ == "__main__":
    main()
