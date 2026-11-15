# Pre-event signals for earnings tail moves: findings (draft, verdict unsigned)

## Hypothesis, scope and success criteria

Information outside the option surface, known before entry, raises the probability that the
earnings reaction exceeds twice the implied move, so that skipping flagged events raises the
next-day buy-back book's mean return. Seven trials (1,616 to 1,622), frozen in `prereg.md`
(SHA-256 `655bdda6fda497dd5fd719ae73551b8b853ac671e1985c7e4373acba9a5bd633`, recorded
2026-11-12T15:34:19Z before any outcome). Pass at discovery needs the tail lift `L` (treated over
untreated tail rate) with a 95% date-clustered interval wholly above 1 and the money gap `G`
(mean `B` treated minus untreated, fraction of margin, next-day buy-back at the touch, net) wholly
below 0.

## Funnel

| Stage | Events |
|---|---|
| Hedged-event-hold panel, status ok (2013-24 main, 2025-26 confirm) | 7,753 + 1,597 = 9,350 |
| Finite ratio | 9,350 |
| With permno | 82.9%; the 2025-26 confirm file carries none |
| With a characteristics row (latest month-end before entry, at most 62 days old) | 6,120 |

Blocks: discovery 2015-19 (2,243 events, tail rate 5.2%), validation 2020-24 (4,676, 4.6%),
confirmation 2025-26 (1,597, 3.0%). Trials T1 to T5 and T7 cannot be scored on 2025-26 because
the confirm file has no permno; this did not bind, as no trial reached confirmation.

Attrition is outcome-dependent: 2015-24 events without a characteristics row have a 1.3% tail
rate (N=799) against 5.2% for matched events (N=6,120); mean `B` is -3.29% without and -3.06% with
(fraction of margin, touch basis). The scored set therefore differs from the panel in tail rate;
the direction of any bias this causes in `L` is not established. Source:
`outputs/research/2026-11-12-tail-event-signals/corrections.json`.

## Results

Per trade. Tail rates treated/untreated; `L` and `G` with 95% date-clustered intervals (5,000
draws, seed 0); null is the percentile of the kept book's mean `B` among 5,000 random skips of
the same count (higher is better for the gate); premium is mean `mid0/m0` treated/untreated.

| Trial | Block | Defined | Treated | Tail rate | L | G | Null pct | Premium | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| T1 peer shock | discovery | 1,887 | 68 | 1.5% / 5.9% | 0.25 [0.00, 0.88] | +0.050 [+0.027, +0.071] | 0.0 | 0.224 / 0.201 | fail, wrong sign |
| T1 | validation (reported) | 4,005 | 324 | 5.6% / 4.8% | 1.17 [0.64, 1.79] | +0.003 [-0.011, +0.017] | 34.7 | 0.221 / 0.221 | |
| T2 O-score top quintile | discovery | 1,799 | 16 | 0.0% / 5.8% | 0.00 | +0.001 [-0.060, +0.057] | 51.5 | 0.250 / 0.206 | fail |
| T2 | validation (reported) | 3,864 | 21 | 19.0% / 5.0% | 3.83 [0.87, 7.69] | -0.063 [-0.215, +0.063] | 98.1 | 0.255 / 0.222 | |
| T3 Z-score bottom quintile | discovery | 1,806 | 145 | 4.1% / 5.9% | 0.70 [0.21, 1.36] | +0.022 [+0.007, +0.036] | 2.2 | 0.171 / 0.209 | fail, wrong sign |
| T4 far below 52-week high | discovery | 1,956 | 33 | 6.1% / 5.7% | 1.06 [0.00, 2.73] | -0.049 [-0.129, +0.022] | 97.6 | 0.313 / 0.201 | fail |
| T5 earnings variability | discovery | 1,882 | 287 | 7.0% / 5.6% | 1.25 [0.75, 1.91] | -0.001 [-0.016, +0.013] | 57.5 | 0.204 / 0.202 | fail |
| T6 own tail history | discovery | 1,967 | 517 | 5.2% / 5.2% | 1.00 [0.61, 1.48] | +0.020 [+0.007, +0.033] | 0.0 | 0.212 / 0.196 | fail, wrong sign on G |
| T6 | validation (reported) | 4,485 | 1,259 | 6.4% / 4.0% | 1.62 [1.22, 2.15] | +0.010 [+0.001, +0.018] | 0.9 | 0.226 / 0.218 | |
| T6 | confirmation (reported) | 1,368 | 383 | 4.7% / 2.2% | 2.10 [1.05, 4.07] | +0.024 [+0.007, +0.042] | 0.1 | 0.259 / 0.244 | |
| T7 two or more flags | discovery | 1,471 | 142 | 4.2% / 6.0% | 0.70 [0.23, 1.31] | +0.021 [-0.001, +0.042] | 2.4 | 0.210 / 0.203 | fail |

No trial passes discovery. Validation and confirmation rows for failed trials are reported for
information only and cannot rescue them.

## Reading

**Confirmatory result: no pre-registered signal is a tail gate.** All seven trials fail discovery
(2015-19). That is the only conclusion this study supports.

## Exploratory, from failed trials, not evidence

The scorer printed validation and confirmation rows for trials that had already failed discovery.
The prereg says those rows cannot rescue a trial; they are recorded here only so they are not
rediscovered as new ideas, and any hypothesis drawn from them must cite this file and be tested on
data clean for it.

- T1, peer shock: 1 tail among 68 treated events in discovery against 108 among 1,819 untreated
  (Fisher exact two-sided p 0.18), so the low treated tail rate is not distinguishable from
  chance, and the bootstrap interval for `L` ([0.00, 0.88]) is an artefact of resampling one
  event. Validation does not repeat it (`L` 1.17 [0.64, 1.79], premium 0.221 against 0.221).
  Earlier wording that peer shocks are over-priced is withdrawn.
- T6, own tail history: `L` 1.00 at discovery; validation and confirmation show `L` above 1 and a
  positive money gap, with premium 0.226 against 0.218 of margin. A difference that small cannot
  carry the earlier claim that the options over-charge for tail-prone names; that claim is
  withdrawn. The 2020-26 own-history numbers are now viewed and are not clean for any
  own-history hypothesis.
- T2, O-score: 4 tails among 21 treated in validation (Fisher p 0.019, unadjusted for seven
  trials, from a trial that failed discovery with 16 treated). Underpowered in every block.

## Process failures in this study

- No power check before freezing: T2 (16 treated) and T4 (33) could not pass at any plausible
  effect; T1 to T5 and T7 could never reach confirmation, because the 2025-26 file carries no
  permno.
- The scorer computed later blocks for failed trials (see above).
- T1 intervals cluster by date only; peer shocks correlate by industry and week, so those
  intervals are too narrow.
- Implementation details not in the prereg: a minimum of 5 treated and 5 untreated to score;
  peer industry codes from the peer's own characteristics month (earliest available before
  2015); "defined" uses the full-sample peer universe.
- The scorer was edited once after freezing (a date-type fix after a crash that printed no
  outcome). Scorer code is not hashed, so this cannot be verified from the record alone.

## Limits

The panel covers 345 names, mostly large; distressed and recently spun-off names such as CTVA
are under-represented, which is where issuer credit should matter most. Industry peers are
limited to panel names. Characteristics come from a monthly research panel, not issuer CDS or
bond spreads, which were not available.

## Trial accounting

Trials 1,616 to 1,622 used. Next free: 1,623. Row in `docs/RESEARCH_STATE.md` not yet added.
