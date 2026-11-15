# Lane 5: niche, structural and cross-sectional event features

Compiled by the team lead from this folder's logs after the lane hit the usage limit. Every
number below is copied from `trials.csv`, `diag1.log` or `heldout.log`; nothing was recomputed.

## Verdict

Nothing survived the held-out read. Twenty-one trials were scored (1,749 to 1,771). One
candidate, early reporting within the industry, was frozen and read once on 2019-24; it failed
(t 1.50, null percentile 94.0).

## Split and basis

Discovery 2013-18; held-out 2019-24 on the hedged event hold, read once after
`freeze_early_in_industry.md` (sha256 prefix 00534f5e46f740f7). Effect y is residual value per
unit of premium, treated minus untreated within implied-move tercile by tenor cells, per trade,
with date-clustered 95% intervals and a cell-matched random null. Real data.

## The candidate and its provenance

Round 1 stated in advance that late reporters, whose industry peers have mostly reported, are
over-priced (trial 1,749). It failed with the wrong sign: -0.057 [-0.120, +0.007], null 2.6.
`diag1.log` then showed the residual falling monotonically across peer-share quintiles (+0.056
in the earliest quintile, -0.034 in the latest), so the mirror hypothesis was formed from the
discovery data. It is therefore discovery-derived, and the held-out read is its only test.

Mechanism recorded before the read: the first reporters in an industry carry unresolved
industry-wide news, and buyers pay a premium for that common uncertainty (Savor and Wilson 2016
on early announcers).

| Trial | Block | Treated | Effect | 95% CI | t | Null pct | Verdict |
|---|---|---|---|---|---|---|---|
| 1,759 early in industry | discovery 2013-18 | 686 | +0.124 | [+0.039, +0.225] | 2.62 | 96.6 | Passed discovery screen |
| 1,761 early in industry, within name | discovery 2013-18 | 498 | +0.208 | [+0.086, +0.353] | 2.99 | 99.8 | Passed discovery screen |
| 1,770 early in industry (frozen) | held-out 2019-24 | 1,674 of 4,550 | +0.029 | [-0.009, +0.066] | 1.50 | 94.0 | Fail |
| 1,771 early in industry, within name | held-out 2019-24 | 1,585 of 4,338 | +0.010 | [-0.029, +0.049] | 0.49 | 89.2 | Fail |

On held-out the sign survived and the size shrank by about three quarters. Treated and control
were balanced on tenor (median 2 days both) and close on implied move (0.051 against 0.055), but
the treated names had tighter half-spreads (0.038 against 0.044) and larger caps (USD 38.9bn
against 31.2bn median). Some of the residual is therefore liquidity, the driver found in lane 2.
By year the early group was better in 2019, 2020, 2022 and 2024 and worse in 2021 and 2023.

## Failed hypotheses (discovery unless stated)

Late in industry (-0.057, wrong sign); three or more peers in the prior week (-0.045); crowded
reporting day top quintile (+0.007); thin reporting day bottom quintile (+0.058, t 1.67);
not fiscal Q4 (-0.031); Friday reaction (+0.014); holiday before expiry (+0.020); low share
price (-0.030); high turnover (-0.031); weekend gap (-0.021, 66 treated); no peer in the prior
week (+0.079, t 1.78, null 93.5); observable-fundamentals sectors (+0.064); sector expanding top
three (-0.033); early, sector-neutral (+0.131, t 2.21, null 90.1); early calendar position
(+0.083, t 1.92, null 80.4); on-cycle month (+0.029); quarter-end window (+0.004, 41 treated);
pre-announced 8-K with one vote per name (+0.065 [-0.001, +0.129], t 1.98, on blocks already
viewed 2015-26); small-lot print share top tercile (-0.063, 2025-26, already viewed).

## Not tested

Supplier and customer links, share-class siblings (one pair in the ledger), sector rebalance
dates.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\lane5-niche\report.md
