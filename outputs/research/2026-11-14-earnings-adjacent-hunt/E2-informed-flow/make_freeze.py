"""
make_freeze.py
Lane E2: write freeze_2026-11-14_reversed_delta_flow.md with the hashes of the held-out scorer and
its local imports, and the note's own hash (computed with that hash replaced by 64 zeros).

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/make_freeze.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import lib
from earnings_iv_crush.research.protocol import block_is_clean

NOTE = lib.HERE / "freeze_2026-11-14_reversed_delta_flow.md"
ZERO = "0" * 64


def _sha(name: str) -> str:
    return hashlib.sha256((lib.HERE / name).read_bytes()).hexdigest()


def main() -> None:
    if NOTE.exists():
        raise SystemExit("freeze note already written; a change is a new dated amendment")
    ok, hits = block_is_clean(lib.ROOT / "research" / "ledger" / "blocks.csv",
                              panel="flow_atm_ticks", period="2025-01-01..2026-12-31",
                              outcome_family="stock_direction_next_session",
                              feature_family="signed_atm_option_flow")
    body = Path(lib.HERE / "freeze_template.txt").read_text(encoding="utf-8")
    txt = body.format(
        zero=ZERO,
        scorer=_sha("score_heldout.py"),
        lib=_sha("lib.py"),
        disc=_sha("score_discovery.py"),
        var=_sha("variants.py"),
        build=_sha("build_features.py"),
        clean=ok,
        clashes=len(hits),
    )
    h = hashlib.sha256(txt.encode("utf-8")).hexdigest()
    NOTE.write_text(txt.replace(ZERO, h), encoding="utf-8")
    (lib.HERE / "freeze_template.txt").unlink()
    print(f"wrote {NOTE.name}; self_sha256 {h}; block clean {ok}")


if __name__ == "__main__":
    main()
