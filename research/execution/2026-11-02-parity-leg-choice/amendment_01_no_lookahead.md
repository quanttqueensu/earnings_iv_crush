# Amendment 01: a leg-choice rule that uses only 15:59 information

Amends `prereg.md` (SHA-256 66ce2ae5d221...) without editing it. Record:
`outputs/research/prereg_2026-11-02-parity-leg-choice-amendment-01.json`. Scorer:
`research/execution/2026-11-02-parity-leg-choice/amend01.py`. Written after the frozen run.

## Why the frozen result is not usable

1. Look-ahead in the rule. The frozen rule chooses the two-call construction when
   `adv > 0`, and `adv` uses the 16:00 closing ask of the share while the options are sold at
   15:59. Choosing on the sign of a quantity that contains the one-minute move harvests that move:
   with a one-minute share move of order 0.1% of spot (about 0.4% of m0), `E[max(adv, 0)]` is
   positive even if the true advantage is zero. The frozen P1 (+0.29% and +0.34% of m0) is of
   that size, so it cannot be read as a lever.
2. Scorer defect against the frozen text. For 2025-26 the frozen text specifies the Yahoo close as
   in the hedged hold's amendment 01 (as traded, split-unadjusted); the scorer used the
   split-adjusted close.

The frozen verdict stands as recorded and is reported as invalid for reason 1.

## Corrected rule

Choose the two-call construction if and only if the put's quoted half-spread exceeds the call's at
15:59 (`(P_ask - P_bid) > (C_ask - C_bid)`), information available at decision time. The gain on a
chosen event is `adv` as defined in the prereg (it may be negative); on other events zero. Because
the choice no longer depends on the closing share price, the one-minute noise averages out of the
mean. 2025-26 shares use the as-traded close.

## Criterion

Unchanged in form: PARITY LEVER if the mean gain per trade (unit m0) has intervals excluding zero
above in discovery and validation and a positive 2025-26 point; BOOK PASS as frozen with `HP = H +
gain`. Dividend exclusion and attrition guard as frozen.

## Trial accounting

A new rule, counted: 1,560 + 1 = 1,561.
