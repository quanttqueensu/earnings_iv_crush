# Amendment 01 to the jump-richness pre-registration

Frozen before any S4 outcome was computed. Record:
`outputs/research/prereg_2026-10-20-jump-richness_amendment_01.json`.

## What changes

The exit mark of the front straddle. The original text marks the exit with `chains._mark`, which
uses `_parse_chain` and so drops any contract whose bid is zero. A mechanical check of the scorer
on 60 discovery events, run before any outcome statistic was computed or printed, found 16 events
(27%) whose exit chain quotes one leg of the sold contract with a zero bid. Those are the
out-of-the-money legs after large moves, so dropping them makes attrition depend on the outcome
(the landmine recorded in `docs/PROTOCOL.md` P12 and the 2025-26 attrition audit).

## New rule

At the exit 15:59 chain, each leg of the sold contract is marked at its mid when the bid is
positive and at half its ask when the bid is zero and the ask is positive, the rule the 2025-26
attrition audit used. A leg with no positive ask, or a contract absent from the exit chain,
remains a drop and is counted in the funnel. The number of legs marked at half the ask is
reported. Everything else in the pre-registration is unchanged.

## Trial accounting

No new trial. S4 remains one trial.
