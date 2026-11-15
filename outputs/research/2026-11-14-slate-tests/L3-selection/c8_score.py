"""c8_score.py: trial 2,953, the top causal tercile of the D-1 option-to-stock volume ratio.

Builds os_d1 = ln(100 x option contracts / stock shares) on the last session strictly before
entry, from the Alpaca daily option bars and the CRSP volume slices, on the re-settled megacap
panel, then scores one block with lib.score_mask. The held-out block is read only if
``freeze_c8.md`` exists and records this file's hash.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c8_score.py --block 2013-18
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402
from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import sha256_file  # noqa: E402

TRIAL = 2953
N_BINS, MIN_PRIOR = 3, 100  # see diagnosis.log section 3
ALPACA = lib.ROOT / "data" / "cache" / "alpaca_legacy"
FEATURE_FAMILY = "option_stock_volume_d1"
SHARES_PER_CONTRACT = 100.0
# residual-tenor strata, calendar days from the reaction session to expiry: weekly-listed names
# leave 1 to 4 days, monthly-only names up to a month (diagnosis.log section 3a)
TENOR_EDGES = (-1, 2, 4, 7, 400)


def _stratified_diff(block: np.ndarray) -> float:
    """Selected minus unselected within tenor strata, weighted by selected count."""
    v, s, k = block[:, 0], block[:, 1] == 1.0, block[:, 2]
    num = den = 0.0
    for g in np.unique(k):
        m = k == g
        if s[m].any() and (~s[m]).any():
            w = float(s[m].sum())
            num += w * (v[m & s].mean() - v[m & ~s].mean())
            den += w
    return float(num / den) if den else float("nan")


def option_volume(ticker: str) -> pd.Series:
    """Total contracts traded per session over every listed contract."""
    p = ALPACA / f"options_{ticker}_1d.parquet"
    if not p.exists():
        return pd.Series(dtype=float)
    d = pd.read_parquet(p, columns=["ts", "volume"])
    day = d["ts"].dt.tz_convert(None).dt.normalize()
    return d.groupby(day)["volume"].sum().astype(float)


def build() -> pd.DataFrame:
    d = pd.read_parquet(HERE / "c8_megacap_corrected.parquet")
    d = d[d["h_status"] == "ok"].copy()
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    sv = pd.read_parquet(HERE / "c8_stock_volume.parquet")
    sv["date"] = pd.to_datetime(sv["date"])
    stock = {int(p): g.set_index("date")["vol"].sort_index() for p, g in sv.groupby("permno")}
    weekend = 0
    d1, ov, sh = [], [], []
    cache: dict[str, pd.Series] = {}
    for t, e, p in zip(d["ticker"], d["entry_date"], d["permno"], strict=True):
        s = stock.get(int(p))
        if s is None or not (s.index < e).any():
            d1.append(pd.NaT)
            ov.append(np.nan)
            sh.append(np.nan)
            continue
        day = s.index[s.index < e][-1]
        if t not in cache:
            cache[t] = option_volume(t)
            if len(cache[t]):
                weekend += int((pd.DatetimeIndex(cache[t].index).dayofweek >= 5).sum())
        o = cache[t]
        d1.append(day)
        ov.append(float(o.get(day, np.nan)) if len(o) else np.nan)
        sh.append(float(s.loc[day]))
    if weekend:
        raise ValueError(f"{weekend} option bars dated on a weekend: the date label is not the session")
    d["d1"], d["opt_vol_d1"], d["stk_vol_d1"] = d1, ov, sh
    ok = (d["opt_vol_d1"] > 0) & (d["stk_vol_d1"] > 0)
    d["os_d1"] = np.where(ok, np.log(SHARES_PER_CONTRACT * d["opt_vol_d1"] / d["stk_vol_d1"]),
                          np.nan)
    print(f"megacap ok {len(d)}; D-1 stock volume {d['stk_vol_d1'].notna().sum()}; "
          f"D-1 option bars {d['opt_vol_d1'].notna().sum()}; os_d1 {np.isfinite(d['os_d1']).sum()}")
    d["bin"] = causal_bins(d["os_d1"].to_numpy(float), d["entry_date"], N_BINS, MIN_PRIOR)
    d["block"] = lib.block_of(d["year"])
    return d


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True, choices=["2013-18", "2019-24"])
    a = ap.parse_args(argv)
    if a.block != "2013-18":
        note = HERE / "freeze_c8.md"
        if not (note.exists() and sha256_file(Path(__file__)) in note.read_text(encoding="utf-8")):
            raise SystemExit("held-out read refused: no freeze note recording this scorer's hash")
    d = build()
    blk = d[d["block"] == a.block]
    pop = blk[blk["bin"] >= 0].reset_index(drop=True)
    print(f"block {a.block}: events {len(blk)}; with os_d1 {np.isfinite(blk['os_d1']).sum()}; "
          f"binned {len(pop)}; top tercile {(pop['bin'] == 2).sum()}")
    # attrition: does dropping unbinned events lean on the outcome?
    drop = blk[blk["bin"] < 0]
    sel = (pop["bin"] == N_BINS - 1).to_numpy()
    r = lib.score_mask(pop, sel)
    r.update(trial=TRIAL, block=a.block, passes=lib.passes(r),
             dropped=int(len(drop)),
             dropped_minus_kept_H_corr_pct=float(100 * (drop["H_corr"].mean()
                                                       - pop["H_corr"].mean()))
             if len(drop) else None)
    comp = ["c_premium", "c_settlement", "c_hedge", "c_equity_cost", "c_fees", "c_financing"]
    r["components_sel_minus_unsel"] = {
        c: float(100 * (pop.loc[sel, c].mean() - pop.loc[~sel, c].mean())) for c in comp
    }
    r["os_d1_mean_by_bin"] = {int(k): float(v) for k, v in pop.groupby("bin")["os_d1"].mean().items()}
    # declared secondary (section 3a): the same contrast inside residual-tenor strata
    from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci
    from earnings_iv_crush.research.protocol import N_BOOT, SEED

    days = (pd.to_datetime(pop["expiry"]) - pd.to_datetime(pop["exit_date"])).dt.days
    stratum = pd.cut(days, list(TENOR_EDGES), labels=False).to_numpy(float)
    keys = pd.to_datetime(pop["exit_date"]).dt.normalize().to_numpy()
    for o in ("residual_value", "H_corr"):
        mat = np.column_stack([pop[o].to_numpy(float), sel.astype(float), stratum])
        lo, hi = cluster_bootstrap_ci(mat, keys, _stratified_diff, n_boot=N_BOOT, seed=SEED)
        r[f"{o}_tenor_stratified"] = {"diff": 100 * _stratified_diff(mat), "lo": 100 * lo,
                                      "hi": 100 * hi}
    r["tenor_table"] = (
        pop.assign(days=days, sel=sel)
        .groupby([pd.cut(days, list(TENOR_EDGES)).astype(str), "sel"])["residual_value"]
        .agg(["mean", "count"]).reset_index().to_dict("records")
    )
    for o in ("residual_value", "H_corr"):
        print(lib.fmt(r, o))
        print(f"  tenor-stratified {o}: {r[f'{o}_tenor_stratified']}")
    print("passes:", r["passes"])
    print(json.dumps(r, indent=2, default=float))
    (HERE / f"c8_results_{a.block}.json").write_text(json.dumps(r, indent=2, default=float),
                                                     encoding="utf-8")
    for fam in ("residual_value", "hedged_hold"):
        lib.log_view(a.block, fam, FEATURE_FAMILY, "L3 c8_score.py trial 2,953 (megacap)", "trial")


if __name__ == "__main__":
    main()
