# Amendment 02 to the post-earnings pre-registration

Amends `_private/postea_prereg.md`
(SHA-256 `bc22613afd90e0dc143ddc4b416761a52fc37bc3541b4b6fda97592a0645ae3d`)
as already amended by amendment 01
(SHA-256 `1cd2ceb493431180b4305b7999f585938062aa6abe2e8beca064cc82f31594ca`).

Frozen before any return, difference or matched pair is computed. Two exclusions in section
7 are corrected. Neither is a change of intent: one was being enforced more loosely than
written, and the other is not computable as written on the contracts the study requests.
The estimand, both controls, the strata, the matching, the inference plan and the decision
rule are untouched.

## 1. "Fewer than 5 reliable strikes at the expiry" is now enforced on strikes

Section 7 excludes an expiry with fewer than five reliable strikes. The implementation
counted **contracts**, not strikes, so an expiry with two strikes quoted two-sided in both
rights passed a test intended to require five. Two paired strikes is not enough to locate a
put-call parity forward with any confidence, and the forward is what every downstream
quantity is measured against.

The test is now the distinct count of strikes carrying a two-sided quote in both rights at
the chosen expiry. On the sample priced when this was written it retains 426 of 581 priced
observations (73.3%). The dropped observations carry a median of three paired strikes
against nine for those retained.

## 2. The strike-ladder half of the deliverable proxy is withdrawn

Section 7 proxies a non-standard deliverable by two conditions: a regular strike ladder, and
a parity forward within 5% of the equity close. The ladder condition is withdrawn. The
forward condition stands alone and is unchanged.

The reason is that the study requests the eleven strikes nearest spot rather than a full
ladder, and real ladders change spacing across that range (a dollar apart near the money,
two and a half further out), so regularity measured on a truncated selection tests spacing
uniformity rather than contract adjustment.

Measured rather than asserted, on the sample priced when this was written:

| Group | n | Median forward-vs-spot deviation | 95th percentile | Median paired strikes |
|---|---|---|---|---|
| ladder test passes | 457 | 0.0020 | 0.0110 | 9 |
| ladder test fails | 124 | 0.0026 | 0.0152 | 3 |

The two groups are indistinguishable on the quantity that actually identifies an adjusted
contract, both far inside the 5% threshold, while they differ by a factor of three on
paired-strike count. The ladder test was therefore not detecting deliverables at all; it was
a noisy restatement of the strike-count test, and it removes only two further percentage
points once the corrected strike test is applied.

The parity forward remains the operative deliverable screen and is the stronger of the two
by construction: an adjusted contract carries strikes on the pre-adjustment price scale, so
its parity forward sits far from the equity close and the 5% test catches it directly.

`ladder_ok` continues to be recorded on every observation so this decision stays auditable
and can be reversed by anyone who disagrees.

## 3. What is unchanged

Everything else. The incremental estimand; control A and control B, reported separately and
never combined; the frozen strata S1, S2 and S3; matching variables and the requirement that
match quality is reported before any outcome is read; the announcement-inside-the-life
exclusion; the ex-dividend flag and its sensitivity subset; event-level clustered inference
and the calendar-time portfolio; the decision rule including that failure under both controls
closes single-name earnings volatility; one trial charged against 1,477.

No outcome, difference or matched pair had been computed at the time this amendment was
frozen. The sample statistics quoted above are funnel counts and contract characteristics,
not returns.
