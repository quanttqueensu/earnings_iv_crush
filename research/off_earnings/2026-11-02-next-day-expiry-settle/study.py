"""
study.py
Sell the next-day-expiry ATM index straddle at the 15:59 bids and settle at intrinsic on the next
close. Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/off_earnings/2026-11-02-next-day-expiry-settle/study.py

References
----------
Muravyev, D. and Ni, X. (2020) Why do option returns change sign from day to night? JFE 136(1).
Bandi, F., Fusari, N. and Renò, R. (2023) 0DTE option pricing. Working paper.
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

from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research.protocol import per_trade_sharpe, verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
IDX = ROOT / "research" / "off_earnings" / "2026-11-01-index-event-crush" / "study.py"
B1 = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"

_s = importlib.util.spec_from_file_location("idx_study", IDX)
assert _s is not None and _s.loader is not None
ix = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ix)

N_TRIALS, SR_TRIALS_STD = 1565, 0.127475
DISPOSAL = 5e-4


def etf_closes() -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(
        list(ix.TICKERS),
        start="2015-12-01",
        end="2026-11-05",
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="ticker",
    )
    out = {}
    for t in ix.TICKERS:
        g = raw[t].dropna(subset=["Close"]).copy()
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = pd.DataFrame({"close": g["Close"], "split": g["Stock Splits"].fillna(0.0)})
    return out


def one(tk: str, t: pd.Timestamp, t1: pd.Timestamp, px: pd.DataFrame) -> dict:
    base = {"ticker": tk, "entry": t, "exit": t1}
    e = ix.load_chain(tk, t, "1559")
    if e is None:
        return {**base, "status": "no_entry_snapshot"}
    e2 = e[ix._two_sided(e) & (e["expiry"] == t1)]
    piv = e2.pivot_table(index="strike", columns="cp", values=["bid", "ask"])
    need = [("bid", "C"), ("ask", "C"), ("bid", "P"), ("ask", "P")]
    if e2.empty or any(c not in piv.columns for c in need):
        return {**base, "status": "no_next_day_expiry"}
    piv = piv[need].dropna()
    if piv.empty:
        return {**base, "status": "no_next_day_expiry"}
    cmid = (piv[("bid", "C")] + piv[("ask", "C")]) / 2
    pmid = (piv[("bid", "P")] + piv[("ask", "P")]) / 2
    k = float((cmid - pmid).abs().idxmin())
    c0b, p0b = float(piv.loc[k, ("bid", "C")]), float(piv.loc[k, ("bid", "P")])
    p0 = float(cmid.loc[k] + pmid.loc[k])
    fwd = k + float(cmid.loc[k] - pmid.loc[k])
    if t1 not in px.index or t not in px.index:
        return {**base, "status": "no_close"}
    if (px.loc[(px.index > t) & (px.index <= t1), "split"] != 0).any():
        return {**base, "status": "split"}
    s1 = float(px.loc[t1, "close"])
    intr = abs(s1 - k)
    net = c0b + p0b - intr - 2 * ix.COMMISSION_PER_SHARE - (DISPOSAL * s1 if intr > 0 else 0.0)
    return {
        **base,
        "status": "ok",
        "strike": k,
        "p0": p0,
        "fwd0": fwd,
        "sale": c0b + p0b,
        "N": net / p0,
        "N_mid": (p0 - intr) / p0,
        "N_rom": net / (p0 + ix.MARGIN_SPOT_FRAC * fwd),
        "weekday": int(t.weekday()),
        "gap_days": int((t1 - t).days),
        "half_spread": (p0 - c0b - p0b) / p0,
    }


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    px = etf_closes()
    rows, funnel = [], Counter()
    for tk in ix.TICKERS:
        days = sorted(
            pd.Timestamp(p.name.split("_")[1]) for p in ix.CHAINS.glob(f"{tk}_*_1559.parquet")
        )
        for t, t1 in zip(days[:-1], days[1:], strict=True):
            r = one(tk, t, t1, px[tk])
            funnel[(tk, r["status"])] += 1
            if r["status"] == "ok":
                r["block"] = ix.block_of(t)
                rows.append(r)
    print("funnel:", {f"{a}:{b}": v for (a, b), v in sorted(funnel.items())})
    d = pd.DataFrame(rows).sort_values(["ticker", "entry"])
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "trades.parquet")
    b1 = pd.read_parquet(B1)
    b1 = b1[(b1["exit_snap"] == "1559") & (b1["status"] == "ok")][
        ["ticker", "entry", "short_touch_net"]
    ]
    b1["entry"] = pd.to_datetime(b1["entry"])
    res: dict = {"funnel": {f"{a}:{b}": v for (a, b), v in funnel.items()}}
    for tk in ix.TICKERS:
        s = d[d["ticker"] == tk]
        r_tk: dict = {}
        for b in ix.BLOCKS:
            x = s[s["block"] == b]
            if len(x) < 20:
                r_tk[b] = {"n": int(len(x))}
                continue
            v = x["N"].to_numpy(float)
            j = x.merge(b1, on=["ticker", "entry"])
            r_tk[b] = {
                "n": int(len(x)),
                "mean_N": [float(v.mean()), *ix.block_ci(v)],
                "sharpe_N": per_trade_sharpe(v),
                "sharpe_N_rom": per_trade_sharpe(x["N_rom"]),
                "mean_N_mid": float(x["N_mid"].mean()),
                "median_half_spread": float(x["half_spread"].median()),
                "skew": float(pd.Series(v).skew()),
                "worst_1pct_share": (
                    float(np.sort(v)[: max(1, len(v) // 100)].sum() / v.sum())
                    if v.sum() != 0
                    else np.nan
                ),
                "by_gap_days": x.groupby("gap_days")["N"]
                .agg(["count", "mean"])
                .round(5)
                .to_dict("index"),
                "paired_minus_B1": [float((j["N"] - j["short_touch_net"]).mean()), int(len(j))],
            }
        r_tk["dsr"] = (
            float(deflated_sharpe_ratio(s["N"].reset_index(drop=True), N_TRIALS, SR_TRIALS_STD))
            if len(s) > 20
            else np.nan
        )
        res[tk] = r_tk
    spy = res["SPY"]
    ok = (
        spy.get("M", {}).get("mean_N", [0, 0])[1] > 0
        and spy.get("P", {}).get("mean_N", [0])[0] > 0
        and spy.get("C", {}).get("mean_N", [0])[0] > 0
    )
    res["verdict"] = "PASS" if ok else "FAIL"
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for tk in ix.TICKERS:
        for b in ix.BLOCKS:
            x = res[tk][b]
            if "mean_N" in x:
                print(
                    tk,
                    b,
                    x["n"],
                    "N %+.4f [%+.4f,%+.4f]" % tuple(x["mean_N"]),
                    "SR %.3f mid %+.4f hs %.4f skew %.1f vsB1 %+.4f(n=%d)"
                    % (
                        x["sharpe_N"],
                        x["mean_N_mid"],
                        x["median_half_spread"],
                        x["skew"],
                        *x["paired_minus_B1"],
                    ),
                )
            else:
                print(tk, b, x)
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
