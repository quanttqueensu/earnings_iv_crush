"""
study.py
Ex-diffusive implied jump over a causal jump forecast, scored on residual value (S4), exactly as
frozen in ``prereg.md``. Also reports the next-session front book on the same events, the
control the hedged-hold study refers to.

Usage
-----
    python research/selection/2026-10-20-jump-richness/study.py [--workers 8]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
AMEND = HERE / "prereg_amendment_01.md"
AMEND_RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}_amendment_01.json"
OUT = ROOT / "outputs" / "research" / HERE.name
FEATS = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold"
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
PANEL_EVENTS = ROOT / "outputs" / "research" / "panel_events.parquet"
PANEL_DAILY = ROOT / "outputs" / "research" / "panel_daily.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"

ENTRY_HALF = 0.012714  # measured attainable entry cost, fraction of mid (fills study)
EXIT_HALF = 0.030182  # measured attainable exit cost, fraction of mid
BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024)}
N_TRIALS = 1539
SR_TRIALS_STD = 0.127475


def exit_mark(row: tuple[str, pd.Timestamp, float, pd.Timestamp]) -> tuple[float, int]:
    """Exit mark of the front contract sold at entry, per amendment 01.

    Each leg at its mid when the bid is positive, at half its ask when the bid is zero (the
    out-of-the-money leg after a large move); returns the mark and how many legs took the
    half-ask rule. ``_parse_chain`` cannot be used here because it drops zero-bid rows.
    """
    ticker, exit_d, strike, expiry = row
    f = CHAINS / f"{ticker}_{exit_d.date()}.parquet"
    if not f.exists() or not np.isfinite(strike):
        return float("nan"), 0
    d = pd.read_parquet(f)
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d = d.assign(
        right=body.str[6],
        strike=pd.to_numeric(body.str[7:], errors="coerce") / 1000.0,
        expiry=pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce"),
        bid=pd.to_numeric(d["bid_px_00"], errors="coerce"),
        ask=pd.to_numeric(d["ask_px_00"], errors="coerce"),
    )
    d = d[(d["strike"] == strike) & (d["expiry"] == expiry)].sort_values("ts_recv")
    total, n_half = 0.0, 0
    for right in ("C", "P"):
        leg = d[d["right"] == right]
        if leg.empty:
            return float("nan"), 0
        bid, ask = float(leg["bid"].iloc[-1]), float(leg["ask"].iloc[-1])
        if not ask > 0:
            return float("nan"), 0
        if bid > 0:
            total += (bid + ask) / 2.0
        else:
            total += ask / 2.0
            n_half += 1
    return total, n_half


def prior_moves(ev: pd.DataFrame, crsp: pd.DataFrame) -> list[np.ndarray]:
    """Each event's prior two-day market-adjusted announcement returns, oldest first."""
    pe = pd.read_parquet(PANEL_EVENTS, columns=["permno", "day0"])
    pe["day0"] = pd.to_datetime(pe["day0"])
    mkt = (
        pd.read_parquet(PANEL_DAILY, columns=["date", "mktrf", "rf"])
        .drop_duplicates("date")
        .set_index("date")
    )
    mkt.index = pd.to_datetime(mkt.index)
    m = (mkt["mktrf"] + mkt["rf"]).sort_index()
    by = {int(p): g.set_index("date")["ret"].sort_index() for p, g in crsp.groupby("permno")}
    moves: dict[int, pd.Series] = {}
    for p, g in pe.groupby("permno"):
        if int(p) not in by:
            continue
        r = by[int(p)]
        idx = r.index
        out = {}
        for d0 in g["day0"].sort_values():
            pos = idx.searchsorted(d0)
            if pos + 1 >= len(idx) or idx[pos] != d0:
                continue
            d1 = idx[pos + 1]
            stock = (1 + r.iloc[pos]) * (1 + r.iloc[pos + 1]) - 1
            mk = (1 + m.get(d0, np.nan)) * (1 + m.get(d1, np.nan)) - 1
            out[d0] = stock - mk
        moves[int(p)] = pd.Series(
            list(out.values()), index=pd.DatetimeIndex(list(out.keys())), dtype=float
        ).sort_index()
    res = []
    for p, d in zip(ev["permno"], ev["entry_date"], strict=True):
        s = moves.get(int(p)) if np.isfinite(p) else None
        res.append(s[s.index < d].to_numpy(float) if s is not None else np.array([]))
    return res


