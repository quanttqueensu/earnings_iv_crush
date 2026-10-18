# Reverse-engineering the term gate: the profitable region is a jump-risk premium, not an inefficiency

Outcome B. The q=0.80 term-spread gate was reverse-engineered to a single continuous
economic variable, that variable was scored on the same yardstick as the gate, frozen, and
applied to the untouched 2013-2018 block. It is **significantly negative out of sample**
(per-trade Sharpe -0.1843, date-clustered CI [-0.3255, -0.0326], N=157, on real quoted
fills). Nothing survives.

Harness check first: thresholding the stored `term_rank` column reproduces the settled book
exactly, N=198 / +0.117321 on 2019-2024, N=193 / -0.005337 on 2013-2018, pooled N=391 /
+0.055992. Every number below sits on that verified path.

## 1. What exactly is profitable, and how broad is the region

The response surface over the term percentile is monotone across its entire length,
Spearman(threshold, Sharpe) = +0.9684, rising from -0.0426 at q=0.00 to +0.1724 at q=0.95.
Read alone that looks like the encouraging case, a smooth gradient in an economically
meaningful parameter.

It is not. A threshold sweep computes cumulative means of the tail above each cut, so it
comes out monotone whenever a single extreme bin carries the book. The disjoint decile sort
separates the two readings:

| term_rank decile | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| mean RoM | -0.0006 | -0.0151 | +0.0049 | -0.0117 | -0.0112 | -0.0130 | -0.0304 | -0.0008 | +0.0008 | **+0.0278** |

Deciles 0 to 8 average -0.0086 and show no ordering. The entire book is decile 9. The
monotone sweep is cumulative-mean arithmetic, not a gradient, and the profitable region is
one tail rather than a plateau. Adjacent cells overlap 0.62 to 0.95 by Jaccard, so the
twenty cells are nested restatements of one selection, not twenty corroborating tests.

## 2. What the gate selects

Standardised mean differences at the frozen cut, largest first: `iv_term_spread` +2.24,
`event_share` +1.99, `front_atm_iv` +1.83, `implied_jump` +1.47, `t_entry` -1.23,
`bkm_kurt` -0.90. The gate buys steep front-vs-back structure, high front-month volatility,
short tenor, and a large priced announcement jump. Every at-entry observable moves
monotonically with the threshold, which is expected given the gate is a percentile of one
of them, and is why the descriptive step cannot on its own name the operative variable.

## 3. The latent variable, and why it looked like the answer

Six economically motivated candidates were built and scored identically. One stood out:

    jump_richness = sqrt(max(front_iv^2 - back_iv^2, 0) * t_entry) / mean |event move| at
                    this name's own strictly prior announcements

the announcement jump the term structure prices, divided by what the name actually
delivers. On the discovery block its disjoint deciles order at Spearman +0.8909 against the
gate's +0.2606, and a size-matched top-quintile book scores +0.1555 against the gate's
+0.0920.

The decomposition of the ratio is what made it credible. On the common subsample (n=707):

| variable | decile Spearman | top-20% Sharpe |
|---|---|---|
| `jump_richness` (ratio) | +0.8909 | +0.1555 |
| `implied_jump` (numerator alone) | +0.0545 | +0.0210 |
| `name_move_hist` (denominator alone) | -0.6364 | -0.1055 |

Neither part carries the result; only the ratio does, and `rho(jump_richness, term_rank)`
is 0.43, so it is not the gate relabelled. The opposite tail behaves oppositely: bottom
quintile -0.0233 (Sharpe -0.2006, CI [-0.3329, -0.0464], excluding zero), top quintile
+0.0189, and a long-short book scores +0.1778 with CI [+0.0580, +0.3137].

**All of that is an artefact of a look-ahead threshold**, established in section 6.

## 4. Where the money actually comes from

Return on margin decomposed into premium collected, the intrinsic value the realised move
punches through the strike, and the value left in the contract at exit:

