# Peer-informed selection scored on repricing: findings

## Hypothesis, scope and success criteria

**Hypothesis.** Earnings information released by economically linked firms earlier in the same reporting season is not fully impounded in the options of a firm that reports later. Two consequences were tested.

- **A.** A later reporter whose priced announcement jump is large relative to its peers' priced jumps this season is overpriced.
- **B.** When this season's earlier peers moved by less than their options priced, the later reporter's options are overpriced.

The null is that no at-entry variable built from same-season peers predicts the repricing component of the short straddle's return.

**Scope.** Three trials frozen in `_private/section21_peer_prereg.md` (SHA-256 `04c3a43b7bada0c9955404b337b281a58ed1c6203478e22073f3fd5a84b6b764`, verified by the scorer before it runs): A with k-means++ return-cluster peers, B with k-means++ peers, and B with two-digit CRSP SIC peers as a comparator. Discovery ran on the 2019-2024 megacap block of `reverse_alpha/panel.parquet` (839 events). Validation on 2013-2018 and confirmation on the 2025-2026 ledger were to run only for a candidate passing the preceding stage. No amendment was needed.

**Primary outcome.** The moneyness-adjusted residual value, a per-trade fraction of margin:

`R_adj = -(exit_mark - BS_straddle(S_exit, K, t_exit, back_atm_iv_entry, r = 0)) * contracts * 100 / margin`

On the discovery block its Spearman correlation with realised over implied move is -0.302 (N=839), reproducing the figure in the pre-registration.

**Discovery criteria (all three required).**
1. **Ordering.** Spearman(decile, mean `R_adj`) across disjoint deciles is at least +0.60, and the top-minus-bottom-quintile difference in mean `R_adj` has a date-clustered CI excluding zero.
2. **Right driver.** The top-minus-bottom difference keeps a clustered CI excluding zero in a regression of `R_adj` on a top indicator and `|log(S_exit/K)|`, and premium collected carries less than half of the top-minus-bottom gap in net return on margin.
3. **Causal agreement.** The causal expanding q=0.80 book's mean `R_adj` has the same sign as, and is at least half of, the full-sample q=0.80 book's.

Intervals are date-clustered percentile bootstraps on entry date, 5,000 draws, seed 0. Net return on margin uses the measured 15:59 cost basis (entry 1.2714%, exit 3.0182% of the mark per side).

## Funnel

| Trial | Discovery events | Name grouped in season | With an eligible peer | Scored |
|---|---|---|---|---|
| A, k-means | 839 | 838 | 632 | 628 |
| B, k-means | 839 | 838 | 632 | 632 |
| B, SIC-2 | 839 | 839 | 486 | 486 |

About a quarter of events report before any cluster-mate has exited in the season, so they carry no candidate value and are excluded from that trial's sorts, as pre-registered. Four A events have eligible peers whose median priced jump is zero. Clusters were refitted for 47 seasons on 47 to 50 names: k=8 every season, smallest cluster 2 names, no singletons. SIC-2 groups number 16 to 18 per season.

## Discovery results

All figures per trade on the discovery block. `R_adj` in fractions of margin; net RoM net of measured cost.

| Criterion | A, k-means | B, k-means | B, SIC-2 |
|---|---|---|---|
| Decile Spearman of mean `R_adj` (need >= +0.60) | +0.127 | -0.079 | +0.358 |
| Top-minus-bottom quintile `R_adj` (N top/bottom) | +0.00002 (126/126) | -0.0030 (127/127) | +0.0030 (97/98) |
| 95% CI | [-0.0039, +0.0040] | [-0.0074, +0.0019] | [-0.0027, +0.0089] |
| **1. Ordering** | **fail** | **fail** | **fail** |
| Top coefficient, controlling for abs(log(S_exit/K)) | +0.0017 | -0.0033 | +0.0020 |
| 95% CI | [-0.0021, +0.0058] | [-0.0077, +0.0014] | [-0.0036, +0.0079] |
| Top-minus-bottom net RoM gap | +0.0192 | +0.0050 | +0.0360 |
| Premium-collected gap | +0.0575 | -0.0018 | +0.0009 |
| Premium share of the net gap (need < 0.5) | 3.00 | -0.36 | 0.03 |
| **2. Right driver** | **fail** | **fail** | **fail** |
| Full-sample q=0.80 book mean `R_adj` (N) | +0.0056 (126) | -0.0001 (127) | +0.0049 (98) |
| Causal q=0.80 book mean `R_adj` (N) | +0.0056 (131) | +0.0007 (106) | +0.0043 (114) |
| Causal over full (need >= 0.5, same sign) | 1.00 | -6.50 | 0.88 |
| **3. Causal agreement** | pass | **fail** | pass |
| **Passes discovery** | **no** | **no** | **no** |

