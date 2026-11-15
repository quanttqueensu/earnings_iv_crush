# Freeze note: E2 informed flow, reversed delta-weighted book (trials 2,721 and 2,722)

Frozen 2026-11-14, before any held-out outcome (2025-26 stock return) was computed. The held-out
scorer `score_heldout.py` was written before this note; its hash and the hashes of every module it
imports from this folder are recorded below, and the scorer refuses to run if any has changed.

self_sha256: ea1ebbc7a04c793ca98733b263b71243f80e0fa9e18f74176bd8834590ca5479
scorer_sha256: c8dc2f792e01d24fec054160b4a1b6b407b423ee6268a99b332aa8cd8c639594
lib.py: af3d995758a826b17c4626462aab0f111ad01df14370913830db654ba7b1b46e
score_discovery.py: 8e0c577fd47cf55014c5c30e2da65e58df14a39c944e6f97c4486002a05794ab
variants.py: 5ed4ec136816402ccb18b1c3b34636b6dccc92a4690930886393cca6761e439d
build_features.py: 0f0dbf036886736b166a69fda353cdfd69d43af7f03aad958b0730ebe6df04a8

The self hash is the SHA-256 of this file with that hash replaced by 64 zeros.

## Rule

S_delta is the delta-weighted, quote-rule signed volume on the event's call and put, trades from
15:00:00 to 15:50:00 ET on the entry session, at least 10 signed contracts (diagnosis.log entries 1
and 5). Causal quintiles (breakpoints from strictly earlier entry dates, 200-event burn-in,
discovery events included in the history). Long the stock in the bottom quintile (net put buying
or call selling), short it in the top quintile, at 15:59 on the entry session; close at 15:59 on
the reaction session. Outcome from 15:59 parity forwards on one expiry for both days (entry 3,
rule (a)). Cost per side: the name's 90th-percentile CRSP closing half-spread in 2024 (else 3 bp)
plus 1 bp.

- 2,721 (primary): every held-out event.
- 2,722 (secondary): events with |K / F(15:50) - 1| <= 2%, breakpoints from every event.

Pass, per rule: date-clustered 95% interval of the mean net return per position above zero, and
the observed mean at or above the 95th percentile of the random-direction and matched nulls. A
Bonferroni reading (97.5% interval and percentiles) is reported beside it because two rules are
read.

## Status of this freeze

- Search behind it: eleven configurations scored on discovery (2,712 to 2,722, trials.csv), none
  passing. The declared primary (2,712) failed with the opposite sign at the margin; this book is
  its reversal, a new mechanism (price pressure from the hedging of put demand, reverting
  overnight) adopted after seeing discovery. 2,721's discovery figure is +0.335% per position
  [-0.180, +0.828], t 1.30, N=593, nulls 95.7 and 93.9.
- Because no rule passed discovery, a held-out pass is a lead for a forward block, not a finding.
- Block: panel flow_atm_ticks, period 2025-01-01..2026-12-31, outcome family
  stock_direction_next_session, feature family signed_atm_option_flow. block_is_clean against
  research/ledger/blocks.csv: True (0 clashes). Adjacent views: F2 sorted the 2025-26
  straddle P&L on the summed (not differenced) imbalance; the 2025-26 hedged-event-hold panel is
  marked viewed for every family; no stock direction on these events has been split by option
  flow before.
- Power: about 385 held-out positions expected (two fifths of 964 signalled events). With a 6.5%
  per-position sd the 95% interval half-width is about 0.65 points and the minimum detectable
  mean (80% power) about 0.93%. The discovery point estimate (+0.335%) would give t near 1.0, so a
  fail is the expected outcome even if the discovery effect were real.
- The held-out event list comes from oos_2026_ledger.csv, which dropped events whose exit leg had
  no bid (large moves); the held-out contracts sit lower in moneyness than discovery's (entry 5).
  Both stated before the read.
