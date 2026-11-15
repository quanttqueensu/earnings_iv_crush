"""
study.py
Hedged event hold: sell the front ATM straddle before the announcement and, instead of buying it
back at the reaction session's 15:59 asks, delta-hedge it with stock from that close and let the
options settle at intrinsic on expiry. Scores the frozen ``prereg.md`` exactly.

Usage
-----
    python research/timing/2026-11-02-hedged-event-hold/study.py            # build and score
    python research/timing/2026-11-02-hedged-event-hold/study.py --rescore  # score the cache

References
----------
Bernard, V. and Thomas, J. (1989) Post-earnings-announcement drift. JAR 27.
de Silva, T., So, E. and Smith, K. (2025) Losing is optional. Review of Finance.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. (2019) Option pricing of earnings
announcement risks. RFS 32(2).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import skew  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio, nyse_sessions  # noqa: E402
from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    hedged_short_straddle,
    straddle_delta,
    straddle_iv,
    year_frac,
)
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"

# ── frozen constants (prereg, Specification) ────────────────────────────────

MARGIN_SPOT_FRAC = 0.20  # the book's Reg-T approximation, common denominator of both arms
FEE = HEDGED.fee_per_contract_leg / 100.0  # USD per share per leg per side
CRSP_END = pd.Timestamp("2024-12-31")  # last CRSP date on disk
BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024)}
DSR_TRIALS, SR_TRIALS_STD = 1550, 0.127475


# ── exit quotes ─────────────────────────────────────────────────────────────


def exit_quotes(ticker: str, day: pd.Timestamp, strike: float, expiry: pd.Timestamp) -> dict:
    """Last 15:59 record per leg for one strike and expiry, read raw (a zero bid is kept)."""
    p = CHAINS / f"{ticker}_{day.date()}.parquet"
    if not p.exists():
        return {"status": "no_exit_chain"}
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d[(d["expiry"] == expiry) & np.isclose(d["strike"], strike)]
    out: dict = {"status": "ok"}
    for r in "CP":
        leg = d[d["right"] == r].sort_values("ts_recv")
        if leg.empty:
            return {"status": "no_exit_leg"}
        out[f"bid_{r}"] = float(leg["bid_px_00"].iloc[-1])
        out[f"ask_{r}"] = float(leg["ask_px_00"].iloc[-1])
    return out


def exit_fwd(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> float:
    """Parity forward on the reaction-session chain for the front expiry (two-sided legs only)."""
    d = pd.read_parquet(CHAINS / f"{ticker}_{day.date()}.parquet").reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d[(d["expiry"] == expiry) & (d["bid_px_00"] > 0) & (d["ask_px_00"] > 0)]
    d = d.sort_values("ts_recv").groupby(["strike", "right"], as_index=False).last()
    d["mid"] = (d["bid_px_00"] + d["ask_px_00"]) / 2
    w = d.pivot(index="strike", columns="right", values="mid").dropna()
    if w.empty or not {"C", "P"} <= set(w.columns):
        return float("nan")
    k = float((w["C"] - w["P"]).abs().idxmin())
    return float(k + w.loc[k, "C"] - w.loc[k, "P"])


# ── stock path ──────────────────────────────────────────────────────────────


def load_crsp() -> dict[int, pd.DataFrame]:
    c = pd.read_parquet(CRSP)
    for col in ("prc", "ret", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()  # CRSP marks a bid-ask midpoint close with a negative sign
    c["date"] = pd.to_datetime(c["date"])
    return {int(k): g.set_index("date").sort_index() for k, g in c.groupby("permno")}


def stock_path(
    crsp: dict[int, pd.DataFrame], permno: float, start: pd.Timestamp, expiry: pd.Timestamp
) -> tuple[str, pd.DataFrame | None]:
    """CRSP rows on every NYSE session from the reaction session to the settlement session."""
    if not np.isfinite(permno) or int(permno) not in crsp:
        return "no_permno", None
    sess = nyse_sessions(start, expiry)
    if len(sess) == 0 or sess[0] != start:
        return "reaction_not_session", None
    g = crsp[int(permno)].reindex(sess)
    if g["prc"].isna().any() or (g["prc"] <= 0).any() or g["ret"].iloc[1:].isna().any():
        return "missing_close", None
    if g["bid"].isna().any() or g["ask"].isna().any():
        return "missing_crsp_quote", None
    if g["cfacpr"].nunique() > 1:
        return "split_in_hold", None
    return "ok", g


# ── one event ───────────────────────────────────────────────────────────────


def build_event(row: pd.Series, crsp: dict[int, pd.DataFrame]) -> dict:
    base = {
        "ticker": row["ticker"],
        "entry_date": row["entry_date"],
        "exit_date": row["exit_date"],
        "expiry": row["front_expiry"],
    }
    if not (row["has_entry_chain"] and np.isfinite(row["front_bid"]) and row["front_bid"] > 0):
        return {**base, "status": "no_front_quote"}
    exp = pd.Timestamp(row["front_expiry"])
    t1 = pd.Timestamp(row["exit_date"])
    if exp > CRSP_END:
        return {**base, "status": "expiry_after_crsp"}
    k, s0, mid0, fwd0 = (
        float(row["front_strike"]),
        float(row["front_bid"]),
        float(row["front_mid"]),
        float(row["front_fwd"]),
    )
    m0 = MARGIN_SPOT_FRAC * fwd0 + s0
    q = exit_quotes(row["ticker"], t1, k, exp)
    if q["status"] != "ok":
        return {**base, "status": q["status"]}
    st, g = stock_path(crsp, row["permno"], t1, exp)
    if st != "ok" or g is None:
        return {**base, "status": st}

    ask_x = q["ask_C"] + q["ask_P"]
    b_ok = q["ask_C"] > 0 and q["ask_P"] > 0
    two_sided = min(q["bid_C"], q["bid_P"]) > 0 and b_ok
    mid_x = (q["bid_C"] + q["ask_C"] + q["bid_P"] + q["ask_P"]) / 2 if two_sided else np.nan

    closes = g["prc"].to_numpy(float)
    hs = ((g["ask"] - g["bid"]) / 2 / g["prc"]).to_numpy(float)
    settle = float(closes[-1])
    n_hedge = len(closes) - 1  # hedging closes: reaction session up to the session before expiry
    hold_days = int((g.index[-1] - t1).days)

    sigma = np.nan
    sig_src = "none"
    if n_hedge > 0:
        if two_sided:
            fx = exit_fwd(row["ticker"], t1, exp)
            sigma = straddle_iv(mid_x, fx, k, year_frac(t1, exp)) if np.isfinite(fx) else np.nan
            sig_src = "exit_chain" if np.isfinite(sigma) else "none"
        if not np.isfinite(sigma) and np.isfinite(row.get("s2_iv", np.nan)):
            sigma, sig_src = float(row["s2_iv"]), "s2_iv"
        if not np.isfinite(sigma):
            return {**base, "status": "no_hedge_vol"}

    intrinsic = abs(settle - k)
    disposal = HEDGED.disposal_bps / 1e4 * settle if intrinsic > 0 else 0.0
    if n_hedge == 0:
        h_net = s0 - intrinsic - 2 * FEE - disposal
        h_mid = mid0 - intrinsic
        hedge_pnl = eq_cost = peak = 0.0
        naked = h_net
        oneshot = h_net
    else:
        cl, rets = closes[:-1], g["ret"].to_numpy(float)[1:]
        taus = np.array([year_frac(d, exp) for d in g.index[:-1]])
        sig = np.full(n_hedge, sigma)
        kw = dict(
            sale_price=s0,
            sale_mid=mid0,
            strike=k,
            fwd=fwd0,
            closes=cl,
            rets=rets,
            taus=taus,
            sigmas=sig,
            half_spreads=hs[:-1],
            settle_close=settle,
        )
        r = hedged_short_straddle(**kw)
        h_net, h_mid = r.net_pnl, r.gross_pnl_mid
        hedge_pnl, eq_cost, peak = r.hedge_pnl, r.equity_cost, r.max_hedge_notional
        naked = hedged_short_straddle(**kw, hedge=False).net_pnl
        # one-shot: the reaction-session hedge held unchanged to settlement
        h0 = straddle_delta(cl[0], k, taus[0], sigma)
        floor = HEDGED.equity_cost_floor_bps / 1e4
        c1 = abs(h0) * (cl[0] * max(hs[0], floor) + settle * max(hs[-2], floor))
        oneshot = s0 - intrinsic + h0 * float(np.sum(cl * rets)) - c1 - 2 * FEE - disposal

    b_net = (s0 - ask_x - 4 * FEE) if b_ok else np.nan
    return {
        **base,
        "status": "ok",
        "b_defined": bool(b_ok),
        "strike": k,
        "m0": m0,
        "s0": s0,
        "mid0": mid0,
        "exit_ask": ask_x,
        "exit_mid": mid_x,
        "settle": settle,
        "intrinsic": intrinsic,
        "hedge_pnl": hedge_pnl,
        "equity_cost": eq_cost,
        "disposal": disposal,
        "peak_hedge_notional": peak,
        "hold_days": hold_days,
        "n_hedge": n_hedge,
        "sigma_src": sig_src,
        "abs_move": abs(closes[0] / fwd0 - 1.0),
        "B": b_net / m0,
        "H": h_net / m0,
        "H_mid": h_mid / m0,
        "naked": naked / m0,
        "oneshot": oneshot / m0,
    }


def build() -> pd.DataFrame:
    f = pd.read_parquet(FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    print(f"  features: {len(f)} events")
    crsp = load_crsp()
    rows = []
    for i, (_, r) in enumerate(f.iterrows()):
        rows.append(build_event(r, crsp))
        if (i + 1) % 1000 == 0:
            print(f"  built {i + 1}/{len(f)}", flush=True)
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "events.parquet")
    return d


# ── scoring ─────────────────────────────────────────────────────────────────


def _ci(x: pd.Series, dates: pd.Series, stat) -> dict:
    iv = date_clustered_ci(x.to_numpy(float), dates, stat)
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n, "clusters": iv.clusters}


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def score(d: pd.DataFrame) -> dict:
    print("funnel (all built events):")
    for k, v in Counter(d["status"]).most_common():
        print(f"  {k:24s} {v}")
    ok = d[d["status"] == "ok"].copy()
    ok["b_defined"] = ok["b_defined"].astype(bool)
    ok["year"] = pd.to_datetime(ok["entry_date"]).dt.year
    print(f"  ok, B undefined (no exit ask on a leg): {int((~ok['b_defined']).sum())}")

    ev = pd.read_parquet(EVENTS)[["ticker", "entry_date", "block", "rom"]]
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    ok = ok.merge(
        ev.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    ok["universe"] = np.where(ok["block"].astype(str).str.startswith("mega"), "megacap", "broad")
    res: dict = {"funnel": dict(Counter(d["status"]))}

    # attrition: dropped-by-B vs kept, on the reaction-session move
    nb = ok[~ok["b_defined"]]
    res["b_undefined_abs_move"] = {
        "dropped_mean": float(nb["abs_move"].mean()) if len(nb) else None,
        "kept_mean": float(ok.loc[ok["b_defined"], "abs_move"].mean()),
        "n_dropped": int(len(nb)),
    }

    for name, (y0, y1) in BLOCKS.items():
        blk = ok[(ok["year"] >= y0) & (ok["year"] <= y1)]
        pb = blk[blk["b_defined"]]
        dates = pb["exit_date"]
        r: dict = {
            "n_ok": int(len(blk)),
            "n_paired": int(len(pb)),
            "P1_mean_H_minus_B": _ci(pb["H"] - pb["B"], dates, _mean),
            "P2_sharpe_H": _ci(blk["H"], blk["exit_date"], per_trade_sharpe),
            "P2_mean_H": _ci(blk["H"], blk["exit_date"], _mean),
            "P2_sharpe_H_paired_set": _ci(pb["H"], dates, per_trade_sharpe),
            "B_sharpe": _ci(pb["B"], dates, per_trade_sharpe),
            "B_mean": float(pb["B"].mean()),
            "H_mid_mean": float(blk["H_mid"].mean()),
            "naked_mean": float(blk["naked"].mean()),
            "oneshot_mean": float(blk["oneshot"].mean()),
            "H_skew": float(skew(blk["H"])),
            "H_worst5": blk.nsmallest(5, "H")[["ticker", "exit_date", "H"]]
            .assign(exit_date=lambda x: x["exit_date"].astype(str))
            .to_dict("records"),
            "share_pnl_worst1pct": float(
                blk.nsmallest(max(1, len(blk) // 100), "H")["H"].sum() / blk["H"].sum()
            ),
            "dsr_H": float(deflated_sharpe_ratio(blk["H"], DSR_TRIALS, SR_TRIALS_STD)),
            "peak_hedge_over_m0_median": float((blk["peak_hedge_notional"] / blk["m0"]).median()),
        }
        # decomposition of H - B per m0 on the paired set
        exit_saved = (pb["exit_ask"] - pb["exit_mid"]) / pb["m0"]
        post_opt = (pb["exit_mid"] - pb["intrinsic"] + pb["hedge_pnl"]) / pb["m0"]
        eq = -(pb["equity_cost"] + pb["disposal"]) / pb["m0"]
        r["decomp_mean"] = {
            "exit_half_spread_saved": float(exit_saved.mean()),
            "post_reaction_option_pnl_mid": float(post_opt.mean()),
            "equity_cost": float(eq.mean()),
            "commission_saved": float((2 * FEE / pb["m0"]).mean()),
            "n_two_sided": int(exit_saved.notna().sum()),
        }
        by_hold = {}
        for lab, lo, hi in (("0", 0, 0), ("1-4", 1, 4), ("5+", 5, 10_000)):
            s = pb[(pb["hold_days"] >= lo) & (pb["hold_days"] <= hi)]
            if len(s) >= 30:
                by_hold[lab] = {
                    "n": int(len(s)),
                    "diff": _ci(s["H"] - s["B"], s["exit_date"], _mean),
                    "H_mean": float(s["H"].mean()),
                    "B_mean": float(s["B"].mean()),
                }
        r["by_hold_days"] = by_hold
        r["by_universe"] = {
            u: {
                "n": int(len(s)),
                "H_mean": float(s["H"].mean()),
                "B_mean": float(s["B"].mean()),
                "diff_mean": float((s["H"] - s["B"]).mean()),
            }
            for u, s in pb.groupby("universe")
        }
        both = pb.dropna(subset=["rom"])
        r["B_vs_ledger_rom"] = {
            "n": int(len(both)),
            "corr": float(both["B"].corr(both["rom"])) if len(both) > 2 else None,
            "B_mean": float(both["B"].mean()),
            "rom_mean": float(both["rom"].mean()),
        }
        res[name] = r

    a, b = res["discovery"], res["validation"]
    p1d = a["P1_mean_H_minus_B"]
    p1v = b["P1_mean_H_minus_B"]
    p2v = b["P2_sharpe_H"]
    pa = p1d["point"] > 0 and p1d["low"] > 0
    pb_ = p1v["point"] > 0 and p1v["low"] > 0
    pc = p2v["point"] > 0 and p2v["low"] > 0 and a["P2_sharpe_H"]["point"] > 0
    if not pa:
        verdict = "CLOSED (kill criterion: P1 fails in discovery)"
    elif pa and pb_ and pc:
        verdict = "PASS"
    elif pa and pb_:
        verdict = "EXIT LEVER ONLY"
    else:
        verdict = "IN-SAMPLE ONLY"
    res["verdict"] = verdict
    return res


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rescore", action="store_true")
    a = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = pd.read_parquet(OUT / "events.parquet") if a.rescore else build()
    res = score(d)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "funnel"}, indent=2, default=str))
    print(f"VERDICT: {res['verdict']}")


if __name__ == "__main__":
    main()
