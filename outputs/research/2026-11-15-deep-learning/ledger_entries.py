"""
ledger_entries.py
Append the 2026-11-15 deep-learning programme to the research ledgers.

Each lane gets one ``trials.csv`` row pointing at the lane's own trial log, plus a team-lead row
for the review check that SUMMARY.md quotes. ``blocks.csv`` gets one row per distinct block view
that a lane or the review recorded. The script is append-only and refuses to run twice. It
recounts each lane's trial log before writing, so the ledger total matches the files on disk.

The lanes froze with notes that hash themselves and their scorers, but the notes were not filed as
pre-registrations. The rows therefore carry the regime ``exploratory-unhashed`` and no LOND index,
as the other 2026-11 programmes do.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/ledger_entries.py
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
PROG = "outputs/research/2026-11-15-deep-learning"
REGIME = "exploratory-unhashed"
DECLARED = "2026-11-15"
VALID_KINDS = {"trial", "descriptive"}
RESERVED = (3132, 3231)
# The review's tenor-rescaled L4 (review/check_gain_source.json), charged because SUMMARY.md
# quotes it.
LEAD_ROW = (
    "SUMMARY.md",
    "deep learning 3,212 (team lead, review check)",
    1,
    "L4 rescaled by tenor tercile recovers most of the networks' gain; exploratory",
)

# ── lanes: (folder, verdict) ─────────────────────────────────────────────────

LANES = [
    ("D0-surface", "targets net of commission; L4 benchmark on H_net; 15:59 chain grids built"),
    ("D1-surface-net", "surface adds nothing beyond its no-surface twin; selected book fails"),
    ("D2-tabular", "gain over L4 is per-event scale on L4's features; selected book fails"),
]
# The review logged its views with a shorter schema (utc, period, viewed_by, kind).
REVIEW = "review"
REVIEW_PANEL = "D0 targets and lane per-event outputs"
REVIEW_OUTCOME = "hedged_hold_H_net"
REVIEW_FEATURE = "dl_review_checks"


def _trial_ids(lane: str) -> list[int]:
    """Distinct four-digit trial numbers inside the reserved block in a lane's trials.csv."""
    path = ROOT / PROG / lane / "trials.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ids: set[int] = set()
    for r in rows:
        for tok in re.findall(r"\d[\d,]{3,4}", r.get("trial_id") or ""):
            n = int(tok.replace(",", ""))
            if RESERVED[0] <= n <= RESERVED[1]:
                ids.add(n)
    if not ids:
        raise ValueError(f"{lane}: no trial numbers found in {path}")
    return sorted(ids)


def _block_rows(folder: str) -> list[dict[str, str]]:
    """Distinct block views a folder recorded, keyed on everything but the timestamp."""
    path = ROOT / PROG / folder / "blocks_viewed.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{folder}: blocks_viewed.csv is empty")
    seen: set[tuple[str, ...]] = set()
    out = []
    for r in rows:
        if folder == REVIEW:
            r = {
                "panel": REVIEW_PANEL,
                "period": r["period"],
                "outcome_family": REVIEW_OUTCOME,
                "feature_family": REVIEW_FEATURE,
                "viewed_by": r["viewed_by"],
                "kind": r["kind"],
            }
        key = (r["panel"], r["period"], r["outcome_family"], r["feature_family"], r["kind"])
        if r["kind"] not in VALID_KINDS:
            raise ValueError(f"{folder}: unknown kind {r['kind']!r}")
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> None:
    trials_csv = LEDGER / "trials.csv"
    if f"{PROG}/D0-surface" in trials_csv.read_text(encoding="utf-8"):
        raise SystemExit("deep-learning rows already in trials.csv; refusing to append twice")
    counted = []
    for lane, verdict in LANES:
        ids = _trial_ids(lane)
        counted.append((lane, len(ids), f"{ids[0]:,}-{ids[-1]:,}", verdict))
    total = sum(n for _, n, _, _ in counted) + LEAD_ROW[2]
    folders = [lane for lane, _ in LANES] + [REVIEW]
    blocks = [(f, r) for f in folders for r in _block_rows(f)]
    for lane, n, span, _ in counted:
        print(f"{lane:16s} {n:3d}  {span}")
    print(f"total {total}; block rows {len(blocks)}")
    with trials_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for lane, n, span, verdict in counted:
            w.writerow(
                [
                    f"{PROG}/{lane}/trials.csv",
                    f"deep learning {span}",
                    n,
                    DECLARED,
                    REGIME,
                    "",
                    "",
                    "",
                    verdict,
                ]
            )
        w.writerow(
            [
                f"{PROG}/{LEAD_ROW[0]}",
                LEAD_ROW[1],
                LEAD_ROW[2],
                DECLARED,
                REGIME,
                "",
                "",
                "",
                LEAD_ROW[3],
            ]
        )
    for folder, r in blocks:
        log_block_view(
            LEDGER / "blocks.csv",
            panel=r["panel"],
            period=r["period"],
            outcome_family=r["outcome_family"],
            feature_family=r["feature_family"],
            viewed_by=f"deep learning 2026-11-15, {folder}: {r['viewed_by']}",
            kind=r["kind"],
        )
    print(f"appended {len(counted) + 1} trial rows ({total} trials) and {len(blocks)} block rows")


if __name__ == "__main__":
    main()
