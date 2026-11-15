"""
write_freeze.py
Lane D2: writes freeze_D2.md before the held-out read. It records the frozen configuration and
the sha256 of the scorer, the model code, the frozen configuration JSON and the development
search_log.csv (the files score_heldout.verify_freeze checks), plus context files, and it hashes
itself (its own hash line replaced by zeros). Refuses to overwrite an existing freeze.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/write_freeze.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402
import score_heldout as sh  # noqa: E402

CONTEXT = (
    "stage2_configs.json",
    "search_log_raw_appended.csv",
    "search_log_verify.csv",
    "dev_economics.json",
    "search.py",
    "../../../../tests/research/test_dl_tabular.py",
)


def main() -> None:
    if sh.FREEZE.exists():
        raise FileExistsError("freeze_D2.md exists; a freeze is never rewritten")
    fz = json.loads(sh.FROZEN.read_text(encoding="utf-8"))
    s = pd.read_csv(HERE / "search_log.csv").set_index("config_id")
    p, t = s.loc[fz["primary_config_id"]], s.loc[fz["secondary_config_id"]]
    rec = {
        "sha256": {n: sh.sha(HERE / n) for n in sh.HASHED},
        "context_sha256": {n: sh.sha(HERE / n) for n in CONTEXT},
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    folds = ", ".join(
        f"{y} {p[f'gain_vs_l4_{y}']:+.4f} (N={int(p[f'n_{y}'])})" for y in (2016, 2017, 2018)
    )
    text = f"""# D2 freeze

Written before any 2019-24 or 2025-26 outcome or L4 score was read by this lane.

## Frozen configuration

- Primary (drives the economic rule): {fz['primary_config_id']} `{fz['primary']['name']}`,
  Gaussian head K={fz['primary']['K']}, hidden {fz['primary']['hidden']}, weight decay
  {fz['primary']['weight_decay']}, dropout {fz['primary']['dropout']}, learning rate
  {fz['primary']['lr']}.
- Secondary (log score only, infinite mean in H_net): {fz['secondary_config_id']}
  `{fz['secondary_t']['name']}`, Student-t head, hidden {fz['secondary_t']['hidden']}.
- Ensemble seeds {fz['seeds']}; averaged mixture densities.
- Rule: {fz['rule']}.
- Refit: {fz['refit']}.
- Selection: {fz['selection']}.

## Development scores (2016-18 rolling origin, 2-seed ensemble, real data)

Primary, gain over the L4 champion in nats per event, log density of H_net in % of m0:
{folds}; pooled {p['gain_vs_l4_pooled']:+.4f} (N={int(p['n_pooled'])}); over the L4
baseline {p['gain_vs_l4_base_pooled']:+.4f}. Secondary pooled {t['gain_vs_l4_pooled']:+.4f}.
Search: {len(s)} configurations of a budget of 24 (search_log.csv), reproduced exactly by a
full re-run with the frozen code (search_log_verify.csv).

## Hashes

score_heldout.py refuses to run unless every file under sha256 hashes as recorded and this note
hashes to its self-hash.

```json
{json.dumps(rec, indent=1)}
```

freeze_self_sha256: {'0' * 64}
"""
    text = text.replace("freeze_self_sha256: " + "0" * 64,
                        "freeze_self_sha256: " + sh.freeze_self_hash(text))  # fmt: skip
    sh.FREEZE.write_text(text, encoding="utf-8", newline="\n")
    sh.verify_freeze()
    print(text)


if __name__ == "__main__":
    main()
