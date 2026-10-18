# Earnings-date shifts and the short earnings straddle

## Hypothesis, scope and success criteria

Firms that report later than their usual schedule tend to carry worse, more surprising news
(Johnson and So, JFQA 2018). If the implied move does not price that, delayed announcements should
realise larger moves relative to the implied move, and excluding them should raise the short book's
return. Signal: this quarter's reporting lag minus the same quarter's lag a year earlier (Compustat
`rdq` minus `datadate`), public at entry. Groups: delayed (shift of 5 days or more), on-time (within
2 days), advanced (5 days or more earlier). Blocks: the 2013-2024 megacap panel (net RoM, quote
marks, frozen cost) and the attrition-corrected 2025-2026 broad block (net RoM, 11.6% cost), neither
used for this signal before. Pre-registration `research/selection/preregs/date_shift_prereg.md`, SHA-256
ad21eef3..., frozen before any outcome. Pass required on-time minus delayed net RoM above zero
pooled (date-clustered 95% interval above zero) and in each block, delayed events realising more
relative to the implied move, and the exclusion beating 95% of random exclusions.

## Results

Per trade, net return on margin. Date-clustered 95% intervals, 5,000 draws, seed 0.

| Group means (net RoM / realised over implied) | Megacap 2013-24 | Broad 2025-26 |
|---|---|---|
| On-time | -0.69% / 0.79 | -1.20% / 0.69 |
| Delayed | -0.02% / 0.74 | -0.57% / 0.64 |
| Advanced | +1.73% / 0.62 | +0.92% / 0.58 |
| Other shifts (3 to 4 days either way) | -1.68% / 0.87 | -3.52% / 0.69 |

| Test | Result |
|---|---|
| On-time minus delayed, pooled | -0.66% [-1.92%, +0.64%] |
| Same, megacap / broad | -0.67% [-2.04%, +0.79%] / -0.63% [-2.70%, +1.46%] |
| Delayed minus on-time realised/implied | -0.056 [-0.113, -0.000] |
| Lift from excluding delayed events | -0.11% (9.6th percentile of random exclusions) |

## Verdict

**FAIL, with the sign reversed.** Delayed announcements realise slightly *smaller* moves relative to
the implied move than on-time announcements, and the short book does no worse on them. The options
market prices the information in a delayed date, if anything generously.

## Secondary observation (descriptive, cannot be acted on from this test)

Advanced announcements beat on-time ones in both blocks: +2.24% of margin per trade
[+0.32%, +4.12%], with realised/implied of 0.58 to 0.62 against 0.69 to 0.79. This is a secondary
comparison among several, on 174 events, after the primary failed, so it is a hypothesis rather than
a result. Both historical blocks are now used for date-shift signals, so the only clean test left is
forward: record the shift for every new event in the paper radar and score advanced events once a
pre-declared count (about 150) has accrued.

## Reproduction

```
python scripts/research_date_shift.py
```
