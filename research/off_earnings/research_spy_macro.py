"""
research_spy_macro.py
Pre-registered test: SPY straddles across scheduled CPI, payrolls and FOMC releases.

``research/off_earnings/preregs/spy_macro_straddle_prereg.md``. Each trade is entered at the end-of-day snapshot before a
release day and exited at the release day's snapshot, priced at the touch, and compared with
tenor- and regime-matched ordinary days so the generic daily variance premium is separated from
the event premium.

    --pull    fetch one SPY chain per business day from DoltHub into data/cache/spy_macro
    --score   build the trades and score the two pre-registered families

Usage:
    python research/off_earnings/research_spy_macro.py --pull --workers 3
    python research/off_earnings/research_spy_macro.py --score
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

from earnings_iv_crush.engine.stats import deflated_sharpe_ratio, nyse_sessions  # noqa: E402

CACHE = Path("data/cache/spy_macro")
RELEASES = CACHE / "releases.csv"
OUT = Path("outputs/research/spy_macro")
START, END = "2019-01-02", "2024-12-31"
HORIZON_DAYS = 60
TENOR_TOL = 3  # calendar days, frozen
REGIME_TOL = 60  # trading days, frozen
MIN_CONTROLS = 5
MAX_HOLD = 3  # sessions, amendment 01
N_BOOT = 5000
SEED = 0
CI = 0.975  # Bonferroni over the two families
N_TRIALS = 1497 + 2


# ── pull ─────────────────────────────────────────────────────────────────────


def _path(day: pd.Timestamp) -> Path:
    return CACHE / f"SPY_{day.date()}.parquet"


def pull(workers: int) -> None:
    from earnings_iv_crush.data.dolthub_options import fetch_option_chain

    days = pd.bdate_range(START, END)
    todo = [d for d in days if not _path(d).exists()]
    print(f"  {len(days)} business days, {len(todo)} to pull", flush=True)
    lock = threading.Lock()
    st = {"done": 0, "empty": 0, "fail": 0, "t0": time.time()}

    def one(d: pd.Timestamp) -> None:
        try:
            ch = fetch_option_chain(
                "SPY", str(d.date()), horizon_days=HORIZON_DAYS, lookback_days=0
            )
            ch.to_parquet(_path(d))  # an empty frame marks a non-session day
            key = "empty" if ch.empty else "done"
        except Exception:  # noqa: BLE001
            key = "fail"
        with lock:
            st[key] += 1
            n = st["done"] + st["empty"] + st["fail"]
            if n % 100 == 0:
                print(
                    f"  {n}/{len(todo)} done={st['done']} empty={st['empty']} "
                    f"fail={st['fail']} {time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    print(f"PULL DONE {st}", flush=True)


# ── trade construction ───────────────────────────────────────────────────────


def _load(day: pd.Timestamp) -> pd.DataFrame:
    ch = pd.read_parquet(_path(day))
    ok = (ch["bid"] > 0) & (ch["ask"] >= ch["bid"])
    return ch[ok]


def _legs(ch: pd.DataFrame, expiry: pd.Timestamp, strike: float) -> tuple[float, ...] | None:
    s = ch[(ch["expiry"] == expiry) & (ch["strike"] == strike)]
    c, p = s[s["right"] == "C"], s[s["right"] == "P"]
    if len(c) != 1 or len(p) != 1:
        return None
    return (
        float(c["bid"].iloc[0]),
        float(c["ask"].iloc[0]),
        float(p["bid"].iloc[0]),
        float(p["ask"].iloc[0]),
    )


def _trade(prev: pd.Timestamp, day: pd.Timestamp) -> dict | str:
    e, x = _load(prev), _load(day)
    if e.empty or x.empty:
        return "no_chain"
    shared = set(e["expiry"]) & set(x["expiry"])  # amendment 02
    exps = np.sort([d for d in shared if d > day])
    if len(exps) == 0:
        return "no_expiry"
    expiry = pd.Timestamp(exps[0])
    sub = e[e["expiry"] == expiry]
    mid = (sub["bid"] + sub["ask"]) / 2
    piv = sub.assign(mid=mid).pivot_table(index="strike", columns="right", values="mid")
    piv = piv.dropna(subset=["C", "P"]) if {"C", "P"} <= set(piv.columns) else piv.iloc[0:0]
    if piv.empty:
        return "no_pair"
    strike = float((piv["C"] - piv["P"]).abs().idxmin())
    fwd0 = strike + float(piv.loc[strike, "C"] - piv.loc[strike, "P"])
    a, b = _legs(e, expiry, strike), _legs(x, expiry, strike)
    if a is None or b is None:
        return "leg_missing"
    cb0, ca0, pb0, pa0 = a
    cb1, ca1, pb1, pa1 = b
    p0 = (cb0 + ca0 + pb0 + pa0) / 2
    p1 = (cb1 + ca1 + pb1 + pa1) / 2
    xs = x[x["expiry"] == expiry]
    xp = xs.assign(mid=(xs["bid"] + xs["ask"]) / 2).pivot_table(
        index="strike", columns="right", values="mid"
    )
    xp = xp.dropna()
    k1 = float((xp["C"] - xp["P"]).abs().idxmin()) if not xp.empty else np.nan
    fwd1 = k1 + float(xp.loc[k1, "C"] - xp.loc[k1, "P"]) if not xp.empty else np.nan
    return {
        "entry": prev,
        "day": day,
        "expiry": expiry,
        "tenor": (expiry - prev).days,
        "strike": strike,
        "p0": p0,
        "fwd0": fwd0,
        "fwd1": fwd1,
        "long_touch": (cb1 + pb1 - ca0 - pa0) / p0,
        "short_touch": (cb0 + pb0 - ca1 - pa1) / p0,
        "long_mid": (p1 - p0) / p0,
        "half_spread": ((ca0 - cb0) + (pa0 - pb0)) / 2 / p0,
    }


def build() -> pd.DataFrame:
    nyse = nyse_sessions(pd.Timestamp(START), pd.Timestamp(END))
    pos = {d: i for i, d in enumerate(nyse)}
    cached = sorted(
        pd.Timestamp(p.stem.split("_")[1])
        for p in CACHE.glob("SPY_*.parquet")
        if not pd.read_parquet(p, columns=["strike"]).empty
    )
    sessions = [d for d in cached if d in pos]
    print(f"  {len(cached)} non-empty snapshots, {len(sessions)} on NYSE sessions", flush=True)
    if len(sessions) < 100:
        raise RuntimeError(f"only {len(sessions)} usable sessions cached; run --pull first")
    rel = pd.read_csv(RELEASES, parse_dates=["date"])
    kinds = rel.groupby("date")["kind"].apply(lambda s: "+".join(sorted(s))).to_dict()
    rows, funnel = [], {"pairs": 0, "gap_too_long": 0}
    for prev, day in zip(sessions[:-1], sessions[1:], strict=True):
        funnel["pairs"] += 1
        hold = pos[day] - pos[prev]
        if hold > MAX_HOLD:
            funnel["gap_too_long"] += 1
            continue
        r = _trade(prev, day)
        if isinstance(r, str):
            funnel[r] = funnel.get(r, 0) + 1
            continue
        r["kind"] = kinds.get(day, "none")
        r["hold"] = hold
        r["idx"] = pos[day]
        rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no trades built")
    print(f"  funnel: {funnel}, trades {len(df)}", flush=True)
    in_range = rel[(rel["date"] >= sessions[0]) & (rel["date"] <= sessions[-1])]
    missing = sorted(set(in_range["date"]) - set(df["day"]))
    print(f"  releases in range {len(in_range)}, without a trade {len(missing)}", flush=True)
    return df


# ── scoring ──────────────────────────────────────────────────────────────────


def _boot(x: np.ndarray, ci: float = CI) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    m = rng.choice(x, size=(N_BOOT, len(x)), replace=True).mean(axis=1)
    a = (1 - ci) / 2
    return float(np.quantile(m, a)), float(np.quantile(m, 1 - a))


def _paired(df: pd.DataFrame, ev: pd.DataFrame, col: str) -> pd.Series:
    ctrl = df[df["kind"] == "none"]
    out = {}
    for i, r in ev.iterrows():
        m = ctrl[
            ((ctrl["tenor"] - r["tenor"]).abs() <= TENOR_TOL)
            & ((ctrl["idx"] - r["idx"]).abs() <= REGIME_TOL)
            & (ctrl["hold"] == r["hold"])
        ]
        if len(m) >= MIN_CONTROLS:
            out[i] = r[col] - m[col].mean()
    return pd.Series(out, dtype=float)


def _family(df: pd.DataFrame, ev: pd.DataFrame, col: str, name: str) -> dict:
    x = ev[col].to_numpy()
    d = _paired(df, ev, col)
    lo, hi = _boot(x)
    dlo, dhi = _boot(d.to_numpy())
    sr = float(x.mean() / x.std(ddof=1))
    res = {
        "family": name,
        "n": len(x),
        "mean": float(x.mean()),
        "ci": [lo, hi],
        "n_paired": len(d),
        "paired_mean": float(d.mean()),
        "paired_ci": [dlo, dhi],
        "sharpe_per_trade": sr,
        "dsr": float(deflated_sharpe_ratio(pd.Series(x), n_trials=N_TRIALS)),
        "pass_i": lo > 0,
        "pass_ii": dlo > 0,
    }
    res["verdict"] = (
        "PASS"
        if res["pass_i"] and res["pass_ii"]
        else ("generic premium, not event-specific" if res["pass_i"] else "FAIL")
    )
    return res


def score() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_csv(OUT / "trades.csv", index=False)
    rel_mask = df["kind"].str.contains("cpi|nfp", regex=True)
    fomc_mask = df["kind"] == "fomc"
    a1 = _family(df, df[rel_mask], "short_touch", "A1 data releases, short at touch")
    a2 = _family(df, df[fomc_mask], "long_touch", "A2 FOMC only, long at touch")
    for f in (a1, a2):
        print(json.dumps(f, indent=1, default=float))
    # secondary, descriptive
    desc = (
        df.assign(short_mid=-df["long_mid"])
        .groupby("kind")[["long_touch", "short_touch", "long_mid", "half_spread", "tenor", "hold"]]
        .agg(["mean", "count"])
    )
    print(desc.round(4).to_string())
    df["year"] = df["day"].dt.year
    by_year = df[rel_mask].groupby("year")["short_touch"].agg(["mean", "count"])
    print("A1 by year\n", by_year.round(4).to_string())
    by_year2 = df[fomc_mask].groupby("year")["long_touch"].agg(["mean", "count"])
    print("A2 by year\n", by_year2.round(4).to_string())
    df["abs_move"] = (df["fwd1"] - df["fwd0"]).abs() / df["fwd0"]
    moves = df.groupby(df["kind"].map(lambda k: "none" if k == "none" else k))["abs_move"].mean()
    print("mean |forward move| by kind\n", moves.round(5).to_string())
    for name, mask, col in ((a1, rel_mask, "short_touch"), (a2, fomc_mask, "long_touch")):
        worst = df.loc[mask, col].nsmallest(5).round(3).tolist()
        name["worst5"] = worst
    json.dump({"A1": a1, "A2": a2}, open(OUT / "verdict.json", "w"), indent=1, default=float)


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
