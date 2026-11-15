"""
screens.py
Exploratory stock-side screens around after-close earnings events (lane E5, trials 2,802-2,803).

Trial 2,802 is the pre-announcement reversal of So and Wang (2014): causal extreme quintiles of
the market-adjusted return over sessions s-4..s-2 (s = report session), long losers and short
winners from the close of s-2 to the close of s+1, market-hedged. Trial 2,803 is the earnings
announcement premium: long every reporter over the same window, market-hedged. Both are scored
per trade, net of a fixed stock and hedge cost, against pseudo-event windows 20 sessions earlier
on the same names. Declarations are in ``diagnosis.log``; the held-out block runs only after
``freeze_e5_screens.md`` exists and its recorded hashes match.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/screens.py --block discovery
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/screens.py --block heldout

References
----------
So, E. C. and Wang, S. (2014). News-driven return reversals: liquidity provision ahead of
earnings announcements. Journal of Financial Economics 114(1), 20-35.
Savor, P. and Wilson, M. (2016). Earnings announcements and systematic risk. Journal of
Finance 71(1), 83-138.
Barber, B. M., De George, E. T., Lehavy, R. and Trueman, B. (2013). The earnings announcement
premium around the globe. Journal of Financial Economics 108(1), 118-138.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.config import ShadowConfig  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    block_is_clean,
    date_clustered_ci,
    per_trade_sharpe,
)

HERE = Path(__file__).resolve().parent


# ── configuration ──


@dataclass(frozen=True)
class ScreenConfig:
    """Every number the screens use, with its reason."""

    # Project stock half-spread per side (90th pct of 2024 CRSP closing half-spreads, hedged-hold names).
    stock_half_spread_bps: float = ShadowConfig().equity_half_spread_bps
    # Brief rule 5: stock legs pay the half-spread plus 1 bp per side.
    stock_extra_bps: float = 1.0
    # Index hedge, per side (SPY-class quote, conservative).
    hedge_bps: float = 1.0
    # Formation and holding windows in sessions relative to the report session s (So and Wang).
    form_lo: int = -4
    form_hi: int = -2
    hold_lo: int = -1
    hold_hi: int = 1
    # Pseudo-event shift in sessions (non-announcement control on the same name).
    pseudo_shift: int = 20
    # Causal breakpoints: quintile cut-offs from the 500 strictly earlier events, at least 200.
    bp_window: int = 500
    bp_min: int = 200
    q_lo: float = 0.20
    q_hi: float = 0.80
    # Split detection: a close ratio within 3% of a split factor and a move above 40%.
    split_tol: float = 0.03
    split_min_move: float = 0.40
    first_date: str = "2019-01-01"
    last_date: str = "2024-12-31"
    disc_end: str = "2021-12-31"

    @property
    def round_trip(self) -> float:
        """Round-trip cost per trade as a fraction of notional."""
        return 2 * (self.stock_half_spread_bps + self.stock_extra_bps + self.hedge_bps) / 1e4


CFG = ScreenConfig()
SPLIT_FACTORS = (2, 3, 4, 5, 10, 15, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1.5, 2 / 3)
EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
SPOTS = ROOT / "data" / "cache" / "postea_spots_crsp"
FREEZE = HERE / "freeze_e5_screens.md"


# ── data ──


def _market() -> pd.Series:
    files = glob.glob(str(ROOT / "data" / "processed" / "wrds" / "raw" / "crsp_a_stock.dsi.*.parquet"))
    if len(files) != 1:
        raise FileNotFoundError(f"expected one cached dsi slice, found {len(files)}")
    m = pd.read_parquet(files[0], columns=["date", "sprtrn"])
    m["date"] = pd.to_datetime(m["date"])
    return m.set_index("date")["sprtrn"].astype(float)


def _is_split(ratio: np.ndarray) -> np.ndarray:
    move = np.abs(ratio - 1) > CFG.split_min_move
    near = np.zeros_like(move)
    for f in SPLIT_FACTORS:
        near |= np.abs(ratio * f - 1) < CFG.split_tol
    return move & near


def build_windows() -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per event and per pseudo-event: formation and holding returns, market-adjusted."""
    ev = pd.read_parquet(EVENTS, columns=["ticker", "entry_date"]).drop_duplicates()
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    funnel = {"events_all": len(ev)}
    ev = ev[(ev.entry_date >= CFG.first_date) & (ev.entry_date <= CFG.last_date)]
    funnel["events_in_crsp_window"] = len(ev)
    mkt = _market()
    rows: list[dict[str, object]] = []
    miss = {"no_spot_file": 0, "date_not_in_spots": 0, "short_history": 0, "split": 0}
    pseudo_drop = 0
    for tk, g in ev.groupby("ticker"):
        f = SPOTS / f"{tk}.parquet"
        if not f.exists():
            miss["no_spot_file"] += len(g)
            continue
        px = pd.read_parquet(f).dropna()
        px["date"] = pd.to_datetime(px["date"])
        px = px.drop_duplicates("date").set_index("date")["close"].astype(float).abs().sort_index()
        dates = px.index
        idx = {d: i for i, d in enumerate(dates)}
        event_pos = sorted(idx[d] for d in g.entry_date if d in idx)
        for d in g.entry_date:
            if d not in idx:
                miss["date_not_in_spots"] += 1
                continue
            s = idx[d]
            for kind, s0 in (("event", s), ("pseudo", s - CFG.pseudo_shift)):
                lo, hi = s0 + CFG.form_lo - 1, s0 + CFG.hold_hi
                if lo < 0 or hi >= len(dates):
                    if kind == "event":
                        miss["short_history"] += 1
                    continue
                if kind == "pseudo" and any(
                    abs(p - s0) <= (CFG.hold_hi - CFG.form_lo + 1) for p in event_pos
                ):
                    pseudo_drop += 1
                    continue
                seg = px.iloc[lo : hi + 1].to_numpy()
                ratio = seg[1:] / seg[:-1]
                if _is_split(ratio).any():
                    if kind == "event":
                        miss["split"] += 1
                    continue
                r = ratio - 1
                md = dates[lo + 1 : hi + 1]
                m = mkt.reindex(md).to_numpy()
                if not np.isfinite(m).all():
                    raise ValueError(f"market return missing on {list(md[~np.isfinite(m)])}")
                nf = CFG.form_hi - CFG.form_lo + 1
                fr = np.prod(1 + r[:nf]) - np.prod(1 + m[:nf])
                hr = np.prod(1 + r[nf:]) - np.prod(1 + m[nf:])
                rows.append(
                    {"ticker": tk, "report": d, "kind": kind, "anchor": dates[s0], "F": fr, "R": hr}
                )
    for k, v in miss.items():
        funnel[f"drop_{k}"] = v
    funnel["pseudo_dropped_overlap"] = pseudo_drop
    out = pd.DataFrame(rows)
    funnel["event_windows"] = int((out.kind == "event").sum())
    funnel["pseudo_windows"] = int((out.kind == "pseudo").sum())
    if funnel["event_windows"] == 0:
        raise RuntimeError("no event windows built")
    return out, funnel


