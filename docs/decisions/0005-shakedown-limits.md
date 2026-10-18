# 0005. Shakedown limits for the first sessions of the paper book
*Date: 2026-10-18 · Status: Accepted*

**Context:** The ladder, the order log and booking from fills were built and tested offline on
fakes. They have not yet met a real gateway's order states, pacing or rejects.

**Decision:** Start at 3 names a day (`MAX_NAMES_PER_DAY`) and 5 contracts a leg
(`max_contracts_per_leg`, no override), against the specification's 12 and 20. Admission order
is the hash order, so the cap removes events independently of any outcome. Relax to the
specification's values only after the operational go: 20 consecutive regular sessions with zero
reconciliation breaks and every order lifecycle complete.

**Consequences:** A lower trade rate during the shakedown. The 2025-26 block's median entry day
has 3 events, so the cap binds on the busier days of each season; its share of trades kept has
not been computed and should be measured on that block before the P&L timeline is restated. A
ladder defect touches at most three names.
Revert: set both fields to 12 and 20 in `LiveConfig` with a note in this file.
