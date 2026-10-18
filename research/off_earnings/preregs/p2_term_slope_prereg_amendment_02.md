# P2 pre-registration, amendment 02: corporate actions inside the holding window

Declared 2026-10-15, after the first scoring run. That run is void and is reported as such.

## What happened

The first scoring run settled every straddle on the underlying's unadjusted close on the expiry
date. When a split falls between formation and expiry, the strike in the snapshot is on the
pre-split basis and the settlement close on the post-split basis, so the computed payoff is
fictitious: GE (1-for-8 reverse split, August 2021) showed a long-straddle return of +10,130%,
and NFLX, WMT, AVGO, AMZN, GOOGL, NVDA (twice) and TSLA showed +480% to +1,281% for the same
reason. The run's summary statistics were viewed (touch long-short -0.268 per trade, CI
[-0.682, -0.009]); they are void, not a verdict, because the artefact sits in both legs and
dominates the tails.

## What changes

A name-month is excluded, and counted in the funnel, if the yfinance split record shows a split
dated after the formation date and on or before the expiry date. The exclusion depends only on
the corporate-action calendar, which is known in advance (splits are announced weeks ahead), and
not on any return. Re-basing the settlement by the split ratio was considered and rejected: it
is exact for an N-for-1 forward split but not for the non-standard deliverable a reverse split
produces.

Everything else in the pre-registration and amendment 01 stands. The scoring is rerun once with
this exclusion and that run is the result. Because the first run's numbers were seen, the
findings state that the rerun is not blind to them; the change is mechanical and was fixed
before rerunning.
