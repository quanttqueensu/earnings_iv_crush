"""
build_features.py
Per-event option features and CRSP daily paths for the 2026-10-20 studies. Reads no outcomes.

From each event's entry and reaction-session 15:59 ET chains it records the quotes every sibling
study trades (pre-event 20-45 day straddle, front straddle, post-event 14-45 day straddle), the
two-expiry jump splits, the post-event skew and term slope. It also links tickers to CRSP permnos
and caches the daily stock file for the linked names. Nothing here looks past the reaction
session's 15:59 chain except the CRSP cache, which the scorers read only after
``verify_prereg``.

Usage
-----
    python research/timing/2026-10-20-hedged-hold/build_features.py [--workers 8]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
OUT = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold"
CRSP_START = "2011-01-01"  # two years of history before the first 2013 event, for HAR's 500 rows
CRSP_END = "2024-12-31"  # last date on the mirror's daily stock file


def _load(ticker: str, day: pd.Timestamp) -> pd.DataFrame | None:
    f = CHAINS / f"{ticker}_{day.date()}.parquet"
    if not f.exists():
        return None
    return _parse_chain(pd.read_parquet(f))


def _q(prefix: str, q: hh.AtmQuote | None) -> dict:
    keys = ("expiry", "t", "fwd", "strike", "bid", "mid", "ask", "iv")
    if q is None:
        return {f"{prefix}_{k}": np.nan for k in keys}
    return {f"{prefix}_{k}": getattr(q, k) for k in keys}


def _split(prefix: str, a: hh.AtmQuote | None, b: hh.AtmQuote | None) -> dict:
    out = {f"{prefix}_sd2": np.nan, f"{prefix}_jump_var": np.nan, f"{prefix}_valid": False}
    if a is None or b is None or not (np.isfinite(a.iv) and np.isfinite(b.iv)) or b.t <= a.t:
        return out
    s = hh.split_jump_variance(a.iv, a.t, b.iv, b.t)
    out.update(
        {
            f"{prefix}_sd2": s.diffusive_var,
            f"{prefix}_jump_var": s.jump_var,
            f"{prefix}_valid": s.valid,
        }
    )
    return out


def _next_after(expiries: list[pd.Timestamp], after: pd.Timestamp, gap: int) -> pd.Timestamp | None:
    for e in sorted(expiries):
        if (e - after).days >= gap:
            return e
    return None


def features(row: tuple[str, pd.Timestamp, pd.Timestamp]) -> dict:
    """All option features for one event; missing pieces are NaN with a reason flag."""
    ticker, entry, exit_ = row
    rec: dict = {"ticker": ticker, "entry_date": entry, "exit_date": exit_}
    ch = _load(ticker, entry)
    rec["has_entry_chain"] = ch is not None
    if ch is not None:
        exps = sorted(pd.Timestamp(x) for x in ch["expiry"].unique())
        e1 = next((e for e in exps if e.normalize() >= exit_.normalize()), None)
        front = hh.atm_quote(ch, e1, entry) if e1 is not None else None
        rec.update(_q("front", front))
        # S4 split: the expiry after the front by at least a week
        e2j = _next_after(exps, e1, HEDGED.jump_split_min_gap_days) if e1 is not None else None
        rec.update(_split("jsplit", front, hh.atm_quote(ch, e2j, entry) if e2j else None))
        # S1: the 20-45 day straddle holding the event
        es1 = hh.pick_expiry(exps, entry, HEDGED.pre_event_dte, not_before=exit_)
        s1 = hh.atm_quote(ch, es1, entry) if es1 is not None else None
        rec.update(_q("s1", s1))
        if s1 is not None and front is not None:
            if es1 != e1:
                rec.update(_split("s1split", front, s1))
            else:
                e2 = _next_after(exps, e1, HEDGED.split_min_gap_days)
                rec.update(_split("s1split", front, hh.atm_quote(ch, e2, entry) if e2 else None))
        else:
            rec.update(_split("s1split", None, None))
    cx = _load(ticker, exit_)
    rec["has_exit_chain"] = cx is not None
    if cx is not None:
        exps = sorted(pd.Timestamp(x) for x in cx["expiry"].unique())
        es2 = hh.pick_expiry(exps, exit_, HEDGED.post_event_dte)
        s2 = hh.atm_quote(cx, es2, exit_) if es2 is not None else None
        rec.update(_q("s2", s2))
        rec["post_skew"] = hh.put_skew(cx, s2) if s2 is not None and np.isfinite(s2.iv) else np.nan
        far = _next_after(exps, es2, HEDGED.slope_min_gap_days) if es2 is not None else None
        fq = hh.atm_quote(cx, far, exit_) if far is not None else None
        ok = s2 is not None and fq is not None and np.isfinite(s2.iv) and np.isfinite(fq.iv)
        rec["post_slope"] = float(fq.iv - s2.iv) if ok else np.nan
    return rec


def link_permnos(ev: pd.DataFrame) -> pd.Series:
    """CRSP permno live on each event's entry date, matched on ticker spelling variants."""
    from earnings_iv_crush.data import wrds_r2

    var: dict[str, str] = {}
    for t in ev["ticker"].unique():
        for v in {t, t.replace("-", ""), t.replace("-", "."), t.replace(".", "")}:
            var[v] = t
    nm = wrds_r2.read_table(
        "crsp_a_stock",
        "dsenames",
        columns=["permno", "ticker", "namedt", "nameendt"],
        filters=[("ticker", "in", sorted(var))],
    )
    nm["base"] = nm["ticker"].map(var)
    nm["namedt"] = pd.to_datetime(nm["namedt"])
    nm["nameendt"] = pd.to_datetime(nm["nameendt"])
    out = []
    for t, d in zip(ev["ticker"], pd.to_datetime(ev["entry_date"]), strict=True):
        m = nm[(nm["base"] == t) & (nm["namedt"] <= d) & (d <= nm["nameendt"])]
        out.append(int(m["permno"].iloc[0]) if len(m) else np.nan)
    return pd.Series(out, index=ev.index, dtype="float")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    ev = pd.read_parquet(EVENTS, columns=["ticker", "announce_date", "entry_date", "exit_date"])
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    ev["exit_date"] = pd.to_datetime(ev["exit_date"])
    ev = ev.drop_duplicates(["ticker", "entry_date"]).reset_index(drop=True)
    print(f"events: {len(ev)}")
    done = OUT / "features.parquet"
    if done.exists():
        # resumable: the feature step is deterministic, so a finished file is reused
        feat = pd.read_parquet(done)
        if len(feat) != len(ev):
            raise ValueError(f"{done} has {len(feat)} rows, expected {len(ev)}; delete it")
        print(f"reusing {done}")
    else:
        rows = list(zip(ev["ticker"], ev["entry_date"], ev["exit_date"], strict=True))
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            recs = list(pool.map(features, rows, chunksize=64))
        feat = pd.DataFrame(recs)
        feat["announce_date"] = ev["announce_date"].to_numpy()
        feat["permno"] = link_permnos(ev)
    print(
        "funnel: entry chain {}/{}, exit chain {}, front quote {}, s1 quote {}, s1 split valid {}, "
        "s2 quote {}, jump split valid {}, permno {}".format(
            int(feat["has_entry_chain"].sum()),
            len(feat),
            int(feat["has_exit_chain"].sum()),
            int(feat["front_iv"].notna().sum()),
            int(feat["s1_iv"].notna().sum()),
            int(feat["s1split_valid"].fillna(False).astype(bool).sum()),
            int(feat["s2_iv"].notna().sum()),
            int(feat["jsplit_valid"].fillna(False).astype(bool).sum()),
            int(feat["permno"].notna().sum()),
        )
    )
    feat.to_parquet(OUT / "features.parquet", index=False)

    from earnings_iv_crush.data import wrds_r2

    permnos = sorted(int(p) for p in feat["permno"].dropna().unique())
    crsp = wrds_r2.read_table(
        "crsp_a_stock",
        "dsf",
        columns=["permno", "date", "prc", "ret", "cfacpr", "bid", "ask"],
        filters=[
            ("permno", "in", permnos),
            ("date", ">=", pd.Timestamp(CRSP_START).date()),
            ("date", "<=", pd.Timestamp(CRSP_END).date()),
        ],
    )
    crsp["date"] = pd.to_datetime(crsp["date"])
    print(f"crsp rows {len(crsp)} for {crsp['permno'].nunique()} of {len(permnos)} permnos")
    crsp.to_parquet(OUT / "crsp_paths.parquet", index=False)


if __name__ == "__main__":
    main()
