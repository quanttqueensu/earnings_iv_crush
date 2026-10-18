# Pre-registration: the final test set for the single-name earnings vehicle

Frozen before any of the three tests below is computed. Changes after an outcome is viewed
require a dated amendment. SHA-256 recorded in `outputs/research/prereg_final_earnings_set.json`.

## Amendment to the decision rule

The rule in state-of-record section 2.0 fired on 2026-10-06 (conditional hold and megacap
spread gate both failed). On 2026-10-09 the project owner instructed that the remaining ideas be
tested. This set is therefore declared, before any result, as the **final** set for the
single-name earnings straddle: if none of T1 to T3 passes its primary criterion, the vehicle
changes as section 2.0 states, and no further earnings selector, gate, or sizing rule is opened.
Each test must name the mechanism by which it would work; a pass without its mechanism check
passing is reported as unexplained, not as a result.

## T1. Causal spread gate on the 2025-2026 broad block

**Mechanism.** The gross premium is largely compensation for liquidity provision: it is ~7 times
larger on the broad block (+3.44% of margin) than on megacaps (~+0.5%), concentrated where spreads
are wide, and liquidity takers pay the full touch (zero median price improvement in 34,672 prints).
A taker keeps the premium only where the toll is smaller than the premium. The megacap gate lifted
per-trade Sharpe by about 0.05 in both blocks with little spread dispersion to act on; broad-block
round trips span an interquartile range of 7.9% to 22.3% of premium.

**Mechanism check.** The gated book's mean expected cost is below the ungated book's, and its mean
gross return at the mid is not lower than the ungated book's by more than the cost saving.

**Specification.** Identical to test S of `cost_levers_prereg.md`: signal = current entry relative
half-spread plus the name's mean relative exit half-spread over at least 3 earlier completed events
in the block; trade at or below the causal expanding median of strictly earlier eligible events
(minimum 25). Touch-basis P&L (sell entry bid, buy exit ask) priced from the cached 15:59 chains
(`data/cache/backfill_chains`) at the ledger's strike and expiry; margin from the ledger.

**Success.** Gated per-trade Sharpe, date-clustered 95% CI excluding zero and positive, and above
the median of 1,000 participation-matched random draws.

## T2. Risk-normalised sizing

**Mechanism.** Premium collected scales with the risk borne: 91% of the term gate's top-minus-bottom
advantage was premium collected, and the realised move took most of it back. If expected return per
unit of risk is roughly constant across events, equal-notional sizing overweights the riskiest events
and equal-risk sizing is the mean-variance efficient weighting.

**Mechanism check.** The weighted book's mean return per unit of ex-ante risk is not lower than the
unweighted book's (the gain must come from diversification, not from tilting toward higher-mean
events).

**Specification.** Weight `w_i = 1 / r_i`, `r_i = m_i / (0.20 + m_i)`, `m_i` the event's implied
move; `r_i` is the risk of a straddle's return on Reg-T margin (`0.20 S + premium`) in units of spot.
Weights normalised to mean 1 within each block. Weighted per-trade return `w_i * R_i`. Blocks and
bases: megacap 2013-2018 and 2019-2024 (`reverse_alpha/panel.parquet`, measured 15:59 basis),
broad 2025-2026 (`oos_2026_ledger.csv`, `net_rom`, the settled 11.6% basis).

**Success.** The weighted book's per-trade Sharpe has a date-clustered 95% CI excluding zero and
positive in **each** of the three blocks.

## T3. Retail ownership as the selector

**Mechanism.** Retail investors buy options in a concentrated way before earnings, overpay relative
to realised volatility, and generate price impact that market makers capture (de Silva, So and Smith,
*Review of Finance* 2026); market-maker inventory risk has a first-order effect on option prices
(Muravyev, *Journal of Finance* 2016). Retail demand is larger where retail ownership is larger, so at
a given priced move, high-retail-share names should carry richer options.

**Mechanism check.** The top-minus-bottom retail-share gap in net return is **not** carried by premium
collected (premium share below one half), i.e. the selector is not selling bigger options.

**Signal.** `retail_share = 1 - min(IO, 1)`, IO the sum of 13F holdings (`tr_13f.s34`) over shares
outstanding, from the latest 13F report date at least 45 days before entry (the filing lag), matched
on 8-digit CUSIP from CRSP names valid at that date. Sell when high.

**Blocks.** Discovery 2019-2024 megacap; validation 2013-2018 megacap; confirmation 2025-2026 broad,
all names (13F runs to 2025 Q4, so 2026 entries use the 2025 Q4 report).

**Success.** Discovery: Spearman(decile, mean net return) at least +0.60, top-minus-bottom-quintile
CI excluding zero, mechanism check passes. Validation, only if discovery passes: causal q=0.80 book's
per-trade Sharpe minus the matched null's, clustered CI excluding zero. Confirmation, only if
validation passes: the same, once.

## Common

Date-clustered percentile bootstrap, 5,000 draws, seed 0. Per-trade Sharpe; no annualisation without
a stated factor. Three trials; DSR against 1,494.
