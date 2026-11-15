# Freeze: megacap replication of the M4 demeaned-richness rule (trial 2,081)

Written 2026-11-13T17:50Z. No selector outcome on the megacap events has been computed.

## Block status

`research/ledger/blocks.csv` has no megacap row. The universe is not unread for this kind of
question, though. The hedged-hold megacap amendment (2026-11-02) read the unconditional book (H
and B levels, 2013-18 and 2019-24). The reverse-alpha panel, which is the same 1,794 megacap events,
was used for the term gate, the `jump_richness` latent variable and the causal megacap spread
gate. In checking the file layout for this freeze, this lane also saw the unconditional book
levels printed in `megacap.log`. No selector contrast on these events has been seen in this lane.
Status: viewed for neighbouring feature families and unledgered, so any read is exploratory.

## Rule (unchanged from trial 1,897)

The rule is `hyper_m3.json`, the M4 log-space empirical-Bayes jump model with
`round4.recalibrate` (causal Mincer-Zarnowitz, 5-year half-life). The model-fair straddle comes
from `selector.richness`. R_ratio is the mid over the model value, minus 1. R_dm subtracts the
trailing 91-day median of R_ratio. Treated means the top tercile of R_dm, with breakpoints from
strictly earlier dates (min 200). The outcome is yb = B m0 / mid0, the within-cell
treated-minus-control difference, with cells formed from implied-move tercile x tenor.

Changes are confined to the megacap data source, and they are applied mechanically:

- The front straddle and the two-expiry split come from the megacap 15:59 consolidated-BBO
  strips, through the same package functions (`atm_quote`, `split_jump_variance`, 7-day gap).
  These reconcile to the hold table: strike and mid match on 1,183 of 1,183 ok events.
- The model runs over the union of broad and megacap histories.
- The demeaning median, the implied-move terciles and the R_dm breakpoints use the union of
  broad and megacap events, strictly earlier dates only.
- The stale-entry-spot landmine does not apply. The hold table prices from the strips at the
  entry date, and realised moves come from CRSP returns.

Pass rule: date-clustered 95% interval of the yb contrast above zero, and cell-matched
random-null percentile at least 95, as in 1,897.

## Funnel (signal side, no outcome)

| Step | Events |
|---|---|
| Megacap events | 1,794 |
| Hold status ok | 1,183 (398 no exit leg, 162 no hedge vol, 51 no permno) |
| Model forecast | 1,142 |
| Valid split | 1,135 |
| Binned (implied-move tercile assigned) | 1,104 |
| Treated / control | 324 / 780 |

Signal-side attrition check: the top-tercile share is 0.293 among ok events and 0.282 among the
524 non-ok events with a signal. Dropping non-ok events barely changes who is selected. Their
outcomes are unknown, though: the 398 no-exit-leg events are the kind round 1 found to lose.

## Power gate (decided before any read)

The minimum detectable effect is at 80% power, 5% two-sided, per unit premium. The SD comes only
from data already viewed (broad blocks):

| Basis | SE | MDE | Power at +0.101 (1,897) | Power at +0.056 (discovery) |
|---|---|---|---|---|
| 1,897 cluster-bootstrap SE scaled to 324/780 | 0.050 | 0.141 | 0.51 | 0.20 |
| 1,892 cluster-bootstrap SE scaled to 324/780 | 0.048 | 0.135 | 0.55 | 0.21 |
| `protocol.min_detectable_effect`, broad within-cell SD 0.581, design effect 1.015 | | 0.108 | | |

The MDE is 0.11 to 0.14. The effect to be replicated is +0.101 from 1,897, which is the
significant estimate and so likely inflated, against +0.056 in discovery. At about 50% power for
the held-out size and about 20% for the discovery size, a null read would say nothing, and a
pass would be weak evidence. The outcome is therefore not read. Trial 2,081 is logged as not
scored, underpowered.

## Fingerprints (SHA-256, first 16 hex)

The rule code matches the 1,897 freeze: lib.py BCCF1832E52D65C9, selector.py 7FA3519A31CA67B4,
round3.py B933CFEF3A1C3D5E, round4.py AEB4CA9C6BED48AA, build.py F477FF6F7B107FA8. The rest:
hyper_m3.json 6093477BBEBAD337, megacap_signal.py 66EF5863FDC25D26,
megacap_signal_union.parquet 7A148F2E1B0B7F2C.
