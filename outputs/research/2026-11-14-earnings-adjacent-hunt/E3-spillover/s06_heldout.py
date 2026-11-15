"""
s06_heldout.py
Held-out scorer for the frozen rules of the E3 spillover lane: trial 2742 (directional peer
continuation, one session, net at the touch) and trial 2749 (peer variance ratio, the option-arm
gate), on reaction sessions 2019-2024. Read once.

Before scoring it verifies the freeze note: the note's own SHA-256 (computed with its hash line
set to PENDING) and this file's SHA-256 must match the values recorded in the note.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s06_heldout.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import spill  # noqa: E402

HERE = Path(__file__).resolve().parent
NOTE = HERE / "freeze_2026-11-14_spillover.md"
OUT = HERE / "heldout_results.json"
HELDOUT = (2019, 2024)
FROZEN = [2742, 2749]


def _verify() -> None:
    text = NOTE.read_text(encoding="utf-8")
    m_note = re.search(r"note_sha256: ([0-9a-f]{64})", text)
    m_scorer = re.search(r"scorer_sha256: ([0-9a-f]{64})", text)
    if not (m_note and m_scorer):
        raise SystemExit("freeze note lacks recorded hashes")
    blank = text.replace(m_note.group(1), "PENDING")
    if hashlib.sha256(blank.encode("utf-8")).hexdigest() != m_note.group(1):
        raise SystemExit("freeze note was edited after freezing")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != m_scorer.group(1):
        raise SystemExit("held-out scorer differs from the frozen version")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists: the held-out block has already been read")


def main() -> None:
    _verify()
    lines: list[str] = []

    def log(s: str) -> None:
        print(s)
        lines.append(s)

    res = spill.run(HELDOUT, FROZEN, log)
    OUT.write_text(json.dumps(res, indent=2, default=str))
    sys.path.insert(0, str(lib.ROOT))
    from earnings_iv_crush.research.protocol import log_block_view

    for fam in ("peer_stock_return", "peer_realised_variance"):
        log_block_view(HERE / "block_views.csv", panel="peer_spillover_nights", period="2019-24",
                       outcome_family=fam, feature_family="bellwether_reaction",
                       viewed_by="E3 spillover held-out read, trials 2742 and 2749")


if __name__ == "__main__":
    main()
