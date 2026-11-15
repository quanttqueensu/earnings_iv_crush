"""make_freeze.py: write a freeze note that records its own SHA-256 and that of its inputs.

The note's last line is ``Note sha256 (of every byte above this line): <hex>``, the hash of every
byte before that line. Each file named with ``--hash`` gets a ``<name> sha256 <hex>`` line, so a
scorer that checks for its own hash in the note refuses to run if it changed after the freeze.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/make_freeze.py \
        --out freeze_e5.md --body body.txt --hash e5_score.py lib.py
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--body", required=True, help="text file holding the note's prose")
    ap.add_argument("--hash", nargs="+", default=[])
    a = ap.parse_args(argv)
    here = Path(__file__).resolve().parent
    out = here / a.out
    if out.exists():
        raise SystemExit(f"{out.name} exists; a freeze note is written once")
    body = Path(a.body).read_text(encoding="utf-8").rstrip("\n") + "\n\n"
    for f in a.hash:
        body += f"{f} sha256 {hashlib.sha256((here / f).read_bytes()).hexdigest()}\n"
    nh = hashlib.sha256(body.encode("utf-8")).hexdigest()
    out.write_bytes((body + f"Note sha256 (of every byte above this line): {nh}\n").encode("utf-8"))
    print(out, nh)


if __name__ == "__main__":
    main()
