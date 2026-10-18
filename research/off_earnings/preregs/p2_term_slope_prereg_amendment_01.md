# P2 pre-registration, amendment 01: snapshot cadence

Declared 2026-10-15, after the formation chains were partly pulled and before any trade was
built or scored. No straddle return, settlement, sort or outcome had been computed. The
original file `_private/p2_term_slope_prereg.md` is unchanged and its hash stands; this
amendment is hashed separately in `outputs/research/prereg_p2_term_slope.json`.

## What prompted it

Two properties of `post-no-preference/options` were confirmed by an independent check:

1. Snapshots exist only on some sessions (roughly Monday, Wednesday and Friday for single names
   from 2020), and at least one exchange holiday (2020-01-20) carries a snapshot. The adapter's
   default `lookback_days=5` steps back silently to an earlier snapshot, which elsewhere in the
   programme made exit chains byte-identical to entry chains.
2. Each snapshot lists about three expiries (about 14 and 28 days, plus a monthly), and the
   weekly ones rotate between snapshots, so a contract bought on one snapshot is often not
   quoted on the next.

## What changes

**Formation snapshot.** For each name and month, candidate formation dates are NYSE sessions
only (`engine.stats.nyse_sessions`), starting at the last session of the month and stepping
back through earlier sessions no more than five calendar days before the month-end. Each
candidate is queried by its exact date (no adapter step-back). The formation date is the
latest candidate with a non-empty snapshot; the formation close, the days to expiry, the
earnings-exclusion window and the settlement all use that date. A name-month with no snapshot
in the window is dropped and counted. This implements the original text ("stepping back at most
five calendar days") with the date recorded explicitly rather than inferred.

**Clustering and sort key.** Because names in one month can form on different sessions (up to
two sessions apart), the quintile sort and the bootstrap cluster are the formation month, not
the exact date. All trades formed in one month move together in each draw, which is at least
as conservative as clustering on dates. 5,000 draws, seed 0, unchanged.

**Issue 2 does not bind here.** The straddle is held to expiry and settled at intrinsic on the
underlying's close, so no exit snapshot is read and no contract has to be quoted on a later
snapshot. The findings report this explicitly.

**Funnel additions.** Name-months whose formation snapshot is not the month's last session,
and name-months with no snapshot in the window, are reported.

Nothing else changes: universe, period, signal, traded expiry, exclusion, arms, primary
statistic, kill rule, matched null (permutation within formation month) and deflation stand.
