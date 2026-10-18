# SPY straddles across macro releases: not testable on the free DoltHub source

## Hypothesis, scope and success criteria

Pre-registration `research/off_earnings/preregs/spy_macro_straddle_prereg.md` (SHA-256 97169169...), amendments 01 and 02
(`research/off_earnings/preregs/spy_macro_and_runup_amendment_0{1,2}.md`, both written before any outcome). Short SPY
at-the-money straddles across CPI and payrolls releases (family A1) and long straddles across FOMC
decisions (family A2) should earn the announcement premium at the touch, beyond tenor- and
regime-matched ordinary days (Londono and Samadi, Federal Reserve IFDP 2023). Pass required both the
absolute and the paired interval above zero at 97.5%.

## Result

| Stage | Count |
|---|---|
| Business days requested, 2019-01-02 to 2024-12-31 | 1,565 |
| Non-empty SPY snapshots | 752 (717 on NYSE sessions) |
| Consecutive snapshot pairs at most 3 sessions apart | 707 |
| No expiry present in both snapshots | 168 |
| Expiry shared but the entry strike absent at exit | 460 |
| Priced trades | 79 (6 of them on release days) |

A1 has 5 priced events and A2 has 1, with no matched controls meeting the pre-registered minimum. The
test returns no inference: **inconclusive, data-infeasible**, not evidence for or against the
hypothesis. The two declared trials are still counted in the programme ledger.

## Why the source cannot carry this test

The DoltHub `option_chain` table is a sampled surface, not a contract history:

- snapshots exist on roughly three sessions a week from 2020 and almost none for SPY in 2019;
- each snapshot lists about three expiries (roughly 14 and 28 days after the snapshot date plus one
  monthly), and the short ones rotate between snapshots;
- each expiry carries about 20 strikes on a grid that moves with the snapshot (SPY 2022-03-14:
  375, 384, 392, 400; 2022-03-16: 370, 382, 392, 400), so a given contract rarely reappears.

Single names fare better because a monthly expiry and round strikes persist more often (69 of the
first 79 run-up windows with both snapshots priced), but SPY's moving grid defeats exact-contract
round trips.

## Consequence for earlier work

The repository's DoltHub adapter defaults to stepping back up to five calendar days when a date has
no snapshot. In `outputs/research/dolthub_sp500_events.parquet`, 152 of the first 300 events have
byte-identical entry and exit chains, so any exit-side quantity drawn from those chains equals the
entry. The tests built on that file (the entry-spread replication) failed, so no verdict changes, but
no DoltHub-derived exit mark should be reused without `lookback_days=0` and an exact-contract check.

## What would make the test possible

A daily SPY or SPX contract history: Cboe DataShop end-of-day files, OptionMetrics (section 11 of
the handbook), or the Databento OPRA `cbbo-1m` schema already used for single names, which carries
every listed contract (a capped cost estimate is needed before any pull).
