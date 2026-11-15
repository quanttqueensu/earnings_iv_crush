"""
score_corrections.py
Size of each L1 valuation correction against the stored ``H`` (paired mean, date-clustered 95%
interval, N) and the corrected headline level, by block. Descriptive valuation, not a trial of
any selector. Writes ``corrections_summary.json`` and appends to ``blocks_viewed.csv``.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/score_corrections.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    block_is_clean,
    date_clustered_ci,
    log_block_view,
    per_trade_sharpe,
)

HERE = Path(__file__).resolve().parent
PANEL = HERE / "base_corrected.parquet"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
LEDGER = ROOT / "research" / "ledger" / "blocks.csv"
VIEWS = HERE / "blocks_viewed.csv"
BLOCKS = ("2013-18", "2019-24", "2025-26")


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _ci(x: pd.Series, dates: pd.Series, stat=_mean) -> dict:
    ok = x.notna()
    if ok.sum() < 2:
        return {"point": None, "low": None, "high": None, "n": int(ok.sum())}
    iv = date_clustered_ci(x[ok].to_numpy(float), dates[ok], stat)
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n, "clusters": iv.clusters}


def entry_exercise_check(d: pd.DataFrame) -> dict:
    """Ex-dates on the reaction session make the entry close the last cum day; is exercise
    optimal there? Uses the 15:59 parity forward for spot and the entry straddle's own IV."""
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "front_iv", "front_fwd"])
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    x = d[d["exdiv_on_or_before_reaction"].fillna(False).astype(bool)].merge(
        f.drop(columns="front_fwd"), on=["ticker", "entry_date"], how="left"
    )
    opt = 0
    for _, r in x.iterrows():
        tau = hh.year_frac(r["exit_date"], r["expiry"])
        s = float(r["front_fwd"])
        if s > r["strike"] and np.isfinite(r["front_iv"]):
            put = hh._bs_put(s - r["div_in_hold"], r["strike"], tau, float(r["front_iv"]))
            opt += int(r["div_in_hold"] > put)
    return {"events_exdate_on_or_before_reaction": int(len(x)), "exercise_optimal_at_entry": opt}


def main() -> None:
    d = pd.read_parquet(PANEL)
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c])
    ok = d[d["h_status"] == "ok"].copy()
    res: dict = {
        "funnel": d.groupby(["block", "h_status"])
        .size()
        .rename("n")
        .reset_index()
        .to_dict("records"),
        "entry_exercise": entry_exercise_check(ok),
    }
    clean = {}
    for blk in BLOCKS:
        is_clean, clashes = block_is_clean(
            LEDGER,
            panel="hedged_event_hold",
            period=blk,
            outcome_family="hedged_hold",
            feature_family="valuation_correction",
        )
        clean[blk] = {"clean": is_clean, "clashing_rows": int(len(clashes))}
        log_block_view(
            VIEWS,
            panel="base_corrected",
            period=blk,
            outcome_family="hedged_hold",
            feature_family="valuation_correction",
            viewed_by="L1-corrections score_corrections.py",
            kind="descriptive",
        )
    res["block_is_clean_hedged_event_hold"] = clean
    for blk in BLOCKS:
        b = ok[ok["block"] == blk]
        dts = b["exit_date"]
        r: dict = {"n": int(len(b))}
        for name in ("H_net", "H_exdiv", "H_fin", "H_corr"):
            r[f"{name}_minus_H"] = _ci(b[name] - b["H_rebuilt"], dts)
        r["H_exdiv_minus_H_net"] = _ci(b["H_exdiv"] - b["H_net"], dts)
        r["H_fin_minus_H_net"] = _ci(b["H_fin"] - b["H_net"], dts)
        r["H_corr_minus_H_net"] = _ci(b["H_corr"] - b["H_net"], dts)
        r["exdiv_part_with_rates"] = _ci(b["H_corr"] - b["H_fin"], dts)
        r["put_exercise_part_sensitivity"] = _ci(b["H_corr_put"] - b["H_corr"], dts)
        for name in ("H_rebuilt", "H_net", "H_exdiv", "H_fin", "H_corr", "H_corr_put", "H_skip"):
            r[f"{name}_mean"] = _ci(b[name], dts)
            r[f"{name}_sharpe"] = _ci(b[name], dts, per_trade_sharpe)
        r["residual_value_mean"] = _ci(b["residual_value"], dts)
        r["skipped_by_exdate_rule"] = int(b["H_skip"].isna().sum())
        r["exdiv_in_hold"] = int(b["exdiv_in_hold"].fillna(False).astype(bool).sum())
        r["exdiv_unknown"] = int(b["exdiv_in_hold"].isna().sum())
        r["call_assigned_exdiv"] = int(b["call_assigned_exdiv"].fillna(False).astype(bool).sum())
        r["call_assigned_corr"] = int(b["call_assigned"].fillna(False).astype(bool).sum())
        r["put_assigned_put_variant"] = int(
            b["put_assigned_put_variant"].fillna(False).astype(bool).sum()
        )
        r["special_div"] = int(b["special_div"].fillna(False).astype(bool).sum())
        r["lnFK_mean_bp"] = float(1e4 * b["lnFK"].mean())
        comp = [c for c in b.columns if c.startswith("c_")]
        r["components_mean_H_corr"] = {c: float(b[c].mean()) for c in comp}
        # the skip rule's cost of attrition: are skipped events different on the old outcome?
        sk = b["H_skip"].isna()
        if sk.any() and (~sk).any():
            r["skip_attrition_H_net"] = {
                "skipped_mean": float(b.loc[sk, "H_net"].mean()),
                "kept_mean": float(b.loc[~sk, "H_net"].mean()),
                "skipped_residual_value_mean": float(b.loc[sk, "residual_value"].mean()),
                "kept_residual_value_mean": float(b.loc[~sk, "residual_value"].mean()),
                "n_skipped": int(sk.sum()),
                "diff_H_net_skipped_minus_kept": list(
                    hh.top_minus_bottom_ci(
                        b["H_net"].to_numpy(float), sk.to_numpy(), (~sk).to_numpy(), dts
                    )
                ),
            }
        res[blk] = r
    (HERE / "corrections_summary.json").write_text(
        json.dumps(res, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
