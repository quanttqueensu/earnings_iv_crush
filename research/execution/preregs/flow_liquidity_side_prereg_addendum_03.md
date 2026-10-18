# Addendum 03 to the flow and liquidity-side pre-registration

Written after the reconciliation gate stopped the second scoring attempt (34.7% of events over the
1%-of-margin tolerance) and before any paired outcome, fill rate, markout or signed-flow statistic
was viewed.

The gate compared the tick-built cross book at 15:59:59 ET with the cached chain touch, which is the
consolidated BBO sampled at 15:59:00 ET. A diagnostic that rebuilt the tick cross at 15:59:00 found
a median gap of 0.0 and no event over tolerance (N=1,223), against a median of 0.50% of margin and
33.5% over tolerance at 15:59:59. The tick data reproduce the chain exactly at the same instant; the
gate tripped on a one-minute timestamp difference, not a data defect.

Change: the reconciliation gate compares the tick cross at 15:59:00 with the 15:59:00 chain touch.
The paired F1 comparison is unchanged (resting order against crossing at 15:59:59), as are the go
criteria, fill rules, markouts, blocks and F2. The diagnostic is kept in the findings.
