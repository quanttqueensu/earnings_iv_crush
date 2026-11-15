"""
freeze.py
Write or verify a self-hashing freeze note for an L2 lever.

Usage
-----
    python freeze.py write <note.md> <body.txt> <file> [<file> ...]
    python freeze.py verify <note.md>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2lib as L  # noqa: E402


def main(argv: list[str]) -> None:
    if argv[0] == "write":
        note, body = Path(argv[1]), Path(argv[2]).read_text(encoding="utf-8")
        d = L.write_freeze(note, body, [Path(f) for f in argv[3:]])
        print(f"wrote {note} self sha256 {d}; verifies {L.verify_freeze(note)}")
    elif argv[0] == "verify":
        print(f"{argv[1]} verifies: {L.verify_freeze(Path(argv[1]))}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
