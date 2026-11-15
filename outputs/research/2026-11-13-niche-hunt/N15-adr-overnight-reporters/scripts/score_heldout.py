"""
score_heldout.py
The single held-out read for lane N15 (D1 in 2026). Verifies the freeze note's recorded hash of
its own body and of this scorer, then builds the 2026 events, runs the entry-only bracket check
and scores the frozen configuration (trial 2,503, variant ``pending``) and the pre-declared
attrition robustness read (trial 2,504, variant ``pending_fill``).

Usage
-----
    python .../scripts/score_heldout.py
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

LANE = Path(__file__).resolve().parents[1]
FREEZE = LANE / "freeze_N15.md"
HASH_LINE = re.compile(r"^SHA-256 of this note above this line: ([0-9a-f]{64})$", re.M)
SCORER_LINE = re.compile(r"^SHA-256 of scripts/score_heldout.py: ([0-9a-f]{64})$", re.M)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def verify() -> None:
    text = FREEZE.read_text(encoding="utf-8")
    m = HASH_LINE.search(text)
    if m is None:
        raise SystemExit("freeze note carries no self-hash line; refusing to read held-out")
    body = text[: m.start()]
    if _sha(body.encode("utf-8")) != m.group(1):
        raise SystemExit("freeze note body changed since it was hashed; refusing")
    s = SCORER_LINE.search(body)
    if s is None or _sha(Path(__file__).read_bytes()) != s.group(1):
        raise SystemExit("held-out scorer changed since the freeze; refusing")
    print("freeze verified: note body and scorer hashes match")


def run(*args: str) -> None:
    cmd = [sys.executable, *args]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    verify()
    s = LANE / "scripts"
    run(str(s / "build_events.py"), "--year", "2026")
    run(str(s / "bracket_check.py"), "--year", "2026")
    run(str(s / "score.py"), "--year", "2026", "--variant", "pending")
    run(str(s / "score.py"), "--year", "2026", "--variant", "pending_fill")


if __name__ == "__main__":
    main()
