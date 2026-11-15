"""
study.py
Small-cap night-minus-day spread: long close-to-open, short open-to-close. Scores the frozen
``prereg.md`` on IWM 2001-15, an unseen small-cap ETF basket, and a 10:00-forward print check.

Usage
-----
    python research/off_earnings/2026-11-02-smallcap-night-day-spread/study.py

References
----------
Berkman, H., Koch, P., Tuttle, L. and Zhang, Y. (2012) Paying attention: overnight returns and the
hidden cost of buying at the open. JFQA 47(4), 715-741.
Lou, D., Polk, C. and Skouras, S. (2019) A tug of war: overnight versus intraday expected returns.
JFE 134(1), 192-213.
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

from earnings_iv_crush.research.protocol import verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
IDX = ROOT / "research" / "off_earnings" / "2026-11-01-index-event-crush" / "study.py"

_s = importlib.util.spec_from_file_location("idx_study", IDX)
assert _s is not None and _s.loader is not None
ix = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ix)

BASKET = ("IJR", "VB", "IWN", "IWO", "VTWO")
COST = {"IWM": 1e-4, **{t: 2e-4 for t in BASKET}}
C1 = ("2001-01-02", "2015-12-31")
C2 = ("2016-01-04", "2026-10-30")


def legs(raw: pd.DataFrame, tk: str, funnel: Counter) -> pd.DataFrame:
    g = raw[tk].copy()
    g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
    g = g[g["Close"].notna()]
    o, c = g["Open"], g["Close"]
    dv, sp = g["Dividends"].fillna(0.0), g["Stock Splits"].fillna(0.0)
    d = pd.DataFrame(
        {
            "open": o,
            "close": c,
            "prev_close": c.shift(),
            "ON": (o + dv) / c.shift() - 1,
            "ID": c / o - 1,
        }
    )
    bad = (sp != 0) | ~(o > 0) | ~(c > 0) | d["prev_close"].isna()
    funnel[f"{tk}:rows"] += len(d)
    funnel[f"{tk}:dropped"] += int(bad.sum())
    d = d[~bad].copy()
    d["S"] = d["ON"] - d["ID"] - 2 * COST[tk]
    return d


def summ(v: pd.Series) -> dict:
    x = v.dropna().to_numpy(float)
    lo, hi = ix.block_ci(x)
    w = (1 + pd.Series(x)).cumprod()
    return {
        "n": int(x.size),
        "mean_bp": [x.mean() * 1e4, lo * 1e4, hi * 1e4],
        "annual_mean": float(x.mean() * 252),
        "annual_sharpe": float(x.mean() / x.std(ddof=1) * np.sqrt(252)),
        "max_dd": float((w / w.cummax() - 1).min()),
    }


def fwd(day: pd.Timestamp, snap: str) -> float | None:
    c = ix.load_chain("IWM", day, snap)
    if c is None:
        return None
    c = c[ix._two_sided(c)]
    if c.empty:
        return None
    c = c[c["expiry"] == c["expiry"].min()]
    piv = c.assign(mid=(c["bid"] + c["ask"]) / 2).pivot_table(
        index="strike", columns="cp", values="mid"
    )
    if not {"C", "P"} <= set(piv.columns):
        return None
    piv = piv[["C", "P"]].dropna()
    if piv.empty:
        return None
    k = float((piv["C"] - piv["P"]).abs().idxmin())
    return k + float(piv.loc[k, "C"] - piv.loc[k, "P"])


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    import yfinance as yf

    tickers = ["IWM", *BASKET, "SPY"]
    raw = yf.download(
        tickers,
        start="2000-06-01",
        end="2026-11-05",
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="ticker",
    )
    funnel: Counter = Counter()
    L = {t: legs(raw, t, funnel) for t in ["IWM", *BASKET]}
    spy = raw["SPY"]["Close"].copy()
    spy.index = pd.to_datetime(spy.index).tz_localize(None).normalize()
    spy_r = spy.pct_change()
    res: dict = {"funnel": dict(funnel)}

    # ── criterion 1: IWM 2001-15 ──
    iwm = L["IWM"].loc[C1[0] : C1[1]]
    res["c1_iwm_2001_15"] = summ(iwm["S"])
    res["c1_legs"] = {
        "ON_net": summ(iwm["ON"] - COST["IWM"]),
        "ID_short_net": summ(-iwm["ID"] - COST["IWM"]),
    }
    res["c1_sub"] = {"2001-07": summ(iwm.loc[:"2007", "S"]), "2008-15": summ(iwm.loc["2008":, "S"])}

    # ── criterion 2: basket 2016-26 ──
    S = pd.DataFrame({t: L[t].loc[C2[0] : C2[1], "S"] for t in BASKET})
    cnt = S.notna().sum(axis=1)
    funnel["basket_sessions_lt3"] = int((cnt < 3).sum())
    bsk = S[cnt >= 3].mean(axis=1)
    res["c2_basket"] = summ(bsk)
    res["c2_per_etf"] = {t: summ(S[t]) for t in BASKET}
    res["c2_cost0"] = summ(bsk + 2 * 2e-4)
    res["c2_cost2x"] = summ(bsk - 2 * 2e-4)
    res["c2_corr_spy"] = float(pd.concat([bsk, spy_r], axis=1).dropna().corr().iloc[0, 1])

    # ── criterion 3: IWM 10:00-forward print check ──
    w = L["IWM"].loc[C2[0] : C2[1]]
    rows, f3 = [], Counter()
    for t, r in w.iterrows():
        f = fwd(t, "1000")
        if f is None or not np.isfinite(f) or f <= 0:
            f3["no_forward"] += 1
            continue
        f3["ok"] += 1
        # ON = (O + D) / C_prev - 1, so the dividend is recovered as D = (1 + ON) C_prev - O
        div = (1 + r["ON"]) * r["prev_close"] - r["open"]
        on10 = (f + div) / r["prev_close"] - 1
        id10 = r["close"] / f - 1
        rows.append(
            {
                "date": t,
                "ON10": on10,
                "ID10": id10,
                "S10": on10 - id10 - 2 * COST["IWM"],
                "S": r["S"],
                "open_vs_fwd10": r["open"] / f - 1,
            }
        )
    res["c3_funnel"] = dict(f3)
    d3 = pd.DataFrame(rows).set_index("date")
    res["c3_iwm_fwd10"] = summ(d3["S10"])
    res["c3_iwm_open_same_sessions"] = summ(d3["S"])
    res["c3_legs"] = {
        "ON10_net": summ(d3["ON10"] - COST["IWM"]),
        "ID10_short_net": summ(-d3["ID10"] - COST["IWM"]),
    }

    ok1 = res["c1_iwm_2001_15"]["mean_bp"][1] > 0
    ok2 = res["c2_basket"]["mean_bp"][1] > 0
    ok3 = res["c3_iwm_fwd10"]["mean_bp"][0] > 0
    res["criteria"] = {"c1": ok1, "c2": ok2, "c3": ok3}
    res["verdict"] = "PASS" if ok1 and ok2 and ok3 else "FAIL"
    OUT.mkdir(parents=True, exist_ok=True)
    d3.to_parquet(OUT / "iwm_fwd10.parquet")
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(res, indent=1, default=lambda x: round(x, 4) if isinstance(x, float) else str(x))
    )
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
