"""
ledger_entries.py
Append the 2026-11-14 slate-tests programme to the research ledgers: one ``trials.csv`` row per
lane, pointing at the lane's own trial log, and one ``blocks.csv`` row per distinct block view a
lane recorded in its ``blocks_viewed.csv``. Append-only, refuses to run twice, and recounts each
lane's trial log before writing so the ledger total matches the files on disk.

The lanes froze with notes that hash themselves and their scorers but were not filed as
pre-registrations under ``outputs/research/prereg_*``, so the rows carry the regime
``exploratory-unhashed`` and no LOND index, as the earlier 2026-11 hunts do.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/ledger_entries.py
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
PROG = "outputs/research/2026-11-14-slate-tests"
REGIME = "exploratory-unhashed"
DECLARED = "2026-11-14"
VALID_KINDS = {"trial", "descriptive"}
# Charged by the team lead after review (SUMMARY.md, review corrections 6 and 7): L2's B1
# like-for-like statistic switch (3,072) and L4's scored spread-gate comparison (3,073).
LEAD_ROW = ("SUMMARY.md", "slate tests 3,072-3,073 (team lead, review)", 2,
            "statistic switch and an unnumbered scored comparison, charged after review")

# Numbers a lane named but never scored (its trials.csv says "number unused"): not trials.
UNSCORED = {2955}

# ── lanes: (folder, verdict) ─────────────────────────────────────────────────

LANES = [
    ("L1-corrections", "valuation corrections; netting, early call assignment, financing; A1 re-strike"),
    ("L2-execution", "cost levers; 0.30 delta band with commission holds held-out (cost recovery)"),
    ("L3-selection", "no selector survives; C8 fails held-out, carried by tenor"),
    ("L4-bayes", "density forecast beats baseline held-out; selected book fails economically"),
]


def _trial_ids(lane: str) -> list[int]:
    """Distinct four-digit trial numbers in a lane's trials.csv."""
    path = ROOT / PROG / lane / "trials.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ids: set[int] = set()
    for r in rows:
        for tok in re.findall(r"\d[\d,]{3,4}", r.get("trial_id") or ""):
            n = int(tok.replace(",", ""))
            if 2832 <= n <= 3131 and n not in UNSCORED:
                ids.add(n)
    if not ids:
        raise ValueError(f"{lane}: no trial numbers found in {path}")
    return sorted(ids)


def _block_rows(lane: str) -> list[dict[str, str]]:
    """Distinct block views a lane recorded, keyed on everything but the timestamp."""
    path = ROOT / PROG / lane / "blocks_viewed.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    seen: set[tuple[str, ...]] = set()
    out = []
    for r in rows:
        key = (r["panel"], r["period"], r["outcome_family"], r["feature_family"], r["kind"])
        if key in seen:
            continue
        if r["kind"] not in VALID_KINDS:
            raise ValueError(f"{lane}: unknown kind {r['kind']!r}")
        seen.add(key)
        out.append(r)
    return out


def main() -> None:
    trials_csv = LEDGER / "trials.csv"
    if f"{PROG}/L1-corrections" in trials_csv.read_text(encoding="utf-8"):
        raise SystemExit("slate-tests rows already in trials.csv; refusing to append twice")
    counted = []
    for lane, verdict in LANES:
        ids = _trial_ids(lane)
        counted.append((lane, len(ids), f"{ids[0]:,}-{ids[-1]:,}", verdict))
    total = sum(n for _, n, _, _ in counted) + LEAD_ROW[2]
    blocks = [(lane, r) for lane, _ in LANES for r in _block_rows(lane)]
    for lane, n, span, _ in counted:
        print(f"{lane:16s} {n:3d}  {span}")
    print(f"total {total}; block rows {len(blocks)}")
    with trials_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for lane, n, span, verdict in counted:
            w.writerow(
                [
                    f"{PROG}/{lane}/trials.csv",
                    f"slate tests {span}",
                    n,
                    DECLARED,
                    REGIME,
                    "",
                    "",
                    "",
                    verdict,
                ]
            )
        w.writerow([f"{PROG}/{LEAD_ROW[0]}", LEAD_ROW[1], LEAD_ROW[2], DECLARED, REGIME, "", "", "",
                    LEAD_ROW[3]])
    for lane, r in blocks:
        log_block_view(
            LEDGER / "blocks.csv",
            panel=r["panel"],
            period=r["period"],
            outcome_family=r["outcome_family"],
            feature_family=r["feature_family"],
            viewed_by=f"slate tests 2026-11-14, {lane}: {r['viewed_by']}",
            kind=r["kind"],
        )
    print(f"appended {len(counted) + 1} trial rows ({total} trials) and {len(blocks)} block rows")


if __name__ == "__main__":
    main()
