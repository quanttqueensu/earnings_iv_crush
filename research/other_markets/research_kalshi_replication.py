"""
research_kalshi_replication.py
Pre-registered replication of the Kalshi maker result on 81 release series it has never seen.

``research/other_markets/preregs/kalshi_maker_replication_prereg.md``. The snapshot, liquidity filter, favourite rule,
taker and maker pricing, strictly-through fill rule and fees are the original tests' code, reused
unchanged by pointing it at a separate cache. Events already in the original sample are removed.
Inference clusters by release date, since releases on one day share information.

Usage:
    python research/other_markets/research_kalshi_replication.py --pull
    python research/other_markets/research_kalshi_replication.py --score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.other_markets.research_kalshi_tails as kt  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402

ORIGINAL = Path("data/cache/kalshi/markets.json")
SERIES = Path("data/cache/kalshi/replication_series.json")
REP = Path("data/cache/kalshi_rep")
OUT = Path("outputs/research/kalshi_replication")
MAKER = 0.0175
N_BOOT, SEED = 5000, 0


def pull() -> None:
    REP.mkdir(parents=True, exist_ok=True)
    seen = set(pd.read_json(ORIGINAL)["event_ticker"])
    cutoff = pd.Timestamp(kt._get("/historical/cutoff")["market_settled_ts"])
    markets: list[dict] = []
    for s in json.loads(SERIES.read_text()):
        events = [
            e
            for e in kt._paged("/events", "events", series_ticker=s, status="settled")
            if e["event_ticker"] not in seen
        ]
        n0 = len(markets)
        for e in events:
            ms = kt._paged("/markets", "markets", event_ticker=e["event_ticker"])
            if not ms:
                ms = kt._paged("/historical/markets", "markets", event_ticker=e["event_ticker"])
            markets += [
                {**m, "series": s, "event_series": e.get("series_ticker", s)}
                for m in ms
                if m.get("strike_type") in kt.LADDER and kt._f(m.get("volume_fp")) > 0
            ]
        print(
            f"  {s}: {len(events)} new events, {len(markets) - n0} traded ladder markets",
            flush=True,
        )
    pd.DataFrame(markets).to_json(REP / "markets.json", orient="records")
    todo = [m for m in markets if not (REP / f"{m['ticker']}.json").exists()]
    print(f"  candles: {len(todo)} to fetch", flush=True)
    for i, m in enumerate(todo, 1):
        close = pd.Timestamp(m["close_time"])
        ct = int(close.timestamp())
        path = (
            f"/historical/markets/{m['ticker']}/candlesticks"
            if close <= cutoff
            else f"/series/{m['event_series']}/markets/{m['ticker']}/candlesticks"
        )
        try:
            c = kt._get(path, start_ts=ct - 25 * 3600, end_ts=ct, period_interval=60).get(
                "candlesticks", []
            )
        except RuntimeError:
            c = None
        (REP / f"{m['ticker']}.json").write_text(json.dumps(c))
        if i % 250 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} candle sets", flush=True)
    print("  PULL DONE", flush=True)


def _trades(ticker: str, start: int, end: int, historical: bool) -> pd.DataFrame:
    f = REP / "trades" / f"{ticker}.json"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        path = "/historical/trades" if historical else "/markets/trades"
        f.write_text(json.dumps(kt._paged(path, "trades", ticker=ticker, min_ts=start, max_ts=end)))
    df = pd.DataFrame(json.loads(f.read_text()))
    if not df.empty:
        df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    return df


def _book(b: pd.DataFrame, col: str, label: str) -> dict:
    keys, r = b["release_date"].to_numpy(), b[col].to_numpy()

    def avg(i: np.ndarray) -> float:
        i = i.astype(int)
        return float(pd.Series(r[i]).groupby(keys[i]).mean().mean())

    idx = np.arange(len(b), dtype=float)
    lo, hi = (
        cluster_bootstrap_ci(idx, keys, avg, n_boot=N_BOOT, seed=SEED)
        if len(b) > 2
        else (np.nan, np.nan)
    )
    return {
        "book": label,
        "n_bets": len(b),
        "n_dates": int(b["release_date"].nunique()),
        "mean_ret_date_avg": avg(idx) if len(b) else np.nan,
        "ci_low": lo,
        "ci_high": hi,
    }


def score() -> None:
    kt.CACHE = REP  # reuse the original snapshot and bet code, unchanged, on the new cache
    snap = kt.snapshots()
    bets = kt.bets(snap)
    mk = pd.read_json(REP / "markets.json").set_index("ticker")
    cut = pd.Timestamp(kt._get("/historical/cutoff")["trades_created_ts"])
    cpi_days = {
        pd.Timestamp(t).date()
        for t, s in zip(mk["close_time"], mk["series"], strict=True)
        if "CPI" in s.upper()
    }
    rows = []
    for _, b in bets.iterrows():
        close = pd.Timestamp(mk.loc[b["ticker"], "close_time"])
        c = json.loads((REP / f"{b['ticker']}.json").read_text()) or []
        ends = [x["end_period_ts"] for x in c if x["end_period_ts"] <= close.timestamp() - 3600]
        tr = _trades(b["ticker"], int(max(ends)), int(close.timestamp()), close <= cut)
        if b["side"] == "yes":
            mp = float(b["bid"])
            hit = len(tr) and ((tr["taker_side"] == "no") & (tr["yes_price"] < mp)).any()
        else:
            mp = 1 - float(b["ask"])
            hit = (
                len(tr)
                and ((tr["taker_side"] == "yes") & (tr["yes_price"] > float(b["ask"]))).any()
            )
        fee = MAKER * mp * (1 - mp)
        rows.append(
            {
                **b.to_dict(),
                "release_date": close.date(),
                "maker_price": mp,
                "filled": bool(hit),
                "maker_ret": (float(b["won"]) - mp - fee) / (mp + fee),
            }
        )
    d = pd.DataFrame(rows)
    f = d[d["filled"]]
    print(f"  candidates {len(d)}, maker fills {len(f)} ({len(f) / max(len(d), 1):.1%})")
    out = [_book(f, "maker_ret", "maker"), _book(d, "ret", "taker")]
    nc = d[~d["release_date"].isin(cpi_days)]
    out += [
        _book(nc[nc["filled"]], "maker_ret", "maker_ex_cpi_days"),
        _book(nc, "ret", "taker_ex_cpi_days"),
    ]
    edge = (f["won"].astype(float) - f["maker_price"]).to_numpy()
    elo, ehi = cluster_bootstrap_ci(
        edge, f["release_date"].to_numpy(), lambda v: float(v.mean()), n_boot=N_BOOT, seed=SEED
    )
    won, fil, kk = d["won"].to_numpy(float), d["filled"].to_numpy(), d["release_date"].to_numpy()

    def gap(i: np.ndarray) -> float:
        i = i.astype(int)
        return float(won[i][fil[i]].mean() - won[i][~fil[i]].mean())

    glo, ghi = cluster_bootstrap_ci(
        np.arange(len(d), dtype=float), kk, gap, n_boot=N_BOOT, seed=SEED
    )
    res = pd.DataFrame(out)
    print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(
        f"  maker win minus price {edge.mean():+.4f} [{elo:+.4f}, {ehi:+.4f}]; "
        f"filled minus unfilled win rate {gap(np.arange(len(d), dtype=float)):+.4f} [{glo:+.4f}, {ghi:+.4f}]"
    )
    m = res.iloc[0]
    print(
        f"\n  PRIMARY: {'PASS' if m['ci_low'] > 0 else 'FAIL'}   mechanism check: {elo > 0 and not ghi < 0}"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "bets.csv", index=False)
    res.to_csv(OUT / "kalshi_replication.csv", index=False)
    print(f"  wrote {OUT.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.pull:
        pull()
    if a.score:
        score()


if __name__ == "__main__":
    main()
