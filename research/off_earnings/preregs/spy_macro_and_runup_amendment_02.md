# Amendment 02 to the SPY macro straddle and vega run-up pre-registrations

Written after amendment 01 and after a coverage count (number of snapshot pairs sharing an expiry), and
before any return, P&L or price change was computed for either test.

## What was found

Each DoltHub snapshot lists about three expiries, at roughly 14 and 28 days after the snapshot date
plus one monthly, and the short expiries rotate from one snapshot to the next. The shortest expiry
at entry is therefore usually absent at exit (SPY: 700 of 707 eligible pairs failed on a missing
leg). Restricting to expiries present in both snapshots leaves 540 of 707 SPY pairs, with a median
tenor at entry of 49 calendar days (interquartile range 30 to 56).

## Change

In both tests the expiry is the shortest listed expiry, strictly after the pre-registered bound,
that appears in both the entry and the exit snapshot. The strike rule is applied within that
expiry at entry. Nothing else changes. The event's share of the straddle's variance is smaller at
these tenors, which lowers power; the tenor-matched controls (SPY) and the matched null windows
(run-up) still make the comparison like for like.
