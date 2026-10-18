"""
research_kalshi_maker.py
Pre-registered test: the same Kalshi favourites, bought with resting bids instead of at the ask.

``research/other_markets/preregs/kalshi_maker_prereg.md``. The candidate set is exactly the taker test's 383 bets; only
the side of the spread changes. A resting bid counts as filled only when a later trade prints
strictly through it, so queue position is never assumed. The mechanism check asks whether fills
concentrate in losers (adverse selection).

Usage:
    python research/other_markets/research_kalshi_maker.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from research.other_markets.research_kalshi_tails import CACHE, _get, _paged  # noqa: E402

BETS = Path("outputs/research/kalshi_tails/bets.csv")
OUT = Path("outputs/research/kalshi_maker")
TRADES = CACHE / "trades"
MAKER = 0.0175
N_BOOT, SEED = 5000, 0


def snapshot_end(ticker: str, close: pd.Timestamp) -> int | None:
    c = json.loads((CACHE / f"{ticker}.json").read_text())
    ends = [x["end_period_ts"] for x in c or [] if x["end_period_ts"] <= close.timestamp() - 3600]
    return max(ends) if ends else None


def trades(ticker: str, start: int, end: int, historical: bool) -> pd.DataFrame:
    f = TRADES / f"{ticker}.json"
    if not f.exists():
        TRADES.mkdir(parents=True, exist_ok=True)
        path = "/historical/trades" if historical else "/markets/trades"
        rows = _paged(path, "trades", ticker=ticker, min_ts=start, max_ts=end)
        f.write_text(json.dumps(rows))
    df = pd.DataFrame(json.loads(f.read_text()))
    if df.empty:
        return df
    df["yes_price"] = pd.to_numeric(df["yes_price_dollars"], errors="coerce")
    df["count"] = pd.to_numeric(df["count_fp"], errors="coerce")
    return df


def main() -> None:
    bets = pd.read_csv(BETS)
    mk = pd.read_json(CACHE / "markets.json").set_index("ticker")
    cut = pd.Timestamp(_get("/historical/cutoff")["trades_created_ts"])
    rows: list[dict] = []
    reasons: dict[str, int] = {}
    for _, b in bets.iterrows():
        close = pd.Timestamp(mk.loc[b["ticker"], "close_time"])
        start = snapshot_end(b["ticker"], close)
        if start is None:
            reasons["no snapshot"] = reasons.get("no snapshot", 0) + 1
            continue
        tr = trades(b["ticker"], int(start), int(close.timestamp()), close <= cut)
        if b["side"] == "yes":
            price = float(b["bid"])
            hit = tr[(tr["taker_side"] == "no") & (tr["yes_price"] < price)] if len(tr) else tr
        else:
            price = 1 - float(b["ask"])
            hit = (
                tr[(tr["taker_side"] == "yes") & (tr["yes_price"] > float(b["ask"]))]
                if len(tr)
                else tr
            )
        fee = MAKER * price * (1 - price)
        won = bool(b["won"])
        rows.append(
            {
                "event": b["event"],
                "series": b["series"],
                "ticker": b["ticker"],
                "side": b["side"],
                "maker_price": price,
                "taker_price": float(b["price"]),
                "won": won,
                "filled": len(hit) > 0,
                "through_volume": float(hit["count"].sum()) if len(hit) else 0.0,
                "ret": (float(won) - price - fee) / (price + fee),
            }
        )
    d = pd.DataFrame(rows)
    print(f"  funnel: {len(bets)} candidates, measured {len(d)}, dropped {reasons}")
    f = d[d["filled"]]
    print(f"  filled {len(f)} of {len(d)} ({len(f) / max(len(d), 1):.1%})")
    if len(f) < 10:
        raise SystemExit(f"{len(f)} fills - too few to score")

    keys, r = f["event"].to_numpy(), f["ret"].to_numpy()

    def ev_avg(i: np.ndarray) -> float:
        i = i.astype(int)
        return float(pd.Series(r[i]).groupby(keys[i]).mean().mean())

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(f), dtype=float), keys, ev_avg, n_boot=N_BOOT, seed=SEED
    )
    edge = (f["won"].astype(float) - f["maker_price"]).to_numpy()
    elo, ehi = cluster_bootstrap_ci(edge, keys, lambda v: float(v.mean()), n_boot=N_BOOT, seed=SEED)
    allk, won_all, fill_all = (
        d["event"].to_numpy(),
        d["won"].to_numpy(float),
        d["filled"].to_numpy(),
    )

    def win_gap(i: np.ndarray) -> float:
        i = i.astype(int)
        a, b = won_all[i][fill_all[i]], won_all[i][~fill_all[i]]
        return float(a.mean() - b.mean()) if len(a) and len(b) else float("nan")

    glo, ghi = cluster_bootstrap_ci(
        np.arange(len(d), dtype=float), allk, win_gap, n_boot=N_BOOT, seed=SEED
    )
    res = {
        "n_candidates": len(d),
        "n_filled": len(f),
        "n_events_filled": int(f["event"].nunique()),
        "mean_ret_event_avg": ev_avg(np.arange(len(f), dtype=float)),
        "ci_low": lo,
        "ci_high": hi,
        "filled_win_rate": float(f["won"].mean()),
        "unfilled_win_rate": float(d.loc[~d["filled"], "won"].mean()),
        "win_gap_filled_minus_unfilled": win_gap(np.arange(len(d), dtype=float)),
        "win_gap_ci_low": glo,
        "win_gap_ci_high": ghi,
        "mean_maker_price": float(f["maker_price"].mean()),
        "mean_taker_price_same_bets": float(f["taker_price"].mean()),
        "win_minus_price": float(edge.mean()),
        "wmp_ci_low": elo,
        "wmp_ci_high": ehi,
        "median_through_volume": float(f["through_volume"].median()),
    }
    for k, v in res.items():
        print(f"  {k:32s} {v:.4f}" if isinstance(v, float) else f"  {k:32s} {v}")
    passed = lo > 0
    mech = elo > 0 and not ghi < 0
    print(f"\n  PRIMARY: {'PASS' if passed else 'FAIL'}   mechanism check: {mech}")
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "maker_bets.csv", index=False)
    pd.DataFrame([res]).to_csv(OUT / "kalshi_maker.csv", index=False)
    print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
