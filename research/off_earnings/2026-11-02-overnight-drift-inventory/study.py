"""
study.py
Overnight index drift after intraday selling: buy at the close auction when the 15:59 intraday
return is in the bottom causal tercile, sell at the next open. Scores the frozen ``prereg.md``.

Usage
-----
    python research/off_earnings/2026-11-02-overnight-drift-inventory/study.py

References
----------
Boyarchenko, N., Larsen, L. and Whelan, P. (2023) The overnight drift. RFS 36(9), 3502-3547.
Lou, D., Polk, C. and Skouras, S. (2019) A tug of war: overnight versus intraday expected returns.
JFE 134(1), 192-213.
Cliff, M., Cooper, M. and Gulen, H. (2008) Return differences between trading and non-trading
hours: like night and day. Working paper.
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

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    matched_random_null,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
IDX = ROOT / "research" / "off_earnings" / "2026-11-01-index-event-crush" / "study.py"

_s = importlib.util.spec_from_file_location("idx_study", IDX)
assert _s is not None and _s.loader is not None
ix = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ix)

COST = 1e-4  # round trip, auction fills
SEED_START, SEED_END = "2010-01-04", "2015-12-31"
MIN_PRIOR = 250


# ── data ──
def yahoo() -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(
        list(ix.TICKERS),
        start=SEED_START,
        end="2026-11-05",
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="ticker",
    )
    out = {}
    for t in ix.TICKERS:
        g = raw[t].dropna(subset=["Close", "Open"]).copy()
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = pd.DataFrame(
            {
                "open": g["Open"],
                "close": g["Close"],
                "div": g["Dividends"].fillna(0.0),
                "split": g["Stock Splits"].fillna(0.0),
            }
        )
    return out


def forward_1559(tk: str, day: pd.Timestamp) -> float | None:
    c = ix.load_chain(tk, day, "1559")
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


def sessions(tk: str, px: pd.DataFrame) -> tuple[pd.DataFrame, Counter]:
    funnel: Counter = Counter()
    days = sorted(
        pd.Timestamp(p.name.split("_")[1]) for p in ix.CHAINS.glob(f"{tk}_*_1559.parquet")
    )
    idx = px.index
    rows = []
    for t in days:
        funnel["snapshot"] += 1
        if t not in idx:
            funnel["no_yahoo_t"] += 1
            continue
        i = idx.get_loc(t)
        if i + 1 >= len(idx):
            funnel["no_next"] += 1
            continue
        t1 = idx[i + 1]
        if px["split"].iloc[i + 1] != 0:
            funnel["split"] += 1
            continue
        f = forward_1559(tk, t)
        if f is None or not np.isfinite(f) or f <= 0:
            funnel["no_forward"] += 1
            continue
        o, c = px["open"].iloc[i], px["close"].iloc[i]
        on = (px["open"].iloc[i + 1] + px["div"].iloc[i + 1]) / c - 1
        rows.append(
            {
                "ticker": tk,
                "date": t,
                "next": t1,
                "r_id": f / o - 1,
                "r_id_close": c / o - 1,
                "ON": on,
                "weekday": int(t.weekday()),
            }
        )
        funnel["ok"] += 1
    return pd.DataFrame(rows), funnel


# ── statistics ──
def summ(x: pd.Series) -> dict:
    v = x.to_numpy(float)
    if v.size < 20:
        return {"n": int(v.size)}
    lo, hi = ix.block_ci(v)
    k = max(1, v.size // 100)
    return {
        "n": int(v.size),
        "mean": [float(v.mean()), lo, hi],
        "sharpe": per_trade_sharpe(v),
        "worst_1pct_sum_over_total": float(np.sort(v)[:k].sum() / v.sum()) if v.sum() else None,
    }


def annual(d: pd.DataFrame, sel: pd.Series, col: str) -> dict:
    daily = np.where(sel, d[col], 0.0)
    years = (d["date"].iloc[-1] - d["date"].iloc[0]).days / 365.25
    per_year = float(sel.sum() / years)
    return {
        "trades_per_year": per_year,
        "annual_mean": float(daily.mean() * 252),
        "annual_sharpe_daily_series": float(daily.mean() / daily.std(ddof=1) * np.sqrt(252)),
        "basis": "daily P&L series, flat when unselected, 252 sessions per year",
    }


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    px = yahoo()
    res: dict = {}
    allrows = []
    for tk in ix.TICKERS:
        d, funnel = sessions(tk, px[tk])
        print(tk, "funnel:", dict(funnel))
        seed = px[tk].loc[SEED_START:SEED_END]
        seed_v = (seed["close"] / seed["open"] - 1).to_numpy(float)
        vals = np.concatenate([seed_v, d["r_id"].to_numpy(float)])
        dates = np.concatenate([seed.index.to_numpy(), d["date"].to_numpy()])
        bins = causal_bins(vals, dates, 3, MIN_PRIOR)[seed_v.size :]
        d["bin"] = bins
        if (d["bin"] < 0).any():
            raise ValueError(f"{tk}: {(d['bin'] < 0).sum()} scored sessions unassigned")
        d["block"] = d["date"].map(ix.block_of)
        for c in (0.0, 1e-4, 2e-4):
            d[f"N{int(c * 1e4)}"] = d["ON"] - c
        sel = d["bin"] == 0
        r: dict = {
            "funnel": dict(funnel),
            "signal_agreement_corr": float(d[["r_id", "r_id_close"]].corr().iloc[0, 1]),
            "selected": {b: summ(d.loc[sel & (d["block"] == b), "N1"]) for b in ix.BLOCKS},
            "by_bin_pooled": {int(b): summ(g["N1"]) for b, g in d.groupby("bin")},
            "by_bin_block": {
                f"{b}|{k}": summ(g["N1"]) for (b, k), g in d.groupby(["block", "bin"])
            },
            "unconditional": {b: summ(d.loc[d["block"] == b, "N1"]) for b in ix.BLOCKS},
            "selected_cost0": summ(d.loc[sel, "N0"]),
            "selected_cost2": summ(d.loc[sel, "N2"]),
            "selected_weekday": {int(w): summ(g["N1"]) for w, g in d[sel].groupby("weekday")},
            "annual_selected": annual(d, sel, "N1"),
            "annual_unconditional": annual(d, pd.Series(True, index=d.index), "N1"),
        }
        nul = matched_random_null(d["N1"].to_numpy(float), sel.to_numpy(), np.mean)
        r["null_percentile_mean"] = nul.percentile
        r["null_observed"] = nul.observed
        res[tk] = r
        allrows.append(d)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(allrows).to_parquet(OUT / "sessions.parquet")
    s = res["SPY"]["selected"]
    ok = (
        s["M"].get("mean", [0, 0])[1] > 0
        and s["P"].get("mean", [0])[0] > 0
        and s["C"].get("mean", [0])[0] > 0
        and res["SPY"]["null_percentile_mean"] >= 95
    )
    res["verdict"] = "PASS" if ok else "FAIL"
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for tk in ix.TICKERS:
        r = res[tk]
        print(
            f"\n{tk} corr(fwd signal, close signal) {r['signal_agreement_corr']:.3f} "
            f"null pct {r['null_percentile_mean']:.1f}"
        )
        for lab in ("selected", "unconditional"):
            for b, x in r[lab].items():
                print(
                    f"  {lab:13s} {b} n={x['n']:4d} mean {x['mean'][0]*1e4:+.2f}bp "
                    f"[{x['mean'][1]*1e4:+.2f},{x['mean'][2]*1e4:+.2f}] SR {x['sharpe']:.3f}"
                )
        for b, x in r["by_bin_pooled"].items():
            print(
                f"  bin {b} n={x['n']} mean {x['mean'][0]*1e4:+.2f}bp "
                f"[{x['mean'][1]*1e4:+.2f},{x['mean'][2]*1e4:+.2f}]"
            )
        print("  annual selected", r["annual_selected"])
        print("  annual uncond  ", r["annual_unconditional"])
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
