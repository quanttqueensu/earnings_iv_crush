"""
forensics.py
Step 2 of lane2-forensics: rank discovery events by P&L, write case files for 20 worst, 10 best
and 10 median events, and tabulate every pre-entry feature for the worst 5%, the middle and the
best 5%. Descriptive, discovery block only.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane2-forensics/forensics.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lib import load

HERE = Path(__file__).resolve().parent
OUTCOME_COLS = {
    "B", "H", "H_mid", "naked", "oneshot", "exit_ask", "exit_mid", "settle", "intrinsic",
    "hedge_pnl", "equity_cost", "disposal", "peak_hedge_notional", "abs_move", "ratio",
    "pnl_margin", "pnl_prem", "signed_react", "ret_entry_day", "n_hedge", "hold_days",
    "sigma_src", "status",
}  # fmt: skip
CASE_ID = ["group", "rank", "ticker", "announce_date", "entry_date", "session", "tenor", "dte"]
CASE_OUT = [
    "pnl_margin", "pnl_prem", "implied_move", "abs_move", "ratio", "signed_react", "mid0",
    "exit_ask",
]  # fmt: skip
CASE_FEATS = [
    "spread_pct", "front_iv", "term_slope", "jump_share", "skew_25d", "gics2", "gics6",
    "market_equity", "me_bucket", "px_prev", "ret_5d", "ret_20d", "ret_60d", "ret_250d",
    "pos_52w", "dist_52w_high", "rv_5d", "rv_60d", "quiet_ratio", "im_over_rv", "hist_n",
    "hist_abs_mean", "hist_abs_max", "im_over_hist", "im_over_histmax", "im_rel_own", "im_prev",
    "ratio_prev_mean", "prev_tail", "gap_prev_d", "yoy_shift_d", "dow_entry", "dow_same_share",
    "session_switch", "season_pos", "fiscal_q4", "listed_days", "age", "peer_n_5s",
    "peer_z_mean_5s", "peer_z_max_5s", "peer_ratio_mean_5s", "peer_ratio_max_5s", "peer_n_30d",
    "peer_ratio_mean_30d", "e_def", "e_exec_change", "e_restatement", "e_material_agreement",
    "e_acquisition_done", "e_restructuring", "e_impairment", "e_prelim_results", "e_reg_fd",
    "e_merger_form_180d", "e_late_form_365d", "e_amend_form_365d", "e_n8k_100d", "vix",
    "vix_chg_20d", "o_score", "z_score", "earnings_variability", "niq_su", "saleq_gr1",
    "turnover_126d", "stock_spread_bps",
]  # fmt: skip


def main() -> None:
    d = load("discovery")
    d = d.sort_values("pnl_margin").reset_index(drop=True)
    n = len(d)
    k = int(round(0.05 * n))
    d["pnl_rank_pct"] = (np.arange(n) + 0.5) / n
    worst, best = d.iloc[:k], d.iloc[-k:]
    mid = d.iloc[int(0.4 * n) : int(0.6 * n)]
    print(f"funnel discovery {n}; worst 5% {len(worst)}; best 5% {len(best)}; middle fifth {len(mid)}")
    print(
        f"share of total loss carried by worst 5%: sum pnl_margin worst {worst['pnl_margin'].sum():+.2f}, "
        f"all {d['pnl_margin'].sum():+.2f}, all excluding worst {d['pnl_margin'].iloc[k:].sum():+.2f} "
        f"(fractions of margin summed over events)"
    )
    for nm, g in (("worst", worst), ("middle", mid), ("best", best), ("all", d)):
        print(
            f"  {nm:6s} N {len(g):5d} pnl_margin {g['pnl_margin'].mean():+.4f} pnl_prem "
            f"{g['pnl_prem'].mean():+.3f} implied {g['implied_move'].mean():.4f} realised "
            f"{g['abs_move'].mean():.4f} ratio {g['ratio'].mean():.2f} up-move share "
            f"{(g['signed_react'] > 0).mean():.2f}"
        )

    # case files: 20 worst, 10 best, 10 around the median
    half = n // 2
    cases = pd.concat(
        [
            d.iloc[:20].assign(group="worst", rank=np.arange(1, 21)),
            d.iloc[-10:][::-1].assign(group="best", rank=np.arange(1, 11)),
            d.iloc[half - 5 : half + 5].assign(group="median", rank=np.arange(1, 11)),
        ]
    )
    cases[CASE_ID + CASE_OUT + CASE_FEATS].to_csv(HERE / "case_files.csv", index=False, float_format="%.5g")
    print(f"written case_files.csv with {len(cases)} events")

    # feature contrast table
    num = [
        c for c in d.columns
        if c not in OUTCOME_COLS and pd.api.types.is_numeric_dtype(d[c])
        and c not in ("permno", "year", "cell", "im_bin", "strike", "m0", "s0", "mid0", "F0")
    ]  # fmt: skip
    rows = []
    for c in num:
        sd = d[c].std()
        if not np.isfinite(sd) or sd == 0:
            continue
        rows.append(
            {
                "feature": c,
                "n_def": int(d[c].notna().sum()),
                "worst": worst[c].mean(),
                "middle": mid[c].mean(),
                "best": best[c].mean(),
                "all": d[c].mean(),
                "z_worst_vs_mid": (worst[c].mean() - mid[c].mean()) / sd,
                "z_best_vs_mid": (best[c].mean() - mid[c].mean()) / sd,
                "z_worst_vs_best": (worst[c].mean() - best[c].mean()) / sd,
                "worst_med": worst[c].median(),
                "mid_med": mid[c].median(),
                "best_med": best[c].median(),
            }
        )
    t = pd.DataFrame(rows).sort_values("z_worst_vs_mid", key=np.abs, ascending=False)
    t.to_csv(HERE / "feature_contrast.csv", index=False, float_format="%.5g")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(t.round(3).to_string(index=False))
    for c in ("tenor", "session", "gics2", "me_bucket", "dow_entry", "year"):
        tab = pd.DataFrame(
            {
                "worst": worst[c].value_counts(normalize=True),
                "middle": mid[c].value_counts(normalize=True),
                "best": best[c].value_counts(normalize=True),
                "all": d[c].value_counts(normalize=True),
            }
        ).round(3)
        print(f"\n{c}\n{tab.to_string()}")


if __name__ == "__main__":
    main()
