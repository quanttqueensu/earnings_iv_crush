"""
research_kalshi_tails.py
Pre-registered pilot: selling both tails of Kalshi scheduled-release distributions.

``research/other_markets/preregs/kalshi_macro_tails_prereg.md``. A ladder of "at least X" contracts on a scheduled
number prices the market's distribution for it; at the release it collapses to a point. The
straddle-seller's analogue is to buy the favourite side of every contract priced at 90% or more.
The mechanism under test is the favourite-longshot bias documented on Kalshi; the counter-evidence
is that Kalshi macro densities are reported well calibrated.

    --pull    settled events, ladder markets and hourly candles into data/cache/kalshi
    --score   snapshot one hour before close, apply the rule, score with event clustering

Usage:
    python research/other_markets/research_kalshi_tails.py --pull
    python research/other_markets/research_kalshi_tails.py --score

References
----------
Burgi, C., Deng, W. and Whelan, K. (2025). Makers and Takers: The Economics of the Kalshi
Prediction Market. CEPR Discussion Paper DP20631.
Diercks, A. M., Katz, J. D. and Wright, J. H. (2026). Kalshi and the Rise of Macro Markets. NBER
Working Paper 34702.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402

API = "https://api.elections.kalshi.com/trade-api/v2"
CACHE = Path("data/cache/kalshi")
OUT = Path("outputs/research/kalshi_tails")
SERIES = [
    "KXJOBLESSCLAIMS",
    "KXCONTCLAIMS",
    "KXCPI",
    "KXCPICORE",
    "KXCPIYOY",
    "KXCPICOREYOY",
    "KXPAYROLLS",
]
LADDER = {"greater_or_equal", "greater"}
FAV = 0.90
TAKER = 0.07
PAUSE = 0.12  # seconds between calls; well inside the public rate limit
N_BOOT = 5000
SEED = 0


# ── pull ─────────────────────────────────────────────────────────────────────


def _get(path: str, **params: object) -> dict:
    for attempt in range(5):
        try:
            r = requests.get(API + path, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(PAUSE)
            return r.json()
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Kalshi request failed repeatedly: {path} {params}")


def _paged(path: str, key: str, **params: object) -> list[dict]:
    out, cur = [], None
    while True:
        d = _get(path, limit=200, **params, **({"cursor": cur} if cur else {}))
        out += d.get(key, [])
        cur = d.get("cursor")
        if not cur:
            return out


def pull() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cutoff = pd.Timestamp(_get("/historical/cutoff")["market_settled_ts"])
    markets: list[dict] = []
    for s in SERIES:
        events = _paged("/events", "events", series_ticker=s, status="settled")
        n0 = len(markets)
        for e in events:
            et = e["event_ticker"]
            ms = _paged("/markets", "markets", event_ticker=et)
            if not ms:
                ms = _paged("/historical/markets", "markets", event_ticker=et)
            for m in ms:
                if m.get("strike_type") in LADDER:
                    markets.append({**m, "series": s, "event_series": e.get("series_ticker", s)})
        print(f"  {s}: {len(events)} events, {len(markets) - n0} ladder markets", flush=True)
    pd.DataFrame(markets).to_json(CACHE / "markets.json", orient="records")

    todo = [m for m in markets if not (CACHE / f"{m['ticker']}.json").exists()]
    print(f"  candles: {len(markets)} markets, {len(todo)} to fetch", flush=True)
    for i, m in enumerate(todo, 1):
        close = pd.Timestamp(m["close_time"])
        ct = int(close.timestamp())
        params = {"start_ts": ct - 25 * 3600, "end_ts": ct, "period_interval": 60}
        if close <= cutoff:
            path = f"/historical/markets/{m['ticker']}/candlesticks"
        else:
            path = f"/series/{m['event_series']}/markets/{m['ticker']}/candlesticks"
        try:
            c = _get(path, **params).get("candlesticks", [])
        except RuntimeError:
            c = None
        (CACHE / f"{m['ticker']}.json").write_text(json.dumps(c))
        if i % 200 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} candle sets fetched", flush=True)
    print("  PULL DONE", flush=True)


# ── score ────────────────────────────────────────────────────────────────────


def _f(x: object) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")


def snapshots() -> pd.DataFrame:
    mk = pd.read_json(CACHE / "markets.json")
    rows: list[dict] = []
    reasons: dict[str, int] = {}

    def drop(why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    for _, m in mk.iterrows():
        f = CACHE / f"{m['ticker']}.json"
        c = json.loads(f.read_text()) if f.exists() else None
        if not c:
            drop("no candles")
            continue
        close = int(pd.Timestamp(m["close_time"]).timestamp())
        df = pd.DataFrame(
            {
                "end": [x["end_period_ts"] for x in c],
                "bid": [_f((x.get("yes_bid") or {}).get("close")) for x in c],
                "ask": [_f((x.get("yes_ask") or {}).get("close")) for x in c],
                "vol": [_f(x.get("volume")) for x in c],
            }
        ).sort_values("end")
        snap = df[df["end"] <= close - 3600]
        if snap.empty:
            drop("no candle an hour before close")
            continue
        s = snap.iloc[-1]
        vol24 = float(snap[snap["end"] > s["end"] - 86400]["vol"].sum())
        if m.get("result") not in ("yes", "no"):
            drop("unresolved")
            continue
        rows.append(
            {
                "series": m["series"],
                "event": m["event_ticker"],
                "ticker": m["ticker"],
                "strike": _f(m.get("floor_strike")),
                "bid": s["bid"],
                "ask": s["ask"],
                "vol24": vol24,
                "yes_won": m["result"] == "yes",
            }
        )
    print(
        f"  snapshot funnel: {len(mk)} ladder markets, {len(rows)} snapshotted, dropped {reasons}"
    )
    if not rows:
        raise SystemExit("no market could be snapshotted - refusing to score")
    return pd.DataFrame(rows)


def bets(snap: pd.DataFrame) -> pd.DataFrame:
    ok = (snap["vol24"] > 0) & (snap["bid"] > 0) & (snap["ask"] > snap["bid"]) & (snap["ask"] < 1)
    s = snap[ok].copy()
    print(f"  liquidity filter: {len(snap)} -> {len(s)} markets")
    fav_yes = s["bid"] >= FAV
    fav_no = s["ask"] <= 1 - FAV
    b = pd.concat(
        [
            s[fav_yes].assign(side="yes", price=s["ask"], won=s["yes_won"]),
            s[fav_no].assign(side="no", price=1 - s["bid"], won=~s["yes_won"]),
        ]
    )
    b["fee"] = TAKER * b["price"] * (1 - b["price"])
    b["ret"] = (b["won"].astype(float) - b["price"] - b["fee"]) / (b["price"] + b["fee"])
    return b


def pit(snap: pd.DataFrame) -> pd.Series:
    """Position of each release's realised value in its implied CDF, from ladder mids."""
    out = {}
    for ev, g in snap.groupby("event"):
        g = g.dropna(subset=["strike"]).sort_values("strike")
        mid = ((g["bid"] + g["ask"]) / 2).clip(0, 1).to_numpy()
        won = g["yes_won"].to_numpy()
        if len(g) < 3:
            continue
        cdf_below = 1 - mid  # P(X < k)
        ky = np.flatnonzero(won)
        kn = np.flatnonzero(~won)
        lo = cdf_below[ky[-1]] if len(ky) else 0.0
        hi = cdf_below[kn[0]] if len(kn) else 1.0
        out[ev] = float((lo + hi) / 2)
    return pd.Series(out, name="pit")


