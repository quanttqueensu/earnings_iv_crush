"""
ledger_entries.py
Append the 2026-11-14 earnings-adjacent hunt to the research ledgers: one ``trials.csv`` row per
lane, pointing at the lane's own trial log, and one ``blocks.csv`` row per outcome block a lane
viewed. Append-only, refuses to run twice, and recounts each lane's trial log before writing so
the ledger total matches the files on disk.

The lanes froze with notes that hash themselves and their scorers but were not filed as
pre-registrations under ``outputs/research/prereg_*``, so the rows carry the regime
``exploratory-unhashed`` and no LOND index, as the 2026-11-13 hunts do.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/ledger_entries.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

LEDGER = ROOT / "research" / "ledger"
HUNT = "outputs/research/2026-11-14-earnings-adjacent-hunt"
REGIME = "exploratory-unhashed"
DECLARED = "2026-11-14"

# ── trials: (lane folder, trial-id column, verdict) ──────────────────────────

TRIALS = [
    ("E1-gamma-scalp", "trial", "held-out fail; reaction-hour long gamma pays about 12x its gross"),
    ("E2-informed-flow", "trial_id", "held-out fail; reversed book adopted after discovery"),
    ("E3-spillover", "trial", "held-out fail; transfer complete by the reaction close"),
    ("E4-expiry-mechanics", "trial_id", "held-out fail; no pinning, OI-proxy strike choice null"),
    ("E5-literature-and-practice", "trial_id", "held-out fail on all read screens"),
]

# ── blocks: (panel, period, outcome family, feature family, viewed by, kind) ─

BLOCKS = [
    ("megacap_exit_ticks", "2023-24", "reaction_hour_long_gamma", "intraday_hedge_frequency",
     "E1 2,682-2,693", "trial"),
    ("broad_exit_ticks", "2025H1", "reaction_hour_long_gamma", "intraday_hedge_frequency",
     "E1 2,682-2,693", "trial"),
    ("broad_exit_ticks", "2025H2-2026H1", "reaction_hour_long_gamma", "intraday_hedge_frequency",
     "E1 2,682 held-out", "trial"),
    ("broad_exit_ticks", "2025H1", "stock_return_direction", "reaction_hour_reversal",
     "E1 2,693", "trial"),
    ("megacap_pre_ticks", "2023-24", "dm1_hour_long_gamma", "intraday_hedge_frequency",
     "E1 controls", "descriptive"),
    ("broad_pre_ticks", "2025H1", "dm1_hour_long_gamma", "intraday_hedge_frequency",
     "E1 controls", "descriptive"),
    ("flow_atm_ticks", "2023-03-28..2024-12-31", "stock_direction_next_session",
     "signed_atm_option_flow", "E2 2,712-2,722", "trial"),
    ("flow_atm_ticks", "2025-01-01..2026-12-31", "stock_direction_next_session",
     "signed_atm_option_flow", "E2 2,721-2,722 held-out", "trial"),
    ("hedged_event_hold", "2023-03-28..2024-12-31", "residual_value", "signed_atm_option_flow",
     "E2 2,714", "trial"),
    ("peer_spillover_nights", "2013-18", "peer_stock_return", "bellwether_reaction",
     "E3 2,742-2,752", "trial"),
    ("peer_spillover_nights", "2013-18", "peer_realised_variance", "bellwether_reaction",
     "E3 2,747, 2,749", "trial"),
    ("peer_spillover_nights", "2019-24", "peer_stock_return", "bellwether_reaction",
     "E3 2,742 held-out", "trial"),
    ("peer_spillover_nights", "2019-24", "peer_realised_variance", "bellwether_reaction",
     "E3 2,749 held-out", "trial"),
    ("hedged_event_hold", "2013-18", "expiry_pinning", "strike_grid", "E4 2,772", "trial"),
    ("hedged_event_hold_megacap", "2013-18", "expiry_pinning", "strike_grid", "E4 2,772",
     "trial"),
    ("hedged_event_hold", "2019-24", "expiry_pinning", "strike_grid", "E4 2,772 held-out",
     "trial"),
    ("hedged_event_hold_megacap", "2019-24", "expiry_pinning", "strike_grid",
     "E4 2,772 held-out", "trial"),
    ("hedged_event_hold_megacap", "2014-18", "hedged_hold", "open_interest_proxy", "E4 2,773",
     "trial"),
    ("hedged_event_hold_megacap", "2019-24", "hedged_hold", "open_interest_proxy",
     "E4 2,773 held-out", "trial"),
    ("hedged_event_hold", "2013-24", "hedged_hold", "exdiv_exercise_bias", "E4 part (b)",
     "descriptive"),
    ("crsp_event_windows", "2019-21", "stock_return_direction",
     "pre_event_return_and_unconditional", "E5 2,802-2,803", "trial"),
    ("crsp_event_windows", "2022-24", "stock_return_direction",
     "pre_event_return_and_unconditional", "E5 2,802-2,803 held-out", "trial"),
    ("crsp_expiry_weeks", "2019-21", "basket_return", "option_expiration_week", "E5 2,804",
     "trial"),
    ("hedged_event_hold", "2013-18", "residual_value", "report_session", "E5 2,805", "trial"),
    ("hedged_event_hold", "2019-24", "residual_value", "report_session", "E5 2,805 held-out",
     "trial"),
]


def _count(lane: str, col: str) -> tuple[int, str]:
    """Distinct trial numbers in a lane's trials.csv, and their range for the label."""
    path = ROOT / HUNT / lane / "trials.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ids = sorted({int(r[col]) for r in rows if re.fullmatch(r"\d{4}", (r[col] or "").strip())})
    if not ids:
        raise ValueError(f"{lane}: no trial numbers found in {path}")
    return len(ids), f"{ids[0]:,}-{ids[-1]:,}"


def main() -> None:
    trials_csv = LEDGER / "trials.csv"
    if f"{HUNT}/E1-gamma-scalp" in trials_csv.read_text(encoding="utf-8"):
        raise SystemExit("earnings-adjacent rows already in trials.csv; refusing to append twice")
    counted = [(lane, *_count(lane, col), verdict) for lane, col, verdict in TRIALS]
    total = sum(n for _, n, _, _ in counted)
    for lane, n, span, _ in counted:
        print(f"{lane:30s} {n:3d}  {span}")
    print(f"total {total}")
    with trials_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for lane, n, span, verdict in counted:
            w.writerow(
                [
                    f"{HUNT}/{lane}/trials.csv",
                    f"earnings-adjacent hunt {span}",
                    n,
                    DECLARED,
                    REGIME,
                    "",
                    "",
                    "",
                    verdict,
                ]
            )
    for panel, period, outcome, feature, who, kind in BLOCKS:
        log_block_view(
            LEDGER / "blocks.csv",
            panel=panel,
            period=period,
            outcome_family=outcome,
            feature_family=feature,
            viewed_by=f"earnings-adjacent hunt 2026-11-14, {who}",
            kind=kind,
        )
    print(f"appended {len(counted)} trial rows ({total} trials) and {len(BLOCKS)} block rows")


if __name__ == "__main__":
    main()
