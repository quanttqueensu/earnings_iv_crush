"""
research_deribit_macro.py
Pre-registered pilot: the macro-release crush in BTC options on Deribit.

``research/other_markets/preregs/deribit_macro_event_prereg.md``. Sell the BTC straddle on the daily expiry that spans
a CPI, payrolls or FOMC release, and compare it with the identical trade on a matched ordinary
day, so the general BTC variance premium is netted out and only the event premium remains.

Release times come from the close times of settled Kalshi events (each closes minutes before its
release). Trades, marks and the initiator's side come from Deribit's free public history API;
settlement from Deribit's daily ``btc_usd`` delivery prices.

    --pull    trade windows and delivery prices into data/cache/deribit
    --score   build event and control straddles, score the paired difference

Usage:
    python research/other_markets/research_deribit_macro.py --pull
    python research/other_markets/research_deribit_macro.py --score
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
from research.other_markets.research_kalshi_tails import _get as kalshi_get  # noqa: E402
from research.other_markets.research_kalshi_tails import _paged as kalshi_paged  # noqa: E402

HIST = "https://history.deribit.com/api/v2/public"
LIVE = "https://www.deribit.com/api/v2/public"
CACHE = Path("data/cache/deribit")
OUT = Path("outputs/research/deribit_macro")

SERIES = {"KXCPI": "cpi", "KXPAYROLLS": "payrolls", "KXFED": "fomc"}
START = pd.Timestamp("2023-01-01", tz="UTC")
LEAD = pd.Timedelta(minutes=60)
WINDOW = pd.Timedelta(hours=4)
MIN_SELL_TRADES = 5
FEE_UNDERLYING, FEE_CAP = 0.0003, 0.125
K_ATM = np.sqrt(2 / np.pi)
N_BOOT = 5000
SEED = 0


# ── events ───────────────────────────────────────────────────────────────────


def release_times() -> pd.DataFrame:
    f = CACHE / "releases.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["close_time"])
    rows = []
    for s, kind in SERIES.items():
        for e in kalshi_paged("/events", "events", series_ticker=s, status="settled"):
            et = e["event_ticker"]
            ms = kalshi_get("/markets", event_ticker=et, limit=1).get("markets", [])
            if not ms:
                ms = kalshi_get("/historical/markets", event_ticker=et, limit=1).get("markets", [])
            if ms:
                rows.append({"event": et, "kind": kind, "close_time": ms[0]["close_time"]})
    df = pd.DataFrame(rows)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df = df[df["close_time"] >= START].sort_values("close_time").reset_index(drop=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)
    return df


def control_time(t: pd.Timestamp, event_days: set) -> pd.Timestamp | None:
    for weeks in (1, 2):
        c = t - pd.Timedelta(days=7 * weeks)
        near = {(c + pd.Timedelta(days=k)).date() for k in (-1, 0, 1)}
        if not near & event_days:
            return c
    return None


# ── pull ─────────────────────────────────────────────────────────────────────


def _req(url: str, **params: object) -> dict:
    for attempt in range(6):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(0.1)
            return r.json()["result"]
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Deribit request failed repeatedly: {url} {params}")


def trades_window(end: pd.Timestamp) -> pd.DataFrame:
    """All BTC option trades in [end - WINDOW, end], cached by window end."""
    f = CACHE / f"trades_{end:%Y%m%dT%H%M}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    lo, hi = int((end - WINDOW).timestamp() * 1000), int(end.timestamp() * 1000)
    out, start = [], lo
    while True:
        r = _req(
            f"{HIST}/get_last_trades_by_currency_and_time",
            currency="BTC",
            kind="option",
            start_timestamp=start,
            end_timestamp=hi,
            count=1000,
            sorting="asc",
        )
        tr = r.get("trades", [])
        out += tr
        if not r.get("has_more") or not tr:
            break
        start = tr[-1]["timestamp"] + 1
    df = pd.DataFrame(out).drop_duplicates("trade_id") if out else pd.DataFrame()
    df.to_parquet(f)
    return df


def delivery_prices() -> pd.Series:
    f = CACHE / "delivery_btc_usd.json"
    if not f.exists():
        rows, off = [], 0
        while True:
            r = _req(f"{LIVE}/get_delivery_prices", index_name="btc_usd", offset=off, count=1000)
            rows += r["data"]
            off += len(r["data"])  # the API caps a page at 100 regardless of ``count``
            if not r["data"] or off >= r["records_total"]:
                break
        f.write_text(json.dumps(rows))
    d = pd.DataFrame(json.loads(f.read_text()))
    return pd.Series(d["delivery_price"].to_numpy(), index=pd.to_datetime(d["date"]).dt.date)


def pull() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rel = release_times()
    days = set(rel["close_time"].dt.date)
    ends = []
    for t in rel["close_time"]:
        ends.append(t - LEAD)
        c = control_time(t, days)
        if c is not None:
            ends.append(c - LEAD)
    print(f"  {len(rel)} releases since {START.date()}, {len(ends)} windows", flush=True)
    for i, e in enumerate(ends, 1):
        trades_window(e)
        if i % 20 == 0 or i == len(ends):
            print(f"  {i}/{len(ends)} windows", flush=True)
    delivery_prices()
    print("  PULL DONE", flush=True)


# ── build ────────────────────────────────────────────────────────────────────


def _parse(df: pd.DataFrame) -> pd.DataFrame:
    p = df["instrument_name"].str.split("-", expand=True)
    df = df.assign(
        expiry=pd.to_datetime(p[1], format="%d%b%y", errors="coerce").dt.tz_localize("UTC")
        + pd.Timedelta(hours=8),
        strike=pd.to_numeric(p[2], errors="coerce"),
        right=p[3],
    )
    return df.dropna(subset=["expiry", "strike"])


def straddle(entry: pd.Timestamp, release: pd.Timestamp, deliv: pd.Series) -> dict | None:
    tr = trades_window(entry)
    if tr.empty:
        return None
    tr = _parse(tr)
    tr = tr[pd.to_datetime(tr["timestamp"], unit="ms", utc=True) <= entry]
    exps = np.sort(tr.loc[tr["expiry"] > release + pd.Timedelta(minutes=10), "expiry"].unique())
    if not len(exps):
        return None
    expiry = pd.Timestamp(exps[0])
    if expiry - release > pd.Timedelta(hours=24):
        return None  # no daily expiry spanning only this release
    x = tr[tr["expiry"] == expiry].sort_values("timestamp")
    index = float(tr.sort_values("timestamp")["index_price"].iloc[-1])
    last = x.groupby(["strike", "right"]).tail(1).set_index(["strike", "right"])
    both = [
        k
        for k in last.index.get_level_values(0).unique()
        if (k, "C") in last.index and (k, "P") in last.index
    ]
    if not both:
        return None
    k = float(min(both, key=lambda s: abs(s - index)))
    sells = x[x["direction"] == "sell"]
    if len(sells) < MIN_SELL_TRADES:
        return None
    h = float(np.median((sells["mark_price"] - sells["price"]) / sells["mark_price"]))
    marks = pd.to_numeric(last["mark_price"], errors="coerce")
    legs_mark = [float(marks.loc[(k, r)]) * index for r in ("C", "P")]
    legs_fill = [m * (1 - h) for m in legs_mark]
    fees = sum(min(FEE_UNDERLYING * index, FEE_CAP * f) for f in legs_fill)
    d_raw = deliv.get(expiry.date())
    if d_raw is None:
        return None
    d = float(d_raw)
    premium = sum(legs_fill)
    settle = abs(float(d) - k)
    buys = x.loc[x["direction"] == "buy", "amount"].sum()
    sells_amt = x.loc[x["direction"] == "sell", "amount"].sum()
    return {
        "expiry": expiry,
        "strike": k,
        "index": index,
        "hours_to_expiry": (expiry - entry).total_seconds() / 3600,
        "seller_discount": h,
        "premium": premium,
        "fees": fees,
        "settle": settle,
        "ret_notional": (premium - fees - settle) / index,
        "ret_premium": (premium - fees - settle) / premium,
        "implied_var": (sum(legs_mark) / (K_ATM * index)) ** 2,
        "realised_var": float(np.log(float(d) / index) ** 2),
        "net_taker_buy": float((buys - sells_amt) / max(buys + sells_amt, 1e-12)),
    }


def score() -> pd.DataFrame:
    rel = release_times()
    deliv = delivery_prices()
    days = set(rel["close_time"].dt.date)
    rows: list[dict] = []
    reasons: dict[str, int] = {}
    for _, r in rel.iterrows():
        t = r["close_time"]
        ev = straddle(t - LEAD, t, deliv)
        c_t = control_time(t, days)
        ct = straddle(c_t - LEAD, c_t, deliv) if c_t is not None else None
        why = "event straddle unbuildable" if ev is None else ("no control" if ct is None else None)
        if why or ev is None or ct is None:
            key = why or "unbuildable"
            reasons[key] = reasons.get(key, 0) + 1
            continue
        rows.append(
            {
                "event": r["event"],
                "kind": r["kind"],
                "release": t,
                **{f"ev_{k}": v for k, v in ev.items()},
                **{f"ct_{k}": v for k, v in ct.items()},
            }
        )
    print(f"  funnel: {len(rel)} releases, paired {len(rows)}, dropped {reasons}")
    if len(rows) < 10:
        raise SystemExit(f"{len(rows)} pairs - too few to score")
    d = pd.DataFrame(rows)
    d["diff"] = d["ev_ret_notional"] - d["ct_ret_notional"]
    d["mech"] = (d["ev_implied_var"] - d["ct_implied_var"]) - (
        d["ev_realised_var"] - d["ct_realised_var"]
    )
    keys = d["event"].to_numpy()

    def ci(v: np.ndarray) -> tuple[float, float]:
        return cluster_bootstrap_ci(v, keys, lambda x: float(x.mean()), n_boot=N_BOOT, seed=SEED)

    out = []
    for label, g in [("all", d), *d.groupby("kind")]:
        kk = g["event"].to_numpy()

        def f(v: np.ndarray, kk: np.ndarray = kk) -> tuple[float, float]:
            return cluster_bootstrap_ci(v, kk, lambda x: float(x.mean()), n_boot=N_BOOT, seed=SEED)

        lo, hi = f(g["diff"].to_numpy())
        mlo, mhi = f(g["mech"].to_numpy())
        out.append(
            {
                "slice": label,
                "n_pairs": len(g),
                "event_ret_notional": float(g["ev_ret_notional"].mean()),
                "control_ret_notional": float(g["ct_ret_notional"].mean()),
                "event_hit": float((g["ev_ret_notional"] > 0).mean()),
                "diff_mean": float(g["diff"].mean()),
                "diff_ci_low": lo,
                "diff_ci_high": hi,
                "mech_mean": float(g["mech"].mean()),
                "mech_ci_low": mlo,
                "mech_ci_high": mhi,
                "event_ret_premium": float(g["ev_ret_premium"].mean()),
                "median_seller_discount": float(g["ev_seller_discount"].median()),
                "spearman_ret_vs_taker_buy": float(
                    g["ev_ret_notional"].corr(g["ev_net_taker_buy"], method="spearman")
                ),
            }
        )
    res = pd.DataFrame(out)
    print(res.T.to_string(float_format=lambda v: f"{v:.5f}"))
    a = res.iloc[0]
    print(
        f"\n  PRIMARY: {'PASS' if a['diff_ci_low'] > 0 else 'FAIL'}   "
        f"mechanism (implied excess > realised excess): {a['mech_ci_low'] > 0}"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "pairs.csv", index=False)
    _ = ci  # event-level helper retained for the pooled slice
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args()
    if args.pull:
        pull()
    if args.score:
        score().to_csv(OUT / "deribit_macro.csv", index=False)
        print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
