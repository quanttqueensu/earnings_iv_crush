# Amendment 01 to the name-persistence pre-registration

Dated 2026-08-11, before the executable-mark run. The original pre-registration is
preserved unmodified; its SHA-256 remains
`9f60331977c2e964adfe112724029cfa5bc88ef21eda3258dddac832890ff3e2` and must be verified
byte-identical when this run is reported. This amendment supersedes the original's
decision rule only where stated; everything not mentioned here carries over unchanged.

Raised by the external reviewer. Both changes tighten the test rather than loosen it.

## Change 1: the primary estimand is the incremental advantage, not the overlay's level

**Original.** The out-of-sample criterion required the overlay's own name-block interval
to exclude zero.

**Amended.** The primary inferential object is

    delta = E[R | rich overlay] - E[R | eligible universe]

where the **eligible universe** is every event whose name already has at least three
prior events, so the signal is defined. The overlay is a subset of the eligible universe,
not an independent sample, so every bootstrap resamples the underlying clusters and
recomputes both means inside each draw rather than treating the two groups as separate.

**Why.** Testing whether the overlay's own return excludes zero tests whether short
earnings straddles are profitable in absolute terms. The hypothesis is not that. It is
that a name's prior richness predicts its next event's richness. Only the difference
against the eligible universe isolates that, and comparing against the *eligible*
universe rather than all events also prevents the three-prior eligibility requirement
from entering as a confound.

**Secondary consequence, stated in advance.** A proportional cost applied to both groups
largely cancels in a difference, so delta is far less sensitive to the cost model than
the levels are. What will not cancel is the measured cost model's asymmetry between entry
and exit interacting with any difference in premium level between the two groups. That
interaction, not the cost level, is what verdict 2 below actually tests.

## Change 2: existence and tradability are separate verdicts

**Original.** A single verdict, in which failure of the measured-cost arm made the whole
result negative.

**Amended.** Two verdicts, reported independently and never merged:

**Verdict 1, persistence supported.** All three of:

1. The overlay's mean return exceeds the eligible universe's in **both** windows.
2. The 2022-2024 out-of-sample interval for **delta** excludes zero under the frozen
   inference procedure.
3. The advantage survives dropping the single largest contributing name.

Evaluated on **gross** executable marks. This is an economic question about whether the
payoff is predictable, and it is answered before frictions.

**Verdict 2, tradable persistence supported.** Verdict 1's three conditions all hold
again under the **measured fixed-boundary execution-cost model**: 1.7871% per side,
asymmetric, entry 1.2714% and exit 3.0182%, from the 34,672-print study.

**The flat 11.6%-of-premium arm is retained as a pre-specified sensitivity and is
reported in full. It may not veto verdict 1.** If the flat arm and the measured arm
disagree, the measured arm governs verdict 2 and the disagreement is reported as the
finding.

## Change 3: inference is reported three ways

**Primary.** Name-block bootstrap, resampling whole names, because the hypothesis is
explicitly name-level persistence.

**Also reported.** Announcement-date-clustered bootstrap, and a two-way name-by-date
clustered interval on mean delta using the standard additive decomposition
`V_name + V_date - V_name∩date`.

**Why.** A common quarter or earnings-season shock could produce apparent firm
persistence if the rich names happen to concentrate in favourable seasons. Name clustering
alone cannot detect that. If the date-clustered or two-way interval crosses zero while
the name-block interval does not, verdict 1 is **not** awarded and the divergence is
reported as the result.

## Unchanged

Signal construction, minimum three priors, top-30% overlay threshold, 1st/99th
winsorisation, 5,000 draws, seed 0, both windows, the executable two-leg 15:59 marking,
return on margin as the primary unit with return on premium alongside, the stale-spot
hazard, and the trial accounting of one trial.

The signal remains the causal expanding mean of the name's past **move-space** return,
not of its executable return. Holding the signal fixed is what keeps the payoff
measurement the only thing under test.

## Binding

No further specification change after this file is hashed. Any further change requires
amendment 02 and both are reported alongside the result.
