# D1 state

Updated 2026-11-15 12:45 EST. Lane complete, addendum included; nothing in progress.

## Done

- Code: `d1lib.py`, `d1data.py`, `d1eval.py`, `search.py`, `write_freeze.py`, `score_heldout.py`,
  `write_trials.py`, `write_cards.py`, `explore_gain.py`, `surface_contribution.py`.
- Tests `tests/research/test_dl_heads.py`: 51 passed in the venv; skip in the main environment.
- Search: 40 configurations, `search_log.csv` (`search_round1.log`, `search_round2.log`).
- Freeze: `freeze_D1.md`, `frozen_config.json` (16:32 UTC).
- Held-out reads, each once: `heldout/results_{primary,secondary,control_primary,
  control_secondary}_{2019-24,2025-26}.json`, with cards and logs `heldout_*.log`.
- `surface_contribution_{2019-24,2025-26}.json`, `explore_gain_*_2019-24.json` (exploratory).
- Addendum (`addendum.py`, `freeze_D1_addendum.md`, `addendum_search_log.csv`,
  `heldout/results_fill_control_*.json`, `heldout/mask_occlusion_*_2019-24.json`), trials
  3,166 to 3,169.
- `trials.csv` (3,142 to 3,169), `cards.parquet`, `evidence.md`, `diagnosis.log` entries 1 to 5,
  `blocks_viewed.csv`.

## Not started

- Nothing required. Do not re-run any held-out read: the scorer refuses once a result exists.

## Trial numbers used

3,142 to 3,169 (28). 3,170 to 3,181 unused.
