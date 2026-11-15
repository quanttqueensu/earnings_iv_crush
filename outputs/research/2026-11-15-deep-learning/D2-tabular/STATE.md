# D2 state

Updated 2026-11-15 11:55 EST. All items complete.

Done
- Declarations and results: diagnosis.log entries [1] to [5].
- Search 24 of 24 (search_log.csv; reproduced exactly by search_log_verify.csv).
- Freeze freeze_D2.md (16:30:52Z); frozen_config.json (c17 primary, c14 secondary).
- 2019-24 frozen read: heldout_2019-24.json, heldout_2019-24_events.parquet (trials 3,182 to
  3,185). 2025-26 exploratory read: heldout_2025-26.json, heldout_2025-26_events.parquet
  (trials 3,186 to 3,189). Neither is ever re-run (the scorer refuses).
- Exploratory decomposition explore_2019_24.json; D1 comparison compare_d1.json.
- trials.csv (write_trials.py), evidence.md.
- Tests tests/research/test_dl_tabular.py: 32 pass in the venv; skipped without torch.

In progress
- None.

Not started
- None in scope. Possible follow-ups for the team lead: an L4 variant with a feature-dependent
  scale (the mechanism D2 found), and an economic rule that uses the predictive width.

Trials used: 3,182 to 3,189. 3,190 to 3,211 unused.
