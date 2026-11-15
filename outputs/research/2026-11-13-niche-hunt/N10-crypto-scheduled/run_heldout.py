"""
run_heldout.py
The only path to lane N10's held-out read. It checks that the freeze note's own SHA-256 and the
SHA-256 of every scorer file it lists match the files on disk, refuses to run if any differ or
if any scorer was modified after the note, then runs the frozen held-out configurations once
and refuses a second run.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/run_heldout.py
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTE = HERE / "freeze_2026-11-13_monthly-expiry.md"
DONE = HERE / "logs_heldout_DONE.txt"
SELF_LINE = re.compile(r"^Note SHA-256 \(every line above this one\): ([0-9a-f]{64})$", re.M)
FILE_LINE = re.compile(r"^\| `([\w.]+)` \| ([0-9a-f]{64}) \|$", re.M)

RUNS = [
    (
        "2366",
        [
            "score_pilot_b.py",
            "--block",
            "heldout",
            "--trial",
            "2366",
            "--stat",
            "premium",
            "--note",
            "HELD-OUT primary (frozen)",
        ],
    ),
    (
        "2367",
        [
            "score_pilot_b.py",
            "--block",
            "heldout",
            "--trial",
            "2367",
            "--stat",
            "premium",
            "--exclude-macro",
            "--note",
            "HELD-OUT robustness: macro windows excluded",
        ],
    ),
    ("2368", ["ibclock.py", "--block", "heldout", "--trial", "2368"]),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify() -> None:
    text = NOTE.read_text(encoding="utf-8")
    m = SELF_LINE.search(text)
    if not m:
        raise SystemExit("freeze note has no self-hash line")
    body = text[: m.start()]
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != m.group(1):
        raise SystemExit("freeze note self-hash does not match: the note was edited")
    listed = FILE_LINE.findall(text)
    if not listed:
        raise SystemExit("freeze note lists no scorer files")
    for name, h in listed:
        f = HERE / name
        if sha(f) != h:
            raise SystemExit(f"{name} changed since the freeze")
        if f.stat().st_mtime > NOTE.stat().st_mtime:
            raise SystemExit(f"{name} is newer than the freeze note")
    print(f"  freeze verified: note and {len(listed)} files match")


def main() -> None:
    if DONE.exists():
        raise SystemExit("held-out block already read once; refusing a second read")
    verify()
    log = []
    for tid, cmd in RUNS:
        r = subprocess.run(
            [sys.executable, *cmd], cwd=HERE, capture_output=True, text=True, encoding="utf-8"
        )
        out = f"== trial {tid}: {' '.join(cmd)}\n{r.stdout}{r.stderr}"
        print(out)
        log.append(out)
        if r.returncode != 0:
            raise SystemExit(f"trial {tid} failed")
    DONE.write_text("\n".join(log), encoding="utf-8")


if __name__ == "__main__":
    main()