def causal_side(df: pd.DataFrame) -> pd.Series:
    """+1 bottom quintile, -1 top quintile, 0 middle, NaN warm-up; breakpoints from earlier dates."""
    ev = df[df.kind == "event"].sort_values("report")
    side = pd.Series(np.nan, index=df.index)
    f_hist = ev[["report", "F"]].to_numpy()
    reports = ev["report"].to_numpy()
    for i, row in df.iterrows():
        prior = f_hist[reports < np.datetime64(row["report"])][-CFG.bp_window :, 1].astype(float)
        if prior.size < CFG.bp_min:
            continue
        lo, hi = np.quantile(prior, [CFG.q_lo, CFG.q_hi])
        side[i] = 1.0 if row["F"] <= lo else (-1.0 if row["F"] >= hi else 0.0)
    return side


# ── scoring ──


def _ci(x: pd.Series, d: pd.Series, stat=np.mean) -> dict[str, float]:
    iv = date_clustered_ci(x.to_numpy(), d.to_numpy(), stat=stat)
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n, "clusters": iv.clusters}


def score(df: pd.DataFrame, block: str) -> dict[str, object]:
    cut = pd.Timestamp(CFG.disc_end)
    sel = df.report <= cut if block == "discovery" else df.report > cut
    d = df[sel].copy()
    res: dict[str, object] = {"block": block, "round_trip_cost": CFG.round_trip}
    ev, ps = d[d.kind == "event"], d[d.kind == "pseudo"]
    # 2,803: announcement premium.
    net = ev.R - CFG.round_trip
    res["t2803_net_mean"] = _ci(net, ev.report)
    res["t2803_gross_mean"] = _ci(ev.R, ev.report)
    res["t2803_pseudo_gross_mean"] = _ci(ps.R, ps.report)
    res["t2803_sharpe_net"] = per_trade_sharpe(net)
    # 2,802: reversal on causal extreme quintiles.
    e2 = ev[ev.side.isin([1.0, -1.0])]
    p2 = ps[ps.side.isin([1.0, -1.0])]
    sg_e, sg_p = e2.side * e2.R, p2.side * p2.R
    res["t2802_n_warmup_skipped"] = int(ev.side.isna().sum())
    res["t2802_net_mean"] = _ci(sg_e - CFG.round_trip, e2.report)
    res["t2802_gross_mean"] = _ci(sg_e, e2.report)
    res["t2802_pseudo_gross_mean"] = _ci(sg_p, p2.report)
    res["t2802_long_leg_gross"] = _ci(e2.R[e2.side > 0], e2.report[e2.side > 0])
    res["t2802_short_leg_gross"] = _ci(-e2.R[e2.side < 0], e2.report[e2.side < 0])
    res["t2802_sharpe_net"] = per_trade_sharpe(sg_e - CFG.round_trip)
    # Week clustering as a robustness read (adjacent report dates share holding sessions).
    wk = e2.report.dt.to_period("W").dt.start_time
    res["t2802_net_mean_week_cluster"] = _ci(sg_e - CFG.round_trip, wk)
    wk3 = ev.report.dt.to_period("W").dt.start_time
    res["t2803_net_mean_week_cluster"] = _ci(net, wk3)
    for t in ("2802", "2803"):
        nm = res[f"t{t}_net_mean"]
        res[f"t{t}_pass"] = bool(
            nm["low"] > 0 and res[f"t{t}_gross_mean"]["point"] > res[f"t{t}_pseudo_gross_mean"]["point"]
        )
    return res


def _verify_freeze() -> None:
    if not FREEZE.exists():
        raise SystemExit("held-out refused: freeze note missing")
    text = FREEZE.read_text(encoding="utf-8")
    m = re.search(r"screens\.py sha256: ([0-9a-f]{64})", text)
    if not m or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != m.group(1):
        raise SystemExit("held-out refused: scorer hash does not match the freeze note")
    body, _, tail = text.rpartition("note sha256: ")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != tail.strip()[:64]:
        raise SystemExit("held-out refused: freeze note hash does not match")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    if a.block == "heldout":
        _verify_freeze()
        clean, clash = block_is_clean(
            ROOT / "research" / "ledger" / "blocks.csv",
            panel="crsp_event_windows",
            period="2022-24",
            outcome_family="stock_return_direction",
            feature_family="pre_event_return_and_unconditional",
        )
        print(f"block_is_clean: {clean}; clashes: {len(clash)}")
    df, funnel = build_windows()
    print("funnel:", json.dumps(funnel))
    df["side"] = causal_side(df)
    res = score(df, a.block)
    res["funnel"] = funnel
    out = HERE / f"screens_{a.block}.json"
    out.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
