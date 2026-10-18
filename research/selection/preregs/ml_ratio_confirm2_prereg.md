# Pre-registration: second confirmation of the frozen ML ratio model on July-August 2026 events

## Why

The frozen model of `_private/ml_ratio_prereg.md` (model SHA-256
884e149d3c0ad3aefb35c91fceea2485dbabffb9610f02c1ad04e5fad974a1fc, ridge alpha 10, sell threshold
0.72618 on predicted realised/implied) failed its pre-registered rule: the 2022-2024 megacap test
failed and the 2025-2026 broad confirmation passed (selected events +2.02% of margin per trade
against -1.12% for all, Spearman +0.113 [+0.055, +0.168]). The result is recorded as a failure. This
is a new, separately declared test of the broad-universe result on events the model, and every test
in this programme, has never touched.

## Data

- Events: the 199 events of `outputs/research/backfill_ledger.csv` (entries 2026-07-13 to
  2026-08-06), the only post-June-2026 events with cached 15:59 chains on both sessions. Session:
  AMC when entry date equals announcement date, BMO otherwise.
- Features: built by `earnings_iv_crush.data.real_events.build_execution_events` with the Alpaca
  chain and price fetchers of `scripts/build_broad_oos_2025.py`, the same code path that produced
  the 2025-2026 features; the date shift and name-prior-ratio as in `research_ml_ratio._derive`
  (prior events drawn from the 2025-2026 block for the name-prior ratio).
- Outcomes: the short ATM straddle marked from the cached 15:59 chains exactly as
  `scripts/audit_oos_2026_attrition.py` does (ledger strike and expiry rules, zero-bid exit legs at
  ask / 2, 11.6%-of-premium round-trip cost, Reg-T margin), giving net RoM and realised/implied.

## Decision rule

With the frozen model and threshold unchanged:
1. **Primary:** mean net RoM of selected events minus mean net RoM of unselected events > 0, with a
   date-clustered 95% bootstrap interval above zero (5,000 draws, seed 0).
2. Selected events' mean net RoM > 0.
Both are required. Secondary: Spearman(prediction, realised/implied) with interval; selected share;
results at the actual 15:59 touch if tick data exist (they do not for this window).

Power, stated now: with about 200 events and the 2025-2026 effect size (selected minus unselected
about 8 points of margin, per-trade standard deviation about 12 points), the expected interval
half-width is about 4 points, so a true effect of that size would usually be detected and one under
a third of it would not.

## What is not allowed

No change to the model, threshold, features, outcome construction or tests after any outcome is
seen. A pass earns a forward paper test with the model frozen; it is not a production claim.
