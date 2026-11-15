# L1 corrections: state

Updated 2026-11-15 02:25 EST. Hard stop 05:30 EST. Every item in the lane is done.

## Done

| Item | Result file |
|---|---|
| Corrected panel, A2, A3, F2 | `base_corrected.parquet` (final), `CORRECTIONS.md` (final) |
| Package (earlier run) | `optimal_call_exercise`, `optimal_put_exercise`, the `hedge_ratios` override, financing, `HoldCorrectionsConfig` |
| A5 netted strangle | `hedged_hold.hedged_short_strangle`; `tests/research/test_hedged_strangle.py` (210 pass); L2 told by message |
| A5 re-valuation of 1,819 and 1,826 | `a5_revalue.py`, `a5_net/`, `a5_results.json`, `a5_build.log`, `a5_score.log` |
| A1 re-strike and headline change | `a1_restrike.py`, `oos_2026_ledger_restrike.csv` (verified complete: byte-identical on rerun), `a1_results.json`, `a1.log` |
| A6 53aa4898 re-strike, 1,779 and 1,780 source, defect reach | `a6_restrike.py`, `a6_results.json`, `a6_events.parquet`, `a6.log`, `defect_table.csv` |
| A4 special dividends | `a4_special_divs.py`, `a4_results.json`, `a4_events.csv`, `a4.log` |
| A7 trial count | `a7_trial_count.py`, `trial_count.csv`, `a7.log` |
| Dossier and records | `evidence.md`, `trials.csv`, `diagnosis.log`, `blocks_viewed.csv` |

Checks: `python -m pytest tests/research -q` gives 448 passed. ruff and black are clean on the
lane's files, and `python -m mypy earnings_iv_crush` is clean.

## In progress

Nothing.

## Not started

Nothing in scope. Open follow-ups are listed in `defect_table.csv` (status `open`).

## Trial numbers used

2,832 to 2,840 (nine). 2,841 to 2,891 are unused.
