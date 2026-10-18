# Pre-registration: peer-informed selection scored on repricing, not size

Frozen before any candidate below is computed on any block. Nothing in this file may be
changed after a candidate's first outcome is viewed; a change requires a separate dated
amendment file, and both are reported. The SHA-256 of this file is recorded in
`outputs/research/prereg_section21.json`.

## Hypothesis

Earnings information released by economically linked firms earlier in the same reporting
season is not fully impounded in the options of a firm that reports later. Two observable
consequences are tested.

- **A, peer-relative pricing.** A later reporter whose priced announcement jump is large
  relative to the jumps its peers were priced for this season is overpriced.
- **B, peer realisation transfer.** When this season's earlier peers moved by less than their
  options priced, the later reporter's options are overpriced, and conversely.

The null is that no at-entry variable built from same-season peers predicts the repricing
component of the short straddle's return.

## Prior work and differentiation

Hann, Kim and Zheng (2019, *Review of Accounting Studies*) show that a first announcer's
implied-volatility change predicts its industry peers' implied-volatility changes, across
3,030 firms in 217 industries, 1996-2017, and test no trading strategy. Information
transfer in equity returns around peer announcements is older (Foster 1981; Ramnath 2002).
The differentiation here is threefold: the outcome is the repricing component of a traded,
quote-marked straddle net of measured cost; peer groups are formed from return co-movement
rather than a static industry code; and the test runs on a liquid megacap universe where
the prior is that such transfer is already priced.

The strongest counter-evidence is recent. Frankel, Godigbe and Rabier (2025, *Journal of
Accounting Research*) find that focal-peer return co-movement is significantly *lower* on
focal-firm announcement dates than on other dates, including for large surprises, industry
leaders and firms with correlated earnings, and find no evidence that announcements release
more common information than ordinary days. If that holds for the options market, B has
nothing to transfer, and peer groups formed from ordinary-day return correlation (as here) may
not identify the firms whose announcements are informative for each other. Hann, Kim and Zheng
also document that the market does react to peers, and reaction is not under-reaction. A null
result is therefore the expected outcome, and is reported as such.

## What was dropped, and why

The section 2.1 draft listed an implied-over-own-history richness candidate. It is not
tested. Its tested form, `jump_richness`, was significantly negative out of sample (per-trade
Sharpe -0.1843, CI [-0.3255, -0.0326], N=157, `reverse_alpha/frozen_validation.csv`). Variants
built at entry only (`clean_iv/richness_construction.csv`) either rank almost identically
(corrected numerator: Spearman 0.990 / 0.970) or move toward `term_rank` under shrinkage
(Spearman 0.518 / 0.502). The pre-announcement run-up slope is not tested here because its
inputs are not on disk.

## Universe and blocks

| Block | Role | Traded events | Peer pool |
|---|---|---|---|
| 2019-2024 megacap | discovery | `reverse_alpha/panel.parquet`, block `discovery_2019_2024` | the same 50-name megacap universe |
| 2013-2018 megacap | validation | `reverse_alpha/panel.parquet`, block `holdout_2013_2018` | the same 50-name megacap universe |
| 2025-2026 broad, megacap subset | confirmation, primary | `oos_2026_ledger.csv` rows whose ticker is in the megacap universe | the same 50-name megacap universe |
| 2025-2026 broad, all names | confirmation, secondary | `oos_2026_ledger.csv` | all 346 names |

The peer pool is held at the megacap universe in every primary block so that peer density
is not itself a difference between blocks. Neither candidate has been computed on any block.
The 2013-2018 block has been used for other selectors, never for a peer-based one. The
2025-2026 block's outcomes were viewed once, for the term gate; its spreads and entry prices
were read for the calendar cost study, which computes no return.

## Frozen specification

### Season and peer eligibility

- **Season.** Announcements are assigned to windows 10 January to 9 April, 10 April to 9 July,
  10 July to 9 October, 10 October to 9 January.
- **Eligible peer of event i.** A name in i's cluster for that season, other than i, with an
  announcement in the same season whose exit session is on or before i's entry session, so
  its realised move is fully known at i's 15:59 entry.
- Events with no eligible peer have no candidate value and are excluded from that
  candidate's sorts. The count is printed as a funnel, never silently dropped.

### Peer clusters (k-means++)

Refit once per season, using only data strictly before the season's first day.

1. Daily log returns for every universe name over the 252 trading days ending the last
   session before the season starts. A name with fewer than 200 valid returns in the window
   is left out of that season's clustering and has no peers.
2. Market-residualise each name: OLS on the leave-one-out equal-weighted mean return of the
   other universe names over the same window. Without this step the clusters sort on beta,
   not on economic linkage.
3. Standardise each residual series to zero mean, unit variance. Squared Euclidean distance
   between standardised series is then 2T(1 - rho), so k-means on them clusters on residual
   correlation.
4. `sklearn.cluster.KMeans(n_clusters=k, init="k-means++", n_init=50, random_state=0)`, with
   `k = round(N_names / 6)`: k=8 for the 50-name pool and k=58 for 346 names. The rule is fixed
   now and not tuned.

