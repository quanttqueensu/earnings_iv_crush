# The frozen term-structure selector

Everything about the q=0.80 term gate: its out-of-sample verdicts, the pooled twelve-year book, attribution, the 2025-26 broad block and the attrition audit that showed that ledger was biased upward. The gate selects jump size, not mispricing, and does not carry forward. It stays fully specified because the twelve-year record was produced with it and its replacement is benchmarked against it.

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/frozen_selector/agent_comparison.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `agent_comparison.py` | Score every strategy variant on one basis, through one code path |
| `audit_oos_2026_attrition.py` | Audit of outcome-dependent attrition in the 2025-2026 straddle ledger |
| `broad_pername_gate.py` | Can the broad book use a per-name trailing gate instead of the coarse pooled cut? |
| `research_remark_verdict.py` | Every load-bearing claim, recomputed under the repaired mark |
| `research_why_stale.py` | Root-cause of the below-intrinsic exit marks |
| `run_broad_oos_verdict.py` | Read the 2025-2026 broad block against the locked gate and report significance |
| `run_driver_attribution.py` | Is the gated book's P&L carried by theta, by vega, or by the underlying move? |
| `run_extension_verdict.py` | Score the 2013-2018 quote-marked extension on the frozen specification |
| `run_performance_panel.py` | Full performance panel for the quote-marked book: risk, drawdown, and selection-bias deflation |
| `run_remark_verdict.py` | Score the quote-marked book against the pre-registered specification |
| `score_oos_2026.py` | Score the 2025-2026 broad-universe block on the settled book's own basis |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`remark_prereg.md`](preregs/remark_prereg.md)
- [`remark_prereg_amendment_01.md`](preregs/remark_prereg_amendment_01.md)

## Findings

- [`forward_window_backfill.md`](findings/forward_window_backfill.md): Backfill: short earnings straddle, 2026-07-21 to 2026-08-11
- [`oos_2026_attrition_audit.md`](findings/oos_2026_attrition_audit.md): 2025-2026 straddle ledger: outcome-dependent attrition overstates the unconditional book
- [`skew_validation.md`](findings/skew_validation.md): Skew lever - out-of-sample validation (Databento OPRA, 2019-2023)

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
