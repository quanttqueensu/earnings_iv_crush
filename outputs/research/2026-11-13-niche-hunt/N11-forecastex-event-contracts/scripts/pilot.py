"""pilot.py: ForecastEx cross-venue gap (H1) and favourite-longshot (H2) pilot scorer.

Implements diagnosis.log entry 1. Builds one observation per ForecastEx contract (entry print in
(R - 24 h, R - 1 h]), attaches the Kalshi twin's mid from the last complete hourly candle at or
before the print (H1), settles from the ForecastEx daily prices file, and scores a block.

Usage
-----
    python scripts/pilot.py --block discovery --trial 2382 [--a 0.02] [--gap 0.04]
    python scripts/pilot.py --block heldout ...   # refused unless a freeze note exists
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fexlib import DATA, load_pairs, parse_ts  # noqa: E402

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
)

LANE = Path(__file__).resolve().parents[1]


# ── configuration (diagnosis.log entry 1) ──────────────────────────────────────


@dataclass(frozen=True)
class PilotConfig:
    a: float = 0.02  # adverse fill allowance vs the print: half the 4.0c core-CPI Roll spread
    fee: float = 0.01  # ForecastEx exchange fee per contract (fee schedule); IB commission zero
    gap: float = 0.04  # H1 threshold on |Kalshi mid - ForecastEx print|
    fav: float = 0.90  # H2 favourite threshold
    window_h: float = 24.0  # entry window opens R - 24 h
    lead_h: float = 1.0  # and closes R - 1 h
    max_stale_h: float = 2.0  # Kalshi candle end at most 2 h before the print
    max_price: float = 0.99  # highest bid ForecastEx accepts
    split: str = "2026-01-01"  # discovery before, held-out from
    entry: str = "first"  # "first": fill at the signal print; "next": fill at the next print
    last_fill_h: float = 5 / 60  # a fill print must precede R by at least 5 minutes


H1_PRODUCTS = ["FFDEC", "FF", "CPIY", "CPIC", "UNR", "PREMP"]
H2_PRODUCTS = H1_PRODUCTS + ["IJC", "PCEY"]
KALSHI_SERIES = {"FFDEC": "KXFEDDECISION", "FF": "KXFED", "CPIY": "KXCPIYOY",
                 "CPIC": "KXCPICOREYOY", "UNR": "KXU3", "PREMP": "KXPAYROLLS"}
FFDEC_MAP = {"E0": "H0", "E-25": "C25", "M-50": "C26", "E25": "H25", "H50": "H26"}


def _funnel(name: str, n: int, log: list[str]) -> None:
    log.append(f"{name}: {n}")
    print(f"  funnel {name}: {n}", flush=True)


# ── observations ───────────────────────────────────────────────────────────────


def settlements() -> pd.DataFrame:
    """YES settlement per contract on its expiration date; must be exactly 0 or 1."""
    pr = pd.read_parquet(DATA / "prices.parquet")
    pr = pr[pr.subtype.eq("YES")].copy()
    pr["exp_date"] = parse_ts(pr.expiration_date).dt.tz_convert("America/Chicago").dt.date
    pr["date"] = pd.to_datetime(pr.date).dt.date
    s = pr[pr.date.eq(pr.exp_date)][["event_contract", "settlement_price"]]
    s = s.assign(settle=s.settlement_price.astype(float)).drop_duplicates("event_contract")
    return s[["event_contract", "settle"]]


def observations(cfg: PilotConfig, log: list[str]) -> pd.DataFrame:
    p = load_pairs()
    p = p[p["prod"].isin(H2_PRODUCTS)]
    _funnel("ForecastEx contracts in H2 products with any print", p.event_contract.nunique(), log)
    w = p[(p.h > cfg.lead_h) & (p.h <= cfg.window_h)].sort_values("t")
    e = w.groupby("event_contract", as_index=False).first()
    _funnel("contracts with an entry print in (R-24h, R-1h]", len(e), log)
    if cfg.entry == "next":
        # signal at the first print; fill at the next print on the contract, before R - 5 min
        later = p.merge(e[["event_contract", "t"]].rename(columns={"t": "t0"}), on="event_contract")
        later = later[(later.t > later.t0) & (later.h > cfg.last_fill_h)].sort_values("t")
        nx = later.groupby("event_contract", as_index=False).first()[["event_contract", "t", "y"]]
        e = e.merge(nx.rename(columns={"t": "t_fill", "y": "y_fill"}), on="event_contract",
                    how="left")
        _funnel("  of which a later print exists before R - 5 min", int(e.y_fill.notna().sum()), log)
        e = e[e.y_fill.notna()]
    else:
        e["t_fill"], e["y_fill"] = e.t, e.y
    s = settlements()
    e = e.merge(s, on="event_contract", how="left")
    _funnel("  of which settlement row found", int(e.settle.notna().sum()), log)
    e = e[e.settle.isin([0.0, 1.0])]
    _funnel("  of which settled exactly 0 or 1", len(e), log)
    e["strike"] = e.event_contract.str.split("_").str[-1]
    e["release_date"] = e.exp.dt.tz_convert("UTC").dt.date
    return e[["event_contract", "prod", "strike", "exp", "release_date", "t", "y", "q", "settle",
              "t_fill", "y_fill"]]


def attach_kalshi(e: pd.DataFrame, cfg: PilotConfig, log: list[str]) -> pd.DataFrame:
    mk = pd.read_parquet(DATA / "kalshi_markets.parquet")
    cd = pd.read_parquet(DATA / "kalshi_candles.parquet")
    mk["close_date"] = pd.to_datetime(mk.close_time, utc=True).dt.date
    mk["suffix"] = mk.ticker.str.split("-").str[-1]
    mk["fs"] = pd.to_numeric(mk.floor_strike, errors="coerce")
    e = e[e["prod"].isin(H1_PRODUCTS)].copy()
    _funnel("H1 contracts with entry print and settlement", len(e), log)
    keys = []
    for r in e.itertuples():
        ser = KALSHI_SERIES[r.prod]
        cand = mk[(mk.series == ser) & (mk.close_date == r.release_date)]
        if r.prod == "FFDEC":
            hit = cand[cand.suffix == FFDEC_MAP.get(r.strike, "none")]
        elif r.prod == "FF":
            hit = cand[np.isclose(cand.fs, float(r.strike) + 0.125)]
        else:
            hit = cand[np.isclose(cand.fs, float(r.strike))]
        keys.append(hit.ticker.iloc[0] if len(hit) == 1 else None)
    e["kticker"] = keys
    e = e[e.kticker.notna()]
    _funnel("  matched to exactly one Kalshi twin", len(e), log)
    res = mk.set_index("ticker").result
    e["kres"] = e.kticker.map(res).map({"yes": 1.0, "no": 0.0})
    cd["end"] = pd.to_datetime(cd.ts.astype(float), unit="s", utc=True)
    cd["bid"] = pd.to_numeric(cd.bid, errors="coerce")
    cd["ask"] = pd.to_numeric(cd.ask, errors="coerce")
    cd = cd.sort_values("end")
    qs = []
    for r in e.itertuples():
        c = cd[(cd.ticker == r.kticker) & (cd.end <= r.t)
               & (cd.end >= r.t - pd.Timedelta(hours=cfg.max_stale_h))]
        if c.empty:
            qs.append(np.nan)
            continue
        b, k = c.bid.iloc[-1], c.ask.iloc[-1]
        qs.append((b + k) / 2 if 0 < b < k < 1 else np.nan)
    e["kq"] = qs
    e["has_q"] = e.kq.notna()
    _funnel("  with a two-sided Kalshi candle within 2h before the print", int(e.has_q.sum()), log)
    return e


# ── scoring ──────────────────────────────────────────────────────────────────


def _bets_from_side(
    df: pd.DataFrame, buy_yes: np.ndarray, cfg: PilotConfig, a: float
) -> pd.DataFrame:
    entry = np.where(buy_yes, df.y_fill + a, 1 - df.y_fill + a).clip(max=cfg.max_price)
    payoff = np.where(buy_yes, df.settle, 1 - df.settle)
    out = df.assign(buy_yes=buy_yes, entry=entry, payoff=payoff)
    out["pnl"] = out.payoff - out.entry - cfg.fee
    out["ros"] = out.pnl / (out.entry + cfg.fee)
    return out


def _ci(v: pd.Series, d: pd.Series) -> dict:
    iv = date_clustered_ci(v.to_numpy(), pd.to_datetime(d), stat=np.mean)
    return {"mean": iv.point, "lo": iv.low, "hi": iv.high, "n": iv.n, "dates": iv.clusters}


def score_h1(m: pd.DataFrame, cfg: PilotConfig, a: float) -> dict:
    m = m[m.has_q]
    g = m.kq - m.y
    sel = g.abs() >= cfg.gap
    bets = _bets_from_side(m[sel], (g[sel] > 0).to_numpy(), cfg, a)
    out: dict = {"n_obs": len(m), "n_bets": int(sel.sum())}
    if len(bets) >= 2:
        out["net_pnl"] = _ci(bets.pnl, bets.release_date)
        out["ros"] = _ci(bets.ros, bets.release_date)
        cap = np.sign(g[sel]) * (m.settle[sel] - m.y_fill[sel])
        out["gross_gap_capture"] = _ci(cap, bets.release_date)
        both = pd.concat([_bets_from_side(m, np.ones(len(m), bool), cfg, a),
                          _bets_from_side(m, np.zeros(len(m), bool), cfg, a)])
        mask = np.concatenate([(sel & (g > 0)).to_numpy(), (sel & (g < 0)).to_numpy()])
        nc = matched_random_null(both.pnl.to_numpy(), mask, stat=np.mean)
        out["random_side_null_pctile"] = float((nc.null < nc.observed).mean() * 100)
        out["by_product"] = bets.groupby("prod").pnl.agg(["count", "mean"]).round(4).to_dict()
    out["brier_fex"] = float(((m.y - m.settle) ** 2).mean())
    out["brier_kalshi"] = float(((m.kq - m.settle) ** 2).mean())
    dd = (m.y - m.settle) ** 2 - (m.kq - m.settle) ** 2
    out["brier_fex_minus_kalshi"] = _ci(dd, m.release_date) if len(m) >= 2 else None
    out["settlement_agreement"] = (
        m.assign(ag=(m.kres == m.settle)).groupby("prod").ag.mean().round(4).to_dict())
    return out


def score_h2(e: pd.DataFrame, cfg: PilotConfig, a: float) -> dict:
    sel = (e.y >= cfg.fav) | (e.y <= 1 - cfg.fav)
    bets = _bets_from_side(e[sel], (e.y[sel] >= cfg.fav).to_numpy(), cfg, a)
    out: dict = {"n_obs": len(e), "n_bets": int(sel.sum())}
    if len(bets) >= 2:
        out["net_pnl"] = _ci(bets.pnl, bets.release_date)
        out["ros"] = _ci(bets.ros, bets.release_date)
        fill = np.where(bets.buy_yes, bets.y_fill, 1 - bets.y_fill)
        out["win_minus_price"] = _ci(bets.payoff - fill, bets.release_date)
        out["by_product"] = bets.groupby("prod").pnl.agg(["count", "mean"]).round(4).to_dict()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--a", type=float, default=PilotConfig.a)
    ap.add_argument("--gap", type=float, default=PilotConfig.gap)
    ap.add_argument("--entry", choices=["first", "next"], default=PilotConfig.entry)
    ap.add_argument("--window-h", type=float, default=PilotConfig.window_h)
    args = ap.parse_args()
    if args.block == "heldout" and not list(LANE.glob("freeze_*.md")):
        raise SystemExit("held-out block refused: no freeze note")
    cfg = PilotConfig(a=args.a, gap=args.gap, entry=args.entry, window_h=args.window_h)
    log: list[str] = []
    e = observations(cfg, log)
    split = pd.Timestamp(cfg.split).date()
    blk = e[(e.release_date < split) if args.block == "discovery" else (e.release_date >= split)]
    _funnel(f"{args.block} block observations", len(blk), log)
    m = attach_kalshi(blk, cfg, log)
    # attrition check: do dropped H1 observations (no two-sided quote) differ in outcome?
    att = {"settle_rate_with_q": float(m[m.has_q].settle.mean()) if m.has_q.any() else None,
           "settle_rate_without_q": float(m[~m.has_q].settle.mean()) if (~m.has_q).any() else None}
    res = {"trial": args.trial, "block": args.block, "config": asdict(cfg), "funnel": log,
           "attrition": att, "H1": {}, "H2": {}}
    for a in sorted({cfg.a, 0.01, 0.03}):
        res["H1"][f"a={a}"] = score_h1(m, cfg, a)
        res["H2"][f"a={a}"] = score_h2(blk, cfg, a)
    out = LANE / "logs" / f"pilot_{args.block}_trial{args.trial}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
