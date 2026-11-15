"""
run.py
Lane E1 discovery scoring: the declared primary (trial 2,682) with its controls C1-C3, the
mechanism statistic, and the numbered variants scored afterwards on the discovery block only.

Discovery block (diagnosis.log entry 3): megacap_2023_2024 plus broad_2025_2026 entries before
2025-07-01. The held-out block is never touched here; ``heldout.py`` reads it once after the
freeze.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/run.py primary
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/run.py variants
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    Interval,
    date_clustered_ci,
    matched_random_null,
    per_trade_sharpe,
)

SPLIT = pd.Timestamp("2025-07-01")


def discovery_mask(ev: pd.DataFrame) -> np.ndarray:
    return ((ev["block"] == "megacap_2023_2024")
            | ((ev["block"] == "broad_2025_2026") & (ev["entry_date"] < SPLIT))).to_numpy()


def ci(x: np.ndarray, dates: pd.Series) -> Interval:
    return date_clustered_ci(x, dates, stat=np.mean)


def fmt(iv: object, scale: float = 100.0) -> str:
    p, lo, hi = iv.point * scale, iv.low * scale, iv.high * scale  # type: ignore[attr-defined]
    return f"{p:+.3f} [{lo:+.3f}, {hi:+.3f}] (N={iv.n}, {iv.clusters} dates)"  # type: ignore


def first_finite_move(s: lib.Session, spot: np.ndarray) -> np.ndarray:
    f = s.fwd
    out = np.full(f.shape[0], np.nan)
    for i in range(f.shape[0]):
        row = f[i][np.isfinite(f[i])]
        if row.size:
            out[i] = abs(row[0] / spot[i] - 1.0)
    return out


def score(tag: str, trial: int, block: str, x: np.ndarray, dates: pd.Series, rule: str,
          basis: str, label: str, note: str = "") -> str:
    iv = ci(x, dates)
    lib.log_trial({
        "trial": trial, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "block": block, "rule": rule, "statistic": "mean", "basis": basis, "n": iv.n,
        "clusters": iv.clusters, "point": round(iv.point * 100, 4), "low": round(iv.low * 100, 4),
        "high": round(iv.high * 100, 4), "per_trade_sharpe": round(per_trade_sharpe(x), 4),
        "label": label, "note": note,
    })
    return f"  {tag}: {fmt(iv)} %; per-trade Sharpe {per_trade_sharpe(x):+.3f}"


# ── primary ─────────────────────────────────────────────────────────────────


def primary() -> None:
    ev, grid = lib.load()
    disc = discovery_mask(ev)
    d1 = lib.session(ev, grid, "D1")
    print(f"events extracted: {len(ev)}; discovery block: {int(disc.sum())}")
    ok = lib.entry_ok(d1) & np.isfinite(ev["s0"].to_numpy()) & disc
    move = first_finite_move(d1, ev["spot_entry"].to_numpy(float))
    kept, dropped = disc & ok, disc & ~ok
    print(f"  funnel: discovery {int(disc.sum())} -> two-sided at 15:01 and IV ok {int(kept.sum())}"
          f" (dropped {int(dropped.sum())}; of those with no D1 quote at all "
          f"{int((dropped & ~np.isfinite(move)).sum())})")
    print(f"  attrition check, |reaction move|: kept {np.nanmean(move[kept]):.4f} "
          f"(N={int(np.isfinite(move[kept]).sum())}), dropped {np.nanmean(move[dropped]):.4f} "
          f"(N={int(np.isfinite(move[dropped]).sum())})")
    e = ev[kept].reset_index(drop=True)
    s = lib.session(e, grid[kept], "D1")
    dates = e["exit_date"]
    out = lib.scalp(s, clock_sec=300)
    stat = lib.scalp(s, clock_sec=None)
    debit, m0 = out["debit"].to_numpy(), e["m0"].to_numpy()
    print(f"  entry debit median {np.median(debit):.3f}/share; ask-minus-mid at entry median "
          f"{np.median((out['ask0'] - out['mid0']) / debit) * 100:.2f}% of debit; exit legs with "
          f"no bid {int(out['no_exit_bid'].sum())}; stale final F {int(out['stale_end'].sum())}; "
          f"rebalances skipped (no F or IV) {int(out['n_skip'].sum())} of "
          f"{len(out) * 12}")
    lines = ["Trial 2,682 (primary): long held straddle D+1 15:01 ask -> 15:59 bid, 5-min hedge"]
    net = out["net"].to_numpy() / debit
    lines.append(score("net, % of debit", 2682, "discovery", net, dates,
                       "long D1 15:01-15:59, 5-min clock, lag 30s, 4bp stock", "% debit, net touch",
                       "primary"))
    lines.append("  same, % of m0: " + fmt(ci(out["net"].to_numpy() / m0, dates)))
    g = out["gross_mid"].to_numpy() / debit
    gm = np.isfinite(g)
    lines.append("  C1 gross at mid, % of debit: " + fmt(ci(g[gm], dates[gm])))
    rt = out["touch_rt"].to_numpy() / debit
    lines.append("  round-trip option touch, % of debit: " + fmt(ci(rt[gm], dates[gm])))
    hp = (out["hedge_pnl"] - stat["hedge_pnl"] - out["stock_cost"] + stat["stock_cost"])
    lines.append("  C2 5-min minus static hedge, net, % of debit: "
                 + fmt(ci(hp.to_numpy() / debit, dates)))
    lines.append("  stock cost, % of debit: " + fmt(ci(out["stock_cost"].to_numpy() / debit, dates)))
    # decomposition of the gross at the mid: vega part from the change in straddle IV
    k0, k1 = lib.k_of("15:01:00"), lib.k_of("15:59:00")
    iv0 = lib.straddle_iv(s.mid[:, k0], s.fwd[:, k0], s.strike, s.tau(k0))
    iv1 = lib.straddle_iv(s.mid[:, k1], s.fwd[:, k1], s.strike, s.tau(k1))
    f0 = s.fwd[:, k0]
    sd = iv0 * np.sqrt(s.tau(k0))
    d1v = (np.log(f0 / s.strike) + 0.5 * sd * sd) / sd
    vega = 2 * f0 * np.exp(-0.5 * d1v ** 2) / np.sqrt(2 * np.pi) * np.sqrt(s.tau(k0))
    vpart = vega * (iv1 - iv0) / debit
    vm = np.isfinite(vpart) & gm
    lines.append("  IV change 15:01->15:59, vol points: "
                 + fmt(ci((iv1 - iv0)[vm], dates[vm]), 100.0))
    lines.append("  vega part of C1, % of debit: " + fmt(ci(vpart[vm], dates[vm])))
    lines.append("  gamma-minus-theta remainder of C1, % of debit: "
                 + fmt(ci((g - vpart)[vm], dates[vm])))
    delta0 = np.abs(lib.straddle_delta(f0, s.strike, s.tau(k0), iv0))
    lines.append(f"  |straddle delta| at entry: median {np.nanmedian(delta0):.2f}, "
                 f"share above 0.5 {np.nanmean(delta0 > 0.5):.2f}")
    # C3: same rule on D-1
    dm1 = lib.session(e, grid[kept], "Dm1")
    ok3 = lib.entry_ok(dm1)
    if ok3.sum() > 10:
        e3 = e[ok3].reset_index(drop=True)
        s3 = lib.session(e3, grid[kept][ok3], "Dm1")
        o3 = lib.scalp(s3, clock_sec=300)
        lines.append("  C3 same rule on D-1, net % of debit: "
                     + fmt(ci(o3["net"].to_numpy() / o3["debit"].to_numpy(), e3["exit_date"])))
        g3 = o3["gross_mid"].to_numpy() / o3["debit"].to_numpy()
        m3 = np.isfinite(g3)
        lines.append("  C3 gross at mid on D-1, % of debit: "
                     + fmt(ci(g3[m3], e3["exit_date"][m3])))
    kill = ci(g[gm], dates[gm]).high < np.nanmean(rt[gm])
    lines.append(f"  kill rule (C1 upper bound below mean round-trip touch): {kill}")
    txt = "\n".join(lines)
    print(txt)
    pd.concat([e[["block", "ticker", "entry_date", "exit_date", "m0"]], out], axis=1).to_parquet(
        HERE / "cache" / "primary_discovery.parquet")
    (HERE / "primary_discovery.log").write_text(txt + "\n", encoding="utf-8")


# ── mechanism and variants ──────────────────────────────────────────────────


def variants() -> None:
    ev, grid = lib.load()
    disc = discovery_mask(ev)
    d1 = lib.session(ev, grid, "D1")
    kept = disc & lib.entry_ok(d1) & np.isfinite(ev["s0"].to_numpy())
    e = ev[kept].reset_index(drop=True)
    s = lib.session(e, grid[kept], "D1")
    dates = e["exit_date"]
    lines = []
    # 2,683 mechanism: variance signature, D1 and D-1, 15:01-15:59
    k0, k1 = lib.k_of("15:01:00"), lib.k_of("15:59:00")
    for name in ("D1", "Dm1"):
        ss = lib.session(e, grid[kept], name)
        sig = lib.rv_signature(ss, k0, k1, (12, 60, 180))  # 1, 5, 15 minutes
        m = sig.notna().all(axis=1).to_numpy() & (sig["rv_60s"] > 0).to_numpy()
        vr15 = (sig["rv_900s"] / sig["rv_60s"]).to_numpy()
        vr5 = (sig["rv_300s"] / sig["rv_60s"]).to_numpy()
        lines.append(f"2,683 {name}: VR(5m/1m) median {np.median(vr5[m]):.3f}, mean "
                     + fmt(ci(vr5[m], dates[m]), 1.0)
                     + f"; VR(15m/1m) median {np.median(vr15[m]):.3f}, mean "
                     + fmt(ci(vr15[m], dates[m]), 1.0))
        lf = np.log(ss.fwd[:, k0:k1 + 1:12])
        r = np.diff(lf, axis=1)
        ac = np.array([np.corrcoef(x[:-1], x[1:])[0, 1] if np.isfinite(x).all() and x.std() > 0
                       else np.nan for x in r])
        am = np.isfinite(ac)
        lines.append("      lag-1 autocorrelation of 1-minute F returns: "
                     + fmt(ci(ac[am], dates[am]), 1.0))
        lib.log_trial({"trial": 2683, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "block": f"discovery {name}", "rule": "variance ratio 15m/1m of parity F",
                       "statistic": "mean VR", "basis": "ratio", "n": int(m.sum()),
                       "point": round(float(np.mean(vr15[m])), 4),
                       "label": "descriptive", "note": "mechanism; parity noise biases VR down"})
    # hedging-frequency variants, net % of debit, discovery only
    specs = [
        (2684, "1-min clock", dict(clock_sec=60)),
        (2685, "15-min clock", dict(clock_sec=900)),
        (2686, "0.10 delta band, checked each minute", dict(band=0.10)),
        (2687, "5-min clock, no lag (noise-bias check, not tradeable)", dict(clock_sec=300,
                                                                              lag_sec=0)),
        (2688, "5-min clock, 10 bp + 1 bp stock cost", dict(clock_sec=300, stock_bps=11.0)),
    ]
    base = lib.scalp(s, clock_sec=300)
    for tid, name, kw in specs:
        o = lib.scalp(s, **kw)
        x = o["net"].to_numpy() / o["debit"].to_numpy()
        lines.append(score(f"{tid} {name}, net % debit", tid, "discovery", x, dates, name,
                           "% debit, net touch", "exploratory"))
        dif = (o["hedge_pnl"] - o["stock_cost"] - base["hedge_pnl"] + base["stock_cost"])
        lines.append("      minus primary (hedge net of stock cost), % debit: "
                     + fmt(ci(dif.to_numpy() / base["debit"].to_numpy(), dates)))
    # 2,689: paired D+1 minus D-1 gross at the mid, same events (is the post-event hour special?)
    dm1 = lib.session(e, grid[kept], "Dm1")
    o_m1 = lib.scalp(dm1, clock_sec=300)
    pm = (base["gross_mid"] / base["debit"] - o_m1["gross_mid"] / o_m1["debit"]).to_numpy()
    pmm = np.isfinite(pm) & lib.entry_ok(dm1)
    lines.append(score("2689 paired D+1 minus D-1, gross at mid, % debit", 2689, "discovery",
                       pm[pmm], dates[pmm], "D1 minus D-1 gross mid, 5-min clock",
                       "% debit, gross mid", "exploratory"))
    # 2,690: near-the-money subset at entry (causal: delta known at 15:00:30), with matched null
    f0 = s.fwd[:, k0 - 6]
    iv0 = lib.straddle_iv(s.mid[:, k0 - 6], f0, s.strike, s.tau(k0 - 6))
    dl0 = np.abs(lib.straddle_delta(f0, s.strike, s.tau(k0 - 6), iv0))
    near = dl0 < 0.25
    x = (base["net"] / base["debit"]).to_numpy()
    gx = (base["gross_mid"] / base["debit"]).to_numpy()
    lines.append(score(f"2690 |delta| < 0.25 at entry (N={int(near.sum())}), net % debit", 2690,
                       "discovery", x[near], dates[near], "near-ATM subset", "% debit, net touch",
                       "exploratory"))
    gn = near & np.isfinite(gx)
    lines.append("      gross at mid: " + fmt(ci(gx[gn], dates[gn]))
                 + "; round-trip touch "
                 + f"{np.nanmean((base['touch_rt'] / base['debit']).to_numpy()[gn]) * 100:.2f}%"
                 + "; stock cost "
                 + f"{np.mean((base['stock_cost'] / base['debit']).to_numpy()[near]) * 100:.2f}%")
    nul = matched_random_null(x, near, stat=np.mean, n_draws=2000)
    lines.append(f"      matched random null on net: percentile {nul.percentile:.1f}")
    # 2,691 mirror: the short hold's position over 15:01-15:59, hedged on the 5-min clock versus
    # left unhedged until the close (as the hold is); difference is hedge P&L net of stock cost
    sh = lib.scalp(s, clock_sec=300, side=-1)
    # the hold puts on its first hedge at 15:59 anyway, so the 15:59 unwind leg is not an extra
    # cost of hedging earlier: add it back
    unwind = np.abs(sh["h_end"].to_numpy()) * s.fwd[:, k1] * (lib.STOCK_HALF_BPS
                                                             + lib.STOCK_EXTRA_BPS) / 1e4
    diff = (sh["hedge_pnl"] - sh["stock_cost"]).to_numpy() + np.nan_to_num(unwind)
    lines.append(score("2691 mirror: short hold hedged 5-min from 15:01 minus unhedged, % of m0",
                       2691, "discovery", diff / e["m0"].to_numpy(), dates,
                       "short hold, intraday hedge vs none in the last hour", "% m0, net",
                       "exploratory"))
    lines.append("      same in % of the short's credit at 15:01 bid: "
                 + fmt(ci(diff / sh["bid0"].to_numpy(), dates)))
    sh_st = lib.scalp(s, clock_sec=None, side=-1)
    d2 = (sh["hedge_pnl"] - sh["stock_cost"] - sh_st["hedge_pnl"] + sh_st["stock_cost"]).to_numpy()
    lines.append("      5-min clock minus one static hedge at 15:01, % of m0: "
                 + fmt(ci(d2 / e["m0"].to_numpy(), dates)))
    txt = "\n".join(lines)
    print(txt)
    (HERE / "variants_discovery.log").write_text(txt + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["primary", "variants"])
    a = ap.parse_args()
    {"primary": primary, "variants": variants}[a.what]()


if __name__ == "__main__":
    sys.exit(main())
