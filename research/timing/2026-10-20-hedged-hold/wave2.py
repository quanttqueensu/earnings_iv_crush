"""
wave2.py
The declared second wave of the hedged-hold study (amendment 01): W2a, S1 at 46 to 120 days;
W2b, S2 selected by the post-event term slope; W2c, GARCH(1,1) with an announcement dummy in
place of HAR on the S3b arm (the arm with the higher discovery top-minus-bottom estimate).

Reuses the scoring machinery of ``study.py`` unchanged. Discovery first; validation only for a
candidate that passes discovery.

Usage
-----
    python research/timing/2026-10-20-hedged-hold/wave2.py [--workers 8]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import build_features as bf  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import study  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import verify_prereg  # noqa: E402

AMEND = HERE / "prereg_amendment_01.md"
AMEND_RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}_amendment_01.json"
W2A_DTE = (46, 120)
W2C_ARM = "S3b"  # discovery top-minus-bottom: S3a -0.732, S3b +0.036 (amendment 01 rule)
study.N_TRIALS = 1542  # this wave's DSR input, per amendment 01


def w2a_features(row: tuple[str, pd.Timestamp, pd.Timestamp]) -> dict:
    """The 46-120 day straddle holding the event and its split against the front expiry."""
    ticker, entry, exit_ = row
    rec: dict = {"ticker": ticker, "entry_date": entry}
    ch = bf._load(ticker, entry)
    if ch is None:
        rec.update(bf._q("s1", None))
        rec.update(bf._split("s1split", None, None))
        return rec
    exps = sorted(pd.Timestamp(x) for x in ch["expiry"].unique())
    e1 = next((e for e in exps if e.normalize() >= exit_.normalize()), None)
    front = hh.atm_quote(ch, e1, entry) if e1 is not None else None
    es = hh.pick_expiry(exps, entry, W2A_DTE, not_before=exit_)
    sold = hh.atm_quote(ch, es, entry) if es is not None else None
    rec.update(bf._q("s1", sold))
    if sold is not None and front is not None and es != e1:
        rec.update(bf._split("s1split", front, sold))
    elif sold is not None and front is not None:
        e2 = bf._next_after(exps, e1, HEDGED.split_min_gap_days)
        rec.update(bf._split("s1split", front, hh.atm_quote(ch, e2, entry) if e2 else None))
    else:
        rec.update(bf._split("s1split", None, None))
    return rec


def run_w2a(ev: pd.DataFrame, paths: study.Paths, workers: int, summary: dict) -> None:
    print("\n== W2a: S1 at 46-120 days ==")
    for blk in study.BLOCKS:
        if blk == "validation" and not summary["W2a_discovery"]["pass"]:
            print("  W2a fails discovery: validation not run (kill criterion)")
            return
        b = ev[ev["block"] == blk].reset_index(drop=True)
        rows = list(zip(b["ticker"], b["entry_date"], b["exit_date"], strict=True))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            f = pd.DataFrame(list(pool.map(w2a_features, rows, chunksize=32)))
        base = b.drop(columns=[c for c in b.columns if c.startswith(("s1_", "s1split_"))])
        b2 = pd.concat([base, f.drop(columns=["ticker", "entry_date"])], axis=1)
        res = study.run_book(b2, paths, "S1")
        d = pd.concat([b2, res], axis=1)
        summary[f"W2a_{blk}_attrition"] = study.attrition(b2, res["reason"], paths, f"W2a {blk}")
        ok = d[d["reason"] == "ok"]
        print(
            f"  median days to expiry sold: {float((ok['expiry'] - ok['entry_date']).dt.days.median())}"
        )
        summary[f"W2a_{blk}"] = study.score_book(ok, f"W2a {blk}")


def run_w2b(s2: pd.DataFrame, summary: dict) -> None:
    print("\n== W2b: S2 selected by the post-event term slope (seller's top = lowest slope) ==")
    d = s2[np.isfinite(s2["post_slope"])].copy()
    raw = hh.causal_bins(d["post_slope"], d["exit_date"], 3, HEDGED.tercile_min_prior)
    d["bin"] = np.where(raw >= 0, 2 - raw, -1)  # bin 2 = lowest slope, the seller's choice
    for blk in study.BLOCKS:
        if blk == "validation" and not summary["W2b_discovery"]["pass"]:
            print("  W2b fails discovery: validation not run (kill criterion)")
            return
        summary[f"W2b_{blk}"] = study.score_selector(d[d["block"] == blk], f"W2b {blk}")


def garch_params(paths: study.Paths, permno: int, quarter: pd.Timestamp, excl: set) -> np.ndarray:
    g = paths.by[permno]
    g = g[g.index < quarter]
    r = np.log1p(g["ret"].to_numpy(float))
    if r.size < HEDGED.har_min_rows or not np.isfinite(r).all():
        return np.full(4, np.nan)
    dummy = np.isin(g.index.normalize(), list(excl)).astype(float)
    return hh.garch_fit(r, dummy)


def run_w2c(s2: pd.DataFrame, paths: study.Paths, excl_by_ticker: dict, summary: dict) -> None:
    print(f"\n== W2c: GARCH(1,1) with announcement dummy on the {W2C_ARM} arm ==")
    for blk in study.BLOCKS:
        if blk == "validation" and not summary["W2c_discovery"]["pass"]:
            print("  W2c fails discovery: validation not run (kill criterion)")
            return
        # burn-in for the causal terciles uses every earlier event, so signals are needed from
        # the start of the sample, not only inside the block
        d = s2[s2["block"].isin(["discovery"] if blk == "discovery" else list(study.BLOCKS))]
        d = d.copy()
        cache: dict = {}
        sig, nfail = [], 0
        for _, e in d.iterrows():
            dec = pd.Timestamp(e["exit_date"])
            q = pd.Timestamp(dec.year, 3 * ((dec.month - 1) // 3) + 1, 1)
            excl = {x for x in excl_by_ticker.get(e["ticker"], set())}
            key = (int(e["permno"]), q)
            if key not in cache:
                cache[key] = garch_params(paths, key[0], q, {x for x in excl if x < q})
            p = cache[key]
            g = paths.by[int(e["permno"])]
            g = g[g.index < dec]
            r = np.log1p(g["ret"].to_numpy(float))
            dummy = np.isin(g.index.normalize(), [x for x in excl if x < dec]).astype(float)
            h = int(
                np.busday_count(
                    (dec + pd.Timedelta(days=1)).date(),
                    (pd.Timestamp(e["expiry"]) + pd.Timedelta(days=1)).date(),
                )
            )
            gv = hh.garch_annual_variance(r, dummy, p, h) if np.isfinite(r).all() else np.nan
            nfail += int(not np.isfinite(gv))
            sig.append(e["s2_iv"] ** 2 / gv if gv > 0 else np.nan)
        d["signal"] = sig
        print(f"  GARCH fits {len(cache)}, signal missing on {nfail} of {len(d)}")
        d["bin"] = hh.causal_bins(d["signal"], d["exit_date"], 3, HEDGED.tercile_min_prior)
        summary[f"W2c_{blk}"] = study.score_selector(d[d["block"] == blk], f"W2c {blk}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(study.PREREG, study.RECORD)[:12]}")
    print(f"amendment 01 verified, sha256 {verify_prereg(AMEND, AMEND_RECORD)[:12]}")
    feat = pd.read_parquet(study.OUT / "features.parquet")
    crsp = pd.read_parquet(study.OUT / "crsp_paths.parquet")
    cols = ["prc", "ret", "cfacpr", "bid", "ask"]
    crsp[cols] = crsp[cols].astype(float)  # the mirror stores CRSP numerics as Decimal
    paths = study.Paths(crsp)
    feat["block"] = study.block_of(feat["entry_date"])
    ev = feat[feat["block"].isin(list(study.BLOCKS))].reset_index(drop=True)
    excl_by_ticker = (
        pd.read_parquet(study.EVENTS, columns=["ticker", "exit_date"])
        .assign(exit_date=lambda x: pd.to_datetime(x["exit_date"]).dt.normalize())
        .groupby("ticker")["exit_date"]
        .apply(set)
        .to_dict()
    )
    s2 = pd.read_parquet(study.OUT / "S2_events.parquet")
    summary: dict = {}
    run_w2b(s2, summary)
    run_w2c(s2, paths, excl_by_ticker, summary)
    run_w2a(ev, paths, args.workers, summary)
    (study.OUT / "summary_wave2.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"\nwrote {study.OUT / 'summary_wave2.json'}")


if __name__ == "__main__":
    main()
