# Freeze: trial 2,772, pinning on the post-earnings expiry

Frozen exactly as declared in `diagnosis.log` entry 2, before the held-out block is read. No
parameter was changed after discovery; one configuration was scored (search count 1).

## Rule

Per hedged-hold event (broad and megacap panels, status ok), pin = 1 if the CRSP close lies within
USD 0.125 of a strike listed on the front expiry in the reaction-session chain. pin_E is the expiry
session; pin_C averages E+1, E+2 and E-1 where E-1 falls after the reaction session. Events with a
split within E-1 to E+2, a close outside the listed grid on E, or no control session drop, with a
funnel. Primary: mean(pin_E - pin_C), `date_clustered_ci`, clusters = expiry session, 95%.

Pass: lower bound above zero. Kill: the interval contains zero or lies below it.

## Discovery reading (2013-18, already seen)

+0.17 percentage points [-1.24, +1.66], t 0.23, N 3,188 events on 255 expiry sessions; pin_E
24.7%, pin_C 24.6%. The kill rule fires on discovery. The held-out read measures the same frozen
statistic on the weekly-expiry era, where the sample is larger; it cannot rescue the trial.

## Held-out block

2019-24, same panels. `block_is_clean` against `research/ledger/blocks.csv` returns clean for
panel `hedged_event_hold` and `hedged_event_hold_megacap`, period 2019-24, outcome family
`expiry_pinning`, feature family `strike_grid` (no matching row). The expiry-session closes of
these events enter the settlement leg of H, which earlier studies viewed; no study computed a
strike-distance statistic on them.

## Files at freeze (sha256)

- `score_pin.py` f6ede2897dc1774e309715a15577aecfbb1226e73efb58f9dd6e07aab0a259a4 (held-out scorer, written first)
- `build_pin.py` e416b68b5c81aae6ffd06d9805f7285b99ebf366fe94413cfad40b53c6d27bbb
- `pin_inputs.parquet` 4c358aac891b3eee2dd0a094fcd48b11582d65d21a26e2a218c44b4077c5118f

Freeze time: 2026-11-14T18:43:29Z. Held-out command:
`python score_pin.py --block heldout`, run once.

SHA-256 of this note above this line: 62c966138409d1d79ec16dc5c856937eacd7687524b37166b67a5c4c94cef672
