"""
score_discovery.py
Lane E2: outcomes and trials on the discovery block (entries 2023-03-28 to 2024-12-31).

Builds the close-to-close outcome from 15:59 parity forwards, audits it against CRSP, then scores
the declared trials (diagnosis.log entry 1) and any variant passed with --variant.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/score_discovery.py --outcomes
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/score_discovery.py --declared
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy import stats

import lib
from earnings_iv_crush.research.hedged_hold import causal_bins

OUTC = lib.HERE / "outcomes_discovery.parquet"
DATE = "entry_date"


# ── outcomes ────────────────────────────────────────────────────────────────


def _fwds(rec: dict) -> dict:
    exp = lib.outcome_expiry(rec["ticker"], rec["entry_date"], rec["exit_date"], rec["expiry"])
    base = {"ticker": rec["ticker"], "entry_date": rec["entry_date"], "exp_used": exp}
    if exp is None:
        return {**base, "F_e": np.nan, "F_x": np.nan, "st_e": "no_chain", "st_x": "no_chain"}
    fe, ke, se = lib.chain_fwd(rec["ticker"], rec["entry_date"], exp)
    fx, kx, sx = lib.chain_fwd(rec["ticker"], rec["exit_date"], exp)
    return {**base, "F_e": fe, "K_e": ke, "st_e": se, "F_x": fx, "K_x": kx, "st_x": sx}


def build_outcomes() -> None:
    f = pd.read_parquet(lib.HERE / "features_discovery.parquet")
    f = f[f["status"] == "ok"]
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(_fwds, f[["ticker", "entry_date", "exit_date", "expiry"]]
                             .to_dict("records"), chunksize=8))
    o = pd.DataFrame(rows)
    print("funnel: entry forward", o["st_e"].value_counts().to_dict(),
          "| exit forward", o["st_x"].value_counts().to_dict())
    o["R_cc"] = o["F_x"] / o["F_e"] - 1

    # CRSP: audit, half-spreads, opens
    pm = lib.permno_map()
    crsp = lib.load_crsp()
    f2 = f.merge(o, on=["ticker", "entry_date"])
    f2["permno"] = f2["ticker"].map(pm)
    print(f"funnel: permno found for {int(f2['permno'].notna().sum())} of {len(f2)}")
    rec = []
    for _, r in f2.iterrows():
        out = {"ticker": r["ticker"], "entry_date": r["entry_date"]}
        if np.isfinite(r["permno"]):
            p = int(r["permno"])
            try:
                g = crsp.loc[p]
            except KeyError:
                g = None
            if g is not None:
                e, x = r["entry_date"], r["exit_date"]
                if e in g.index and x in g.index:
                    win = g.loc[(g.index > e) & (g.index <= x)]
                    ret = pd.to_numeric(win["ret"], errors="coerce")
                    out["R_crsp"] = float(np.prod(1 + ret.to_numpy()) - 1) if ret.notna().all() \
                        else np.nan
                    pe, px = g.loc[e, "prc"] / g.loc[e, "cfacpr"], g.loc[x, "prc"] / g.loc[x, "cfacpr"]
                    out["R_crsp_px"] = float(px / pe - 1)
                    out["half_e"] = float(g.loc[e, "half"])
                    out["half_x"] = float(g.loc[x, "half"])
                    out["prc_e"] = float(g.loc[e, "prc"])
                    out["cfac_e"] = float(g.loc[e, "cfacpr"])
                    out["cfac_x"] = float(g.loc[x, "cfacpr"])
        rec.append(out)
    c = pd.DataFrame(rec)
    o = o.merge(c, on=["ticker", "entry_date"], how="left")

    # CRSP opens on the reaction session (trial 2,713), one projected R2 read
    from earnings_iv_crush.data import wrds_r2

    perms = sorted({int(p) for p in f2["permno"].dropna()})
    op = wrds_r2.read_table("crsp_a_stock", "dsf", columns=["permno", "date", "openprc"],
                            filters=[("permno", "in", perms), ("date", ">=", dt.date(2023, 3, 1)),
                                     ("date", "<=", dt.date(2024, 12, 31))])
    op["date"] = pd.to_datetime(op["date"])
    op["openprc"] = pd.to_numeric(op["openprc"], errors="coerce").abs()
    key = f2[["ticker", "entry_date", "exit_date", "permno"]].dropna()
    key = key.merge(op.rename(columns={"date": "exit_date"}), on=["permno", "exit_date"], how="left")
    o = o.merge(key[["ticker", "entry_date", "openprc"]], on=["ticker", "entry_date"], how="left")
    print(f"funnel: reaction-session CRSP open for {int(o['openprc'].notna().sum())} events")
    o.to_parquet(OUTC)
    print(f"wrote {OUTC.name}")


def audit() -> None:
    """Rule 4: the parity-forward return against CRSP, correlation and signed gap by subgroup."""
    f = pd.read_parquet(lib.HERE / "features_discovery.parquet")
    o = pd.read_parquet(OUTC).merge(f[["ticker", "entry_date", "exit_date", "expiry", "cache"]],
                                    on=["ticker", "entry_date"])
    a = o.dropna(subset=["R_cc", "R_crsp"]).copy()
    a["gap"] = a["R_cc"] - a["R_crsp"]
    a["exdiv"] = (a["R_crsp"] - a["R_crsp_px"]).abs() > 5e-5
    a["split"] = a["cfac_e"] != a["cfac_x"]
    a["expiry_near"] = (pd.to_datetime(a["expiry"]) - pd.to_datetime(a["exit_date"])).dt.days <= 2
    print(f"AUDIT parity forward vs CRSP close-to-close, N={len(a)}: corr "
          f"{a['R_cc'].corr(a['R_crsp']):.4f}, mean signed gap {a['gap'].mean()*1e4:+.2f} bp, "
          f"median |gap| {a['gap'].abs().median()*1e4:.2f} bp")
    for name in ("exdiv", "split", "expiry_near"):
        for v, g in a.groupby(name):
            ci = lib.mean_ci(g["gap"].to_numpy(), g[DATE])
            print(f"  {name}={v}: N={len(g)} mean gap {ci.point*1e4:+.2f} bp "
                  f"[{ci.low*1e4:+.2f}, {ci.high*1e4:+.2f}], median |gap| "
                  f"{g['gap'].abs().median()*1e4:.2f} bp")
    for v, g in a.groupby("cache"):
        print(f"  cache={v}: N={len(g)} mean gap {g['gap'].mean()*1e4:+.2f} bp, corr "
              f"{g['R_cc'].corr(g['R_crsp']):.4f}")
    big = a[a["gap"].abs() > 0.01]
    print(f"  events with |gap| > 1%: {len(big)}")


# ── scoring ─────────────────────────────────────────────────────────────────


def frame(outcome: str = "R_cc") -> pd.DataFrame:
    f = pd.read_parquet(lib.HERE / "features_discovery.parquet")
    o = pd.read_parquet(OUTC)
    d = f.merge(o, on=["ticker", "entry_date"], how="left")
    d = d.sort_values(DATE, kind="stable").reset_index(drop=True)
    half_e = d["half_e"].where(d["half_e"].notna(), lib.DEFAULT_HALF_BPS / 1e4)
    half_x = d["half_x"].where(d["half_x"].notna(), lib.DEFAULT_HALF_BPS / 1e4)
    d["cost"] = half_e + half_x + 2 * lib.EXTRA_BPS / 1e4
    mc = d["cache"] == "megacap_2023_2024"
    d["R_prim"] = d["R_cc"].where(~mc, d["R_crsp"])  # entry 3 (b)
    if outcome == "R_co":
        d["R_co"] = d["openprc"] / (d["prc_e"] / d["cfac_e"] * d["cfac_x"]) - 1
    return d


def score_direction(d: pd.DataFrame, sig: str, outcome: str, min_n: str = "n_signed",
                    floor: float = lib.MIN_SIGNED, flip: bool = False,
                    mask: np.ndarray | None = None) -> dict:
    """Long top causal quintile of ``sig``, short the bottom; net mean, CI, Sharpe and nulls."""
    v = d[sig].where(d[min_n] >= floor)
    b = causal_bins(v.to_numpy(), d[DATE], lib.N_BINS, lib.MIN_PRIOR)
    d = d.assign(bin=b)
    if mask is not None:  # restrict positions and pool after the causal binning
        d = d[np.asarray(mask, dtype=bool)]
    pool = d[(d["bin"] >= 0) & d[outcome].notna()]
    n_drop = int(((d["bin"] >= 0) & d[outcome].isna()).sum())
    pos = pool[pool["bin"].isin([0, lib.N_BINS - 1])].copy()
    s = np.where(pos["bin"] == lib.N_BINS - 1, 1.0, -1.0) * (-1 if flip else 1)
    pos["net"] = s * pos[outcome] - pos["cost"]
    pos["gross"] = s * pos[outcome]
    m = lib.mean_ci(pos["net"].to_numpy(), pos[DATE])
    sh = lib.sharpe_ci(pos["net"].to_numpy(), pos[DATE])
    sd_boot = (m.high - m.low) / (2 * 1.96)
    p_dir = lib.null_random_direction(None, pos[outcome].to_numpy(), pos["cost"].to_numpy(),
                                      m.point)
    nl, ns = int((s > 0).sum()), int((s < 0).sum())
    p_mat = lib.null_matched(pool[outcome].to_numpy(), pool["cost"].to_numpy(), nl, ns, m.point)
    long_ = pos[s > 0]["gross"].mean()
    short_ = pos[s < 0]["gross"].mean()
    rho = stats.spearmanr(pool[sig], pool[outcome]).statistic
    res = {"n": len(pos), "n_long": nl, "n_short": ns, "pool": len(pool), "dropped_no_outcome":
           n_drop, "effect": m.point, "ci_low": m.low, "ci_high": m.high,
           "t": m.point / sd_boot if sd_boot > 0 else np.nan, "sharpe": sh.point,
           "sharpe_lo": sh.low, "sharpe_hi": sh.high, "gross": pos["gross"].mean(),
           "cost": pos["cost"].mean(), "long_gross": long_, "short_gross": short_,
           "null_dir_pct": p_dir, "null_matched_pct": p_mat, "spearman_pool": rho,
           "clusters": m.clusters}
    return res


def show(tag: str, r: dict) -> None:
    print(f"{tag}: N={r['n']} ({r['n_long']}L/{r['n_short']}S, pool {r['pool']}, "
          f"{r['clusters']} dates) net {r['effect']*100:+.3f}% [{r['ci_low']*100:+.3f}, "
          f"{r['ci_high']*100:+.3f}] t {r['t']:+.2f} | Sharpe {r['sharpe']:+.3f} "
          f"[{r['sharpe_lo']:+.3f}, {r['sharpe_hi']:+.3f}] | gross {r['gross']*100:+.3f}% "
          f"cost {r['cost']*1e4:.1f} bp rt | long gross {r['long_gross']*100:+.3f}% short gross "
          f"{r['short_gross']*100:+.3f}% | null dir {r['null_dir_pct']:.1f} matched "
          f"{r['null_matched_pct']:.1f} | pool Spearman {r['spearman_pool']:+.3f} | "
          f"dropped (no outcome) {r['dropped_no_outcome']}")


def verdict(r: dict) -> str:
    if r["ci_high"] < 0:
        return "FAIL (interval wholly below zero: opposite sign, not rescued)"
    ok = r["ci_low"] > 0 and r["null_dir_pct"] >= 95 and r["null_matched_pct"] >= 95
    return "PASS" if ok else "FAIL"


def log(tid: int, hyp: str, r: dict, label: str, basis: str) -> None:
    lib.log_trial({"trial_id": tid, "hypothesis": hyp, "block": "discovery 2023-03-28..2024-12-31",
                   "n": r["n"], "effect": f"{r['effect']:.6f}", "ci_low": f"{r['ci_low']:.6f}",
                   "ci_high": f"{r['ci_high']:.6f}", "t": f"{r['t']:.2f}",
                   "sharpe": f"{r['sharpe']:.4f}", "null_dir_pct": f"{r['null_dir_pct']:.1f}",
                   "null_matched_pct": f"{r['null_matched_pct']:.1f}", "basis": basis,
                   "verdict": verdict(r), "label": label})


BASIS = ("mean net return per position, fraction of stock notional, per trade, round trip, at the "
         "touch (half-spread + 1 bp per side), date-clustered 95%")


def attrition(d: pd.DataFrame) -> None:
    """Do events without a signal or outcome differ in move size? (outcome-dependence test)"""
    has = d["R_crsp"].notna()
    a = d[has].copy()
    a["absmove"] = a["R_crsp"].abs()
    nosig = a["n_signed"] < lib.MIN_SIGNED
    print(f"attrition: no signal (signed < {lib.MIN_SIGNED}) N={int(nosig.sum())} mean |CRSP move| "
          f"{a.loc[nosig, 'absmove'].mean()*100:.2f}% vs kept {a.loc[~nosig, 'absmove'].mean()*100:.2f}%"
          f" (Mann-Whitney p {stats.mannwhitneyu(a.loc[nosig,'absmove'], a.loc[~nosig,'absmove']).pvalue:.3f})")
    noout = a["R_prim"].isna()
    if noout.any():
        print(f"attrition: no parity outcome N={int(noout.sum())} mean |CRSP move| "
              f"{a.loc[noout, 'absmove'].mean()*100:.2f}% vs kept {a.loc[~noout, 'absmove'].mean()*100:.2f}%"
              f" (Mann-Whitney p {stats.mannwhitneyu(a.loc[noout,'absmove'], a.loc[~noout,'absmove']).pvalue:.3f})")


def right_driver(d: pd.DataFrame) -> None:
    d = d.copy()
    d["intraday"] = d["f_flow_1550"] / d["f_flow_1500"] - 1
    ok = d[(d["n_signed"] >= lib.MIN_SIGNED)]
    r1 = stats.spearmanr(ok["S"], ok["intraday"], nan_policy="omit").statistic
    print(f"right driver: Spearman(S, 15:00-15:50 forward move) {r1:+.3f}, N={len(ok)}")
    if "R_crsp" in ok:
        # prior session move from CRSP (entry close vs the session before) is not on this frame;
        # the intraday move is the declared check
        pass


def selector_2714(d: pd.DataFrame) -> dict:
    """|S| bottom two causal terciles sold; residual value on the one-night buy-back B."""
    spec = importlib.util.spec_from_file_location(
        "laneD", lib.ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneD-jump-model/lib.py")
    lD = importlib.util.module_from_spec(spec)
    sys.modules["laneD"] = lD
    spec.loader.exec_module(lD)
    e = pd.read_parquet(lib.HH_EVENTS, columns=["ticker", "entry_date", "status", "B", "m0", "s0",
                                                "mid0"])
    e["entry_date"] = pd.to_datetime(e["entry_date"])
    x = d.merge(e, on=["ticker", "entry_date"], how="left")
    print(f"selector funnel: events {len(x)}, with B {int(x['B'].notna().sum())}")
    x = x.dropna(subset=["B"]).sort_values(DATE).reset_index(drop=True)
    x["fwd0"] = (x["m0"] - x["s0"]) / 0.20
    x["imove"] = x["mid0"] / x["fwd0"]
    a = np.abs(x["S"].where(x["n_signed"] >= lib.MIN_SIGNED))
    tb = causal_bins(a.to_numpy(), x[DATE], 3, lib.MIN_PRIOR)
    ib = causal_bins(x["imove"].to_numpy(), x[DATE], 3, lib.MIN_PRIOR)
    keep = (tb >= 0) & (ib >= 0)
    y = x.loc[keep, "B"].to_numpy()
    flag = tb[keep] <= 1
    cells = ib[keep] * 10000 + x.loc[keep, DATE].dt.year.to_numpy()
    r = lD.score_flag(y, flag, cells, x.loc[keep, DATE])
    lvl_sel = lib.mean_ci(y[flag], x.loc[keep, DATE][flag])
    lvl_all = lib.mean_ci(y, x.loc[keep, DATE])
    print(f"2,714 selector: N={r['n']} selected {r['n_treated']}; residual value (within cell, "
          f"selected minus unselected B, per trade, units of m0, net at the touch) "
          f"{r['delta']*100:+.3f}% [{r['lo']*100:+.3f}, {r['hi']*100:+.3f}] t {r['t']:+.2f}, "
          f"cell null pct {r['null_pct']:.1f}; selected book {lvl_sel.point*100:+.3f}% "
          f"[{lvl_sel.low*100:+.3f}, {lvl_sel.high*100:+.3f}] vs all {lvl_all.point*100:+.3f}%")
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcomes", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--declared", action="store_true")
    ap.add_argument("--selector", action="store_true")
    a = ap.parse_args()
    if a.outcomes:
        build_outcomes()
    if a.audit:
        audit()
    if a.declared:
        d = frame("R_co")
        attrition(d)
        right_driver(d)
        r = score_direction(d, "S", "R_prim")
        show("2,712 primary S, close-to-close", r)
        print("  verdict:", verdict(r))
        rb = score_direction(d, "S", "R_crsp")
        show("  robustness (not a trial): 2,712 on CRSP close-to-close for every event", rb)
        log(2712, "ATM call-minus-put signed flow 15:00-15:50 predicts close-to-close", r,
            "discovery, declared primary", BASIS)
        r2 = score_direction(d, "S", "R_co")
        show("2,713 S, close-to-open (secondary)", r2)
        print("  verdict:", verdict(r2))
        log(2713, "same signal, close (CRSP 16:00) to reaction-session CRSP open", r2,
            "discovery, declared secondary, cannot rescue 2,712", BASIS + "; CRSP close to open")
    if a.selector:
        d = frame("R_co")
        r3 = selector_2714(d)
        ok = r3["lo"] > 0 and r3["null_pct"] >= 95
        lib.log_trial({"trial_id": 2714, "hypothesis": "|S| bottom two terciles as a short-straddle "
                       "selector, residual value on one-night buy-back B", "block":
                       "discovery 2023-03-28..2024-12-31", "n": r3["n"],
                       "effect": f"{r3['delta']:.6f}", "ci_low": f"{r3['lo']:.6f}",
                       "ci_high": f"{r3['hi']:.6f}", "t": f"{r3['t']:.2f}",
                       "null_matched_pct": f"{r3['null_pct']:.1f}", "basis": "within-cell residual "
                       "value, selected minus unselected B, units of m0, per trade, net at touch",
                       "verdict": "PASS" if ok else "FAIL", "label": "discovery, declared"})


if __name__ == "__main__":
    main()
