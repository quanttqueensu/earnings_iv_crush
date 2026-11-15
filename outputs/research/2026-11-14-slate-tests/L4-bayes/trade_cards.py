"""
trade_cards.py
Lane L4: one card per event of the base panel (taken, skipped or not scored) from the frozen
champion's walk-forward run, and ``trade_cards_summary.md`` on the twenty largest surprises.

Reads files only: ``run_H_corr.parquet`` (written once by ``score_heldout.py``), L1's corrected
panel (outcome, components, flags) and the 15:59 features. Nothing is re-fitted.

Card columns
------------
keys and block; the champion's 15:59 features as built (``f_*``); the prior predictive
(``pred_*``: model-scale location and scale, degrees of freedom, P(H > 0), median and mean of
H in % of m0, the decision under each declared rule) and the baseline's P(H > 0); the realised
outcome and L1's components in % of m0 (they sum to ``H_corr``); the surprise (PIT, the
normalised quantile residual, log score and its gain over the baseline); what the trade did to
the posterior once it settled (update date, robust weight ``lambda_hat``, the change in each
coefficient's posterior mean ``d_*``, in the name's and the industry's intercept); L1's flags.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/trade_cards.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402

RUN = HERE / "run_H_corr.parquet"
TOP = 20
PCT = C.ONLINE_BAYES.pct_per_unit


def build() -> pd.DataFrame:
    run = pd.read_parquet(RUN)
    d = l4iter.load_all()
    if not (run[["ticker", "entry_date"]].reset_index(drop=True)
            .equals(d[["ticker", "entry_date"]].reset_index(drop=True))):  # fmt: skip
        raise ValueError("run and panel rows are not aligned")
    cfg = C.ONLINE_BAYES_L4_MODEL
    feats = ob.build_feature_set(d, cfg)
    cards = d[["ticker", "entry_date", "expiry", "announce_date", "block"]].copy()
    for c in ob.FEATURE_SETS[cfg.feature_set]:
        cards[f"f_{c}"] = feats[c].to_numpy()
    cards["f_premium_pct_m0"] = feats["premium_share"].to_numpy() * PCT
    m = {c: run[f"m_{c}"] for c in ("pred_loc", "pred_scale", "pred_df", "p_pos",
                                     "pred_median_y", "pred_mean_y", "decide", "decide_ev",
                                     "scored", "n_settled_at_entry", "pit", "quantile_resid",
                                     "log_score", "lambda_hat", "update_date", "dname", "dgroup",
                                     "name_effect_at_entry", "group_effect_at_entry")}  # fmt: skip
    cards["pred_loc_model_scale"] = m["pred_loc"]
    cards["pred_scale_model_scale"] = m["pred_scale"]
    cards["pred_df"] = m["pred_df"]
    cards["pred_p_pos"] = m["p_pos"]
    cards["pred_median_H_pct"] = m["pred_median_y"]
    cards["pred_mean_H_pct"] = m["pred_mean_y"]
    cards["baseline_p_pos"] = run["b_p_pos"]
    cards["n_settled_at_entry"] = m["n_settled_at_entry"]
    cards["scored"] = m["scored"].astype(bool)
    cards["decision_p"] = np.where(cards["scored"], np.where(m["decide"], "trade", "skip"),
                                   "not scored")  # fmt: skip
    cards["decision_ev"] = np.where(cards["scored"], np.where(m["decide_ev"], "trade", "skip"),
                                    "not scored")  # fmt: skip
    cards["H_corr_pct"] = l4lib.target(d, "H_corr", cfg)
    for c in l4lib.COMPONENTS:
        cards[f"{c}_pct"] = d[c].to_numpy(float) * PCT
    cards["residual_value_pct"] = d["residual_value"].to_numpy(float) * PCT
    cards["pit"] = m["pit"]
    cards["surprise_quantile_resid"] = m["quantile_resid"]
    cards["log_score"] = m["log_score"]
    cards["log_score_gain_vs_baseline"] = m["log_score"] - run["b_log_score"]
    cards["update_date"] = m["update_date"]
    cards["lambda_hat"] = m["lambda_hat"]
    for c in [c for c in run.columns if c.startswith("d_")]:
        cards[c] = run[c]
    cards["d_name_intercept"] = m["dname"]
    cards["d_industry_intercept"] = m["dgroup"]
    cards["name_effect_at_entry"] = m["name_effect_at_entry"]
    cards["industry_effect_at_entry"] = m["group_effect_at_entry"]
    for c in l4lib.FLAGS:
        cards[c] = d[c].to_numpy()
    comp_sum = cards[[f"{c}_pct" for c in l4lib.COMPONENTS]].sum(axis=1, min_count=1)
    gap = (comp_sum - d["H_corr"] * PCT).abs()
    if (gap > 1e-9).any():
        raise ValueError(f"components do not sum to H_corr on {int((gap > 1e-9).sum())} rows")
    print(
        f"[cards] {len(cards)} events; scored {int(cards['scored'].sum())}; decision_p trade "
        f"{int((cards['decision_p'] == 'trade').sum())}, decision_ev trade "
        f"{int((cards['decision_ev'] == 'trade').sum())}; no outcome "
        f"{int(cards['H_corr_pct'].isna().sum())}"
    )
    return cards


def summary(cards: pd.DataFrame) -> str:
    sc = cards[cards["scored"] & cards["pit"].notna()].copy()
    sc["abs_surprise"] = sc["surprise_quantile_resid"].abs()
    top = sc.sort_values(["abs_surprise", "log_score"], ascending=[False, True]).head(TOP)
    comps = [f"{c}_pct" for c in l4lib.COMPONENTS]
    feat = [c for c in cards.columns if c.startswith("f_")]
    lines = [
        "# Trade cards: the twenty largest surprises",
        "",
        "Source: `trade_cards.parquet` (every number below is computed from it by "
        "`trade_cards.py`). Surprise is the normalised quantile residual of the realised H_corr "
        "under the frozen champion's prior predictive (standard normal if the forecast is right; "
        "negative is worse for the seller than forecast). Basis: per trade, % of m0, net at the "
        f"touch. Pool: {len(sc)} scored events, 2013-26; the 2019-24 and 2025-26 parts are "
        "walk-forward and exploratory (both blocks were viewed before this lane).",
        "",
        "## The twenty",
        "",
        "| Rank | Block | Surprise | PIT | H_corr | Premium | Settlement | Hedge | Other | "
        "Pred. median | P(H>0) | Decision |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, (_, r) in enumerate(top.iterrows(), 1):
        other = sum(r[c] for c in comps[3:])
        lines.append(
            f"| {i} | {r['block']} | {r['surprise_quantile_resid']:+.2f} | {r['pit']:.2e} | "
            f"{r['H_corr_pct']:+.1f} | {r['c_premium_pct']:+.1f} | {r['c_settlement_pct']:+.1f} "
            f"| {r['c_hedge_pct']:+.1f} | {other:+.2f} | {r['pred_median_H_pct']:+.1f} | "
            f"{r['pred_p_pos']:.2f} | {r['decision_p']} |"
        )
    neg = int((top["surprise_quantile_resid"] < 0).sum())
    lines += [
        "",
        "## What they had in common",
        "",
        f"- Direction: {neg} of {TOP} are losses beyond the forecast (negative surprise), "
        f"{TOP - neg} are gains beyond it.",
        f"- Blocks: {top['block'].value_counts().to_dict()} against the pool's "
        f"{sc['block'].value_counts(normalize=True).round(3).to_dict()} (shares).",
        f"- Distinct announcement dates {top['announce_date'].nunique()}, distinct names "
        f"{top['ticker'].nunique()}.",
        f"- Mean components, top {TOP} against the pool (% of m0): "
        + "; ".join(f"{c[2:-4]} {top[c].mean():+.2f} vs {sc[c].mean():+.2f}" for c in comps)
        + ".",
        f"- Settlement share of the miss: the settlement component explains "
        f"{_share(top, sc):.0%} of the top {TOP}'s excess loss over the pool mean.",
        f"- Flags: ex-dividend in hold {_rate(top, 'exdiv_in_hold')} vs {_rate(sc, 'exdiv_in_hold')}"
        f"; call assigned {_rate(top, 'call_assigned')} vs {_rate(sc, 'call_assigned')}.",
        "- Features at entry (mean causal z of the top twenty is not stored; raw means, top vs "
        "pool): "
        + "; ".join(f"{c[2:]} {top[c].mean():+.3f} vs {sc[c].mean():+.3f}" for c in feat[:8])
        + ".",
        f"- Robust weight when absorbed (lambda_hat, 1 is full weight): median "
        f"{top['lambda_hat'].median():.3f} against the pool's {sc['lambda_hat'].median():.3f}.",
        f"- Largest single-trade shift of any coefficient's posterior mean among the twenty: "
        f"{_max_shift(top):.4f} (model scale), against the pool's 99th percentile "
        f"{_q_shift(sc, 0.99):.4f}.",
        "",
    ]
    return "\n".join(lines)


def _share(top: pd.DataFrame, pool: pd.DataFrame) -> float:
    ex_h = top["H_corr_pct"].mean() - pool["H_corr_pct"].mean()
    ex_s = top["c_settlement_pct"].mean() - pool["c_settlement_pct"].mean()
    return float(ex_s / ex_h) if ex_h else float("nan")


def _rate(df: pd.DataFrame, col: str) -> str:
    x = pd.to_numeric(df[col], errors="coerce")
    return f"{x.mean():.2f} (N {int(x.notna().sum())})"


def _max_shift(df: pd.DataFrame) -> float:
    cols = [c for c in df.columns if c.startswith("d_") and c not in ("d_name_intercept",
                                                                    "d_industry_intercept")]  # fmt: skip
    return float(np.nanmax(np.abs(df[cols].to_numpy(float))))


def _q_shift(df: pd.DataFrame, q: float) -> float:
    cols = [c for c in df.columns if c.startswith("d_") and c not in ("d_name_intercept",
                                                                    "d_industry_intercept")]  # fmt: skip
    return float(np.nanquantile(np.nanmax(np.abs(df[cols].to_numpy(float)), axis=1), q))


def main() -> None:
    cards = build()
    tmp = HERE / "trade_cards.parquet.tmp"
    cards.to_parquet(tmp, index=False)
    tmp.replace(HERE / "trade_cards.parquet")
    cards.to_csv(HERE / "trade_cards.csv", index=False)
    (HERE / "trade_cards_summary.md").write_text(summary(cards), encoding="utf-8")
    print(json.dumps({"written": ["trade_cards.parquet", "trade_cards.csv",
                                  "trade_cards_summary.md"]}))  # fmt: skip


if __name__ == "__main__":
    main()