| book | premium collected | gap cost | residual value at exit | costs | net |
|---|---|---|---|---|---|
| all events | +0.2086 | -0.1635 | -0.0401 | -0.0104 | -0.0054 |
| `jump_richness` top 20% | +0.2344 | -0.1562 | -0.0484 | -0.0109 | +0.0189 |
| `jump_richness` bottom 20% | +0.1959 | -0.1688 | -0.0402 | -0.0102 | -0.0233 |
| frozen term gate q=0.80 | +0.2497 | -0.1884 | -0.0324 | -0.0117 | +0.0171 |

The top-minus-bottom gap of +0.0422 splits as **+0.0385 from premium collected**, +0.0126
from a smaller gap cost, and **-0.0082 from residual value at exit**. Ninety-one per cent of
the edge is selling a bigger option. The residual-value term, which is where genuine
volatility overpricing would appear, moves the wrong way.

This answers the question the mandate poses. The selection is not predicting the crush and
is not finding cheaper contracts to trade. It is **bearing more announcement jump risk and
being paid for it**, with the realised move giving back most of the extra premium. That is a
risk premium with a fat left tail, not a mispricing, and it is the same finding the driver
attribution reached from the other direction.

## 5. Confounds and concentration

Ten neutralisations of `jump_richness` all leave a positive Sharpe individually, ranging
+0.1010 to +0.1966, including within-name and within-year demeaning. Controlling jointly for
all seven mechanical variables collapses it to **+0.0015**. That joint control regresses the
ratio on its own constituents so it is arguably over-control, but the honest reading is that
the ratio adds nothing linear beyond its components and its value rests entirely on the
non-linearity of the division.

Concentration is severe. On 29 names and 113 dates, the **top five names contribute 89.0%**
of total return and the top ten trades contribute 56.9%. Leave-one-out keeps all 29 names,
all 6 years and all 20 quarters positive, so no single unit is load-bearing, but a book
whose return is nine tenths five names is not a diversified effect.

Execution is not the problem and never was. The selected population's quoted entry width is
0.0393 of mid against 0.0385 unconditionally, a 2.3% difference, so the signal does not
select into cheap contracts. Taking both quoted sides on the contract actually traded costs
about 0.018 of per-trade Sharpe on the selected book.

## 6. Discovery versus validation, and the defect that killed it

The section-3 result used the **full-sample** 80th percentile of `jump_richness` as the
threshold. That is look-ahead: the cut is not knowable at the time of the trade. Rebuilt as
an expanding percentile against strictly prior events, the same construction the term gate
uses, on the same discovery block:

| threshold | N | executable Sharpe | CI |
|---|---|---|---|
| causal q=0.70 | 171 | +0.0804 | [-0.0627, +0.2739] |
| causal q=0.80 | 102 | +0.0912 | [-0.0886, +0.3681] |
| causal q=0.90 | 48 | **-0.0403** | [-0.2747, +0.3497] |

The improvement over the gate disappears, and the tail inverts: the most extreme cut is
negative. The look-ahead was worth roughly 0.05 of per-trade Sharpe and the entire apparent
gain over the term gate.

Frozen at q=0.80 and applied to the untouched 2013-2018 block:

| block | signal | N | mean RoM | Sharpe | hit | CI | DSR |
|---|---|---|---|---|---|---|---|
| 2019-2024 | term gate | 198 | +0.0187 | +0.1295 | 0.692 | [-0.0214, +0.3479] | 0.0002 |
| 2019-2024 | `rich_rank` | 102 | +0.0116 | +0.0912 | 0.657 | [-0.0919, +0.3681] | 0.0013 |
| 2013-2018 | term gate | 193 | -0.0027 | -0.0184 | 0.601 | [-0.1500, +0.1386] | 0.0000 |
| 2013-2018 | `rich_rank` | 157 | -0.0169 | **-0.1843** | 0.529 | **[-0.3255, -0.0326]** | 0.0000 |

