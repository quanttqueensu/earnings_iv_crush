# Pre-registration: premium-and-spread combined gates on the forward paper book

Frozen before any outcome for the declared block is computed: the block is the transmitting paper
book's trades, and none exists when this text is frozen. Changes after an outcome is viewed require
a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-07-forward-combined-gates.json`. Scorer:
`research/selection/2026-11-07-forward-combined-gates/study.py`.

## Hypothesis

Among the events the paper book trades, those with a large premium feature and a narrow quoted
entry spread carry more residual value (the option value the market gives back by the exit, net of
the intrinsic value the move created) than the rest, by more than a random selection of the same
size. Mechanism: the spread gate alone kept events that carried no gross premium (broad 2025-26),
and premium size alone is what the term gate selected (91% of its advantage was premium
collected). Requiring both, and scoring on residual value rather than P&L, asks whether narrow-spread
names with rich premiums are mispriced rather than merely large.

Two trials:

- G1: `iv_term_spread_nearest` at or above the causal two-thirds quantile AND `entry_rel_spread` at
  or below the causal median.
- G2: `implied_move` at or above the causal median AND `entry_rel_spread` at or below the causal
  median.

## Data and blocks

Source: the IBKR paper book's transmitting stores (`outputs/live/forward_ledger_nostop.parquet`,
`forward_reconciliation.parquet`, `open_positions.parquet`), copied from the cloud host. Universe and
rule are the book's own (unconditional, 346-name broad universe, one-session hold, shakedown caps).
One block: every transmitted trade with an exit on or after 2026-11-09. Dry-run trades are excluded.
No outcome of this block has been viewed by any study; it does not exist at freezing.

Evidence condition: the book runs on delayed IB quotes (market data type 4) by owner decision. The
residual value is marked at the recorded exit mid, so execution cost is outside it, but the mid is
itself about 15 minutes stale. Reports state the market data type beside every figure.

## Specification

- Features are the values recorded on each position at entry, before the outcome exists.
- Causal thresholds: for a trade with announcement date d, each quantile is taken over the finite
  values of that feature on transmitted trades with an announcement date strictly earlier than d.
  A trade needs at least 25 such prior values for every feature in the gate (the project's
  `MIN_HIST` in `earnings_iv_crush/research/gates.py`, not chosen here); otherwise it is unscored
  and counted in the funnel.
- Quantile levels: two-thirds for the term spread (a top third, wider than the closed q=0.80 term
  gate so that the intersection keeps a usable count), median for the implied move and the spread.
  Not swept.
- Residual value per trade, as a fraction of margin, from the decomposition in
  `research/selection/reverse_alpha_lib.py` (premium + gap + residual value + cost = return on
  margin): `-(exit_mid - |spot_exit - strike|) x 100 x contracts / margin`, with `exit_mid` the
  recorded `assumed_mid_mark_ps` and margin the book's `0.20 x spot + premium` approximation.
- Every bin is reported (P5): for each gate, the four disjoint cells of premium feature (above or
  below its threshold) by spread (at or below, or above its median), with N and mean residual
  value.

## Primary statistic and inference

Primary: mean residual value per trade (fraction of margin, at the exit mid, gross of execution)
of the selected trades, against the participation-matched random null over the scored pool
(`protocol.matched_random_null`, statistic the mean, 5,000 draws, seed 0), and the
selected-minus-unselected difference in mean residual value with a date-clustered bootstrap
interval (announcement dates resampled, 5,000 draws, seed 0). Secondary: per-trade Sharpe and mean
of net return on margin for the selected trades (`protocol.date_clustered_ci`).

## Success criterion

No verdict before a gate has 150 selected scored trades. At that point a gate passes only if all
three hold: the matched-null percentile is at least 95, the lower bound of the
selected-minus-unselected interval is above zero, and the selected mean net return on margin is
above zero.

## Kill criterion

At 150 selected scored trades, a gate that misses any of the three conditions fails and is closed.
Neither gate can rescue the other. There is no early stop either way: scoring never changes what the
book trades. Expected horizon: G1 selects about one trade in six and G2 about one in four, so 150
selected trades need roughly 900 and 600 book trades, several earnings seasons at the shakedown
cap of three names a day. Interim reports are status, not evidence.

## Trial accounting

Two trials, G1 and G2. The largest count in the hash records is 1,567
(`prereg_2026-11-02-smallcap-night-day-spread.json`), so these are trials 1,568 and 1,569.
