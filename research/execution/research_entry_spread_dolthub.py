"""
research_entry_spread_dolthub.py
Pre-registered entry-spread filter, tested on the free DoltHub 2019-2024 block.

``research/execution/preregs/entry_spread_dolthub_prereg.md``. The hypothesis came from exploring the 2025-2026
broad block after a failed test, so it is only evidence if it reproduces here, on a source and
time stamp that played no part in finding it. The threshold (entry half-spread at most 3.82% of
mid) is fixed and never re-estimated.

Two stages, so the free pull can run unattended and resume:

    --pull    fetch entry- and exit-date chains from DoltHub into data/cache/dolthub_spread
    --score   price the straddles at the touch and score the filtered book

Usage:
    python research/execution/research_entry_spread_dolthub.py --pull --workers 3
    python research/execution/research_entry_spread_dolthub.py --score
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data.sectors import MEGACAP_SECTOR  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

EVENTS = Path("outputs/research/dolthub_sp500_events.parquet")
CACHE = Path("data/cache/dolthub_spread")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/entry_spread_dolthub")

THRESHOLD = 0.0382  # frozen in the pre-registration
REGT_SPOT = 0.20
N_TRIALS = 1495
N_BOOT = 5000
SEED = 0


# ── pull ─────────────────────────────────────────────────────────────────────


def _path(ticker: str, day: pd.Timestamp) -> Path:
    return CACHE / f"{ticker}_{pd.Timestamp(day).date()}.parquet"


def pull(workers: int) -> None:
    from earnings_iv_crush.data.dolthub_options import fetch_option_chain

    CACHE.mkdir(parents=True, exist_ok=True)
    ev = pd.read_parquet(EVENTS)
    jobs = sorted(
        {(t, pd.Timestamp(d)) for t, d in zip(ev["ticker"], ev["entry_date"], strict=True)}
        | {(t, pd.Timestamp(d)) for t, d in zip(ev["ticker"], ev["exit_date"], strict=True)}
    )
    todo = [j for j in jobs if not _path(*j).exists()]
    print(
        f"  {len(jobs)} ticker-days, {len(jobs) - len(todo)} cached, {len(todo)} to pull",
        flush=True,
    )
    lock = threading.Lock()
    state = {"done": 0, "fail": 0, "t0": time.time()}

    def one(job: tuple[str, pd.Timestamp]) -> None:
        t, d = job
        try:
            ch = fetch_option_chain(t, str(d.date()))
            ch.to_parquet(_path(t, d))
        except Exception:  # noqa: BLE001
            with lock:
                state["fail"] += 1
        with lock:
            state["done"] += 1
            n = state["done"]
            if n % 50 == 0 or n == len(todo):
                rate = n / max(time.time() - state["t0"], 1e-9)
                eta = (len(todo) - n) / max(rate, 1e-9) / 60
                print(
                    f"  {n}/{len(todo)} pulled, {state['fail']} failed, "
                    f"{rate:.2f}/s, eta {eta:.0f} min",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    print(f"  PULL DONE: {state['done']} attempted, {state['fail']} failed", flush=True)


# ── score ────────────────────────────────────────────────────────────────────


def _touch(ch: pd.DataFrame, strike: float, expiry: pd.Timestamp) -> tuple[float, float] | None:
    leg = ch[(ch["strike"] == strike) & (ch["expiry"] == expiry)]
    c, p = leg[leg["right"] == "C"], leg[leg["right"] == "P"]
    if c.empty or p.empty:
        return None
    bid = float(c["bid"].iloc[0] + p["bid"].iloc[0])
    ask = float(c["ask"].iloc[0] + p["ask"].iloc[0])
    return (bid, ask) if ask > bid > 0 else None


def build() -> pd.DataFrame:
    ev = pd.read_parquet(EVENTS)
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    reasons: dict[str, int] = {}

    def drop(why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    rows = []
    for _, e in ev.iterrows():
        pi, po = _path(e["ticker"], e["entry_date"]), _path(e["ticker"], e["exit_date"])
        if not (pi.exists() and po.exists()):
            drop("chain not pulled")
            continue
        ci, co = pd.read_parquet(pi), pd.read_parquet(po)
        if ci.empty or co.empty:
            drop("empty chain")
            continue
        exps = np.sort(pd.to_datetime(ci["expiry"]).unique())
        exps = exps[exps >= np.datetime64(e["exit_date"])]
        if not len(exps):
            drop("no expiry after exit")
            continue
        expiry = pd.Timestamp(exps[0])
        ci["expiry"], co["expiry"] = pd.to_datetime(ci["expiry"]), pd.to_datetime(co["expiry"])
        qi, qo = _touch(ci, e["strike"], expiry), _touch(co, e["strike"], expiry)
        if qi is None:
            drop("entry straddle unquoted")
            continue
        if qo is None:
            drop("exit straddle unquoted")
            continue
        mid_in, mid_out = sum(qi) / 2, sum(qo) / 2
        margin = (REGT_SPOT * float(e["spot_entry"]) + mid_in) * 100
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "expiry": expiry,
                "megacap": e["ticker"] in MEGACAP_SECTOR,
                "entry_rel": (qi[1] - qi[0]) / (qi[1] + qi[0]),
                "rom_touch": (qi[0] - qo[1]) * 100 / margin,
                "rom_gross_mid": (mid_in - mid_out) * 100 / margin,
            }
        )
    print(f"  funnel: {len(ev)} events, scored {len(rows)}, dropped {reasons}")
    if not rows:
        raise SystemExit("nothing scoreable - refusing to report an empty book")
    return pd.DataFrame(rows)


def _sharpe(x: np.ndarray) -> float:
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def score() -> pd.DataFrame:
    d = build()
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])
    books = {
        "filtered": d[d["entry_rel"] <= THRESHOLD],
        "unfiltered": d,
        "filtered_megacap": d[(d["entry_rel"] <= THRESHOLD) & d["megacap"]],
        "filtered_non_megacap": d[(d["entry_rel"] <= THRESHOLD) & ~d["megacap"]],
        "above_threshold": d[d["entry_rel"] > THRESHOLD],
    }
    rows = []
    for label, b in books.items():
        x = b["rom_touch"].to_numpy()
        if len(x) < 3:
            rows.append({"book": label, "n": len(x)})
            continue
        keys = b["entry_date"].dt.strftime("%Y-%m-%d").to_numpy()
        lo, hi = cluster_bootstrap_ci(x, keys, _sharpe, n_boot=N_BOOT, seed=SEED)
        g = b["rom_gross_mid"].to_numpy()
        rows.append(
            {
                "book": label,
                "n": len(x),
                "mean_rom_touch": float(x.mean()),
                "sharpe_touch": _sharpe(x),
                "ci_low": lo,
                "ci_high": hi,
                "hit_rate": float((x > 0).mean()),
                "mean_gross_mid": float(g.mean()),
                "se_gross_mid": float(g.std(ddof=1) / np.sqrt(len(g))),
                "median_entry_rel": float(b["entry_rel"].median()),
                "dsr": float(
                    deflated_sharpe_ratio(pd.Series(x), n_trials=N_TRIALS, sr_trials_std=sr_std)
                ),
            }
        )
    res = pd.DataFrame(rows).set_index("book")
    f, u = res.loc["filtered"], res.loc["unfiltered"]
    passed = bool(f["ci_low"] > 0)
    mech = bool(
        f["mean_rom_touch"] > u["mean_rom_touch"]
        and f["mean_gross_mid"] >= u["mean_gross_mid"] - u["se_gross_mid"]
    )
    print(res.T.to_string(float_format=lambda v: f"{v:.4f}"))
    print(f"\n  PRIMARY: {'PASS' if passed else 'FAIL'}   mechanism check: {mech}")
    return res.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    if args.pull:
        pull(args.workers)
    if args.score:
        OUT.mkdir(parents=True, exist_ok=True)
        score().to_csv(OUT / "entry_spread_dolthub.csv", index=False)
        print(f"  wrote {(OUT / 'entry_spread_dolthub.csv').resolve()}")


if __name__ == "__main__":
    main()
