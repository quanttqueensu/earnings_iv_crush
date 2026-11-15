"""
build_panel.py
Joins the round 1 per-event feature panels (macro, forensics, surface, niche) onto the hedged
event hold spine for the lane E walk-forward model, keeping only features with a stated
pre-entry timestamp. Writes panel.parquet and feature_map.csv in this folder. No outcome is
analysed here.

Spine: lane5-niche/features.parquet (9,350 broad hedged-hold events with status ok, 2013-26;
outcomes H, H_mid, y and the causal implied-move tercile x tenor cell come from the frozen
loader of research/selection/2026-11-10-nonprice-selectors-hedged-hold).

Feature timestamps (every kept column is listed in feature_map.csv with its stamp)
-----------------------------------------------------------------------------------
macro_lag   close of the session before the entry session (lane1 *_lag)
sched       release and reporting calendars fixed before entry; tenor and weekday facts
q1559       entry-session 15:59:00 ET consolidated quotes (lane3 chain, front/s1 expiries)
crsp_prior  CRSP daily closes strictly before the entry session (lane2 price path)
eom_prior   monthly characteristics at the last month end before the entry month
filings     EDGAR filings dated strictly before entry (lane2 e_*)
own_prior   the name's own events whose reaction closed strictly before entry
peer_prior  peers' reactions dated strictly before entry

Dropped on purpose: every outcome and exit-side column; lane3 exit-chain (s2_*, post_*)
columns; lane3 f_* and rich_js/hist/im (themselves fitted on outcomes); lane1 *_same (entry
session close, after 15:59); lane1 seas_share_sofar_expost and seas_same_day_n and lane5
crowd_panel (panel membership, ex post); lane1 columns sourced from the model-zoo events file
(front_atm_iv, back_atm_iv, iv_term_spread, log_mcap, trailing_rv, is_amc, disp_*), because its
2025-26 rows may come from Alpaca end-of-day chains; lane2 ret_entry_day and signed_react.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/build_panel.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
R1 = HERE.parents[1] / "2026-11-13-alpha-hunt"
KEY = ["ticker", "entry_date"]

# ── feature map: (column, source, group, timestamp) ──────────────────────────
# Groups: cost (liquidity, size, spread), surface (option-implied at 15:59), history (own past
# events), price (stock path), fundamentals (characteristics, filings), peers, macro, calendar.

LANE5 = [
    ("half_spread", "cost", "q1559"), ("me", "cost", "eom_prior"), ("prc", "cost", "eom_prior"),
    ("turnover_126d", "cost", "eom_prior"), ("dolvol_126d", "cost", "eom_prior"),
    ("implied_move", "surface", "q1559"), ("front_iv", "surface", "q1559"),
    ("front_t", "surface", "q1559"), ("dte", "calendar", "sched"),
    ("amc", "calendar", "sched"), ("sess_to_expiry", "calendar", "sched"),
    ("gap_days", "calendar", "sched"), ("exit_wd", "calendar", "sched"),
    ("holiday_to_expiry", "calendar", "sched"), ("holiday_in_gap", "calendar", "sched"),
    ("days_to_qend", "calendar", "sched"), ("month", "calendar", "sched"),
    ("fqtr", "calendar", "sched"), ("crowd_all", "calendar", "sched"),
    ("peer_share", "peers", "peer_prior"), ("n_peers", "peers", "peer_prior"),
    ("peer_week", "peers", "peer_prior"), ("ind_prior", "peers", "peer_prior"),
]
LANE3 = [
    ("s1_iv", "surface", "q1559"), ("s1_t", "surface", "q1559"),
    ("jsplit_jump_var", "surface", "q1559"), ("jump_share", "surface", "q1559"),
    ("iv_term_spread", "surface", "q1559"), ("entry_spread", "cost", "q1559"),
    ("depth_imb", "cost", "q1559"), ("depth_tot", "cost", "q1559"),
    ("atm_stale_h", "cost", "q1559"), ("last_vs_mid", "cost", "q1559"),
    ("traded_frac", "cost", "q1559"), ("n_strikes", "cost", "q1559"),
    ("wing_curv", "surface", "q1559"), ("wing_skew", "surface", "q1559"),
    ("wing_spread", "cost", "q1559"), ("wing_gap", "surface", "q1559"),
    ("abs_skew", "surface", "q1559"), ("carry_mag", "surface", "q1559"),
    ("depth_rel", "cost", "q1559"), ("hist_move", "history", "own_prior"),
    ("hist_ratio", "history", "own_prior"), ("rich_own", "history", "own_prior"),
    ("rich_event", "history", "own_prior"), ("log_sj", "surface", "q1559"),
]
LANE2 = [
    ("skew_25d", "surface", "q1559"), ("variance_risk_premium", "surface", "q1559"),
    ("bkm_skew", "surface", "q1559"), ("bkm_kurt", "surface", "q1559"),
    ("term_slope", "surface", "q1559"), ("im_over_rv", "surface", "q1559"),
    ("season_pos", "calendar", "sched"), ("shift", "calendar", "sched"),
    ("dow_entry", "calendar", "sched"), ("fiscal_q4", "calendar", "sched"),
    ("ret_5d", "price", "crsp_prior"), ("ret_20d", "price", "crsp_prior"),
    ("ret_60d", "price", "crsp_prior"), ("ret_250d", "price", "crsp_prior"),
    ("pos_52w", "price", "crsp_prior"), ("dist_52w_high", "price", "crsp_prior"),
    ("dist_52w_low", "price", "crsp_prior"), ("rv_5d", "price", "crsp_prior"),
    ("rv_20d", "price", "crsp_prior"), ("rv_60d", "price", "crsp_prior"),
    ("max_abs_ret_60d", "price", "crsp_prior"), ("quiet_ratio", "price", "crsp_prior"),
    ("run_abs_5d_over_im", "price", "crsp_prior"), ("trailing_rv", "price", "crsp_prior"),
    ("listed_days", "price", "crsp_prior"), ("stock_spread_bps", "cost", "crsp_prior"),
    ("bidaskhl_21d", "cost", "eom_prior"), ("market_equity", "cost", "eom_prior"),
    ("age", "fundamentals", "eom_prior"), ("rvol_21d", "price", "eom_prior"),
    ("ivol_capm_252d", "price", "eom_prior"), ("beta_60m", "price", "eom_prior"),
    ("o_score", "fundamentals", "eom_prior"), ("z_score", "fundamentals", "eom_prior"),
    ("be_me", "fundamentals", "eom_prior"), ("ni_me", "fundamentals", "eom_prior"),
    ("saleq_gr1", "fundamentals", "eom_prior"), ("niq_su", "fundamentals", "eom_prior"),
    ("saleq_su", "fundamentals", "eom_prior"),
    ("earnings_variability", "fundamentals", "eom_prior"),
    ("rmax5_21d", "price", "eom_prior"), ("iskew_capm_21d", "price", "eom_prior"),
    ("debt_me", "fundamentals", "eom_prior"), ("f_score", "fundamentals", "eom_prior"),
    ("ret_12_1", "price", "eom_prior"), ("eqnpo_12m", "fundamentals", "eom_prior"),
    ("hist_n", "history", "own_prior"), ("hist_abs_mean", "history", "own_prior"),
    ("hist_abs_max", "history", "own_prior"), ("hist_abs_med", "history", "own_prior"),
    ("hist_z_mean", "history", "own_prior"), ("hist_z_max", "history", "own_prior"),
    ("gap_prev_d", "history", "own_prior"), ("yoy_shift_d", "history", "own_prior"),
    ("dow_same_share", "history", "own_prior"), ("session_switch", "history", "own_prior"),
    ("im_rel_own", "history", "own_prior"), ("ratio_prev_mean", "history", "own_prior"),
    ("prev_tail", "history", "own_prior"), ("n_prior_panel", "history", "own_prior"),
    ("im_prev", "history", "own_prior"), ("im_over_hist", "history", "own_prior"),
    ("im_over_histmax", "history", "own_prior"),
    ("peer_n_5s", "peers", "peer_prior"), ("peer_z_mean_5s", "peers", "peer_prior"),
    ("peer_z_max_5s", "peers", "peer_prior"), ("peer_ratio_mean_5s", "peers", "peer_prior"),
    ("peer_ratio_max_5s", "peers", "peer_prior"), ("peer_n_30d", "peers", "peer_prior"),
    ("peer_ratio_mean_30d", "peers", "peer_prior"), ("peer_panel_n_5s", "peers", "peer_prior"),
    ("e_exec_change", "fundamentals", "filings"), ("e_restatement", "fundamentals", "filings"),
    ("e_auditor_change", "fundamentals", "filings"),
    ("e_material_agreement", "fundamentals", "filings"),
    ("e_acquisition_done", "fundamentals", "filings"),
    ("e_restructuring", "fundamentals", "filings"), ("e_impairment", "fundamentals", "filings"),
    ("e_prelim_results", "fundamentals", "filings"), ("e_reg_fd", "fundamentals", "filings"),
    ("e_debt", "fundamentals", "filings"), ("e_merger_form_180d", "fundamentals", "filings"),
    ("e_late_form_365d", "fundamentals", "filings"),
    ("e_amend_form_365d", "fundamentals", "filings"), ("e_n8k_100d", "fundamentals", "filings"),
    ("e_n8k_nonearn_30d", "fundamentals", "filings"),
]
MACRO_BASE = [
    "spy", "vix", "vix9d", "vix3m", "vvix", "skew", "baa10y", "t10y2y", "dgs2", "dgs10",
    "dtwexbgs", "spy_ret1", "spy_ret5", "spy_ret20", "rv5", "rv20", "vix_minus_rv20",
    "vix_rv_ratio", "vix_chg1", "vix_chg5", "vix_chg20", "ts_9d", "ts_3m", "dd", "baa_chg20",
    "abs_dgs10_1", "abs_dgs10_5", "abs_dgs2_5", "usd_chg20", "abs_spy_ret1",
]
LANE1 = [(f"{c}_lag", "macro", "macro_lag") for c in MACRO_BASE if c != "spy"] + [
    ("beta", "price", "crsp_prior"),
    ("cal_fomc_to_next", "calendar", "sched"), ("cal_fomc_since", "calendar", "sched"),
    ("cal_fomc_exit", "calendar", "sched"), ("cal_fomc_entry", "calendar", "sched"),
    ("cal_cpi_to_next", "calendar", "sched"), ("cal_cpi_since", "calendar", "sched"),
    ("cal_cpi_exit", "calendar", "sched"), ("cal_cpi_entry", "calendar", "sched"),
    ("cal_nfp_to_next", "calendar", "sched"), ("cal_nfp_since", "calendar", "sched"),
    ("cal_nfp_exit", "calendar", "sched"), ("cal_nfp_entry", "calendar", "sched"),
    ("cal_any_exit", "calendar", "sched"), ("cal_any_entry", "calendar", "sched"),
    ("cal_min_to_next", "calendar", "sched"), ("seas_week", "calendar", "sched"),
    ("seas_sofar_ratio", "peers", "peer_prior"), ("seas_sofar_n", "calendar", "peer_prior"),
    ("seas_last10_ratio", "peers", "peer_prior"), ("seas_last10_med", "peers", "peer_prior"),
]

SPINE_KEEP = [
    "ticker", "entry_date", "exit_date", "expiry", "announce_date", "m0", "s0", "mid0", "H",
    "H_mid", "y", "B", "im_bin", "cell", "tenor",
]


def _load(path: Path, cols: list[str], name: str) -> pd.DataFrame:
    x = pd.read_parquet(path, columns=KEY + cols)
    x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    dup = int(x.duplicated(KEY).sum())
    if dup:
        raise ValueError(f"{name}: {dup} duplicate keys")
    return x


def main() -> None:
    sp = pd.read_parquet(R1 / "lane5-niche" / "features.parquet")
    sp["entry_date"] = pd.to_datetime(sp["entry_date"]).dt.normalize()
    d = sp[SPINE_KEEP + [c for c, _, _ in LANE5 if c not in SPINE_KEEP]].copy()
    print(f"funnel: spine {len(d)} hedged-hold ok events, "
          f"{int((d['im_bin'] >= 0).sum())} with a causal implied-move tercile")
    n0 = len(d)
    for path, spec, name in (
        (R1 / "lane3-surface-flow" / "all_features.parquet", LANE3, "lane3"),
        (R1 / "lane2-forensics" / "ledger_all.parquet", LANE2, "lane2"),
        (R1 / "lane1-macro" / "panel.parquet", LANE1, "lane1"),
    ):
        x = _load(path, [c for c, _, _ in spec], name)
        d = d.merge(x, on=KEY, how="left", validate="one_to_one", indicator=f"_in_{name}")
        hit = d[f"_in_{name}"] == "both"
        print(f"funnel: {name} matched {int(hit.sum())} of {n0}; matched by year "
              f"{d.loc[hit].groupby(d['announce_date'].dt.year).size().to_dict()}")
        d[f"_in_{name}"] = hit
    if len(d) != n0:
        raise ValueError("join changed the row count")
    # dispersion: single-name front IV over prior-close VIX (lane1 recipe, 15:59 lane3 IV)
    d["disp_iv_ratio"] = d["front_iv"] * 100 / d["vix_lag"]
    fmap = [(c, g, t) for c, g, t in LANE5 + LANE3 + LANE2 + LANE1]
    fmap.append(("disp_iv_ratio", "surface", "q1559"))
    fm = pd.DataFrame(fmap, columns=["feature", "group", "timestamp"])
    if fm["feature"].duplicated().any():
        raise ValueError(f"duplicate features {fm.loc[fm['feature'].duplicated(), 'feature']}")
    for c in fm["feature"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").astype(float)
    cov = d[fm["feature"]].notna().mean()
    fm["coverage"] = fm["feature"].map(cov).round(4)
    fm["coverage_2025_26"] = fm["feature"].map(
        d.loc[d["announce_date"].dt.year >= 2025, fm["feature"]].notna().mean()
    ).round(4)
    fm.to_csv(HERE / "feature_map.csv", index=False)
    print(f"features kept {len(fm)}; by group {fm['group'].value_counts().to_dict()}")
    print("features below 50% coverage:", fm.loc[fm["coverage"] < 0.5, "feature"].tolist())
    # covered vs uncovered outcome for each source join (attrition check)
    for name in ("lane3", "lane2", "lane1"):
        m = d[f"_in_{name}"] & (d["announce_date"].dt.year <= 2024)
        print(f"attrition {name} 2013-24: covered n {int(m.sum())} mean y {d.loc[m, 'y'].mean():+.4f}"
              f" | uncovered n {int((~m & (d['announce_date'].dt.year <= 2024)).sum())} mean y "
              f"{d.loc[~m & (d['announce_date'].dt.year <= 2024), 'y'].mean():+.4f}")
    d.to_parquet(HERE / "panel.parquet", index=False)
    print(f"wrote {HERE / 'panel.parquet'} {d.shape}")


if __name__ == "__main__":
    main()
