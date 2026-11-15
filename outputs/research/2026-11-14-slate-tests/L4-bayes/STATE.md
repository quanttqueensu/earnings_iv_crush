# L4 state

Rewritten after each iteration. Read with `diagnosis.log` before resuming.

## Done

- Stage 1: `earnings_iv_crush/research/online_bayes.py`, `tests/research/test_online_bayes.py`,
  `OnlineBayesConfig` in `config.py`, declaration (`diagnosis.log` entries 1 to 3), synthetic
  pipeline check (`pipeline_check.log`).
- Iteration round 1: package additions (Student-t scale mixture, industry level, variance power,
  wide feature set, z clip, Yeo-Johnson loss-ratio target, expected-value rule, coefficient
  path), all defaults reproducing stage 1; 50 tests in `test_online_bayes.py`.
- Discovery search: `search_log.csv`, 800 rows (H_corr 568, residual_value 232).
- Freeze: `ONLINE_BAYES_L4_*` in `config.py`; `freeze_online_bayes.md`; `discovery_fit.json`.
- Held-out read, once: `heldout_results.json`, `run_*.parquet`, `coef_path_*.csv`,
  `gauge_*.csv`, `posterior_frozen.npz`; lock row in `heldout_runs.jsonl`.
  NEVER rerun `score_heldout.py`.
- Exploratory decomposition: `decomposition.json`.
- Trade cards: `trade_cards.parquet`, `trade_cards.csv`, `trade_cards_summary.md`.
- Figures and insight: `fig_coef_paths.png`, `fig_gauge.png`, `fig_pit.png`,
  `insight_numbers.json`, `insight.md`.
- Forward mode: `forward_check.log` (exit 2, N=0, live and dry).
- Round 2 (exploratory, 2025-26 only, the last round): `round2_results.json`,
  `round2_mean_monitor.csv`.
- Dossier: `evidence.md`; `trials.csv` complete.

## In progress

- Final checks (pytest, ruff, black, mypy) and the final message to the team lead.

## Not started

- Nothing. Two rounds used; no further round is allowed.

## Trial numbers used

- 3,012 to 3,023 (3,012 and 3,017 discovery fits; 3,013 to 3,016 and 3,018 to 3,021 held-out;
  3,022 and 3,023 round 2). 3,024 to 3,071 unused.