Returns: CRSP daily (`dsf`, adjusted through `cfacpr`) via the R2 mirror wherever it covers the
window, yfinance auto-adjusted closes otherwise. A window spanning both is spliced at the last
CRSP date, and a run aborts if the two sources' daily returns disagree by more than 1 basis
point on the median of overlapping days.

**Comparator, reported and counted as a trial.** Candidate B is also built with peers defined
by the two-digit CRSP SIC code (`siccd`) as of the season's first day, carried forward from the
last available record where the mirror ends.

### Priced announcement jump

For every event, at entry, with both expiries containing the announcement:

    E = max(f^2 - b^2, 0) * t_f * t_b / (t_b - t_f),    J = sqrt(E)

where f and b are the front and back ATM implied volatilities, `t_f` is the front tenor, and
`t_b` is the back tenor. `t_b` is the actual back expiry's tenor where the chain records it,
otherwise `t_f + 21/365`.

### Candidates

- **A.** `log(J_i / median(J_p over eligible peers p))`. Sell when high.
- **B.** `-median(realised_move_p / implied_move_p over eligible peers p)`. Sell when high, i.e.
  when this season's earlier peers moved by less than they were priced for.

### Outcome variables

**Primary: moneyness-adjusted residual value.** Per event,

    R_adj = -(exit_mark - BS_straddle(S_exit, K, t_exit, sigma = back_atm_iv_entry, r = 0)) * contracts * 100 / margin

where `exit_mark` is the quote mark of the sold straddle at the exit close. This is the part
of the residual value not explained by where the stock finished, measured against the
market's own diffusive volatility at entry. On the discovery block, before this file was
written and with no candidate computed, its Spearman correlation with realised over implied
move is -0.302, against +0.814 for the unadjusted residual value. The remaining dependence
comes from the exit smile and is controlled below.

**Secondary: net return on premium**, the event-premium channel in a unit that selling a
larger option does not raise mechanically. Net return on margin is reported for comparison
with the settled verdict.

### Thresholds and inference

- **Trade rule for validation and confirmation.** Sell when the candidate is at or above the
  causal expanding 0.80 quantile of strictly earlier events' candidate values, with a minimum
  of 25 prior values (`MIN_HIST`, as for the term gate).
- **Null.** A participation-matched random draw from the same block's eligible events,
  seed 0.
- **Intervals.** Date-clustered percentile bootstrap, 5,000 draws, seed 0.
- **Sharpe.** Per-trade; any annualisation by the square root of the block's own trades per
  year, stated.
- **Cost.** The measured 15:59 basis (entry 1.2714%, exit 3.0182% per side) as primary; the
  11.6%-of-premium round trip as a second arm. Both reported.

## Success criteria

A candidate passes discovery (2019-2024) only if **all three** hold.

1. **Ordering.** Across disjoint deciles of the candidate, Spearman(decile, mean `R_adj`) is
   at least +0.60, **and** the top-minus-bottom-quintile difference in mean `R_adj` has a
   clustered CI excluding zero.
2. **Right driver.** That top-minus-bottom difference keeps a clustered CI excluding zero in a
   regression of `R_adj` on a top/bottom indicator plus `|log(S_exit/K)|`. Premium collected
   also carries less than half of the top-minus-bottom gap in net return on margin.
3. **Causal agreement.** The causal q=0.80 book's mean `R_adj` has the same sign as, and is at
   least half of, the full-sample q=0.80 book's.

**Validation** (2013-2018), only for a candidate that passed discovery: the causal q=0.80
book's per-trade Sharpe of net return on margin, minus the matched null's, has a clustered CI
on the difference excluding zero, and the book's mean `R_adj` is positive.

**Confirmation** (2025-2026 megacap subset, primary), only for a candidate that passed
validation: the same test, run once.

## Kill rules

- A candidate failing any discovery criterion stops. It is not validated, re-thresholded or
  re-specified.
- A candidate failing validation stops. The confirmation block is not opened for it.
- The SIC comparator cannot rescue B. If the comparator passes where k-means fails, that is
  reported as a finding about the peer definition, and B is still recorded as failed.

## Trial accounting

Three trials: A, B with k-means peers, B with SIC peers. The ledger base is 1,486
(`reverse_alpha/findings.md`, section 6). The state of record quotes 1,476 for the
term-structure search alone; the difference is the reverse-alpha search. DSR is reported
against 1,489. No threshold, window, k or reference volatility will be varied after an
outcome is viewed.

## References

Foster, G. (1981). Intra-industry Information Transfers Associated with Earnings Releases.
*Journal of Accounting and Economics* 3(3), 201-232.

Frankel, R., Godigbe, B. G. and Rabier, M. (2025). Information Spillovers at Earnings
Announcements. *Journal of Accounting Research* 63(1), 319-362.

Hann, R. N., Kim, H. and Zheng, Y. (2019). Intra-industry Information Transfers: Evidence from
Changes in Implied Volatility around Earnings Announcements. *Review of Accounting Studies*
24, 927-971.

Ramnath, S. (2002). Investor and Analyst Reactions to Earnings Announcements of Related Firms:
An Empirical Analysis. *Journal of Accounting Research* 40(5), 1351-1376.

Arthur, D. and Vassilvitskii, S. (2007). k-means++: The Advantages of Careful Seeding.
*Proceedings of the 18th ACM-SIAM Symposium on Discrete Algorithms*, 1027-1035.
