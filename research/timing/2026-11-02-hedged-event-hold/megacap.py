"""
megacap.py
Amendment 02 of the hedged event hold: the megacap universe, front contract and exit quotes from the
megacap book's 15:59 consolidated-BBO strips, stock from CRSP.

Usage
-----
    python research/timing/2026-11-02-hedged-event-hold/megacap.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import atm_quote  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
AMEND = HERE / "amendment_02_megacap.md"
RECORD = ROOT / "outputs" / "research" / "prereg_2026-11-02-hedged-event-hold-amendment-02.json"
OUT = ROOT / "outputs" / "research" / HERE.name
STRIPS = ROOT / "data" / "processed" / "databento_quotes"

_spec = importlib.util.spec_from_file_location("hedged_event_hold_study", HERE / "study.py")
assert _spec is not None and _spec.loader is not None
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)


def _strip(ticker: str, day: pd.Timestamp) -> pd.DataFrame | None:
    p = STRIPS / ticker / f"{day.date()}_chain.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["expiry", "strike", "right", "bid", "ask"])
    d["expiry"] = pd.to_datetime(d["expiry"])
    return d


def _two_sided(d: pd.DataFrame) -> pd.DataFrame:
    x = d[(d["bid"] > 0) & (d["ask"] > 0)].rename(columns={"bid": "bid_px_00", "ask": "ask_px_00"})
    return x.assign(mid=(x["bid_px_00"] + x["ask_px_00"]) / 2)


def exit_quotes(ticker: str, day: pd.Timestamp, strike: float, expiry: pd.Timestamp) -> dict:
    d = _strip(ticker, day)
    if d is None:
        return {"status": "no_exit_chain"}
    d = d[(d["expiry"] == expiry) & np.isclose(d["strike"], strike)]
    out: dict = {"status": "ok"}
    for r in "CP":
        leg = d[d["right"] == r]
        if leg.empty or not np.isfinite(leg["ask"].iloc[-1]):
            return {"status": "no_exit_leg"}
        out[f"bid_{r}"] = float(np.nan_to_num(leg["bid"].iloc[-1]))
        out[f"ask_{r}"] = float(leg["ask"].iloc[-1])
    return out


def exit_fwd(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> float:
    d = _strip(ticker, day)
    if d is None:
        return float("nan")
    x = _two_sided(d[d["expiry"] == expiry])
    w = x.pivot_table(index="strike", columns="right", values="mid", aggfunc="last").dropna()
    if w.empty or not {"C", "P"} <= set(w.columns):
        return float("nan")
    k = float((w["C"] - w["P"]).abs().idxmin())
    return float(k + w.loc[k, "C"] - w.loc[k, "P"])


def front_row(r: pd.Series) -> pd.Series | None:
    d = _strip(r["ticker"], r["entry_date"])
    if d is None:
        return None
    exps = sorted(e for e in d["expiry"].unique() if e >= r["exit_date"])
    if not exps:
        return None
    q = atm_quote(_two_sided(d), pd.Timestamp(exps[0]), r["entry_date"])
    if q is None:
        return None
    out = r.copy()
    out["has_entry_chain"] = True
    out["front_expiry"], out["front_t"], out["front_fwd"] = q.expiry, q.t, q.fwd
    out["front_strike"], out["front_bid"], out["front_mid"] = q.strike, q.bid, q.mid
    out["front_ask"], out["front_iv"] = q.ask, q.iv
    return out


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def main() -> None:
    print(f"amendment verified, sha256 {verify_prereg(AMEND, RECORD)[:12]}")
    st.exit_quotes, st.exit_fwd = exit_quotes, exit_fwd
    ev = pd.read_parquet(st.EVENTS)
    ev = ev[ev["block"] == "megacap"][["ticker", "entry_date", "exit_date"]].copy()
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno", "s2_iv"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    ev = ev.merge(
        f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    print(f"  megacap events {len(ev)}, with permno {int(ev['permno'].notna().sum())}")
    crsp = st.load_crsp()
    rows, funnel0 = [], Counter()
    for _, r in ev.iterrows():
        fr = front_row(r)
        if fr is None:
            funnel0["no_entry_front"] += 1
            rows.append(
                {"ticker": r["ticker"], "entry_date": r["entry_date"], "status": "no_entry_front"}
            )
            continue
        if pd.isna(fr["permno"]):
            rows.append(
                {"ticker": r["ticker"], "entry_date": r["entry_date"], "status": "no_permno"}
            )
            continue
        rows.append(st.build_event(fr, crsp))
    d = pd.DataFrame(rows)
    d.to_parquet(OUT / "events_megacap.parquet")
    print("funnel:")
    for k, v in Counter(d["status"]).most_common():
        print(f"  {k:24s} {v}")
    ok = d[d["status"] == "ok"].copy()
    ok["b_defined"] = ok["b_defined"].astype(bool)
    ok["year"] = pd.to_datetime(ok["entry_date"]).dt.year
    res: dict = {"funnel": dict(Counter(d["status"]))}
    for name, (y0, y1) in st.BLOCKS.items():
        blk = ok[ok["year"].between(y0, y1)]
        pb = blk[blk["b_defined"]]
        r: dict = {"n_ok": int(len(blk)), "n_paired": int(len(pb))}
        for k, x, dts, stat in (
            ("P1_mean_H_minus_B", pb["H"] - pb["B"], pb["exit_date"], _mean),
            ("P2_sharpe_H", blk["H"], blk["exit_date"], per_trade_sharpe),
            ("P2_mean_H", blk["H"], blk["exit_date"], _mean),
            ("B_sharpe", pb["B"], pb["exit_date"], per_trade_sharpe),
        ):
            iv = date_clustered_ci(x.to_numpy(float), dts, stat)
            r[k] = {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n}
        r["H_mid_mean"] = float(blk["H_mid"].mean())
        r["B_mean"] = float(pb["B"].mean())
        res[name] = r
    a, b = res["discovery"], res["validation"]
    lever = all(x["P1_mean_H_minus_B"]["low"] > 0 for x in (a, b))
    book = b["P2_sharpe_H"]["low"] > 0 and a["P2_sharpe_H"]["point"] > 0
    res["verdict"] = (
        ("megacap exit lever holds" if lever else "megacap exit lever fails")
        + "; "
        + ("book passes" if book else "book fails")
    )
    (OUT / "results_megacap.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(f"VERDICT: {res['verdict']}")


if __name__ == "__main__":
    main()
