"""
a7_trial_count.py
A7: one tracked trial count, rebuilt from its three sources and written to ``trial_count.csv``.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a7_trial_count.py

Sources, all read-only:

- every hash record ``outputs/research/prereg_*.json`` with a ``dsr_trial_count``;
- ``research/ledger/trials.csv`` (read with the csv module, because one row is malformed);
- ``docs/RESEARCH_STATE.md`` section 1, for the components no file records as a number.

The count is a running sum of components, each with its source. Three totals are written, because
the pre-ledger base is not resolved on disk: the low base (about 1,506), the declared
conservative base (1,532, the deflation input section 1 prescribes) and a base that counts the
375-strategy model zoo as 375 trials rather than one verdict.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
LEDGER = ROOT / "research" / "ledger" / "trials.csv"
OUT = HERE / "trial_count.csv"
L1_TRIALS = HERE / "trials.csv"

# components that only docs/RESEARCH_STATE.md section 1 records (no machine-readable source)
BASE_RECORD = 1498  # prereg_p1_skew_reaction.json, the last count fixed in a hash record
AFTER_RECORD = {
    "date shift": 1,
    "ML ratio predictor": 9,
    "its second confirmation": 1,
    "nested walk-forward": 1,
}
ZOO = 375  # the 15:59 model zoo, reported as one verdict
BASE_LOW, BASE_DECLARED = 1506, 1532  # the two working-note totals section 1 cannot reconcile


def _hash_records() -> list[tuple[str, int]]:
    out = []
    for p in sorted((ROOT / "outputs" / "research").glob("prereg_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  unreadable hash record {p.name}: {exc!r}", file=sys.stderr)
            continue
        if isinstance(d, dict) and "dsr_trial_count" in d:
            out.append((p.name, int(d["dsr_trial_count"])))
    return out


def _ledger() -> tuple[list[list[str]], list[int]]:
    rows = list(csv.reader(LEDGER.open(encoding="utf-8")))
    bad = [i + 1 for i, r in enumerate(rows) if len(r) != len(rows[0])]
    return rows, bad


def _sum_block(rows: list[list[str]], pattern: str) -> tuple[int, int]:
    m = [r for r in rows[1:] if r[4] == "exploratory-unhashed" and re.search(pattern, r[0])]
    return sum(int(r[2]) for r in m), len(m)


def main() -> None:
    recs = _hash_records()
    top = max(recs, key=lambda x: x[1])
    rows, bad = _ledger()
    print(f"hash records with dsr_trial_count: {len(recs)}; largest {top[1]} ({top[0]})")
    print(f"ledger rows {len(rows) - 1}; malformed lines {bad}")
    a1, n1 = _sum_block(rows, r"2026-11-13-alpha-hunt/")
    a2, n2 = _sum_block(rows, r"2026-11-13-alpha-hunt-2/")
    nh, n3 = _sum_block(rows, r"2026-11-13-niche-hunt/")
    ea, n4 = _sum_block(rows, r"2026-11-14-earnings-adjacent-hunt/")
    l1 = 0
    if L1_TRIALS.exists():
        with L1_TRIALS.open(encoding="utf-8") as fh:
            l1 = sum(1 for _ in csv.DictReader(fh))
    numbered = 1628 - 1544  # 1,545 to 1,628: contiguous numbers fixed by the hash records
    comp = [
        ("pre-ledger base, low working note", BASE_LOW, "docs/RESEARCH_STATE.md s1", "low"),
        (
            "pre-ledger base, declared conservative",
            BASE_DECLARED,
            "docs/RESEARCH_STATE.md s1",
            "declared",
        ),
        (
            "pre-ledger base, zoo counted as 375",
            BASE_RECORD + sum(AFTER_RECORD.values()) + ZOO,
            "prereg_p1_skew_reaction.json 1,498 + s1 components",
            "zoo",
        ),
        (
            "hedged-hold, jump-richness, post-event, inversion (1,533 to 1,544)",
            12,
            "prereg_2026-10-21-inversion-confirm.json dsr 1,544",
            "all",
        ),
        (
            "numbered trials 1,545 to 1,628 (2026-11-01 to 2026-11-12)",
            numbered,
            "hash records 2026-11-01 to 2026-11-12; prereg_2026-11-12-* declare 1,616 to 1,628",
            "all",
        ),
        (
            "alpha hunt 1 (exploratory, unhashed)",
            a1,
            f"research/ledger/trials.csv, {n1} rows",
            "all",
        ),
        (
            "resting-entry confirmation 1,779 and 1,780 (P16-P21)",
            2,
            "research/ledger/trials.csv (6 rows for 2 trials: declarations, renumbering, verdicts)",
            "all",
        ),
        (
            "alpha hunt 2 (exploratory, unhashed)",
            a2,
            f"research/ledger/trials.csv, {n2} rows",
            "all",
        ),
        ("niche hunt (exploratory, unhashed)", nh, f"research/ledger/trials.csv, {n3} rows", "all"),
        (
            "earnings-adjacent hunt (exploratory, unhashed)",
            ea,
            f"research/ledger/trials.csv, {n4} rows",
            "all",
        ),
        (
            "slate tests L1 corrections (2,832 to 2,891 block)",
            l1,
            "outputs/research/2026-11-14-slate-tests/L1-corrections/trials.csv",
            "all",
        ),
    ]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["component", "trials", "source", "applies_to"])
        for c in comp:
            w.writerow(c)
        tail = sum(c[1] for c in comp if c[3] == "all")
        for lab, base in (("low", BASE_LOW), ("declared", BASE_DECLARED), ("zoo", comp[2][1])):
            w.writerow([f"TOTAL ({lab} base)", base + tail, "sum of base and every 'all' row", lab])
        w.writerow(["largest dsr_trial_count in any hash record", top[1], top[0], "check"])
        w.writerow(["slate tests L2 to L4", "", "not yet counted; the team lead adds them", "open"])
    print(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
