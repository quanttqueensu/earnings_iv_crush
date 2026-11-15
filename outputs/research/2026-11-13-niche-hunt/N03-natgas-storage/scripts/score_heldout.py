"""score_heldout.py: the single held-out read (2019-01-01 to 2024-04-05) for trials 2142-2145.

Refuses to run unless the freeze note and its sidecar hash exist and the hashes of this file
and lib.py match those recorded in the note. Writes logs/heldout_results.json and prints the
pass or fail of each pre-registered rule. Run once.

Usage:
  python -I scripts/score_heldout.py <lane_dir>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    lane = Path(sys.argv[1])
    note = lane / "freeze_heldout.md"
    side = lane / "freeze_heldout.md.sha256"
    out_path = lane / "logs" / "heldout_results.json"
    if out_path.exists():
        raise SystemExit("held-out already read; refusing a second read")
    if not note.exists() or not side.exists():
        raise SystemExit("freeze note or its sidecar hash is missing")
    if side.read_text().split()[0] != _sha(note):
        raise SystemExit("freeze note changed after it was hashed")
    text = note.read_text(encoding="utf-8")
    for name in ("score_heldout.py", "lib.py"):
        h = _sha(lane / "scripts" / name)
        if h not in text:
            raise SystemExit(f"{name} hash {h} not recorded in the freeze note")

    sys.path.insert(0, str(lane / "scripts"))
    import lib

    f = lib.load_futures(lane)
    r = lib.same_contract_returns(f)
    p, funnel = lib.weekly_panel(r)
    h = lib.block(p, lib.HELDOUT)
    print(f"held-out weeks {len(h)}: {h['week'].min().date()} to {h['week'].max().date()}")
    h2 = h.copy()
    h2["r1_thu"], h2["r1_tue"], h2["r1_wed"] = h2["r2_thu"], h2["r2_tue"], h2["r2_wed"]
    res = {
        "2142_rho_c1": lib.rho_stats(h, "1"),
        "2143_rho_c2": lib.rho_stats(h, "2"),
        "2144_short_c1": lib.short_stats(h),
        "2145_short_c2": lib.short_stats(h2),
    }
    verdict = {
        "2142": res["2142_rho_c1"]["rho_lo"] > lib.RHO_PASS,
        "2143": res["2143_rho_c2"]["rho_lo"] > lib.RHO_PASS,
        "2144": res["2144_short_c1"]["ev_lo"] > 0 and res["2144_short_c1"]["diff_lo"] > 0,
        "2145": res["2145_short_c2"]["ev_lo"] > 0 and res["2145_short_c2"]["diff_lo"] > 0,
    }
    for k, v in res.items():
        print(k, json.dumps({a: round(b, 5) for a, b in v.items()}))
    print("pass:", verdict)
    out_path.write_text(json.dumps({"results": res, "pass": verdict}, indent=2))


if __name__ == "__main__":
    main()
