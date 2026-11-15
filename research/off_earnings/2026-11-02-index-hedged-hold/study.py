"""
study.py
Hedge-hold the daily index straddle to expiry instead of buying it back the next session.
Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/off_earnings/2026-11-02-index-hedged-hold/study.py

References
----------
Muravyev, D. and Ni, X. (2020) Why do option returns change sign from day to night? JFE 136(1).
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
from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    hedged_short_straddle,
    straddle_iv,
    year_frac,
)
from earnings_iv_crush.research.protocol import per_trade_sharpe, verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
IDX = ROOT / "research" / "off_earnings" / "2026-11-01-index-event-crush" / "study.py"
TRADES = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"

_s = importlib.util.spec_from_file_location("idx_study", IDX)
assert _s is not None and _s.loader is not None
ix = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ix)

N_TRIALS, SR_TRIALS_STD = 1556, 0.127475


def etf_bars() -> dict[str, pd.DataFrame]:
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
        out[t] = pd.DataFrame(
            {
                "close": g["Close"],
                "ret": g["Adj Close"].pct_change(),
                "split": g["Stock Splits"].fillna(0.0),
            }
        )
    return out


def one(r: pd.Series, g: pd.DataFrame) -> dict:
    t0, exp = r["entry"], r["expiry"]
    w = g.loc[t0:exp]
    if len(w) < 2 or w.index[0] != t0:
        return {"status": "missing_bars"}
    if (w["split"].iloc[1:] != 0).any():
        return {"status": "split_in_hold"}
    sig = straddle_iv(r["p0"], r["fwd0"], r["strike"], year_frac(t0, exp))
    if not np.isfinite(sig):
        return {"status": "no_entry_iv"}
    cl = w["close"].to_numpy(float)
    n = len(cl) - 1
    res = hedged_short_straddle(
        sale_price=r["c0b"] + r["p0b"],
        sale_mid=r["p0"],
        strike=r["strike"],
        fwd=r["fwd0"],
        closes=cl[:-1],
        rets=w["ret"].to_numpy(float)[1:],
        taus=np.array([year_frac(d, exp) for d in w.index[:-1]]),
        sigmas=np.full(n, sig),
        half_spreads=np.zeros(n),
        settle_close=float(cl[-1]),
    )
    return {
        "status": "ok",
        "IH": res.net_pnl / r["p0"],
        "IH_mid": res.gross_pnl_mid / r["p0"],
        "IH_rom": res.net_pnl / (r["p0"] + ix.MARGIN_SPOT_FRAC * r["fwd0"]),
        "days": n,
    }


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = pd.read_parquet(TRADES)
    d = d[(d["exit_snap"] == "1559") & (d["status"] == "ok")].copy()
    for c in ("entry", "exit", "expiry"):
        d[c] = pd.to_datetime(d[c])
    bars = etf_bars()
    rows, funnel = [], Counter()
    for _, r in d.iterrows():
        o = one(r, bars[r["ticker"]])
        funnel[o["status"]] += 1
        if o["status"] == "ok":
            rows.append({**r[["ticker", "entry", "block", "p0", "short_touch_net"]].to_dict(), **o})
    print("funnel:", dict(funnel))
    z = pd.DataFrame(rows).sort_values("entry")
    OUT.mkdir(parents=True, exist_ok=True)
    z.to_parquet(OUT / "trades.parquet")
    res: dict = {"funnel": dict(funnel)}
    for tk in ix.TICKERS:
        s = z[z["ticker"] == tk]
        r_tk: dict = {}
        for b in ix.BLOCKS:
            x = s[s["block"] == b]
            diff = (x["IH"] - x["short_touch_net"]).to_numpy(float)
            ih = x["IH"].to_numpy(float)
            r_tk[b] = {
                "n": int(len(x)),
                "P1_mean_IH_minus_B1": [float(diff.mean()), *ix.block_ci(diff)],
                "P2_mean_IH": [float(ih.mean()), *ix.block_ci(ih)],
                "sharpe_IH": per_trade_sharpe(ih),
                "sharpe_IH_rom": per_trade_sharpe(x["IH_rom"]),
                "mean_IH_mid": float(x["IH_mid"].mean()),
                "skew_IH": float(pd.Series(ih).skew()),
                "median_days": float(x["days"].median()),
            }
        pc = s[s["block"].isin(["P", "C"])].sort_values("entry")["IH"].to_numpy(float)
        r_tk["PC_mean_IH"] = [float(pc.mean()), *ix.block_ci(pc)]
        r_tk["dsr_IH"] = float(
            deflated_sharpe_ratio(s["IH"].reset_index(drop=True), N_TRIALS, SR_TRIALS_STD)
        )
        res[tk] = r_tk
    m = res["SPY"]["M"]
    p1 = m["P1_mean_IH_minus_B1"][1] > 0
    p2 = m["P2_mean_IH"][1] > 0
    pc = res["SPY"]["PC_mean_IH"][1] > 0
    res["verdict"] = "PASS" if (p1 and p2 and pc) else ("EXIT LEVER ONLY" if p1 else "FAIL")
    (OUT / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    for tk in ix.TICKERS:
        for b in ix.BLOCKS:
            x = res[tk][b]
            print(
                tk,
                b,
                x["n"],
                "IH-B1 %+.4f [%+.4f,%+.4f]" % tuple(x["P1_mean_IH_minus_B1"]),
                "IH %+.4f [%+.4f,%+.4f]" % tuple(x["P2_mean_IH"]),
                "SR %.3f mid %+.4f skew %.1f days %.0f"
                % (x["sharpe_IH"], x["mean_IH_mid"], x["skew_IH"], x["median_days"]),
            )
        print(tk, "P+C IH %+.4f [%+.4f,%+.4f]" % tuple(res[tk]["PC_mean_IH"]))
    print("VERDICT:", res["verdict"])


if __name__ == "__main__":
    main()