def score() -> pd.DataFrame:
    snap = snapshots()
    b = bets(snap)
    if len(b) < 10:
        raise SystemExit(f"{len(b)} bets - too few to score")
    ev_mean = b.groupby("event")["ret"].mean()
    keys = b["event"].to_numpy()
    r = b["ret"].to_numpy()

    def event_avg(i: np.ndarray) -> float:
        i = i.astype(int)
        return float(pd.Series(r[i]).groupby(keys[i]).mean().mean())

    idx = np.arange(len(b), dtype=float)
    lo, hi = cluster_bootstrap_ci(idx, keys, event_avg, n_boot=N_BOOT, seed=SEED)
    edge = (b["won"].astype(float) - b["price"]).to_numpy()
    m_lo, m_hi = cluster_bootstrap_ci(
        edge, keys, lambda v: float(v.mean()), n_boot=N_BOOT, seed=SEED
    )

    rows = [
        {
            "slice": "all",
            "n_bets": len(b),
            "n_events": int(b["event"].nunique()),
            "mean_ret_event_avg": float(ev_mean.mean()),
            "ci_low": lo,
            "ci_high": hi,
            "win_rate": float(b["won"].mean()),
            "mean_price": float(b["price"].mean()),
            "win_minus_price": float(edge.mean()),
            "wmp_ci_low": m_lo,
            "wmp_ci_high": m_hi,
            "median_vol24": float(b["vol24"].median()),
        }
    ]
    for s, g in b.groupby("series"):
        rows.append(
            {
                "slice": s,
                "n_bets": len(g),
                "n_events": int(g["event"].nunique()),
                "mean_ret_event_avg": float(g.groupby("event")["ret"].mean().mean()),
                "win_rate": float(g["won"].mean()),
                "mean_price": float(g["price"].mean()),
                "win_minus_price": float((g["won"].astype(float) - g["price"]).mean()),
                "median_vol24": float(g["vol24"].median()),
            }
        )
    res = pd.DataFrame(rows)
    p = pit(snap)
    tail = float(((p < 0.10) | (p > 0.90)).mean()) if len(p) else float("nan")
    print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(
        f"\n  PIT over {len(p)} events: tail mass (<0.10 or >0.90) {tail:.3f} vs 0.200 if calibrated;"
        f" quartile shares {np.histogram(p, bins=[0, .25, .5, .75, 1])[0] / max(len(p), 1)}"
    )
    passed = lo > 0
    mech = m_lo > 0
    print(f"  PRIMARY: {'PASS' if passed else 'FAIL'}   mechanism (favourites beat price): {mech}")
    OUT.mkdir(parents=True, exist_ok=True)
    b.to_csv(OUT / "bets.csv", index=False)
    p.to_csv(OUT / "pit.csv")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args()
    if args.pull:
        pull()
    if args.score:
        score().to_csv(OUT / "kalshi_tails.csv", index=False)
        print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