def selector(d: pd.DataFrame, label: str) -> dict:
    d = d[d["bin"] >= 0]
    top, bot = d["bin"] == 2, d["bin"] == 0
    p, lo, hi = hh.top_minus_bottom_ci(d["r_adj"], top, bot, d["entry_date"])
    null = matched_random_null(d["net_rom"].to_numpy(float), top.to_numpy(), stat=np.mean)
    terc = d.groupby("bin").agg(
        n=("r_adj", "size"), r_adj=("r_adj", "mean"), net_rom=("net_rom", "mean")
    )
    out = {
        "label": label,
        "n_assigned": int(len(d)),
        "tmb_r_adj": p,
        "tmb_r_adj_ci": [lo, hi],
        "top_mean_net_rom": null.observed,
        "null_percentile": null.percentile,
        "terciles": terc.reset_index().to_dict(orient="records"),
        "pass": bool(lo > 0 and null.percentile >= 95.0),
    }
    print(
        f"  {label}: assigned {len(d)}, top-minus-bottom R_adj {p:+.4f} [{lo:+.4f}, {hi:+.4f}];"
        f" top net RoM {null.observed:+.4f}, null pct {null.percentile:.1f}"
    )
    print(terc.to_string())
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    print(f"amendment 01 verified, sha256 {verify_prereg(AMEND, AMEND_RECORD)[:12]}")
    feat = pd.read_parquet(FEATS / "features.parquet")
    crsp = pd.read_parquet(FEATS / "crsp_paths.parquet")
    # the mirror stores CRSP numerics as Decimal; cast once so arithmetic is float throughout
    crsp[["prc", "ret", "cfacpr", "bid", "ask"]] = crsp[
        ["prc", "ret", "cfacpr", "bid", "ask"]
    ].astype(float)
    y = pd.to_datetime(feat["entry_date"]).dt.year
    feat["block"] = "other"
    for name, (a, b) in BLOCKS.items():
        feat.loc[(y >= a) & (y <= b), "block"] = name
    ev = feat[feat["block"].isin(list(BLOCKS))].reset_index(drop=True)
    back = pd.read_parquet(EVENTS, columns=["ticker", "entry_date", "back_atm_iv"])
    back["entry_date"] = pd.to_datetime(back["entry_date"])
    ev = ev.merge(back.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])
    n0 = len(ev)
    ev = ev[np.isfinite(ev["front_mid"]) & np.isfinite(ev["front_strike"])].reset_index(drop=True)
    print(f"funnel: {n0} events, {len(ev)} with a front quote")

    jobs = list(
        zip(
            ev["ticker"],
            pd.to_datetime(ev["exit_date"]),
            ev["front_strike"],
            pd.to_datetime(ev["front_expiry"]),
            strict=True,
        )
    )
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        marks = list(pool.map(exit_mark, jobs, chunksize=64))
    ev["exit_mark"] = [m for m, _ in marks]
    ev["half_ask_legs"] = [n for _, n in marks]
    print(
        f"  exit mark found: {int(np.isfinite(ev['exit_mark']).sum())} of {len(ev)};"
        f" legs marked at half the ask: {int(ev['half_ask_legs'].sum())}"
        f" on {int((ev['half_ask_legs'] > 0).sum())} events"
    )

    spot = crsp.assign(prc=crsp["prc"].abs()).set_index(["permno", "date"])["prc"]
    keys = list(
        zip(ev["permno"].fillna(-1).astype(int), pd.to_datetime(ev["exit_date"]), strict=True)
    )
    ev["spot_exit"] = spot.reindex(keys).to_numpy()
    t_exit = (pd.to_datetime(ev["front_expiry"]) - pd.to_datetime(ev["exit_date"])).dt.days / 365.0
    bs = [
        hh.straddle_value(s, k, t, iv) if np.isfinite(s) and np.isfinite(iv) else np.nan
        for s, k, t, iv in zip(
            ev["spot_exit"], ev["front_strike"], t_exit, ev["back_atm_iv"], strict=True
        )
    ]
    ev["margin"] = 0.20 * ev["front_fwd"] + ev["front_mid"]
    ev["r_adj"] = -(ev["exit_mark"] - np.asarray(bs)) / ev["margin"]
    gross = ev["front_mid"] - ev["exit_mark"]
    cost = ENTRY_HALF * ev["front_mid"] + EXIT_HALF * ev["exit_mark"]
    ev["net_rom"] = (gross - cost) / ev["margin"]

    moves = prior_moves(ev, crsp)
    jhat = np.array([hh.jump_forecast(m) for m in moves])
    sj = np.sqrt(ev["jsplit_jump_var"].where(ev["jsplit_valid"].astype(bool)))
    ev["signal"] = sj / jhat
    ok = ev[np.isfinite(ev["r_adj"]) & np.isfinite(ev["net_rom"])].copy()
    print(
        f"  outcome finite {len(ok)}; signal finite {int(np.isfinite(ok['signal']).sum())}"
        f" (valid split {int(ok['jsplit_valid'].astype(bool).sum())},"
        f" jump forecast {int(np.isfinite(jhat).sum())})"
    )
    ok["bin"] = hh.causal_bins(ok["signal"], ok["entry_date"], 3, HEDGED.tercile_min_prior)
    OUT.mkdir(parents=True, exist_ok=True)
    ok.to_parquet(OUT / "events.parquet", index=False)

    summary: dict = {"prereg_sha256": verify_prereg(PREREG, RECORD), "results": {}}
    for blk in BLOCKS:
        b = ok[ok["block"] == blk]
        r = b["net_rom"].to_numpy(float)
        ci = date_clustered_ci(r, b["entry_date"], stat=np.mean)
        summary["results"][f"control_{blk}"] = {
            "n": int(len(r)),
            "mean_net_rom_measured": ci.point,
            "ci": [ci.low, ci.high],
            "per_trade_sharpe": per_trade_sharpe(r),
            "dsr": float(deflated_sharpe_ratio(pd.Series(r), N_TRIALS, SR_TRIALS_STD)),
        }
        print(f"  control next-session front book {blk}: mean net RoM (measured cost) {ci}")
        if blk == "validation" and not summary["results"]["S4_discovery"]["pass"]:
            print("  S4 fails discovery: validation not run (kill criterion)")
            continue
        summary["results"][f"S4_{blk}"] = selector(b, f"S4 {blk}")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"wrote {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
