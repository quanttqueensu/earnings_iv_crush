"""
ledger_entries.py
Append both 2026-11-13 alpha hunts to the research ledgers: one ``trials.csv`` row per lane,
pointing at the lane's own trial log, and one ``blocks.csv`` row per outcome block each lane
viewed. Append-only, and refuses to run twice.

The hunts froze with unhashed notes, so their rows carry the regime ``exploratory-unhashed`` and
no LOND index: they count towards the trial total but none is a confirmatory test under P16-P21.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/ledger_entries.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

LEDGER = ROOT / "research" / "ledger"
H1 = "outputs/research/2026-11-13-alpha-hunt"
H2 = "outputs/research/2026-11-13-alpha-hunt-2"
REGIME = "exploratory-unhashed"
DECLARED = "2026-11-13"

# ── trials: (lane folder, trial ids, distinct trials, verdict) ───────────────

TRIALS = [
    (
        f"{H1}/lane1-macro",
        "1,629-1,657 and 1,644b",
        29,
        "no held-out pass; C2 held-out t 1.84",
    ),
    (f"{H1}/lane2-forensics", "1,659-1,681", 23, "discovery screens only; spread gate"),
    (f"{H1}/lane3-surface-flow", "1,689-1,708", 20, "R5 reversed on held-out"),
    (
        f"{H1}/lane4-structure",
        "1,719-1,740",
        22,
        "15:45 entry and package exploratory passes; no book positive at the touch",
    ),
    (f"{H1}/lane5-niche", "1,749-1,771", 23, "early-in-industry failed held-out"),
    (f"{H2}/laneA-hold-exit", "1,781-1,798", 18, "band 0.10 held-out pass, cost recovery only"),
    (
        f"{H2}/laneB-contract-choice",
        "1,811-1,826",
        16,
        "1,819 held-out pass (confirmatory status contested); 1,826 exploratory; cost recovery",
    ),
    (
        f"{H2}/laneC-post-event-vrp",
        "1,841-1,856",
        16,
        "fail; 1,856 netting correction adopted 2026-11-13",
    ),
    (
        f"{H2}/laneD-jump-model",
        "1,871-1,900 and 2,081",
        31,
        "1,897 exploratory pass t 2.91, 1,898 replication failed; 2,081 not read (underpowered)",
    ),
    (f"{H2}/laneE-walk-forward-model", "1,901-1,922", 22, "fail"),
    (
        f"{H2}/laneF-resting-exit",
        "1,931-1,958",
        28,
        "re-pegged exit exploratory pass broad 2026, fail megacap; loses to the hold",
    ),
    (f"{H2}/laneG-index-event-vol", "1,961-1,984", 24, "fail; held-out C not clean"),
    (f"{H2}/laneH-other-scheduled-events", "1,991-2,017", 27, "fail; pilot, N under 20"),
    (f"{H2}/laneI-entry-day", "2,021-2,036", 16, "fail; cost check passes (early entry loses)"),
    (f"{H2}/laneJ-name-persistence", "2,051-2,080", 30, "fail"),
]

# ── blocks: (panel, period, outcome family, feature family, viewed by) ───────

HOLD = "hedged_event_hold"
BLOCKS = [
    # round 1
    (HOLD, "2013-18", "residual_value", "macro_state", "trials 1,629-1,657"),
    (HOLD, "2019-24", "residual_value", "macro_state", "trials 1,629-1,657"),
    (HOLD, "2013-21", "buyback", "forensics_liquidity_size", "trials 1,659-1,681"),
    (HOLD, "2014-19", "residual_value", "quote_surface_flow", "trials 1,689-1,708"),
    (HOLD, "2016-19", "residual_value", "event_richness_own_history", "trials 1,689-1,708"),
    (HOLD, "2020-24", "residual_value", "event_richness_own_history", "trials 1,689-1,708"),
    (HOLD, "2025-26", "residual_value", "event_richness_own_history", "trials 1,689-1,708"),
    (HOLD, "2013-19", "hold_vs_buyback", "entry_clock_and_hold", "trials 1,719-1,740"),
    (HOLD, "2020-24", "hold_vs_buyback", "entry_clock_and_hold", "trials 1,719-1,740"),
    (HOLD, "2025-26", "hold_vs_buyback", "entry_clock_and_hold", "trials 1,719-1,740"),
    ("broad_entry_ticks", "2025", "entry_execution", "entry_clock", "trials 1,719-1,740"),
    ("broad_entry_ticks", "2026H1", "entry_execution", "entry_clock", "trials 1,719-1,740"),
    ("megacap_entry_ticks", "2020-24", "entry_execution", "entry_clock", "trials 1,719-1,740"),
    (HOLD, "2013-18", "residual_value", "calendar_niche", "trials 1,749-1,771"),
    (HOLD, "2019-24", "residual_value", "calendar_niche", "trials 1,749-1,771"),
    # round 2
    (HOLD, "2013-18", "hold_vs_buyback", "post_announcement_rules", "trials 1,781-1,798"),
    (HOLD, "2019-24", "hold_vs_buyback", "post_announcement_rules", "trials 1,781-1,798"),
    (HOLD, "2013-18", "hedged_hold", "contract_choice", "trials 1,811-1,826"),
    (HOLD, "2019-24", "hedged_hold", "contract_choice", "trials 1,811-1,826"),
    (HOLD, "2013-18", "hold_vs_buyback", "post_event_vol_forecast", "trials 1,841-1,856"),
    (HOLD, "2019-24", "hold_vs_buyback", "post_event_vol_forecast", "trials 1,841-1,856"),
    (HOLD, "2019-24", "residual_value", "structural_jump_model", "trials 1,871-1,896"),
    (HOLD, "2013-18", "residual_value", "structural_jump_model", "trials 1,897-1,900"),
    (HOLD, "2025-26", "residual_value", "structural_jump_model", "trial 1,898"),
    (HOLD, "2016-21", "residual_value", "walk_forward_model", "trials 1,901-1,920"),
    (HOLD, "2022-24", "residual_value", "walk_forward_model", "trial 1,921"),
    ("broad_exit_ticks", "2025", "exit_execution", "resting_exit", "trials 1,931-1,950"),
    ("broad_exit_ticks", "2026H1", "exit_execution", "resting_exit", "trials 1,951-1,958"),
    ("megacap_exit_ticks", "2023-24", "exit_execution", "resting_exit", "trials 1,953-1,954"),
    ("index_event_nights", "2016-18", "index_event_straddle", "megacap_reporters", "lane G"),
    ("index_event_nights", "2019-24", "index_event_straddle", "megacap_reporters", "lane G"),
    ("index_event_nights", "2025-26", "index_event_straddle", "megacap_reporters", "lane G"),
    ("dolthub_scheduled_events", "2019-21", "event_straddle", "adcomm_product", "lane H"),
    ("dolthub_scheduled_events", "2022-24", "event_straddle", "adcomm_product", "lane H"),
    ("dolthub_pre_event_chains", "2019-24", "entry_day", "early_entry", "trials 2,021-2,036"),
    (HOLD, "2013-18", "residual_value", "name_persistence", "trials 2,051-2,072"),
    (HOLD, "2019-24", "residual_value", "name_persistence", "trials 2,073-2,080"),
]


def main() -> None:
    total = sum(t[2] for t in TRIALS)
    if total != 345:
        raise ValueError(f"trial total {total} differs from the audited 117 + 228")
    trials_csv = LEDGER / "trials.csv"
    text = trials_csv.read_text(encoding="utf-8")
    if f"{H2}/laneA-hold-exit" in text:
        raise SystemExit("hunt rows already in trials.csv; refusing to append twice")
    with trials_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for folder, ids, n, verdict in TRIALS:
            w.writerow(
                [f"{folder}/trials.csv", f"alpha hunt {ids}", n, DECLARED, REGIME, "", "", "", verdict]
            )
    for panel, period, outcome, feature, who in BLOCKS:
        log_block_view(
            LEDGER / "blocks.csv",
            panel=panel,
            period=period,
            outcome_family=outcome,
            feature_family=feature,
            viewed_by=f"alpha hunt 2026-11-13, {who}",
            kind="trial",
        )
    print(f"appended {len(TRIALS)} trial rows ({total} trials) and {len(BLOCKS)} block rows")


if __name__ == "__main__":
    main()
