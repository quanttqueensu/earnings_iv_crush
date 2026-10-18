# Amendment 01 to the cost-levers pre-registration

Dated 2026-10-06. Made before any outcome of test H or test S was printed or viewed.

## What changed

Test H's integrity check, "any settlement intrinsic above half the strike aborts the run", is
replaced for the secondary population by a direct split check: an event is excluded, and counted
in the funnel, if the CRSP cumulative price-adjustment factor (`cfacpr`) changes between its entry
session and its front expiry. The primary population's check is unchanged and had already passed.

## Why

The magnitude check was a proxy for split-basis defects. On its first run it stopped the
secondary population on a single event, TSLA entered 2013-05-08, strike 55, closing at 91.50 on
the 2013-05-18 expiry after a 24% announcement gap and a further rally. TSLA had no split in 2013;
the settlement is genuine. Dropping it would remove one of the largest losses a held position can
suffer and bias the test toward holding, the opposite of a conservative repair. A split check
targets the defect the original check was written for without excluding real moves.

## What did not change

The rule, the cut, the cost bases, the populations, the success criterion and the decision rule.
