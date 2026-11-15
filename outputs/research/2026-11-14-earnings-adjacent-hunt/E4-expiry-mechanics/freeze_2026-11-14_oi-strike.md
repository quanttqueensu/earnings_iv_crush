# Freeze: trial 2,773, open-interest-proxy strike choice on the megacap hedged hold

Frozen exactly as declared in `diagnosis.log` entry 2, before the held-out block is read. No
parameter, feature or candidate set was changed after discovery; one configuration was scored
(search count 1).

## Rule

Megacap hedged hold (amendment 02 builder, unchanged), events with Alpaca daily option bars on the
front expiry before the entry date. Feature: V_k, cumulative Alpaca volume (calls plus puts) at
strike k on the front expiry over sessions strictly before the entry date. Candidates K-1, K0,
K+1, each two-sided at 15:59 in the entry strip and buildable. Sell at the candidate with the
largest V_k, K0 unless a neighbour is strictly larger. Event-night delta matched with stock (entry
close to reaction close, CRSP half-spread floored at 1 bp both ways). All legs valued under
`HEDGED_NET`, net at the touch.

Outcome: switch gain over the ATM hold, in the base trade's m0, per trade, zero when K0 is kept.
Primary: mean gain over eligible events, `date_clustered_ci` (reaction-date clusters), 95%.
Pass: lower bound above zero, matched random-switch null percentile at least 95, and the gain net
of entry half-spread saved positive on switched events. Kill: the interval contains zero or lies
below it.

## Discovery reading (2014-18, already seen)

+0.057% of m0 [-0.161, +0.268], t 0.52, N 432 (274 reaction dates), 61% switched, null
percentile 45.8. On switched events the chosen strike's settlement intrinsic was larger by 0.14%
of m0 and it finished nearer the expiry close on 48% of them. The kill rule fires on discovery.
The held-out read measures the same frozen rule once; it cannot rescue the trial.

## Held-out block

2019-24 megacap panel. `block_is_clean` against `research/ledger/blocks.csv` returns clean for
panel `hedged_event_hold_megacap`, period 2019-24, outcome `hedged_hold`, feature
`open_interest_proxy` and also `contract_choice` (no row names the megacap panel). The megacap
hold's own level on 2019-24 was read by amendment 02; strike choice on it was not. Lane B's
broad-panel strike result is a known neighbouring effect.

Reconciliation at build: K0 rebuilt under `HEDGED` reproduces the stored megacap H on all 998
built events, maximum absolute gap 0.0 of m0, no strike mismatch.

## Files at freeze (sha256)

- `score_oi.py` 20f424ff3179f135adad3b497c828295783c6fdde61c0837258edbcdcebc7e88 (held-out scorer, written first)
- `build_oi.py` bd94b39a6425adfb9bebd18b341b34183be31c21610321e27141cffb62bf3993
- `oi_arms.parquet` 57ad824d21a8a97ab988546942dd2fb8bccb45d1651034b0f74c0430ab5ec8d0

Freeze time: 2026-11-14T18:49:57Z. Held-out command:
`python score_oi.py --block heldout`, run once.

SHA-256 of this note above this line: a22fa8a54c738929c5c7c7db695eef66bae36abb5b27b439b5b07a90409795eb