**Reading.** No trial orders the residual value across its deciles, and no top-minus-bottom difference in `R_adj` is distinguishable from zero, with or without the moneyness control. Candidate A's net-RoM gap is a size effect: the top quintile collected 5.75 points more premium per unit of margin than the bottom, three times the net gap, the "sell the bigger option" pattern section 2.1 was designed to filter out. Its decile profile is U-shaped; the bottom decile includes the 16 events whose term structure priced no announcement jump (`J = 0`). Candidate B has no shape with k-means peers. The SIC comparator comes closest to an ordering (decile Spearman +0.36), but its CI spans zero; under the kill rules it is a finding about the peer definition, not a rescue of B.

## Descriptive books (discovery, no inference drawn)

Per-trade Sharpe on net RoM at the measured basis, date-clustered CI; annualised figures use each book's own cadence (trades per year in brackets); DSR against 1,489 trials.

| Book | N | Mean `R_adj` [CI] | Mean net RoM [CI] | Sharpe [CI] | Annualised | DSR |
|---|---|---|---|---|---|---|
| A causal q=0.80 | 131 | +0.0056 [+0.0026, +0.0087] | +0.0077 [-0.0141, +0.0279] | +0.060 [-0.098, +0.255] | +0.29 (24.2/yr) | 0.0000 |
| B k-means causal q=0.80 | 106 | +0.0007 [-0.0024, +0.0038] | -0.0025 [-0.0291, +0.0187] | -0.019 [-0.162, +0.239] | -0.08 (19.2/yr) | 0.0000 |
| B SIC-2 causal q=0.80 | 114 | +0.0043 [+0.0002, +0.0086] | +0.0123 [-0.0173, +0.0367] | +0.085 [-0.087, +0.403] | +0.39 (21.5/yr) | 0.0010 |
| All A-eligible events | 628 | +0.0025 [+0.0007, +0.0042] | -0.0043 [-0.0144, +0.0053] | -0.036 [-0.109, +0.049] | -0.37 (107/yr) | 0.0000 |

Mean `R_adj` is slightly positive across all eligible events, so a positive book mean is the base rate, not a selection effect. On the 11.6%-of-premium cost arm every book's net RoM is negative. No net-RoM Sharpe CI excludes zero.

## Verdict per trial

| Trial | Stages run | Verdict |
|---|---|---|
| A, peer-relative jump, k-means | discovery | failed discovery (criteria 1 and 2) |
| B, peer realisation, k-means | discovery | failed discovery (criteria 1, 2 and 3) |
| B, peer realisation, SIC-2 comparator | discovery | failed discovery (criteria 1 and 2) |

Validation (2013-2018) and confirmation (2025-2026) were not opened. Candidate values were built on 2013-2018 only to count the funnel; no outcome on that block was computed or viewed. The null agrees with Frankel, Godigbe and Rabier (2025), who find no excess common information on announcement dates, and with the prior that on a liquid megacap universe peer transfer is already priced. It does not contradict Hann, Kim and Zheng (2019), who test no traded, cost-net outcome.

## Trial accounting

Three trials added to the base of 1,486, giving 1,489, the count the DSR above uses. The programme ledger has since grown to about 1,505; at that count every DSR is equal or marginally lower.

## Implementation choices fixed before any outcome was computed

- `K` is `strike_mkt`, the strike at which the panel's entry and exit marks were taken; `exit_mark` is `exit_mkt`.
- The back expiry is not recorded on the panel, so `t_b = t_f + 21/365`, the pre-registered fallback.
- Peer events are the panel's own events, both blocks pooled, eligibility set by date.
- A missing return day in a clustering window is set to the residual series' mean (zero after standardisation); `k = round(N/6)` on the names clustered, giving k=8 every season.
- An event with `J = 0` takes negative infinity for A; an event whose eligible peers have median `J = 0` has no A value.
- Returns are CRSP `dsf` prices divided by `cfacpr`; no clustering window needed the yfinance splice.

## Reproduction

```
python scripts/research_section21_peer.py
```
