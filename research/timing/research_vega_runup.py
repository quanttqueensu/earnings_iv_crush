"""
research_vega_runup.py
Pre-registered test of the pre-announcement vega run-up (state of record section 2.5).

``research/timing/preregs/vega_runup_prereg.md`` with amendment 01. A long at-the-money straddle on the front
expiry spanning the event is bought three to six sessions before the last pre-news snapshot and
sold at that snapshot, priced at the touch, and compared with the identical trade on the same name
in a window 30 sessions after the event.

    --pull    discover usable DoltHub snapshots per event and null window and cache the chains
    --score   price the trades and score the pre-registered rule

Usage:
    python research/timing/research_vega_runup.py --pull --workers 3
    python research/timing/research_vega_runup.py --score
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio, nyse_sessions  # noqa: E402

EVENTS = Path("outputs/research/dolthub_sp500_events.parquet")
CACHE = Path("data/cache/dolthub_runup")
OUT = Path("outputs/research/vega_runup")
NULL_SHIFT = 30  # sessions after exit_date, frozen
NULL_CLEAR = 10  # business days free of the ticker's events around the null window
EXIT_LAG = (0, 1, 2)  # sessions before entry_date the exit snapshot may sit
ENTRY_GAP = (3, 4, 5, 6)  # sessions before the exit snapshot the entry may sit
SHORT_GAP = (1, 2)  # secondary variant
HORIZON_DAYS = 70
N_BOOT = 5000
SEED = 0
N_TRIALS = 1497 + 6

NYSE = nyse_sessions(pd.Timestamp("2018-06-01"), pd.Timestamp("2025-06-30"))
POS = {d: i for i, d in enumerate(NYSE)}


def _shift(day: pd.Timestamp, n: int) -> pd.Timestamp:
    """The NYSE session n sessions after ``day`` (negative for before)."""
    i = int(np.searchsorted(NYSE.values, np.datetime64(day)))
    return NYSE[i + n]


# ── windows ──────────────────────────────────────────────────────────────────


def windows() -> pd.DataFrame:
    ev = pd.read_parquet(EVENTS)
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    ev["exit_date"] = pd.to_datetime(ev["exit_date"])
    rows = []
    for _, r in ev.iterrows():
        rows.append(
            {
                "ticker": r["ticker"],
                "kind": "event",
                "event_id": f"{r['ticker']}_{r['entry_date'].date()}",
                "anchor": r["entry_date"],  # last pre-news session
                "expiry_after": r["exit_date"],
            }
        )
        pseudo = _shift(r["exit_date"], NULL_SHIFT)
        lo = pseudo - pd.offsets.BDay(max(ENTRY_GAP) + max(EXIT_LAG) + NULL_CLEAR)
        hi = pseudo + pd.offsets.BDay(1 + NULL_CLEAR)
        mine = ev[ev["ticker"] == r["ticker"]]
        clash = ((mine["entry_date"] >= lo) & (mine["entry_date"] <= hi)).any()
        if not clash:
            rows.append(
                {
                    "ticker": r["ticker"],
                    "kind": "null",
                    "event_id": f"{r['ticker']}_{r['entry_date'].date()}",
                    "anchor": pseudo,
                    "expiry_after": _shift(pseudo, 1),
                }
            )
    w = pd.DataFrame(rows)
    print(
        f"  {int((w['kind'] == 'event').sum())} event windows, "
        f"{int((w['kind'] == 'null').sum())} null windows",
        flush=True,
    )
    return w


# ── pull ─────────────────────────────────────────────────────────────────────


def _path(ticker: str, day: pd.Timestamp) -> Path:
    return CACHE / f"{ticker}_{day.date()}.parquet"


_lock = threading.Lock()


def _chain(ticker: str, day: pd.Timestamp, fetch: bool) -> pd.DataFrame | None:
    """Cached exact-date chain; None when not cached and ``fetch`` is False."""
    p = _path(ticker, day)
    if p.exists():
        return pd.read_parquet(p)
    if not fetch:
        return None
    from earnings_iv_crush.data.dolthub_options import fetch_option_chain

    ch = fetch_option_chain(ticker, str(day.date()), horizon_days=HORIZON_DAYS, lookback_days=0)
    ch.to_parquet(p)
    return ch


def _first(ticker: str, days: list[pd.Timestamp], fetch: bool) -> pd.Timestamp | None:
    for d in days:
        ch = _chain(ticker, d, fetch)
        if ch is not None and not ch.empty:
            return d
    return None


def locate(w: pd.Series, fetch: bool) -> dict:
    """Exit snapshot, primary entry snapshot and short-variant entry snapshot for one window."""
    t = w["ticker"]
    x = _first(t, [_shift(w["anchor"], -k) for k in EXIT_LAG], fetch)
    if x is None:
        return {"exit": None, "entry": None, "entry_short": None}
    e = _first(t, [_shift(x, -k) for k in ENTRY_GAP], fetch)
    es = _first(t, [_shift(x, -k) for k in SHORT_GAP], fetch)
    return {"exit": x, "entry": e, "entry_short": es}


def pull(workers: int) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    w = windows()
    st = {"n": 0, "fail": 0, "t0": time.time()}

    def one(i: int) -> None:
        try:
            locate(w.iloc[i], fetch=True)
        except Exception:  # noqa: BLE001
            with _lock:
                st["fail"] += 1
        with _lock:
            st["n"] += 1
            if st["n"] % 100 == 0:
                print(
                    f"  {st['n']}/{len(w)} windows, fail={st['fail']} "
                    f"{time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, range(len(w))))
    print(f"PULL DONE windows={len(w)} fail={st['fail']}", flush=True)


# ── pricing ──────────────────────────────────────────────────────────────────


def _usable(ch: pd.DataFrame) -> pd.DataFrame:
    return ch[(ch["bid"] > 0) & (ch["ask"] >= ch["bid"])]


def _price(t: str, entry: pd.Timestamp, exit_: pd.Timestamp, after: pd.Timestamp) -> dict | str:
    e = _usable(_chain(t, entry, False))
    x = _usable(_chain(t, exit_, False))
    shared = set(e["expiry"]) & set(x["expiry"])  # amendment 02
    exps = np.sort([d for d in shared if d > after])
    if len(exps) == 0:
        return "no_expiry"
    expiry = pd.Timestamp(exps[0])
    sub = e[e["expiry"] == expiry].assign(mid=lambda d: (d["bid"] + d["ask"]) / 2)
    piv = sub.pivot_table(index="strike", columns="right", values="mid")
    if not {"C", "P"} <= set(piv.columns) or piv.dropna().empty:
        return "no_pair"
    piv = piv.dropna()
    k = float((piv["C"] - piv["P"]).abs().idxmin())

    def legs(ch: pd.DataFrame) -> pd.DataFrame | None:
        s = ch[(ch["expiry"] == expiry) & (ch["strike"] == k)].set_index("right")
        return s if {"C", "P"} <= set(s.index) and len(s) == 2 else None

    a, b = legs(e), legs(x)
    if a is None or b is None:
        return "leg_missing"
    p0 = float((a["bid"] + a["ask"]).sum() / 2)
    p1 = float((b["bid"] + b["ask"]).sum() / 2)
    return {
        "expiry": expiry,
        "strike": k,
        "p0": p0,
        "long_touch": float(b["bid"].sum() - a["ask"].sum()) / p0,
        "long_mid": (p1 - p0) / p0,
        "half_spread": float((a["ask"] - a["bid"]).sum() / 2) / p0,
        "iv0": float(a["iv"].mean()),
        "iv1": float(b["iv"].mean()),
        "hold": POS[exit_] - POS[entry],
    }


def build() -> pd.DataFrame:
    w = windows()
    rows, funnel = [], {}

    def drop(why: str) -> None:
        funnel[why] = funnel.get(why, 0) + 1

    for _, r in w.iterrows():
        loc = locate(r, fetch=False)
        if loc["exit"] is None:
            drop(f"{r['kind']}_no_exit_snapshot")
            continue
        for variant, key in (("primary", "entry"), ("short", "entry_short")):
            if loc[key] is None:
                drop(f"{r['kind']}_{variant}_no_entry_snapshot")
                continue
            res = _price(r["ticker"], loc[key], loc["exit"], r["expiry_after"])
            if isinstance(res, str):
                drop(f"{r['kind']}_{variant}_{res}")
                continue
            res.update(
                ticker=r["ticker"],
                kind=r["kind"],
                variant=variant,
                event_id=r["event_id"],
                entry=loc[key],
                exit=loc["exit"],
                anchor=r["anchor"],
            )
            rows.append(res)
    print(f"  funnel: {funnel}", flush=True)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no trades priced")
    return df


# ── scoring ──────────────────────────────────────────────────────────────────


def _mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def _ci(x: pd.Series, keys: pd.Series) -> list[float]:
    lo, hi = cluster_bootstrap_ci(x.to_numpy(), keys.to_numpy(), _mean, n_boot=N_BOOT, seed=SEED)
    return [float(lo), float(hi)]


def score() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_csv(OUT / "trades.csv", index=False)
    ev = df[(df["kind"] == "event") & (df["variant"] == "primary")]
    nl = df[(df["kind"] == "null") & (df["variant"] == "primary")]
    x = ev["long_touch"]
    paired = ev.merge(nl[["event_id", "long_touch"]], on="event_id", suffixes=("", "_null"))
    d = paired["long_touch"] - paired["long_touch_null"]
    res = {
        "n_events": len(ev),
        "mean_long_touch": float(x.mean()),
        "ci_long_touch": _ci(x, ev["anchor"]),
        "mean_long_mid": float(ev["long_mid"].mean()),
        "ci_long_mid": _ci(ev["long_mid"], ev["anchor"]),
        "n_null": len(nl),
        "mean_null_touch": float(nl["long_touch"].mean()),
        "n_paired": len(paired),
        "paired_mean": float(d.mean()),
        "paired_ci": _ci(d, paired["anchor"]),
        "sharpe_per_trade": float(x.mean() / x.std(ddof=1)),
        "dsr": float(deflated_sharpe_ratio(x.reset_index(drop=True), n_trials=N_TRIALS)),
        "mean_half_spread": float(ev["half_spread"].mean()),
        "mean_iv_change_vol_pts": float((ev["iv1"] - ev["iv0"]).mean() * 100),
        "hold_counts": ev["hold"].value_counts().sort_index().to_dict(),
    }
    res["pass_i"] = res["ci_long_touch"][0] > 0
    res["pass_ii"] = res["paired_ci"][0] > 0
    res["verdict"] = "PASS" if res["pass_i"] and res["pass_ii"] else "FAIL"
    # secondary, descriptive
    sv = df[(df["kind"] == "event") & (df["variant"] == "short")]
    res["short_variant"] = {
        "n": len(sv),
        "mean_long_touch": float(sv["long_touch"].mean()),
        "ci": _ci(sv["long_touch"], sv["anchor"]),
        "mean_long_mid": float(sv["long_mid"].mean()),
    }
    ev = ev.assign(
        year=ev["anchor"].dt.year,
        spread_tercile=pd.qcut(ev["half_spread"], 3, labels=["tight", "mid", "wide"]),
        div=ev["iv1"] - ev["iv0"],
    )
    res["by_year"] = ev.groupby("year")["long_touch"].agg(["mean", "count"]).round(4).to_dict()
    res["by_spread"] = (
        ev.groupby("spread_tercile", observed=True)["long_mid"]
        .agg(["mean", "count"])
        .round(4)
        .to_dict()
    )
    beta = np.polyfit(ev["div"], ev["long_mid"], 1)
    res["mid_on_div"] = {"slope_per_vol_unit": float(beta[0]), "intercept": float(beta[1])}
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(OUT / "verdict.json", "w"), indent=1, default=str)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.pull:
        pull(a.workers)
    if a.score:
        score()


if __name__ == "__main__":
    main()
