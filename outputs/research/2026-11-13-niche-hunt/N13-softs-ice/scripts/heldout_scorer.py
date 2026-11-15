"""heldout_scorer.py: the single held-out read for N13 (trials 2,446 to 2,449).

Refuses to run unless the freeze note's self-hash and the recorded hashes of this file, the
scorer module and the two raw inputs all match. Writes logs/heldout.log and logs/heldout.json.
Usage:
    python scripts/heldout_scorer.py --freeze freeze_2026-11-13_wasde-event-variance.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import event_variance as ev  # noqa: E402

TRIALS = {"CT": 2446, "KC": 2447, "CC": 2448, "SB": 2449}
PLACEBOS = ("KC", "CC")
# Cost translation, pre-stated in diagnosis.log: CT five-session ATM straddle at the 2014-26
# median 60-day realised vol is 2.031 c/lb; one half-spread at 1, 3, 5 ticks per leg as a share
# of premium, plus exchange, clearing and IBKR fees of $2.95 per leg per side ($5.90 on $1,015).
HALF_SPREAD_SHARE = {1: 0.0049, 3: 0.0148, 5: 0.0246}
FEE_SHARE_PER_SIDE = 0.0058


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(freeze: Path) -> None:
    text = freeze.read_text(encoding="utf-8")
    body, _, tail = text.rpartition("Self hash (SHA-256 of every line above this one): ")
    if not tail:
        raise SystemExit("freeze note has no self-hash line")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != tail.strip():
        raise SystemExit("freeze note self-hash mismatch")
    for rel, h in re.findall(r"`([^`]+)` sha256 ([0-9a-f]{64})", body):
        if _sha(ROOT / rel) != h:
            raise SystemExit(f"hash mismatch: {rel}")
    print("freeze verified")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", required=True)
    a = ap.parse_args()
    verify(ROOT / a.freeze)
    out = {}
    lines = []
    for root, trial in TRIALS.items():
        r = ev.score(root, "heldout")
        out[root] = {"trial": trial, **asdict(r)}
        lines.append(r.funnel)
        lines.append(f"  trial {trial}: N={r.n_events} mean excess r^2 {r.mean_excess:.3e} "
                     f"[{r.excess_lo:.3e}, {r.excess_hi:.3e}]  R {r.ratio:.3f} [{r.ratio_lo:.3f}, "
                     f"{r.ratio_hi:.3f}]  robust |r| ratio {r.robust_ratio:.3f}  weekly event "
                     f"share {r.event_share_weekly:.3f}")
    ct = out["CT"]
    confounded = any(out[p]["excess_lo"] > 0 for p in PLACEBOS)
    passed = ct["ratio"] >= ev.PASS_RATIO and ct["excess_lo"] > 0 and not confounded
    lines.append(f"H1 (trial 2446): R >= {ev.PASS_RATIO}: {ct['ratio'] >= ev.PASS_RATIO}; excess "
                 f"lower bound > 0: {ct['excess_lo'] > 0}; placebo confound: {confounded} -> "
                 f"{'PASS' if passed else 'FAIL'}")
    s = ct["event_share_weekly"]
    for k, h in HALF_SPREAD_SHARE.items():
        need = 2 * (h + FEE_SHARE_PER_SIDE) / s
        lines.append(f"  break-even event-variance overpricing, {k}-tick legs, held to expiry: "
                     f"{need:.1%} (event share {s:.3f})")
    out["H1_pass"] = passed
    (ROOT / "logs" / "heldout.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "logs" / "heldout.json").write_text(json.dumps(out, indent=2, default=str),
                                               encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
