"""
b1_auction.py
L2 idea B1: hedge the short straddle with market-on-close orders in the closing auction instead
of paying the closing half-spread at each hedging close. Declared in diagnosis.log entry [2].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b1_auction.py --block 2013-18
    python outputs/research/2026-11-14-slate-tests/L2-execution/b1_auction.py --block 2019-24

No auction data exist on disk, so the auction impact is a declared grid
(``ExecutionLeversConfig.auction_cost_grid_bps``) and every result is assumption-based. The
residual traded at the expiry close keeps the closing half-spread: assignment is not known before
the auction cutoff. Output: ``b1_<block>.json``; one block view is logged per run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import l2lib as L  # noqa: E402
from earnings_iv_crush.config import EXECUTION_LEVERS as XL  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402


def moc_charges(traded: np.ndarray, contracts: int, per_share: float, min_order: float) -> float:
    """Commission and per-share fees of one MOC order per hedging close, per straddle-share.

    ``traded`` is shares per straddle-share at each hedging close. The broker's minimum applies
    to its commission per order; the exchange and clearing fees are per share on top.
    """
    sh = np.rint(100.0 * contracts * np.asarray(traded, float))
    sh = sh[sh >= 1]
    comm = np.maximum(sh * XL.stock_tiered_per_share, min_order)
    fees = sh * per_share
    return float((comm + fees).sum() / (100.0 * contracts))


def continuous_charges(traded: np.ndarray, contracts: int) -> float:
    """The same order count and sizes as marketable limit orders in the continuous market."""
    sh = np.rint(100.0 * contracts * np.asarray(traded, float))
    sh = sh[sh >= 1]
    comm = np.maximum(sh * XL.stock_tiered_per_share, XL.stock_tiered_min_order)
    fees = sh * (XL.stock_take_fee_per_share + XL.stock_clearing_per_share)
    return float((comm + fees).sum() / (100.0 * contracts))


def event_terms(kw: dict, rng: np.random.Generator) -> dict:
    """Costs and notionals of one hedged event, per straddle-share (USD)."""
    closes = np.asarray(kw["closes"], float)
    n = closes.size
    fl = kw["cfg"].equity_cost_floor_bps / 1e4
    hs = np.maximum(np.asarray(kw["half_spreads"], float), fl)
    _, t = L.hedge_sequence(kw)
    c_cur = float((t[:n] * closes * hs).sum())
    q = float((t[:n] * closes).sum())
    out = {"c_cur": c_cur, "q": q, "n_orders_1": int((np.rint(100 * t[:n]) >= 1).sum())}
    moc_fee = XL.moc_exchange_fee_per_share + XL.stock_clearing_per_share
    for nc in XL.commission_contract_sizes:
        out[f"moc_{nc}"] = moc_charges(t[:n], nc, moc_fee, XL.stock_tiered_min_order)
        out[f"cont_{nc}"] = continuous_charges(t[:n], nc)
    # tracking error: the hedge ratio is set from a pre-cutoff price S exp(-e)
    sd = np.asarray(kw["sigmas"], float) * np.sqrt(
        XL.moc_cutoff_minutes / (XL.trading_days_per_year * XL.session_minutes)
    )
    pre = closes * np.exp(-rng.standard_normal(n) * sd)
    hp, tp = L.hedge_sequence(kw, spots=pre)
    rp = hh.hedged_short_straddle(**kw, hedge_ratios=hp)
    c_cur_p = float((tp[:n] * closes * hs).sum())
    c_fin_p = float(tp[n] * float(kw["settle_close"]) * hs[-1])
    if abs(c_cur_p + c_fin_p - rp.equity_cost) > 1e-9 * max(1.0, rp.equity_cost):
        raise AssertionError("tracking-variant cost does not reconcile to the package")
    out.update(
        net_track_oldcost=rp.net_pnl,
        c_cur_p=c_cur_p,
        q_p=float((tp[:n] * closes).sum()),
        moc_p_1=moc_charges(tp[:n], 1, moc_fee, XL.stock_tiered_min_order),
    )
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", required=True, choices=L.BLOCKS)
    a = ap.parse_args(argv)
    d = L.load_base()
    d = d[(d["block"] == a.block) & (d["h_status"] == "ok")].reset_index(drop=True)
    paths = L.load_paths()
    rng = np.random.default_rng(XL.tracking_seed)
    rows = []
    for _, r in d.iterrows():
        p = paths[(r["ticker"], r["entry_date"])]
        base = {"H_corr": r["H_corr"], "m0": r["m0"], "date": r["exit_date"]}
        if p["kw"] is None:
            rows.append({**base, "hedged": False})
            continue
        rows.append({**base, "hedged": True, **event_terms(p["kw"], rng)})
    e = pd.DataFrame(rows).fillna(0.0)
    e["date"] = pd.to_datetime(e["date"])
    print(f"{a.block}: events {len(e)}, hedged {int(e['hedged'].sum())}")
    m0, dates = e["m0"].to_numpy(), e["date"]
    res: dict = {"block": a.block, "n_events": len(e), "n_hedged": int(e["hedged"].sum())}
    res["mean_orders_per_event_N1"] = float(e.loc[e["hedged"], "n_orders_1"].mean())
    res["current_cost_hedging_closes"] = L.iv_dict(L.mean_ci(-e["c_cur"] / m0, dates))
    for nc in XL.commission_contract_sizes:
        res[f"continuous_commission_N{nc}"] = L.iv_dict(L.mean_ci(-e[f"cont_{nc}"] / m0, dates))
    grid = {}
    for bp in XL.auction_cost_grid_bps:
        g = {}
        for nc in XL.commission_contract_sizes:
            dh = (e["c_cur"] - bp / 1e4 * e["q"] - e[f"moc_{nc}"]) / m0
            # like for like: the continuous arm also pays commission and the take fee
            dh_lfl = dh + e[f"cont_{nc}"] / m0
            g[f"N{nc}"] = {
                "paired_vs_H_corr": L.iv_dict(L.mean_ci(dh, dates)),
                "paired_like_for_like": L.iv_dict(L.mean_ci(dh_lfl, dates)),
            }
            print(f"  a={bp} bp N={nc}: dH {L.fmt(L.mean_ci(dh, dates))}")
        grid[str(bp)] = g
    res["grid"] = grid
    h = e[e["hedged"]]
    for nc in XL.commission_contract_sizes:
        be = L.ratio_ci(h["c_cur"] - h[f"moc_{nc}"], h["q"], h["date"])
        res[f"breakeven_bp_N{nc}"] = L.iv_dict(be, scale=1e4)
        be2 = L.ratio_ci(h["c_cur"] + h[f"cont_{nc}"] - h[f"moc_{nc}"], h["q"], h["date"])
        res[f"breakeven_bp_like_for_like_N{nc}"] = L.iv_dict(be2, scale=1e4)
        print(f"  break-even a* N={nc}: {L.fmt(be, 1e4, 2)} bp; like for like {L.fmt(be2, 1e4, 2)}")
    res["mean_current_cost_bp"] = L.iv_dict(L.ratio_ci(h["c_cur"], h["q"], h["date"]), scale=1e4)
    # tracking variant at the middle grid point, N = 1
    bp = XL.auction_cost_grid_bps[1]
    h_track = np.where(
        e["hedged"],
        (e["net_track_oldcost"] + e["c_cur_p"] - bp / 1e4 * e["q_p"] - e["moc_p_1"]) / m0,
        e["H_corr"],
    )
    h_plain = e["H_corr"] + (e["c_cur"] - bp / 1e4 * e["q"] - e["moc_1"]) / m0
    res["tracking"] = {
        "a_bp": bp,
        "paired_track_minus_H_corr": L.iv_dict(L.mean_ci(h_track - e["H_corr"], dates)),
        "paired_track_minus_plain": L.iv_dict(L.mean_ci(h_track - h_plain, dates)),
        "sd_H_corr": float(np.std(e["H_corr"]) * 100),
        "sd_track": float(np.std(h_track) * 100),
        "sd_track_minus_plain": float(np.std(h_track - h_plain) * 100),
        "var_ratio_track_over_plain": L.iv_dict(L.var_ratio_ci(h_track, h_plain, dates), 1.0),
    }
    print(f"  tracking: {res['tracking']['paired_track_minus_plain']}")
    L.write_json(L.HERE / f"b1_{a.block}.json", res)
    L.record_view(a.block, "execution_moc_auction", "L2-execution b1_auction.py")
    print(f"wrote b1_{a.block}.json")


if __name__ == "__main__":
    main()
