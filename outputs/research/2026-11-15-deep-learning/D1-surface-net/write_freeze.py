"""
write_freeze.py
Lane D1 freeze: selects the primary (best eligible D1b) and secondary (best eligible D1a)
configurations from ``search_log.csv`` by the pooled development gain against L4, the rule in
``diagnosis.log`` entry 1, writes ``frozen_config.json`` and ``freeze_D1.md`` with the sha256 of
the scorer, the model code, the frozen configuration and the search log, and a self-hash. Reads
no held-out outcome.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/write_freeze.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LOG = HERE / "search_log.csv"
FROZEN = HERE / "frozen_config.json"
FREEZE = HERE / "freeze_D1.md"
SEEDS = [0, 1, 2, 3, 4]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    if FREEZE.exists():
        raise SystemExit("freeze_D1.md exists; a freeze is written once")
    log = pd.read_csv(LOG)
    log["spec_d"] = log["spec"].map(json.loads)
    log["variant"] = log["spec_d"].map(lambda d: d["variant"])
    log["use_surface"] = log["spec_d"].map(lambda d: d["use_surface"])
    elig = log[log["eligible"].astype(bool) & log["use_surface"]]
    pick = {}
    for which, var in (("primary", "b"), ("secondary", "a")):
        sub = elig[elig["variant"] == var]
        if sub.empty:
            raise ValueError(f"no eligible D1{var} row")
        r = sub.sort_values("gain_l4_pooled", ascending=False, kind="stable").iloc[0]
        pick[which] = {"config_id": r["config_id"], "spec": r["spec_d"],
                       "dev": {k: r[k] for k in r.index if k.startswith(("gain_", "ls_", "n_"))}}
    sha_surf = None
    for line in (HERE / "diagnosis.log").read_text(encoding="utf-8").splitlines():
        if line.startswith("surfaces_sha256: "):
            sha_surf = line.split(": ", 1)[1].strip()
    if sha_surf is None:
        raise ValueError("diagnosis.log does not record the surfaces sha256 the search used")
    ctrl = log[log["eligible"].astype(bool) & ~log["use_surface"]]
    for which in ("control_primary", "control_secondary"):
        # Comparators, not candidates: the no-surface twin of each frozen configuration,
        # read on the same events so the surface's own contribution has a held-out interval.
        twin = {**pick[which.split("_")[1]]["spec"], "use_surface": False}
        # Without the surface, arch and conv_ch build nothing, so they do not enter the match.
        def same(d: dict, t: dict = twin) -> bool:
            drop = ("arch", "conv_ch")
            return {k: v for k, v in d.items() if k not in drop} == {
                k: v for k, v in t.items() if k not in drop
            }

        sub = ctrl[ctrl["spec_d"].map(same)]
        if sub.empty:
            print(f"[freeze] no logged no-surface twin for {which}; none frozen")
            continue
        r = sub.iloc[0]
        pick[which] = {"config_id": r["config_id"], "spec": r["spec_d"],
                       "dev": {k: r[k] for k in r.index if k.startswith(("gain_", "ls_", "n_"))}}
    frozen = {**pick, "seeds": SEEDS, "surfaces_sha256": sha_surf,
              "rule": "trade when the quadrature predictive mean of H_net is above 0"}
    FROZEN.write_text(json.dumps(frozen, indent=2, default=str) + "\n", encoding="utf-8")
    files = {
        "scorer_sha256": HERE / "score_heldout.py",
        "d1lib_sha256": HERE / "d1lib.py",
        "d1data_sha256": HERE / "d1data.py",
        "d1eval_sha256": HERE / "d1eval.py",
        "frozen_config_sha256": FROZEN,
        "search_log_sha256": LOG,
    }
    stamp = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    n = len(log)
    lines = [
        "# Freeze note: lane D1, surface network",
        "",
        f"Written {stamp} after the development search ({n} configurations in "
        "`search_log.csv`) and before any 2019-24 outcome was read by this lane.",
        "",
        "## Hypothesis, scope and success criteria",
        "",
        "Hypothesis: the 15:59 option surface carries information about the distribution of the "
        "hedged short-straddle outcome `H_net` beyond L4's features. Scope: D0's targets, 9,315 "
        "events with `H_net`; 2019-24 read once per configuration with quarterly refits, then "
        "2025-26 exploratory. Criteria as `diagnosis.log` entry 1 and the brief: forecaster pass "
        "(gain against L4 above zero at the date-clustered lower bound, positive in 4 of 6 "
        "years); economic pass on `H_net` and `residual_value` against the tight-spread-per-date "
        "screen, the pool and the matched random null.",
        "",
        "## Frozen configurations",
        "",
    ]
    for which in pick:
        p = pick[which]
        lines += [f"- {which} ({p['config_id']}): `{json.dumps(p['spec'])}`",
                  f"  development: `{json.dumps(p['dev'], default=str)}`"]
    lines += [
        "",
        f"Seeds {SEEDS}, density-averaged. Surfaces sha256 `{sha_surf}`.",
        "The development gains are the best of the search and so biased upwards; the held-out "
        "read is the unbiased one.",
        "",
        "## Hashes",
        "",
    ]
    lines += [f"{k}: {_sha(v)}" for k, v in files.items()]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    FREEZE.write_bytes(body + f"self_sha256: {hashlib.sha256(body).hexdigest()}\n".encode())
    print(FREEZE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
