# Post-earnings volatility overpricing: pre-registered test, both controls fail, and the test is underpowered

One pre-registered trial, charged against the recorded count of 1,476, so the deflated
Sharpe is reported against 1,477. Pre-registration and both amendments frozen and hashed
before any return, difference or matched pair was computed:

| File | SHA-256 | Bytes |
|---|---|---|
| `postea_prereg.md` | `bc22613afd90e0dc143ddc4b416761a52fc37bc3541b4b6fda97592a0645ae3d` | 10,154 |
| `postea_prereg_amendment_01.md` | `1cd2ceb493431180b4305b7999f585938062aa6abe2e8beca064cc82f31594ca` | 4,534 |
| `postea_prereg_amendment_02.md` | `b92018c65922f473c9bf5af8d8afa954b10eabc6cda4b19962c31303c44ac0b4` | 3,901 |

---

## 1. Hypothesis and estimand

Retail option buyers concentrate purchases ahead of high-expected-volatility announcements
and unwind slowly for weeks afterwards (de Silva, Smith and So, *Review of Finance* 2026),
and option traders overestimate volatility after recent announcements, increasingly so with
the size of the surprise (Chung and Louis, *Journal of Empirical Finance* 40, 2017,
220-235). If residual demand leaves ordinary post-event volatility rich, a short straddle
entered after the event and held to expiry should earn **more than the same name's ordinary
short-volatility opportunity**.

The estimand is therefore incremental, never a level:

    Delta_i = R_short(post-EA, i) - R_short(matched control, i)

Two controls, reported separately and never combined:

* **A, same name, non-event.** Same ticker, entered at least 25 business days from any of its
  own announcements. Removes the name's own ordinary volatility pricing.
* **B, same calendar date, cross-name.** A different name on the same date, outside its own
  announcement window. Removes the earnings-season calendar regime that A cannot, because a
  same-name non-event window falls between seasons by construction.

Entry at the close of `t0 + 1` business day ("+2"), short ATM straddle **sold at the bid** as
a liquidity taker, at the listed monthly expiry in the frozen 20-to-45-day band, held to
expiration settlement. Return on Reg-T margin. No signal, no selection, no filter.

## 2. Data and cost

OPRA `cbbo-1m` consolidated quotes marked at 15:59 ET, 2019-02 to 2024-10. Calendar from
Compustat `fundq.rdq` with the bmo/amc session from I/B/E/S announcement times, keeping only
the 80.9% of events whose session came from a real timestamp rather than a default. As-traded
CRSP prices for strike selection and settlement; split-adjusted prices for returns only.

**Spend: $1.6447** on the final pass, about $2.50 including the restarts described in
section 6, against an approved cap of $15 and a pre-pull estimate of $9.25. The estimate was
3.7x too high because it assumed full-session requests; restricting to the closing half-hour
costs 8.3% of a session.

## 3. Funnel

3,310 observations planned from 1,200 sampled events, seed 0.

| Stage | Count | Share |
|---|---|---|
| Priced from quotes | 1,829 | 0.553 |
| — no listed options for the name | 417 | 0.126 |
| — no monthly expiry in the 20-45 day band | 410 | 0.124 |
| — too few two-sided quotes | 268 | 0.081 |
| — nearest strike more than 5% from the forward | 167 | 0.050 |
| — transient API error | 115 | 0.035 |
| — other | 104 | 0.031 |
| Fewer than 5 paired strikes (amendment 02) | −462 | |
| Announcement inside the option's life | −231 | |
| Unsizeable or unmargined | −41 | |
| **Surviving** | **1,095** | |

Surviving by arm: 509 events, 445 control A, 141 control B. The irregular-ladder flag,
recorded but not excluding per amendment 02, fires on 35 of 1,367 (2.6%).

The 12.4% lost to "no monthly expiry in the band" is genuine and mechanical: most single
names list monthlies only, spaced 28 to 35 days apart, against a band 26 days wide, so a
large share of entry dates fall in a gap. It is driven by where the announcement sits in the
expiry cycle.

**Matched pairs: 119 under control A, 110 under control B.** Matching is within
(name, stratum) for A and (date, stratum) for B, without replacement, so the cell structure
costs far more than the funnel does.

## 4. Match quality, reported before any outcome

Standardised mean differences, event against matched control:

| Variable | Control A | Control B |
|---|---|---|
| log-moneyness | −0.030 | +0.006 |
| premium / spot | +0.018 | −0.095 |
| relative bid-ask spread | +0.006 | −0.020 |

All well inside the conventional 0.1 threshold. The matching is not the weak point.

## 5. Result

| | Control A | Control B |
|---|---|---|
| n | 119 | 110 |
| **Mean Delta (RoM)** | **−0.007778** | **+0.024287** |
| Date-clustered CI | [−0.0905, +0.0680] | [−0.0506, +0.0947] |
| Name-clustered CI | [−0.0857, +0.0666] | [−0.0468, +0.1010] |
| Two-way CI | [−0.0868, +0.0712] | [−0.0508, +0.0994] |
| **Reported (widest)** | **[−0.0905, +0.0680]** | **[−0.0508, +0.0994]** |
| Per-trade Sharpe | −0.0179 | +0.0621 |
| Hit rate | 0.504 | 0.564 |

By frozen DTE stratum:

| Stratum | Control A | Control B |
|---|---|---|
| S1 (20-27d) | +0.0463 (n=28) | +0.0792 (n=42) |
| S2 (28-35d) | +0.0016 (n=22) | −0.0669 (n=17) |
| S3 (36-45d) | −0.0327 (n=69) | +0.0095 (n=51) |