All on real quoted fills, selling the bid and buying the ask. Pooled executable: term gate
+0.0553 over N=391, `rich_rank` **-0.0525** over N=259.

The reverse-engineered variable is worse than the gate it was built to explain on causal
discovery, and significantly negative on the holdout. DSR against 1,486 trials is 0.0013 at
best.

## 7. Verdict

The attractive parameter region is an artefact, and the mechanism is now named. The q=0.80
term gate concentrates the book into the top decile of a variable that selects large priced
announcement jumps on short-tenor, high-volatility contracts. Ninety-one per cent of what it
earns is simply a larger premium, most of which the realised move takes back. It is
compensation for bearing announcement jump risk, which is why it does not survive a regime
where that compensation was priced differently, and why no reweighting of the same
information rescues it.

Three specific things would have to be false for that reading to be wrong, and none is:
the disjoint deciles would have to be ordered rather than flat below the top; the residual
value at exit would have to carry the top-minus-bottom gap rather than premium collected;
and the causal threshold would have to score like the look-ahead one.

## 8. What would falsify this

A signal whose top-minus-bottom gap is carried by the residual-value term rather than by
premium collected, that orders across disjoint bins rather than only in one tail, and whose
causal and full-sample thresholds agree. That is a well-defined target and this variable
misses all three.

## 9. Prior literature

Closest known mechanism, and it is known rather than new. The premium for bearing scheduled
announcement risk is documented as a compensated exposure rather than an anomaly: Dubinsky
and Johannes (2006) on extracting the announcement jump from the term structure, Barth and
So (2014) on non-diversifiable announcement risk being priced, and Goyal and Saretto (2009)
on the implied-minus-realised sort, which is the cross-sectional cousin of `jump_richness`
and which they show is concentrated in illiquid, expensive-to-trade names. The finding here
is consistent with all three: an implied-to-realised richness sort that pays gross, is
carried by premium rather than by repricing, and does not survive out of sample on liquid
megacaps.

## 10. Artifacts

| File | Role |
|---|---|
| `panel.parquet` | 1,794 marked, ungated events with the gate stored as a continuous rank |
| `quotes.parquet` | real two-sided quotes on the contract each event trades |
| `response_surface.csv` | 120 cells of the term x move grid |
| `response_surface_deciles.csv` | the disjoint sort that overturns the gradient reading |
| `selected_vs_unselected.csv` | standardised mean differences at three cuts |
| `selection_gradient.csv` | how each observable moves along the surface |
| `latent_candidates.csv` | six candidate variables scored identically |
| `pnl_decomposition.csv` | premium, gap, residual value, cost |
| `monotonicity.csv` | quintile and decile sorts, both tails |
| `confound_tests.csv` | ten neutralisations |
| `concentration.csv` | leave-one-out over names, years, quarters, trades |
| `execution_analysis.csv` | four cost bases including real quoted fills |
| `frozen_validation.csv` | the holdout result |
| `reverse_search_ledger.csv` | every hypothesis, including the failed ones |

## Reproduce

    python scripts/reverse_alpha_panel.py
    python scripts/reverse_alpha_quotes.py
    python scripts/reverse_alpha_p1.py
    python scripts/reverse_alpha_p2.py
    python scripts/reverse_alpha_p4.py

## References

Barth, M. E. and So, E. C. (2014). Non-Diversifiable Volatility Risk and Risk Premiums at
Earnings Announcements. *The Accounting Review*, 89(5), 1579-1607.
Dubinsky, A. and Johannes, M. (2006). Fundamental Uncertainty, Earnings Announcements and
Equity Options. *Working paper, Columbia University*.
Goyal, A. and Saretto, A. (2009). Cross-Section of Option Returns and Volatility. *Journal
of Financial Economics*, 94(2), 310-326.
