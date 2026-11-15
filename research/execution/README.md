# Execution and cost

How the trade is executed and what it costs: the 34,672-print fills study, the measured-cost rescore, the causal spread gates, the DoltHub entry-spread replication (invalid, not failed) and the liquidity-provider study on signed OPRA flow. The open thread is the exit-only maker arm (docs/ROADMAP.md R2).

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/execution/research_calendar_cost.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `research_calendar_cost.py` | What a front-over-back calendar costs to trade, per unit of event premium it keeps |
| `research_entry_spread_dolthub.py` | Pre-registered entry-spread filter, tested on the free DoltHub 2019-2024 block |
| `research_fills_study.py` | Where inside the quoted spread do these options actually trade? |
| `research_flow_liquidity.py` | Pre-registered tests of the liquidity-provider side from signed OPRA trades |
| `research_spread_gate.py` | Pre-registered causal spread gate on both megacap blocks |
| `run_fills_rescore.py` | Re-score the book charging measured fills instead of an assumed half-cross |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`cost_levers_prereg.md`](preregs/cost_levers_prereg.md)
- [`cost_levers_prereg_amendment_01.md`](preregs/cost_levers_prereg_amendment_01.md)
- [`entry_spread_dolthub_prereg.md`](preregs/entry_spread_dolthub_prereg.md)
- [`flow_liquidity_side_prereg.md`](preregs/flow_liquidity_side_prereg.md)
- [`flow_liquidity_side_prereg_addendum_01.md`](preregs/flow_liquidity_side_prereg_addendum_01.md)
- [`flow_liquidity_side_prereg_addendum_02.md`](preregs/flow_liquidity_side_prereg_addendum_02.md)
- [`flow_liquidity_side_prereg_addendum_03.md`](preregs/flow_liquidity_side_prereg_addendum_03.md)

## Findings

- [`cost_levers.md`](findings/cost_levers.md): The two remaining cost levers: both fail their pre-registered criteria
- [`dolthub_defect.md`](findings/dolthub_defect.md): DoltHub option chains: stale exit snapshots invalidate the 2019-2024 DoltHub straddle results
- [`entry_spread_dolthub.md`](findings/entry_spread_dolthub.md): Entry-spread filter on DoltHub 2019-2024: not confirmed
- [`flow_liquidity.md`](findings/flow_liquidity.md): W1: resting orders on the earnings straddle (F1) and customer demand pressure (F2)
- [`2026-11-14-slate-tests.md`](findings/2026-11-14-slate-tests.md): Slate tests: corrected valuation, cost levers and a sequential Bayesian model (exploratory)

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