Calendar-time portfolio, margin-weighted by settlement month:

| | Control A | Control B |
|---|---|---|
| Months | 51 | 54 |
| Mean monthly | −0.0154 | +0.0234 |
| Monthly sd | 0.359 | 0.315 |
| Months positive | 0.510 | 0.519 |
| Monthly Sharpe | −0.043 | +0.074 |
| Annualised by sqrt(12) | −0.149 | +0.258 |

Deflated Sharpe against 1,477 trials, on the paired difference:

| Trial-Sharpe dispersion | Control A | Control B |
|---|---|---|
| 0.019345 (threshold plateau) | 0.1822 | 0.4877 |
| 0.127475 (arms x cost) | 0.0000 | 0.0001 |

Secondary, pre-registered and singular: does Delta increase with the standardised day-0
shock? Control A slope +0.0431, CI [−0.0165, +0.1235], n=108, R² 0.0097. Control B slope
+0.0117, CI [−0.0575, +0.0979], n=104, R² 0.0009. Both contain zero. The Chung and Louis
surprise-magnitude prediction is not reproduced.

Level returns, which are *not* the estimand and establish nothing on their own: post-event
−0.0315, control A −0.0188, control B −0.0185.

### Decision rule as written

The primary requires `E[Delta] > 0` with the interval excluding zero **under both controls
and in the same direction**. Control A is negative and contains zero. Control B is positive
and contains zero. **Neither passes, and the two point estimates disagree in sign.** The rule
as written therefore fires the third branch: single-name earnings volatility closes.

### Why that reading should not be taken at face value

The pre-registration sized the test at 1,200 matched pairs and fixed in advance that "a wide
interval on this sample is to be read as low power, not as evidence of absence". The achieved
sample is **119 and 110 pairs**, roughly a tenth of that.

With a paired standard deviation of 0.435 (A) and 0.391 (B), the minimum effect detectable at
80% power and 5% two-sided is about **0.11 and 0.10 in return on margin**. An effect of ten
percent of margin per trade would be very large. The test cannot distinguish zero from
anything smaller than that, and both point estimates are an order of magnitude below the
detection threshold.

So the honest statement is not "the effect is absent". It is: **the effect, if present at any
plausible magnitude, is smaller than this design can resolve at the sample it achieved.** The
signs disagreeing across controls is consistent with both estimates being noise.

The shortfall is structural rather than a shortage of events. 1,200 sampled events produced
509 priced events but only 119 matched pairs, because matching without replacement inside
(name, stratum) and (date, stratum) cells is far more restrictive than the funnel. Reaching
1,200 pairs would need roughly ten times the draw, which at the measured rate is about $17
of data, affordable but a different study.

**Recorded explicitly: the outcome above has now been seen. Any decision to extend the sample
is conditioned on having seen an inconclusive result, and must be labelled as such rather
than presented as the original pre-registered test at larger N.**

## 6. Implementation defects found and corrected, all before any outcome was read

Each was found by making the funnel report *why* it dropped an observation rather than only
that it did. Each required discarding priced data and restarting.

1. **Free chain feed abandoned.** Its coverage is date-dependent as well as name-dependent
   (0 of 18 sample names resolve in 2019, 11 of 18 in 2024). Controls sit on different dates
   from their events by construction, so the attrition would have selected matched pairs on
   the same axis the comparison runs along. Amendment 01.
2. **Weeklies substituted for monthlies.** The specification names the monthly expiry; the
   code took the nearest listed expiry in the band, which is often a sparse weekly.
3. **Split-adjusted spot against as-traded strikes.** AAPL on 2019-02-11 resolved to 42.36
   against an as-traded 169.43, so every name that split after its observation date failed
   strike selection and every name that did not split passed. This was a selection on
   corporate-action history, not merely lost yield. Fixed by taking as-traded CRSP prices for
   levels and keeping adjusted prices for returns only.
4. **Strike band stricter than the specification.** A ±15% band with five strikes inside it
   rejected sparse-ladder names; the specification asks only for five reliable strikes at the
   expiry. Replaced by the eleven strikes nearest spot. Priced share rose from 36% to 52%.
5. **Strike test counted contracts, not strikes**, so two paired strikes passed a test meant
   to require five. Amendment 02.
6. **Ladder-regularity deliverable proxy withdrawn.** Measured against the forward-vs-spot
   deviation that actually identifies an adjusted contract, the two groups were
   indistinguishable (median 0.0026 against 0.0020, both far inside the 5% threshold) while
   differing threefold on strike count. It was a noisy restatement of the strike test, not a
   deliverable screen. Amendment 02.
7. **Calendar-time Sharpe fabricated.** Spreading each pair's realised difference evenly over
   its holding days produced a near-deterministic daily series and an annualised Sharpe near
   −6. Replaced by a margin-weighted portfolio return per non-overlapping settlement month.

## 7. Artifacts

| File | Role |
|---|---|
| `scripts/build_postea_calendar.py` | Timestamp-validated broad earnings calendar |
| `scripts/build_postea_spot_cache.py` | Bulk as-traded CRSP price cache |
| `scripts/research_postea_pull.py` | Metered OPRA pricing of all three arms |
| `scripts/research_postea.py` | Matching, inference, decision rule |
| `outputs/research/postea_observations.parquet` | Every planned observation with its status |
| `outputs/research/postea_results.csv` | Headline figures per control |
