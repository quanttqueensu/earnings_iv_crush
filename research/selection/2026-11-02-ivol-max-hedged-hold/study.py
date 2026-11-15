"""
study.py
Idiosyncratic volatility (Cao and Han 2013) and lottery demand (Byun and Kim 2016) as causal decile
selectors for the hedged event hold. Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/selection/2026-11-02-ivol-max-hedged-hold/study.py

References
----------
Cao, J. and Han, B. (2013) Cross section of option returns and idiosyncratic stock volatility.
JFE 108(1), 231-249.
Byun, S.-J. and Kim, D.-H. (2016) Gambling preference and individual equity option returns. JFE
122(1), 155-174.
Bali, T., Cakici, N. and Whitelaw, R. (2011) Maxing out: stocks as lotteries. JFE 99(2), 427-446.
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

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
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

IVOL_WIN, IVOL_MIN = 60, 50
MAX_WIN, MAX_MIN = 21, 18
N_BINS, MIN_PRIOR = 10, 200
BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
ATTRITION_TOL = 0.005


# ── returns ─────────────────────────────────────────────────────────────────


def yahoo_returns(tickers: list[str], start: str) -> dict[str, pd.Series]:
    import yfinance as yf

    raw = yf.download(
        tickers,
        start=start,
        end="2026-11-01",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out = {}
    for t in tickers:
        try:
            g = raw[t]["Adj Close"].dropna()
        except KeyError:
            continue
        g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
        out[t] = g.pct_change().dropna()
    return out


def signals(r: pd.Series, mkt: pd.Series, entry: pd.Timestamp) -> tuple[float, float]:
    """IVOL and MAX from returns strictly before ``entry``."""
    past = r[r.index < entry]
    w = pd.concat([past.tail(IVOL_WIN), mkt], axis=1, join="inner").dropna()
    ivol = np.nan
    if len(w) >= IVOL_MIN:
        y, x = w.iloc[:, 0].to_numpy(), w.iloc[:, 1].to_numpy()
        b = np.polyfit(x, y, 1)
        ivol = float(np.std(y - np.polyval(b, x), ddof=2))
    m = past.tail(MAX_WIN).dropna()
    mx = float(m.max()) if len(m) >= MAX_MIN else np.nan
    return ivol, mx


# ── scoring ─────────────────────────────────────────────────────────────────


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _tmb_ci(v: np.ndarray, top: np.ndarray, bot: np.ndarray, dates: pd.Series):
    idx = np.arange(len(v), dtype=float)

    def stat(ii: np.ndarray) -> float:
        k = ii.astype(int)
        t, b = v[k][top[k]], v[k][bot[k]]
        return float(t.mean() - b.mean()) if len(t) and len(b) else np.nan

    return date_clustered_ci(idx, dates, stat)


def score_signal(d: pd.DataFrame, col: str) -> dict:
    out: dict = {}
    for name, (y0, y1) in BLOCKS.items():
        blk = d[d["year"].between(y0, y1)]
        a = blk[blk[f"{col}_bin"] >= 0]
        miss = blk[blk[f"{col}_bin"] < 0]
        top = (a[f"{col}_bin"] == N_BINS - 1).to_numpy()
        bot = (a[f"{col}_bin"] == 0).to_numpy()
        h = a["H"].to_numpy(float)
        tci = date_clustered_ci(h[top], a.loc[top, "exit_date"], per_trade_sharpe)
        nul = matched_random_null(h, top)
        rv = a["RV"].to_numpy(float)
        tmb = _tmb_ci(rv, top, bot, a["exit_date"])
        out[name] = {
            "n_block": int(len(blk)),
            "n_assigned": int(len(a)),
            "n_missing": int(len(miss)),
            "missing_gap_H": float(miss["H"].mean() - a["H"].mean()) if len(miss) else 0.0,
            "n_top": int(top.sum()),
            "top_sharpe": [tci.point, tci.low, tci.high],
            "top_mean_H": float(h[top].mean()),
            "null_percentile": float(nul.percentile),
            "rv_top_minus_bottom": [tmb.point, tmb.low, tmb.high],
            "deciles_sharpe": {
                int(k): round(per_trade_sharpe(g["H"]), 4) for k, g in a.groupby(f"{col}_bin")
            },
            "deciles_mean_H": {
                int(k): round(float(g["H"].mean()), 5) for k, g in a.groupby(f"{col}_bin")
            },
        }
    dsc, val, con = out["discovery"], out["validation"], out["confirmation"]
    steps = [
        ("discovery null", dsc["null_percentile"] >= 95),
        ("validation null", val["null_percentile"] >= 95),
        ("validation book", val["top_sharpe"][1] > 0),
        ("confirmation book", con["top_sharpe"][0] > 0),
        ("confirmation null", con["null_percentile"] >= 95),
    ]
    failed = [s for s, ok in steps if not ok]
    out["verdict"] = "PASS" if not failed else "FAIL at " + ", ".join(failed)
    out["attrition_flag"] = [k for k in BLOCKS if abs(out[k]["missing_gap_H"]) > ATTRITION_TOL]
    return out


def main() -> None:
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    a = pd.read_parquet(HH / "events.parquet")
    c = pd.read_parquet(HH / "events_confirm_2025_26.parquet")
    a, c = a[a["status"] == "ok"].copy(), c[c["status"] == "ok"].copy()
    a["src"], c["src"] = "crsp", "yahoo"
    d = pd.concat([a, c], ignore_index=True)
    for col in ("entry_date", "exit_date", "expiry"):
        d[col] = pd.to_datetime(d[col])
    f = pd.read_parquet(FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = d.merge(
        f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    print(f"  events {len(d)} (crsp {len(a)}, yahoo {len(c)})")

    spy = yahoo_returns(["SPY"], "2010-06-01")["SPY"]
    cr = pd.read_parquet(CRSP)
    cr["date"] = pd.to_datetime(cr["date"])
    cr["ret"] = pd.to_numeric(cr["ret"], errors="coerce")
    crsp = {int(k): g.set_index("date")["ret"].sort_index() for k, g in cr.groupby("permno")}
    yh = yahoo_returns(sorted(c["ticker"].unique()), "2024-06-01")

    funnel: Counter = Counter()
    iv, mx = [], []
    for _, e in d.iterrows():
        if e["src"] == "crsp":
            r = crsp.get(int(e["permno"])) if pd.notna(e["permno"]) else None
        else:
            r = yh.get(e["ticker"])
        if r is None:
            funnel[f"{e['src']}_no_returns"] += 1
            iv.append(np.nan)
            mx.append(np.nan)
            continue
        x, y = signals(r, spy, e["entry_date"])
        funnel[f"{e['src']}_ivol_{'ok' if np.isfinite(x) else 'short'}"] += 1
        iv.append(x)
        mx.append(y)
    print("signal funnel:", dict(funnel))
    d["ivol"], d["max"] = iv, mx
    d["RV"] = d["H"] * d["m0"] / d["s0"]
    d["year"] = d["exit_date"].dt.year
    d = d.sort_values("exit_date").reset_index(drop=True)
    for col in ("ivol", "max"):
        d[f"{col}_bin"] = causal_bins(d[col].to_numpy(float), d["exit_date"], N_BINS, MIN_PRIOR)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")
    res = {"signal_funnel": dict(funnel)}
    res["S1_ivol"] = score_signal(d, "ivol")
    res["S2_max"] = score_signal(d, "max")
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("VERDICT S1 IVOL:", res["S1_ivol"]["verdict"])
    print("VERDICT S2 MAX:", res["S2_max"]["verdict"])


if __name__ == "__main__":
    main()
