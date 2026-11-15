"""score_heldout.py: the single held-out read for trials 2,385, 2,386 and 2,387.

Verifies the SHA-256 of every frozen input listed in the freeze note, then runs the frozen
configurations on releases from 2026-01-01 and applies the pass rules written in the note.

Usage
-----
    python scripts/score_heldout.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

LANE = Path(__file__).resolve().parents[1]
NOTE = LANE / "freeze_2026-11-13.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> None:
    text = NOTE.read_text(encoding="utf-8")
    body, _, tail = text.rpartition("\nSelf hash: ")
    if _sha_bytes((body + "\n").encode("utf-8")) != tail.strip():
        raise SystemExit("freeze note self hash mismatch")
    for rel, digest in re.findall(r"^\| `([^`]+)` \| ([0-9a-f]{64}) \|$", body, flags=re.M):
        if _sha(LANE / rel) != digest:
            raise SystemExit(f"hash mismatch: {rel}")
    print("freeze verified", flush=True)


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    verify()
    py = sys.executable
    subprocess.run([py, "scripts/pilot.py", "--block", "heldout", "--trial", "2387", "--entry",
                    "next"], cwd=LANE, check=True, capture_output=True)
    subprocess.run([py, "scripts/multisignal.py", "--block", "heldout", "--trial", "2386"],
                   cwd=LANE, check=True, capture_output=True)
    single = json.loads((LANE / "logs/pilot_heldout_trial2387.json").read_text())
    multi = json.loads((LANE / "logs/multisignal_heldout_trial2386.json").read_text())
    h1s, h2 = single["H1"]["a=0.02"], single["H2"]["a=0.02"]
    cm = multi["contract_mean_then_date_ci"]
    verdict = {
        "H1_primary_2386_contract_mean": cm,
        "H1_primary_pass": cm["lo"] > 0 and cm["n"] >= 30 and cm["dates"] >= 10,
        "H1_support_2387_single": h1s.get("net_pnl"),
        "H1_support_pass": (h1s.get("net_pnl") or {}).get("mean", -1) > 0,
        "H1_mechanism_gap_capture_2387": h1s.get("gross_gap_capture"),
        "H1_brier_fex_minus_kalshi": h1s.get("brier_fex_minus_kalshi"),
        "H2_2385": h2.get("net_pnl"),
        "H2_pass": bool(h2.get("net_pnl")) and h2["net_pnl"]["lo"] > 0
        and h2["net_pnl"]["n"] >= 30 and h2["net_pnl"]["dates"] >= 10,
    }
    verdict["H1_pass"] = verdict["H1_primary_pass"] and verdict["H1_support_pass"]
    (LANE / "logs/heldout_verdict.json").write_text(json.dumps(verdict, indent=1))
    print(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
