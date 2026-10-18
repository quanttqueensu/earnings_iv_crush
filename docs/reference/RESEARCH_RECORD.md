# Earnings IV Crush: Complete Research Record

> **Reference: the complete research record.** Sections 1 to 6 and 8 to 10 are the detailed
> account behind [`../RESEARCH_STATE.md`](../RESEARCH_STATE.md). Superseded: section 7.3 (the
> retired radar) and section 11 (next steps, replaced by [`../ROADMAP.md`](../ROADMAP.md)). Results
> after mid-October 2026 are in `research/<line>/findings/`.

**Jordan Odorico**

A consolidated record of a research programme that ran from its first backtest to a settled
negative verdict. It is written to stand alone: methodology is described in enough detail to
be evaluated and reproduced independently, and every result is reported with its sample size,
basis and dispersion.

It contains the specification, every result, every measurement defect found, every direction
closed, and the assumptions still open. Nothing is omitted because it reflects badly on the
work. The defects section is the most reusable part of the document, and several results are
reported specifically so that nobody repeats them.

---

## 1. The trade and the specification

### 1.1 The position

Sell the at-the-money straddle on a single name at the close of the session before a
scheduled earnings announcement; buy it back at the close of the session after. The position
is naked, unhedged, and held over exactly one overnight period. The strike is the one nearest
the entry spot and is **fixed for the life of the trade**, so the exit mark prices the
contract actually held.

The economic claim is that implied volatility in the front expiry is inflated by event
uncertainty which resolves at the print, so the seller collects a premium for bearing the
announcement gap. This is the oldest single-name volatility trade in existence and the
unconditional version is roughly fairly priced net of costs, which is this project's null
hypothesis rather than its thesis.

Any edge therefore has to come from **selection**, not from the average trade.

### 1.2 The selector

The selector under test is a **term-structure gate**. For each candidate event, compute

> term spread = (ATM implied volatility, front expiry) − (ATM implied volatility, back expiry)

at the entry close. Both legs are inverted from observed straddle prices at the strike
traded. A steep front, meaning a large positive spread, is the market pricing a
disproportionate share of near-term variance into the days that contain the announcement.

The economic argument is that a steep front confirms the premium is concentrated in the event
itself, so what is being sold is genuinely event variance rather than a general level of
volatility that will persist past the print.

**The gate is causal and expanding, and this construction matters.** For each event, the
threshold is the 80th percentile of the term spreads of all events **strictly prior to it,
pooled across all names**. Nothing from the event's own date or later enters its own
threshold. The pool grows as the sample advances, so early events are judged against a
smaller history. Trade only events whose spread exceeds their own threshold; this admits
roughly 21.7% of candidates.

A per-name variant, where each name's percentile is computed from its own history only, was
also tested and is reported in section 6.5. The pooled form is the one the headline verdict
rests on.

### 1.3 Marking, sizing, and the return unit

**Marks.** Each leg is marked from the consolidated best bid and offer, taken as the last
quote at or before 15:59 exchange-local time on the entry and exit sessions. The straddle
mark is the sum of the two legs' mids, aggregated in dollars before any division. Package
relative spread is measured as the sum of leg-level (ask − bid) divided by the sum of
leg-level mids; equal-weighting the two legs' relative spreads is not valid after an earnings
gap, because the two legs have very different values by then.

**Sizing.** Positions are sized on Reg-T margin approximated as `0.20 × spot + premium` per
share at the money, which is the standard naked-short-option formula with the
out-of-the-money reduction term set to zero. Contract counts are integers, floored.

**Return unit.** The headline unit is **return on margin**: net profit divided by the margin
the position committed. Margin is the scarce resource and it is comparable across names whose
share prices differ by two orders of magnitude. Where a different unit is used, notably
return on premium in some breadth work, it is named explicitly at the point of use, because
the two are not interchangeable and differ by roughly an order of magnitude in level.

**Costs.** The break-even is **11.6% of premium round-trip**. Every result is scored against
that figure unless a measured spread is substituted, which section 4 describes.

**Crush.** Where the realised crush is reported it is the proportional fall in at-the-money
implied volatility from entry to exit, inverted from the book's own marks at the strike
actually traded. Section 5.3 explains why that qualification is load-bearing.

### 1.4 Inference

**Confidence intervals resample whole announcement dates**, not individual trades. Names
reporting on the same day share the tape and are not independent draws; treating them as
independent overstates precision materially on a book where earnings cluster into a few dozen
dates per quarter. Where the natural cluster is the name rather than the date, a name-block
bootstrap is used instead and is labelled as such.

**Annualisation uses the square root of realised trades per year**, derived from the data's
own cadence, never √252. On a book trading roughly 35 times a year the correct factor is
about 5.93. Applying √252 to this book inflates the Sharpe roughly threefold, and doing so
was a real error in an earlier stage of the work; see section 5.1.

**The Deflated Sharpe Ratio is charged against a reconstructed trial count of 1,476.** That
figure counts every threshold, gate, orthogonal filter, parameter grid cell and cost
variation examined across the life of the project. It was reconstructed after the fact, which
is itself a methodological failure: a trial ledger cannot be assembled honestly in
retrospect, and the successor programme described in section 8 pre-registers it instead.

### 1.5 The control

Every result is scored against an unfiltered control that trades identical economics on every
event in the same universe over the same window. Beating zero by declining to trade is
trivial. The gate is tested against **participation**, not against cash.

---

## 2. The verdict

The strategy does not replicate out of sample. This is settled, not provisional.

The universe is 50 large-capitalisation US names. The 2019-2024 block was the original sample;
the 2013-2018 block was built afterwards, on the identical frozen specification, with **no
re-tuning of any parameter**, and is a genuine out-of-sample test on a disjoint six-year
window.

| | 2019-2024 | 2013-2018 | Pooled |
|---|---|---|---|
| N | 198 | 193 | 391 |
| Names | 36 | 30 | 39 |
| Hit rate | 69.19% | 61.14% | 65.22% |
| Mean return on margin | +0.017134 | −0.000799 | +0.008282 |
| **Per-trade Sharpe** | **+0.117321** | **−0.005337** | **+0.055992** |
| Annualised Sharpe | +0.6956 | −0.0319 | +0.328 |
| Annualisation factor | 5.929 | 5.976 | √(trades per year) |
| Trades per year | 35.2 | 35.7 | 35.4 |
| One-sided p | 0.0500 | 0.5296 | 0.1343 |
| Date-clustered 95% CI | [−0.027, +0.327] | [−0.134, +0.153] | [−0.042, +0.180] |
| Total P&L | +$35,491 | −$5,896 | +$29,596 |
| Annual return on account | 2.52% | −0.44% | 0.99% |
| Max drawdown | −$14,936 | −$24,300 | −$24,300 |
| Drawdown duration | 66 trades | 104 trades | 104 trades |
| Calmar | +0.4219 | −0.0449 | +0.107 |
| Profit factor | 1.3969 | 0.9510 | 1.141 |
| Skew of returns | −2.92 | −1.90 | − |
| Excess kurtosis | 18.18 | 9.94 | − |
| Best / worst trade | +$2,709 / −$11,085 | +$2,759 / −$10,615 | +$2,759 / −$11,085 |
| Probabilistic Sharpe vs zero | 0.9176 | 0.4704 | − |
| **Deflated Sharpe (1,476 trials)** | **0.000113** | **7.4e−10** | **≈0** |

**The annualisation basis is the single most important caveat on every Sharpe in this
document.** A per-trade Sharpe of +0.117 on a book that trades 35 times a year annualises to
+0.70, not to +1.86.

### Why the negative is credible rather than merely unlucky

**The sample-size objection is closed on its own terms.** An earlier stage computed that the
then-current point estimate of +0.087 required N = 356 for one-sided 95% significance. Pooled
N is now **391**, past that threshold, and the interval still contains zero. The data arrived
and the edge did not. "Run more events" is not an open avenue.

**The Deflated Sharpe is decisive.** The expected maximum Sharpe from 1,476 no-edge trials is
**+0.429**, more than three times the +0.117 observed on the better block. Under the narrow
term-grid dispersion alone (standard deviation of trial Sharpes 0.0606) the 2019-2024 DSR is
0.153; charged against only the 41 threshold configurations it is 0.425. Nothing clears 0.5.

**Survivorship runs in the strategy's favour and it still fails.** The universe is today's 50
largest US names carried back to 2013, which is selection on present-day size. That should
**help** a short volatility book, since it over-samples firms that survived and grew, and the
2013-2018 block still returns −0.005. A point-in-time reconstitution would make the result
more negative, not less. This strengthens the negative rather than qualifying it, and it is
worth being explicit that the same argument would be entirely insufficient to defend a
positive result.

**Drawdown is 9.4× annualised profit.** The book is underwater for most of the twelve years
and takes 104 trades, roughly three years, to recover from the worst episode. Return
distribution skew is −2.9 with excess kurtosis 18.2, which is the shape a short-volatility
book makes: many small wins, rare very large losses.

**Two years carry the entire record.** 2014 (+$18,533) and 2022 (+$13,972) sum to $32,505 and
**exceed the entire twelve-year total of $29,596**, so the other ten years are net negative in
aggregate.

| Year | P&L | N | | Year | P&L | N |
|---|---|---|---|---|---|---|
| 2013 | −$7,506 | 17 | | 2019 | +$11,558 | 25 |
| 2014 | **+$18,533** | 27 | | 2020 | +$4,586 | 30 |
| 2015 | −$158 | 39 | | 2021 | +$867 | 20 |
| 2016 | −$9,813 | 38 | | 2022 | **+$13,972** | 53 |
| 2017 | +$124 | 31 | | 2023 | +$2,991 | 30 |
| 2018 | −$7,075 | 41 | | 2024 | +$1,517 | 40 |

### The mechanism is real; only the monetisation fails

This distinction matters for anyone deciding what is worth reusing.

At-the-money implied volatility falls on **98.1% of 989 events**, mean fall 48.65 volatility
points. On the gated book the mark-implied crush is +0.3193 in proportional terms, with IV
falling on 91.8% of events.

The driver attribution decomposes realised P&L into theta, vega and spot legs. Volatilities
are inverted from the book's own straddle marks at the strike actually traded, so that
Black-Scholes(entry) = credit received and Black-Scholes(exit) = exit mark are **identities**
rather than approximations, and the legs reconcile to realised P&L with a residual of exactly
zero. Because a path-dependent decomposition is order-sensitive, it is reported under both
orderings:

| Leg | Theta-vega-spot | Spot-vega-theta |
|---|---|---|
| Theta | +$137,359 | +$43,959 |
| **Vega** | **+$355,325** | **+$327,603** |
| Spot | −$401,692 | −$280,570 |

**Vega is the largest positive leg under both orderings.** The crush is real, it is what pays,
and the spot gap is what takes it back. Independently, on clean quote-marked data the
correlation between realised crush and net straddle return is **+0.7342**, so the crush
explains roughly 54% of the variance in the trade's outcome.

The honest reading: this is an efficiently priced announcement. The premium is not larger than
the gap risk borne to collect it.

---

## 3. Data

| Layer | Source | Coverage | Note |
|---|---|---|---|
| Option quotes | OPRA consolidated BBO, 1-minute | 2013-04-01 onward | 15:59 ET snapshot plus a 15:45-15:59 window median as a staleness check |
| Option bars | OPRA daily OHLCV | full | Superseded as a marking basis; see 5.2 |
| Prints for fills study | OPRA consolidated trades | 2023-03-28 onward | 3.2M records over 162 sessions |
| Earnings calendar | Compustat quarterly report dates + I/B/E/S | full | Cross-checked against a commercial calendar; see 5.6 |
| Equity spot | CRSP daily stock file | full | Free adjusted-close feeds used for live and breadth work |
| Free option chains, US | Public crowd-sourced database | 2019-2024 | Three expiries per snapshot at roughly 14, 28 and 49 days |
| Free option chains, India | NSE daily bhavcopy | mid-2024 onward | Settlement price only, no bid or ask |
| Free option chains, Brazil | B3 end-of-day file | 2025 onward | Carries real bid and ask |

**Total metered data spend: approximately $27.** Quote re-mark $17.9, out-of-sample block
build $8.34, execution study $0.04, forward-window backfill $0.33.

### Three data findings worth carrying

**Consolidated 1-minute quotes on OPRA reach back to 2013-04-01.** This was verified against
the vendor's own dataset-range metadata. A widely repeated claim, which the project itself
believed and had written into its documentation, is that consolidated NBBO on OPRA begins
2023-03-28. That is true only of the tick-level consolidated products, not of the 1-minute
aggregated BBO. **That single false belief is why the project marked off last-trade daily
closes for its entire first year**, and it is the root cause of the marking defect in
section 5.2. It is worth stating plainly because the same belief is common.

**Volume, not event count, is what a tick-data vendor bills.** An inherited estimate of $41
for the execution study assumed full option chains over full trading sessions. Restricting the
request to the two contracts the book actually holds over a thirty-minute window cut the cost
by roughly a factor of 1,000, to $0.04. Separately, 1-minute quote aggregates cost about **5×
less** than daily bars for the same symbols, because daily bars bill one row per exchange per
symbol per day and OPRA has many exchanges. Never accept a per-event vendor price without
checking what scope it assumed.

**Point-in-time historical implied volatility was never obtained and remains the largest data
gap.** Institutional access arrived as a parquet mirror of a research database rather than the
full product, and the option-metrics tables were never ingested. Enumerating every available
schema twice confirmed that the only option-bearing data present is index-level volatility
(VIX and relatives, as daily levels, no contracts) and PHLX **currency** options from 1983 to
1997. Neither is usable for single-name earnings. Absolute Sharpe levels throughout this
project are therefore contingent on marks the project constructed itself.

---

## 4. The execution constraint

This is the measurement that most differentiates the work, and it should select the next piece
of research rather than be rediscovered by it.

**Break-even is 11.6% of premium round-trip.**

The execution study measured **34,672 usable prints** drawn from 3.2M records across 162
windows, 15:30:00 to 15:59:59 exchange-local time, with zero failed windows. For each print,
the prevailing consolidated bid and offer at that instant were reconstructed, and the fill was
located on the [bid, ask] interval as a fraction.

| Measure | Value |
|---|---|
| Median price improvement versus the touch | **exactly 0.0%** |
| Fills at the bid | 25.6% |
| Fills at the ask | 28.7% |
| Fills near the mid | 21.2% |
| **Paying the full touch** | **54.3%** |
| Size-weighted fill location | 0.282 |

Fill location is **bimodal**, and this is a trap worth recording. The median fill location of
0.500 reads as mid execution and is purely an artefact of symmetric bimodality: half the
prints sit at one end and half at the other, so the median lands in a region where almost
nothing trades. **Never quote a central tendency on a bimodal fill distribution.** This was
caught only by plotting the distribution before writing it up.

The attainable cost is therefore the **unconditional fixed-time book at 1.7871% per side**,
asymmetric between entry (1.2714%) and exit (3.0182%), reflecting roughly 2:1 post-event quote
widening, against 2.000% previously assumed. Rescoring the frozen specification with only the
cost changed:

| Cost basis | Per side | Pooled Sharpe | One-sided p | P&L | Clustered CI |
|---|---|---|---|---|---|
| Assumed | 2.000% | +0.055992 | 0.1343 | $29,596 | [−0.042, +0.180] |
| **Measured, fixed time (honest)** | **1.7871%** | **+0.062899** | **0.1070** | **$33,789** | **[−0.038, +0.185]** |
| Trade-conditional (**not attainable**) | 0.7611% | +0.096571 | − | − | − |

**The trade-conditional arm is a selection artefact and must never be quoted.** It is the
spread prevailing at the moments trades actually occurred, which is 2.35× tighter than the
same book measured at a fixed 15:59. Trades cluster in tight-spread moments; a strategy that
decides and executes at a fixed time cannot select into them. It is the highest-Sharpe row in
the table, which is exactly why it is dangerous, and it was measured from the same source at
both timings specifically so that no cross-source confound could explain the gap away.

Execution is worth roughly **0.007 of per-trade Sharpe**. It does not change the verdict.

Measured at-the-money relative spreads on this book, the first time they were measured rather
than assumed: 25th percentile 3.37%, median 5.14%, 75th 8.71%, 90th 14.48%, giving a median
half-cross of 2.57% against 2.00% assumed.

**This contradicts a load-bearing assumption in the published options-anomaly literature.**
Goyal and Saretto argue that the average volume-weighted quoted spread on near-the-money
options with 30 to 60 days to expiry is 8.0%, and that profitability survives because "the
effective spread is generally lower than the quoted one". At fixed-time execution on this
sample it is not: median improvement is zero. Vasquez handles the same problem differently and
soundly, by holding to maturity so the spread is crossed once instead of twice, but that
converts the trade into a different risk object.

---

## 5. Defects found, and the rules they generalise to

Six measurement defects were found, four of them after results built on them had been written
up. Each is recorded as symptom, diagnosis, magnitude, and the rule it generalises to. A
reader deciding how much to trust anything here should read this section first.

### 5.1 The annualisation artefact

**Symptom.** A headline annualised Sharpe of +2.04 and a size-matched confidence interval of
[+4.24, +8.30] on a strategy trading about 34 times a year.

**Diagnosis.** A √252 factor applied to a book with roughly 34 independent bets a year,
compounded by netting multiple names within a day and then treating the netted series as
daily. Roughly threefold inflation.

**Magnitude, and the reason it is listed as two events.** The first fix corrected the primary
backtest. A later audit found that the comparison and frequency-neutral reporting functions
**still** defaulted to √252, which measured a further 1.73× inflation on the same book
(size-matched delta 2.45 falling to 1.42). A third instance was found in a parameter sweep
that un-annualised by √252 regardless of each cell's own inferred cadence.

**Rule.** Every scaled number states its basis beside it. For an event book the per-trade
Sharpe is the unambiguous unit, and any annualised figure must name the factor and where it
came from. A single fix in one code path is not a fix.

### 5.2 Marks that violate no-arbitrage

**Symptom.** The canonical published headline of +0.115773 on N = 192 could not be reproduced.

**Diagnosis.** There was no parameter bug. There were two different books. The headline marked
each straddle at the two legs' **daily closing trade prices**; an independent rebuild that
re-priced from inverted implied volatilities returned −0.378 on the identical gate and sample.
Both were correct calculations pricing different things.

The deeper problem is that a book marked at last-trade closes contains prints **below
intrinsic value** , prices at which the option could not have traded, because the holder would
exercise instead. Repairing them moves the result **down**:

| Arm | N | Sharpe | 95% CI |
|---|---|---|---|
| As-is (the published headline) | 192 | +0.115773 | [−0.028, +0.320] |
| Exit rebuilt from put-call parity | 192 | +0.086741 | [−0.049, +0.283] |
| Marks floored at intrinsic value | 192 | +0.074416 | [−0.062, +0.264] |
| *Corrupted trades dropped* | *153* | *+0.328822* | *[+0.135, +0.598]* |

**The dropped-trades arm must never be quoted as the repair.** It drops precisely the
large-move losers, because those are the events where a deep in-the-money leg produces the
sub-intrinsic print. It is therefore selection on the outcome, inside the sample. It is
included here because it is the most attractive number in the entire project and because the
reason it is wrong is not visible from the summary statistic.

**The apparent significance was manufactured by the bad marks.** The unrepaired current book
scores +0.148065 and would clear one-sided 95% on N = 198 alone. The repaired book scores
+0.087393 and requires N = 356. **The entire distance between "significant" and "not
significant" was prints that could not have traded.**

The full reconciliation grid, all reproducing to six decimal places, disentangles two
independent factors, the repair and a later calendar correction: unrepaired marks on the
pre-correction event set give N = 192 and +0.115773; repaired on the same set +0.060432;
unrepaired on the corrected set N = 198 and +0.148065; repaired on the corrected set N = 198
and **+0.087393**. The published figure was the product of two errors pointing the same way.

**A related decision worth stating.** The repair is applied **conditionally**, only where a
mark breaches its own intrinsic floor, never uniformly. A traded price is the best estimate
when it is valid, and the parity rebuild is biased low by a median 1.2% of credit, so applying
it everywhere would inject that flattering bias into every trade. Uniform application lifts
the Sharpe from +0.060 to +0.087, and that measurement is what establishes the uniform version
as outcome-correlated selection rather than cleaning.

**Rule.** A repair that improves a result by dropping observations is selection. A repair that
worsens the result is more likely to be a genuine repair.

### 5.3 The exit strike is re-picked, so the exit volatility describes a contract nobody holds

**Symptom.** A driver attribution reporting that implied volatility **rose** on two thirds of
events and that vega was the largest **negative** leg. Both conclusions were published before
being caught, and both are false.

**Diagnosis.** The event tables record an exit implied volatility measured at the
**post-event** at-the-money strike, not at the strike the book holds. This is deliberate and
defensible for its intended purpose: after a large earnings move the original strike is deep
in or out of the money, and inverting an implied volatility from a near-expiry off-ATM daily
close explodes past 300%. But the resulting quantity describes a **different contract**, and
any decomposition built on it describes a different position.

The consequence for a crush variable computed naively as (IV entry − IV exit) / IV entry is
that it stops measuring the volatility collapse and starts measuring the move. Auditing every
event table constructed over the life of the project:

| Event table | N | Fraction where IV fell | corr(crush, abs move) |
|---|---|---|---|
| Megacap, daily-bar marked | 1,051 | 0.337 | **−0.6466** |
| Megacap, daily-bar marked, extension | 877 | 0.343 | −0.6249 |
| Megacap, early build | 454 | 0.253 | −0.0721 |
| Broad universe, 2024 | 2,381 | 0.881 | +0.4145 |
| Broad universe, 2025 | 2,017 | 0.865 | +0.4262 |
| Broad universe, v2 | 363 | 0.901 | +0.4331 |
| Megacap, v2 | 456 | 0.893 | +0.3804 |
| **Megacap, quote-marked 2013-2018** | **1,117** | **0.900** | **+0.0349** |

Two distinct signatures. The daily-bar-marked megacap tables show IV **rising** on two thirds
of events, against the project's own established 98.1% fall, correlated −0.65 with the
absolute move. Since the straddle's return is itself a function of the move, a crush variable
correlated −0.65 with the move makes **any sort on predicted crush a sort on predicted move**,
and a monotone tercile ordering follows mechanically with no economic content. The broad
tables keep the right sign and carry +0.42, which may be economically real. Only the
quote-marked 2013-2018 table, at +0.035, has a crush that is a genuinely separate quantity
from the move.

**How it was caught.** Not by inspection. A downstream test failed in a way the upstream
result could not explain, and investigating that inconsistency rather than accepting the
favourable upstream number is what surfaced it. The analysis now **raises an error** rather
than pooling silently on any table where IV falls on fewer than 80% of events.

**Rule.** Before using any derived column, verify that it describes the position actually
held. The corrected attribution, which inverts from the book's own marks at the traded strike,
reconciles to realised P&L with residual exactly zero, and that identity is the check that
licenses trusting it.

**Unaddressed.** The event tables still carry the re-picked quantity under a name that invites
the same mistake.

### 5.4 The stale entry spot

**Symptom.** Found while charting the book's worst trade for a write-up: the entry chain's own
quotes imply a forward price of about 216.1 while the event record shows an entry spot of
208.46, which turns out to be the **previous** session's close.

**Diagnosis.** The spot lookup returns the most recent close **at or before** the entry date,
with no counter recording when it fell back. Whenever the price series lacked the entry date
for any reason, the lookup silently substituted the prior session and reported success.

**Magnitude.** Measured against an uncensored put-call-parity forward reconstructed from the
cached entry chains, the absolute log difference exceeds 2% on **16.9% of 1,790 priced events,
and on 27.4% of the 391 gated events** against 13.9% of the non-gated. The exit side is clean,
with a median difference around 0.10%. The lag was confirmed on ten of ten of the worst gated
cases by comparing parity forwards on the announcement day against the prior day.

**Why it concentrates on the gated subset, which is the part that matters.** Both legs of the
term spread are inverted at the recorded spot, and the two expiries have different vegas, so
the error does not cancel between them. It is largest exactly when the stock moved a lot in
the session before the print, which co-moves with a genuinely elevated term spread. The
defect therefore loads onto precisely the events the gate selects.

**Partial correction**, recomputing only the gate statistic at the parity forward while
holding marks and gate rule fixed: pooled Sharpe **+0.0555 falling to +0.0454**, 2019-2024
+0.1114 to +0.0932, 2013-2018 +0.0028 to +0.0004, P&L $28,481 to $23,379. The direction is
against the strategy, so the verdict is unchanged, but it is a **16% haircut on the only block
that ever looked significant**.

**This is the largest unrepaired item in the project.** Strike selection, the marks themselves
and margin-based sizing all still use the stale spot. A full correction requires rebuilding
the event set and re-marking.

**Rule.** Any lookup that can fail soft must count and report its fallbacks. This is the same
class of error as 5.6 and it is exactly what the project's own exclusion-funnel convention
exists to prevent.

### 5.5 The split-basis mismatch

**Symptom.** The first attempt at the 2013-2018 out-of-sample block refused to mark **261 of
1,085 events (24.1%)**, concentrated in nine specific names at 23 events each, which is every
event those names have in the window. The surviving sample scored +0.023504.

**Diagnosis.** Free equity closes are split-**adjusted**; historical OPRA strikes are **raw**,
as they existed on the day. Joining one to the other makes every strike look wrong for any
name that has ever split, by exactly the cumulative split factor. The nine affected names are
the ones that split during the window, which is to say the decade's biggest winners.

**Fix and magnitude.** Multiplying the equity series by a per-date cumulative split factor
before the join dropped refusals to 1.5% (16 of 1,130), with a median absolute log-moneyness
of 0.0028.

**+0.023504 must never be quoted.** It is a sample systematically stripped of the best-
performing names in the universe.

**Rule.** Any join of an adjusted equity series to raw historical strikes is a basis bug. The
refuse-to-mark guard is what made it visible at all, which is the general argument for
fail-loud guards over fail-soft defaults: a softer implementation would have silently marked
those events at the wrong strike and produced a plausible, wrong number.

### 5.6 The session-labelling error, and how one name's bad data contaminated every other name

**Symptom.** One name, a large industrial, passed the term gate on 62.5% of its candidates
against a 21.7% pool average, nearly 3×, and its term spread ran 0.2 to 0.87 where most names
sit at 0.02 to 0.15.

**Diagnosis.** Whether a company reports before the open or after the close determines which
sessions bracket the announcement. Two calendar sources disagree on that flag for 49 of 1,200
events (4.1%), and **47% of that disagreement concentrates in exactly two names**. Repricing
the affected events at the corrected session collapses the outlier name's mean term spread
from **0.522 to 0.154**, from 2.6× the pool average to in line with it, and its gate pass rate
from 62.5% to 29.2%.

**The second-order finding is the one worth carrying.** Because the gate pools all names into
one shared expanding percentile threshold, the inflated spreads were **raising the bar that
every other name's candidates were judged against**. Correcting the one name removed 8 of its
own passes and **added 15 newly-qualifying events across 10 different names**, a net +7 on the
1,051-event pool. One name's bad data was silently distorting the selection decisions made
about all the others.

**Rule.** In any pooled cross-sectional threshold, a contaminated observation changes the
decisions made about every other observation. The instinct to check whether an outlier is real
must extend to checking what the outlier did to the sample it sat in.

**Method note, because the first attempt failed honestly.** The initial diagnostic split the
name's events by mismatch flag and found a real 2× gap, but the flag and a pre/post-2021 date
split were **almost perfectly collinear** in that sample, and the company was in a genuine
restructuring crisis over the same period, which is a real competing explanation for elevated
event uncertainty. That ambiguity was reported as unresolved rather than resolved in the
convenient direction. It was settled only later, by actually repricing at the corrected dates
using a free data source that turned out to reach 21 of the 22 flagged events, after an
earlier check had wrongly concluded no free coverage existed by testing only a local cache.

---

## 6. Everything tried

### 6.1 Gates

| Gate | Result | Status |
|---|---|---|
| **Term spread, 80th percentile** | The one real selector. Pooled +0.056, CI through zero | Alive, not significant |
| Move gate | Additive in sample, fails its own expanding-window OOS test | Dead |
| Skew gate (25-delta put) | Roughly doubles in-sample Sharpe on a 2024-25 cache; DSR 0.00 OOS | Dead |
| Curvature gate | In sample +0.19 with CI clearing zero at n = 145; fails a 2023 holdout | Dead, measurement-limited |
| Per-name gate | 301 trades, per-trade Sharpe +0.85, size-matched delta +0.33 | Alive, superseded basis |

**The move gate** tested whether an option priced expensively relative to a statistical
forecast of the realised move is overpriced. It was additive in sample and failed its own
expanding-window out-of-sample test. It rules out nothing about the economics, but it does
establish that the implied-to-forecast ratio is at least as good at identifying events the
market understands better than the regression does as it is at identifying overpricing.

**The skew gate is the cleanest cautionary case in the project.** The hypothesis was that low
25-delta put skew identifies events where downside hedging demand is not distorting the price.
It roughly doubled per-trade Sharpe in sample. It is dead because the in-sample data was
marked at closes standing in for mids and annualised by √252, so **both the level and the
basis were wrong before the sort was even applied**, and the sort was chosen after several
candidates had been examined, so its trial count was never one.

**The curvature gate deserves a note because it failed for a measurable reason.** Following
Alexiou, Goyal, Kostakis and Rompolis (*Review of Finance*, 2025), pre-earnings **concave**
implied-volatility curves indicate a bimodal risk-neutral distribution and predict lower
straddle returns, which makes them richer for a short. Two concavity measures were built from
the entry smiles: a three-point at-the-money second difference and a central quadratic fit.
In sample the combined arm reached +0.19 with an interval clearing zero at n = 145 and even
improved the worst trade. It did **not** survive a 2023 chronological holdout, where the
out-of-sample subset returned −0.164 against term-only +0.082, and the two concavity measures
were correlated at only −0.04 **with opposite out-of-sample signs**, which is the signature of
two noise measurements rather than two proxies for one thing.

The diagnosis is measurement, not economics. Pre-2023 chains in the project carried the daily
close on both sides, so strike-by-strike implied volatility is noisy, and the single most
concave event in the entire sample turned out to be one bad strike with an IV of 1.18 sitting
between neighbours at 0.76 and 0.73, not a real bimodal hump. **A proper test needs
consolidated-quote intraday surfaces, which are now known to exist back to 2013 and were
believed not to when this was run.** This is one of the few closed items that the data finding
in section 3 reopens.

**Dose-response across the threshold.** This is the evidence that the 80th percentile is a
plateau rather than a lucky cut, and it also contains an honest warning:

| Percentile | N | Per-trade Sharpe |
|---|---|---|
| 0.50 | 943 | −0.0219 |
| 0.60 | 748 | −0.0202 |
| 0.70 | 569 | +0.0153 |
| 0.75 | 500 | +0.0340 |
| **0.80** | **391** | **+0.0560** |
| 0.82 | 354 | +0.0593 |
| 0.85 | 302 | +0.0397 |
| 0.88 | 245 | +0.0452 |
| **0.91** | **189** | **+0.1269** |
| 0.95 | 132 | +0.1051 |

Monotone rise from −0.022 at the median through a broad 0.78-0.82 plateau, a trough at
0.84-0.86, and then an **isolated spike of +0.127 at the 91st percentile on 189 trades**.
That spike is the overfit trap and it is more than twice the plateau value. An earlier version
of this project operated at the 85th percentile, which a dense 0.01-step sweep later showed to
be a local spike sitting above the 0.83-0.84 trough. The 80th percentile was adopted because
its neighbours at 0.78 to 0.82 all sit within about 0.01 of it, which is what an interior node
looks like.

### 6.2 Vehicles and structures

| Structure | Result |
|---|---|
| Naked straddle | The only positive vehicle net of asymmetric cost |
| Iron fly | Wings cost ~2.4% of margin against a 0.6-0.95% budget. Net negative, robust to wing distance |
| Calendar spread | Contradictory evidence; see below |
| Hard stop near −0.30 | Unattainable |
| Hold to expiry, unconditional | Not clearly better |
| **Conditional exit** | Strongest lever in the study, survives a holdout |

**The iron fly** was tested for defined risk at an acceptable premium give-up. Far
out-of-the-money protective wings cost about 2.4% of margin against a break-even budget of
0.6% to 0.95%, so the defined-risk book is net negative and remains so across wing distances.
**The tail is fairly priced.** You cannot buy out of this trade's risk cheaply.

**The hard stop is the cleanest negative in the risk work.** A stop near −0.30 return on
margin appears to cap the tail and lift the Sharpe from +0.116 to +0.198. It cannot fire. With
one mark per day, the position is observed at the entry close and the exit close and nowhere
in between, so a stop placed inside the earnings gap fills at the post-gap price, not at the
floor. The entire apparent benefit is unattainable. **This rules out every intraday risk
control tested on a daily-marked book**, and it generalises: any backtest of a stop on data
with no intraday path is measuring the level the price gapped through, not the level the order
would have filled at.

**The conditional exit is the only item in this list that is not dead.** Hold the short
straddle to weekly expiry when the event's implied move sits below roughly the 75th percentile
of the name's own history; take the next-session exit on the top quartile. The reasoning is
that small-implied-move events are ones where carrying the position through to expiry collects
remaining time value without much gap exposure, while large-implied-move events are exactly
where the gap dominates and getting out promptly matters.

It produces the highest per-trade Sharpe in the study on both cost bases: **+0.132** under
realistic asymmetric costs and **+0.167** under an optimistic symmetric cost, against **+0.116**
for the naked baseline. The paired mean advantage clears zero under the realistic asymmetric
cost (sign test p = 0.002, Wilcoxon p = 0.003) but **not** under the optimistic symmetric cost,
where the direction holds but the mean is not significant. **The lever is therefore contingent
on exit execution being as expensive as the execution study measured**, which is an unusual
and honest dependency: it works because exits are dear, so avoiding one is worth a lot.

It survives a clean chronological holdout with the cut frozen on 2019-2022 and applied once to
2023-2024: out-of-sample next-session book −0.04, conditional +0.17, mean advantage +3.13%
clearing zero, Wilcoxon p = 0.008, n = 66 out of sample, which is small.

Settlement is computed as de-adjusted equity intrinsic value at expiry because weekly-expiry
chains were never cached, so **the magnitude is indicative and only the direction is solid**.

It is not carried into the headline verdict because it changes the risk object: holding to
expiry means carrying several more days of directional exposure. That is a defensible choice
and a reader may want to revisit it, because it is also **the single largest available attack
on the cost constraint**: crossing the spread once instead of twice takes the round-trip
break-even from 11.6% to roughly 5.8%.

**The calendar contradiction, stated rather than resolved.** A structural comparison on 81
common events records:

| Structure | Mean return on risk | Per-trade Sharpe | Hit | Correlation to realised move |
|---|---|---|---|---|
| Straddle | +0.0419 | +0.4198 | 77.8% | −0.125 |
| **Calendar** | **+0.0602** | **+0.6405** | **84.0%** | **−0.066** |
| Iron fly | −0.0535 | −0.1202 | 51.9% | −0.468 |

The calendar beats the straddle on every column, including a lower correlation to the realised
move, which is the property you want if the thesis is that you are selling event variance
rather than taking a directional view. A separate strand of the project records that this
advantage came from a **synthetically priced back month** and that on real chains the calendar
is net negative, between −0.15 and −0.57 depending on construction.

**These two readings have never been reconciled on a common marking basis.** The negative
reading is the more conservative and is probably right, but the only side-by-side structural
comparison in the record disagrees with it, and a reader should know that. There is also a
genuine cost argument against calendars that must be checked rather than assumed either way: a
calendar's net premium is smaller than a straddle's, so the same absolute bid-ask spread is a
larger fraction of it. The general lesson stands regardless: **any leg priced by a model rather
than a quote will look better than it is.**

### 6.3 Orthogonal signals tested as additive filters and rejected

Tested as additional filters layered on the term-gated book, each rejected: the variance risk
premium, the volatility premium (implied minus trailing realised), Bakshi-Kapadia-Madan
risk-neutral skewness, BKM risk-neutral kurtosis, trailing realised volatility, lottery demand,
peer transfer of volatility information, an explicit parametric crush model, and post-earnings
announcement drift measured within the project's own sample.

Each is a candidate feature and **each is a trial**. These nine are a large part of why the
reconstructed trial count reaches 1,476 and why the Deflated Sharpe collapses to essentially
zero. That is the honest price of exploratory breadth, and it is charged rather than forgotten.

### 6.4 The cross-sectional long-short reframe

**Expected.** If a high term spread predicts a rich straddle, the low end should predict a
cheap one, and a long-short is a market-neutral way to express the same view with twice the
signal and half the directional exposure.

**Rejected on the shape of the payoff, not on the statistics.** Regenerating the per-event
data and plotting return by quintile of the signal showed a **top-tail threshold effect, not a
linear factor**: quintiles one through four are flat noise and the entire effect sits in
quintile five. There is no cheap leg to buy. Worse, the long leg would buy straddles into
announcements, paying its own crush plus a second full round trip of transaction costs, and is
net negative standalone.

**Rule worth carrying beyond this project.** Before building a long-short, plot the payoff by
quantile. A threshold effect and a monotone factor produce **identical** top-minus-bottom
summary statistics and are completely different objects, with completely different
implications for whether the short leg alone is the right trade.

### 6.5 Breadth

**Universe expansion with a liquidity-aware cost penalty.** Widening from 50 mega-caps to 346
S&P 500 names, and replacing the single global spread assumption with a per-name spread scaled
by an inverse power of that name's dollar average daily volume, the edge **survives the whole
penalty sweep**. At the harshest setting, where the least-liquid decile carries a roughly 22%
quoted spread, the filtered per-trade Sharpe stays positive, and the size-matched delta
against the control **widens** as costs rise, because the control bleeds more on the illiquid
tail that the filter avoids.

Fresh per-trade Sharpe deltas after the annualisation correction: **+0.51** for the pooled gate
(N = 422) and **+0.33** for the per-name gate (N = 301), both larger than the 45-name
headline's +0.12. Caveats that matter more than the result: the broad book was marked from a
free retail feed, the gate was coarse, and the S&P 500 is not small-cap. **It is a
cost-survival result, not a significance result.**

**The multi-name annualisation problem is genuinely open.** On a 346-name book, netting
positions within a day collapses the return series to about 97 distinct trading periods a
year, because concurrently reporting names land on the same 181 calendar days across a
681-day span. Annualising a daily Sharpe by √97 produces annualised Sharpes around 10, which
is not credible for any real strategy. Calendar-day-count periods per year is simply the wrong
basis for a multi-name day-netted book; it needs either a trade-count basis matching the
single-name convention, or a proper portfolio treatment with correlations and position sizing.
**No size-matched delta interval from the broad-universe work should be quoted until this is
resolved.**

**Name-level richness persistence.** A narrower question the term gate never asked: do names
whose straddles were historically rich stay rich? Working in move space, where the short ATM
straddle's return on premium is approximated as

> return = 1 − |realised move| / implied move

so that the return is positive whenever the stock moved less than the option implied. The
efficient-markets null is that no pre-event variable predicts it. The variable tested is a
name's own prior expanding mean of that return, computed causally and leaving the current
event out. Inference is by **name-block bootstrap**, since events cluster into a few dozen
repeated bets on the same names rather than into independent draws.

| Book | N | Names | Net mean | Hit | Per-trade Sharpe | Name-block 95% CI |
|---|---|---|---|---|---|---|
| Unconditional, 2019-2024 | 901 | 45 | +0.1167 | 64.7% | +0.2009 | [+0.071, +0.163] |
| **Rich overlay, 2019-2024** | 271 | 28 | +0.2043 | 70.8% | **+0.3796** | [+0.113, +0.278] |
| Unconditional, OOS 2022-2024 | 515 | 45 | +0.0801 | 61.7% | +0.1388 | [+0.017, +0.145] |
| **Rich overlay, OOS 2022-2024** | 155 | 21 | +0.1855 | 68.4% | **+0.3581** | [+0.067, +0.285] |

All four intervals exclude zero, including out of sample, and the overlay roughly doubles the
unconditional Sharpe in both windows. The return unit is the move-space proxy above, net of the
flat 11.6% cost, **not a real two-leg straddle mark**. The worst single trade is −4.22 and the
maximum monthly drawdown is −88%.

**This result did not survive re-testing on executable marks, and the table above should be
read only as the move-space finding it is.** A single pre-registered test was run against a
frozen specification and a decision rule declared in advance. Two things changed together, and
both were necessary: the payoff moved from the move-space proxy to a two-leg mark from
consolidated quotes at 15:59, and the estimand moved from the overlay's own level to the
incremental advantage over the **eligible** universe,

> delta = E[R | rich overlay] − E[R | eligible universe],

where eligible means the name already has the three priors the signal requires. Testing the
overlay's own interval against zero, as the original study did, tests whether short earnings
straddles pay in absolute terms. That is not the persistence hypothesis, and it is the reason
the original intervals looked decisive.

Executable return on margin, 45 names, three cost arms:

| Arm | Window | N eligible | N overlay | Overlay | Eligible | delta | Name-clustered CI | Date-clustered CI | Two-way CI |
|---|---|---|---|---|---|---|---|---|---|
| gross | 2019-2024 | 716 | 215 | +0.01174 | +0.00530 | +0.00643 | [−0.0034, +0.0164] | [−0.0054, +0.0180] | [−0.0036, +0.0165] |
| gross | **OOS 2022-2024** | 426 | 128 | +0.00689 | +0.00369 | **+0.00320** | [−0.0108, +0.0154] | [−0.0127, +0.0189] | [−0.0104, +0.0168] |
| measured | 2019-2024 | 716 | 215 | +0.00129 | −0.00571 | +0.00701 | [−0.0032, +0.0175] | [−0.0052, +0.0189] | [−0.0036, +0.0176] |
| measured | **OOS 2022-2024** | 426 | 128 | −0.00408 | −0.00781 | **+0.00373** | [−0.0112, +0.0166] | [−0.0126, +0.0198] | [−0.0106, +0.0180] |
| flat 11.6% | 2019-2024 | 716 | 215 | −0.01188 | −0.01901 | +0.00713 | [−0.0033, +0.0176] | [−0.0048, +0.0187] | [−0.0037, +0.0179] |
| flat 11.6% | OOS 2022-2024 | 426 | 128 | −0.01747 | −0.02189 | +0.00442 | [−0.0107, +0.0174] | [−0.0117, +0.0201] | [−0.0102, +0.0191] |

**The sign is right in all six cells and the magnitude is indistinguishable from zero in all
six.** Every interval contains zero under all three clusterings. Out of sample, removing the
single largest contributing name takes the gross advantage from +0.00320 to −0.00029, so what
advantage exists is carried by one name.

Net of measured fixed-boundary execution, neither the eligible universe (−0.0078 out of sample)
nor the rich overlay (−0.0041) is profitable in absolute terms.

**Verdict against the frozen rule: persistence NOT SUPPORTED, tradable persistence NOT
SUPPORTED.** Both fail on the out-of-sample interval; the gross arm additionally fails the
drop-the-largest-name check.

Two observations worth carrying. Cost barely moves the estimate, +0.0064 gross to +0.0071 at
the flat charge, because a proportional cost applied to both groups largely cancels in a
difference; this was predicted in the amendment before the run and is a reason to prefer the
difference as the estimand. And 155 of the full-window and 89 of the out-of-sample events were
unmarkable or sized to zero contracts, roughly 18%, which is a real sample restriction rather
than a rounding effect.

**One breadth result that must not be quoted.** A separate persistence study on a broader free
database reports an unconditional per-trade Sharpe of +0.626 and a rich overlay of +1.144.
Those figures come from a checkpointed build that **stopped part way through the alphabet**,
holding 64 tickers spanning A to CHD. The universe is alphabetically truncated, not randomly
sampled, which is the most likely explanation for Sharpes roughly three times those of the
completed study above. The completed study is the one to cite.

### 6.6 Geography, and the three ways an edge dies

The cross-market work asked one question: is the term-structure effect structural, or is it a
feature of US option microstructure? The engine's chain fetcher is an injected dependency, so
a new market costs one data adapter plus an earnings calendar.

**India is the decisive test and it is negative.** NSE daily bhavcopy, 120 names, 960 events,
per-name panel gate. Gross return on margin is **negative at every threshold from the 50th to
the 95th percentile**, with the least-bad cell around −0.4% **gross, before any cost exists**.
The gate's per-trade Sharpe of −0.55 marginally beats the control's −0.63, a delta of +0.08,
but the size-matched interval of [−0.85, +8.07] swamps it entirely. The result is invariant
across top-30, 91-name and 120-name panels: four ways of asking the question return one
answer. **There is no gross signal for costs to erode**, so no threshold tuning or cost-model
softening can rescue it.

**Brazil has a gross signal that is uninvestable.** B3 end-of-day data, 61 trades. Gross +6.4%
total return, 68.9% hit rate, +2.1% return on margin, beating the control on every
frequency-neutral read. Then the spread arrives: around 24% quoted on these names, a cost drag
of 13.4% of total return, and the book flips to −7.0% total, 50.8% hit, −2.4% return on
margin. Separately, the tradeable single-name option cross-section in Brazil is five to fifteen
heavily correlated names, so the effective number of independent bets collapses and one
idiosyncratic blow-up dominates the book.

**Europe and Mexico were not built.** No free historical single-name option panel exists for
Europe, and Mexico has no liquid single-name options to crush.

**Read together, the three markets are the three canonical ways an edge dies.** No signal at
all (India). A signal entirely inside the spread (Brazil). A signal that survives costs but not
statistics (United States). That pattern is the strongest available evidence that the effect is
weak and probably specific to US microstructure rather than a structural anomaly.
**Geographic expansion is closed.**

### 6.7 The mid-pricing question, asked and answered

The natural objection to the international results is that they die on costs, so what if
everything were priced at the mid?

Mechanically the answer is already in hand, because **the "gross" column of every backtest in
this project is the mid**: each leg is marked at the settlement or closing mark with no spread
applied. So the mid case is known per market. India loses at the mid, because there is no gross
signal to begin with. Brazil needs the literal mid, because its entire edge is the spread it
cannot cross. The US clears the mid but not the significance bar. **Mid-pricing sharpens the
verdict rather than softening it.**

Is the mid realistic? Not as a blanket fill assumption. It assumes capturing the midpoint on
all four legs of the round trip , sell call and put to open, buy both back to close , which is
the price a market maker quotes around, not the price a liquidity taker receives. Working an
order at the mid does not deliver the mid on average, because passive fills are adversely
selected: you are filled preferentially when the market is moving through your price against
you, and you miss the fills you wanted. The exit timing is worst case, unwinding the morning
after the print alongside everyone else short the event, when post-event spreads are widest.
And quotes widen and skew defensively around announcements.

Muravyev and Pearson (*Review of Financial Studies*, 2020) are the honest counterweight:
execution-timing-aware traders pay materially less than the full quoted spread, so the truth is
a **band**, not a point, roughly a quarter to a half of the half-spread for the most liquid US
names, and never zero. This project's own 34,672-print measurement puts the fixed-time end of
that band at the full touch. Two of the three markets carry no bid or ask in the data at all,
so "the mid" there is really a settlement mark that nobody transacts at intraday.

### 6.8 A measured non-issue

**Pricing-model error.** The engine prices European options with zero interest rate and zero
dividend yield. The straddles have one to seven days to expiry, the discount factor over five
days at 5% is 0.9993, and early exercise on a near-the-money short-dated straddle is
essentially never optimal for either leg.

That reasoning was tested rather than asserted. Against a dividend-aware Black-Scholes-Merton
and a Cox-Ross-Rubinstein American binomial, on all 1,051 events at their own parameters and
period-appropriate short rates: **mean error +0.027% of credit, 95th percentile 0.205%, worst
case 0.682%**, against an 11.6% break-even. Separately the volatility inverter is validated
against an independent reference implementation to 1e−10 across a grid of tenors, volatilities,
rates and moneyness.

This is included because it is a dead end of a useful kind: a plausible source of error,
measured rather than argued about, and found immaterial. No change is warranted, and **the
measurement is what licenses saying so**.

---

## 7. Recent work, not yet in any paper

### 7.1 Forecasting the crush rather than gating the event

**The question.** All 1,476 recorded trials asked the same thing: which events should I short?
Term spread, move gate, skew, curvature, smile concavity, vol-of-vol, micro grids, parameter
grids. Every one is a threshold rule on event selection, and that axis is exhausted. Since vega
is the largest positive leg, and the crush **is** the vega leg, a different axis exists:
forecast the magnitude of the crush from information observable at entry, and sort on the
forecast. A continuous forecast is a different object from a threshold, and it uses every
event rather than only the selected ones.

**Why it is economically plausible.** The crush is not mechanical. A clean in-line print lets
the event premium bleed out and the short vega gets paid in full. A result that re-rates
forward uncertainty leaves the back month elevated, the surface shifts rather than collapses,
and the vega is handed back. How much event premium was priced in, how fat-tailed the priced
distribution is, how rich implied sits to realised, the term shape and recent realised
volatility are all observable at entry and might jointly forecast which regime the print lands
in.

**Method.** Expanding-window ordinary least squares of realised crush on five at-entry
features: the implied move, risk-neutral kurtosis, the volatility premium, the term spread, and
trailing realised volatility. Each event is predicted using **only strictly prior events**, and
out-of-sample R-squared is benchmarked against the prevailing mean rather than against zero,
which is the correct null for a forecasting exercise. Coefficients were then fitted on the
2019-2024 and broad-universe data, **frozen**, and applied without refitting to the untouched
quote-marked 2013-2018 block. Cost is charged exactly once at 11.6% of premium. Intervals
resample whole announcement dates.

**A guard was added after the defect in 5.3 was found**: the analysis now raises an error
rather than pooling silently on any event table where implied volatility falls on fewer than
80% of events. Three tables are excluded on that basis with their measured failure rates
recorded.

**Discovery sample, 4,265 events across four tables:**

| Tercile of forecast | N | Dates | Net mean | Hit | Sharpe | Date-clustered CI | Mean realised crush |
|---|---|---|---|---|---|---|---|
| 0 (lowest) | 1,425 | 239 | +0.0247 | 62.4% | +0.088 | [+0.003, +0.046] | +0.170 |
| 1 | 1,418 | 292 | +0.1583 | 79.6% | +0.604 | [+0.139, +0.177] | +0.336 |
| 2 (highest) | 1,422 | 286 | +0.2100 | 89.7% | +1.063 | [+0.195, +0.225] | +0.531 |

**Discard the discovery numbers.** Those four tables show **unconditional** books at +10% to
+17% net per trade at 72-84% hit rates. That is not credible against the settled +0.056 pooled
verdict on the same trade, so the tables are optimistically marked and the +0.2100 is not a
result. Reporting it here rather than deleting it is the point: it is what the analysis
produced, and the reason to reject it is external to the analysis.

**Frozen coefficients applied to the untouched 2013-2018 block:**

| Tercile of forecast | N | Dates | Net mean | Hit | Sharpe | Date-clustered CI | Mean realised crush |
|---|---|---|---|---|---|---|---|
| 0 (lowest) | 348 | 255 | −0.2770 | 37.9% | −0.338 | [−0.369, −0.198] | +0.115 |
| 1 | 330 | 247 | −0.1603 | 54.2% | −0.227 | [−0.237, −0.090] | +0.340 |
| 2 (highest) | 341 | 274 | **−0.0908** | 57.8% | −0.145 | [−0.161, −0.023] | +0.464 |

**Two findings, pointing in opposite directions.**

The forecast carries **real transferable skill**. On the untouched block the predicted-versus-
realised crush correlation is **+0.1663**, and mean realised crush rises monotonically across
terciles from +0.115 to +0.464. Coefficients fitted on one six-year window and one universe
order the crush correctly on a disjoint six-year window with nothing refitted. That is not
noise.

**Nothing clears costs.** Every holdout tercile is negative net, and the best is −0.0908 with
an interval of [−0.161, −0.023] that **excludes zero on the wrong side**. Forecasting the crush
better does not make the trade profitable, because the crush was never the constraint. The gap
risk and the 11.6% round trip are.

**Orthogonality, which was the plan's designated kill switch.** Since the term spread is one of
the five features, the forecast could simply be the frozen gate re-expressed. Dropping the term
spread from the feature set entirely leaves the discovery terciles essentially unchanged
(+0.0165 / +0.1592 / +0.2173), so the forecast is **not** the term gate wearing a new hat.
Residualising the forecast on the term spread, however, **breaks** the monotonicity
(+0.1428 / +0.0835 / +0.1662), which says the term component and the remainder are not cleanly
separable and the joint object is doing the work.

### 7.2 Can option-implied measures sharpen post-earnings announcement drift?

**Answer: no, and not for the reason the idea would fail on its merits.** The option data and
the drift live in disjoint parts of the universe, so the test can never be run on the sample
that matters.

**Design.** Three conditioners were **pre-declared before any was scored**: earnings surprise
scaled by the implied move; the crush residualised on its expected value given at-entry
features; and the ratio of realised to implied move. Each was used to sort forward 60-day
market-adjusted cumulative abnormal returns, with breakpoints set within the announcement
quarter and intervals from a quarter-clustered bootstrap. All three ran; all three are
negative.

Causality holds by construction: the option leg's exit date coincides with the announcement day
for 1,770 of 1,791 merged events and the equity position is entered the following day, so every
conditioner is observable before entry.

**The baseline failed, which voids the test.** The frozen drift primary, standardised
unexpected earnings, is worth +0.545 net calendar-time Sharpe on the full holdout. In this
option-covered subsample it returns −0.0015 with t = −0.23. There is no drift here to condition.

That has two possible causes demanding opposite conclusions, so it was checked rather than
assumed. Running the **identical** construction over the same window on the full CRSP universe:

| Sample | N | Tercile spread | t | p |
|---|---|---|---|---|
| Full universe | 11,944 | +0.0143 | +2.98 | 0.0029 |
| Option-covered names | 1,861 | −0.0014 | −0.20 | 0.84 |
| Non-option-covered | 10,083 | +0.0157 | +2.84 | 0.0045 |

The harness reproduces drift where drift lives. **The null in the option names is the finding,
not a bug.**

**It is size, not option attention.** The tempting story is that option-market attention speeds
the impounding of earnings news and arbitrages the drift away, which Govindaraj, Liu and Livnat
report. That story is **not identifiable in this data**. Across 23,889 events, option coverage
is effectively absent below the fourth market-cap quintile: quintiles one to three contain 1, 2
and 4 option-covered events respectively. In the one quintile where both groups have real
samples, neither spread is significant and neither is their difference. There is no variation
with which to separate option attention from market capitalisation, and size is both the
simpler explanation and the documented one.

**The consequence for a multi-sleeve book.** Drift in this window is a small and mid-cap effect
that clears its costs by an order of magnitude in the two smallest quintiles: +182 and +239
basis points net against median quoted spreads of 18 and 10 basis points. The short-straddle
sleeve can only trade large, liquid, heavily-optioned names. **The two sleeves are structurally
disjoint.** That is genuine diversification, and it also closes the conditioning question
permanently: no amount of additional option data fixes it, because listed options concentrate in
exactly the names where the drift has been arbitraged away or never existed.

**Trial accounting.** This adds three trials to that programme's existing 16, taking it to 19.
Nothing was claimed, so no deflated Sharpe is quoted, but any future positive on that programme
is now deflated against 19 rather than 16. That cost is recorded rather than absorbed silently.

### 7.3 A live forward recorder and a three-week backfill

A cloud-hosted forward recorder now books paper trades daily with no look-ahead, marking from
free retail option chains. **N = 8 completed trades, mean net −0.053.** Far too few for
inference; it is running to accumulate a clean forward record.

One defect fixed before deployment is worth recording. A beverage company's stock split was
being booked as a 52% earnings move, producing a −6.51 trade that dragged the eight-trade mean
to −0.906. A corporate-action guard, comparing the booked entry spot against the same date's
adjusted spot at exit time and re-basing when they diverge by more than 2%, corrects that trade
to +0.310 and the book mean to −0.053. Same class of error as 5.5.

A **three-week backfill** over the same window, explicitly labelled a **backtest** because
entry decisions were made after the outcomes were knowable:

| Book | N | Dates | Net mean | Hit | Per-trade Sharpe | Date-clustered CI |
|---|---|---|---|---|---|---|
| Unconditional | 241 | 13 | +0.1795 | 71.4% | +0.2985 | [+0.091, +0.276] |
| Rich overlay | 81 | 12 | +0.1998 | 74.1% | +0.3512 | [+0.088, +0.320] |

**This does not revive the strategy, and the reasons come before the numbers.** Thirteen date
clusters is far below the 30 to 50 that cluster-robust asymptotics need, so both intervals are
too narrow and both date-level t-tests rest on 13 and 12 observations. Three weeks is under 1%
of the 391-event evidence base. Eleven of thirteen dates were positive, which is what a calm
three weeks looks like, not what a rediscovered edge looks like. **No tail event occurred**:
worst trade −2.70 against the broad historical book's −4.22 and a −88% monthly drawdown, and
the entire risk of this structure sits in a tail these three weeks did not contain. The top
three dates carry 62.1% of P&L on 72 of 241 trades. Twenty of 261 candidate events were dropped
for missing marks, and if those skew toward wider, less liquid names then the survivors are
mildly favourable, which was not quantified.

**One useful by-product.** Seven events appear in both the paid backfill and the free-feed live
recorder. Implied move correlation **0.9993**, mean absolute difference **0.0008**, net return
difference in means +0.0043. **The free marking path is sound**, so a forward test needs no
metered data.

### 7.4 Sequential earnings-season state: not supported

The first test to condition on **time** rather than on the event or the name. If each earnings
season carries a latent shock intensity the option market does not know at the start of the
season, the reporters who have already printed inside a season are a causal read on it, and the
sign of the earnings-volatility premium could differ between a violent season and a calm one.
That is a hypothesis an unconditional short-volatility book cannot express, which is what made
it worth one trial once every unconditional variant had failed.

The state variable, for event *j* in season *q*, over strictly prior events in the same calendar
quarter, is `S = mean( |realised move| / implied move − 1 )`, with a minimum of five priors.
Season is the calendar quarter of the announce date, fixed in advance. The payoff is the
executable return on margin from two-leg 15:59 consolidated-quote marks, gross and net of the
measured fixed-boundary cost model. The specification is a single-predictor regression with no
controls, both series winsorised at the 1st and 99th percentile, 5,000 bootstrap draws, seed 0,
refitting the slope inside each draw.

| Block | Arm | N | Seasons | Slope | Season CI | Two-way CI | R² |
|---|---|---|---|---|---|---|---|
| 2019-2024 | gross | 708 | 24 | **−0.0334** | [−0.1085, +0.0596] | [−0.1182, +0.0513] | 0.0017 |
| 2022-2024 | gross | 365 | 12 | +0.0138 | [−0.0475, +0.0875] | [−0.0622, +0.0897] | 0.0002 |
| 2013-2018 | gross | 826 | 23 | **+0.0916** | [+0.0383, +0.1619] | [+0.0171, +0.1661] | 0.0129 |
| 2019-2024 | measured | 708 | 24 | −0.0340 | [−0.1106, +0.0621] | [−0.1210, +0.0530] | 0.0017 |
| 2013-2018 | measured | 826 | 23 | +0.0943 | [+0.0389, +0.1665] | [+0.0177, +0.1710] | 0.0129 |

The pre-registered rule required the same slope sign in both disjoint blocks, a season-clustered
interval excluding zero on 2019-2024, and a sign not created by the cost model. Only the third
passes: cost moves the slope by under 0.003, as expected of a charge applied to every
observation.

The only interval excluding zero is 2013-2018, under all three clusterings, and it is also the
block whose sign the other contradicts. Positive in 2013-2018 means a violent season so far
predicts *better* subsequent short-straddle returns, so the market over-corrects within a
season; negative in 2019-2024 means season violence persists. These are opposite mechanisms,
not different magnitudes of one. Either 2013-2018 is noise across 23 season clusters, which is
the parsimonious reading given an R² of 0.0129 and the sign flip, or season-state dependence is
real with a regime-dependent sign, which is untradable without knowing the regime and so is the
original problem one level up.

The binding constraint is season count, not event count; 24 clusters is the effective sample
size, and the pre-registration said in advance that a wide interval here should be read as low
power rather than as evidence of absence. Roughly 165 of 873 scorable events in 2019-2024 were
unmarkable or sized to zero contracts, and 81 of 907 in 2013-2018.

### 7.5 Physical earnings covariance: the firm-identity-weighted hypothesis is killed, and reporter count survives as a sufficient statistic

What died is the firm-identity-weighted covariance hypothesis, that *which* firms report,
weighted by anticipated event importance, adds information beyond *how many* report. Reporter
count emerged as a sufficient calendar statistic for the measured physical correlation effect,
and that effect is itself real and large. The section below reports both parts.

A first-stage test of whether scheduled earnings concentration predicts realised co-movement
among index constituents, using **no option data at all**, on the principle that if the
mechanism is absent in the underlying equities no option mispricing of it can exist. Universe:
top 500 US common stocks by market capitalisation ranked on the prior year-end and held fixed
for the following year, weights from the same snapshot, 2010-2024, about 1.86 million name-days
and 23,691 announcements carrying a causal expected event variance.

**The first specification was defective and its output is discarded.** The outcome was the
cross term of a portfolio of market-model residuals. That construction is degenerate: the
cap-weighted top 500 is, to close approximation, the market factor, so cap-weighting residuals
taken against that factor produces a near-zero portfolio and the cross term collapses to minus
the own-variance term. The daily residual portfolio has standard deviation 0.001207 against
0.016900 for a typical single name. Regressing each piece on the earnings load separately gives
+0.9587 for own variance, +0.2302 for the residual portfolio's variance, and the reported
−0.7285 is the exact difference. The defect is provable a priori from the fact that the
residualising factor and the aggregation weights describe the same portfolio, so the run is
discarded rather than reported, and is not charged as a trial.

The corrected specification uses excess returns throughout and takes as its outcome the
dispersion desk's correlation measure applied to realised rather than implied variances:

    rho = ( V_index − Σ w_i² v_i ) / ( ( Σ w_i √v_i )² − Σ w_i² v_i )

Dividing by the correlation-of-one denominator is what makes this a correlation test.
Undivided, weighted own variance is a small fraction of index variance and the regression would
be answering whether earnings season is a high-volatility period. It is, and that is not the
hypothesis. Non-overlapping 5-day windows, quarter-clustered bootstrap, 5,000 draws, seed 0,
two-sided with both signs interpreted in advance. Mean realised correlation is 0.3364.

| Specification | N | Quarters | Slope on load | Quarter CI | R² |
|---|---|---|---|---|---|
| univariate | 754 | 60 | **−5,259** | [−8,329, −2,993] | 0.0146 |
| + reporter count | 754 | 60 | **+315** | [−2,877, +3,498] | 0.0393 |
| + market variance | 754 | 60 | −5,236 | [−8,246, −3,320] | 0.2264 |
| + all controls | 754 | 60 | **+580** | [−4,231, +4,649] | 0.2455 |
| rank load (secondary) | 754 | 60 | −0.147 | [−0.202, −0.094] | 0.0447 |
| sub-period 2010-2016 | 353 | 28 | −31,563 | [−44,290, −19,407] | 0.0545 |
| sub-period 2017-2024 | 401 | 32 | −2,642 | [−4,756, −699] | 0.0068 |
| bellwether windows | 151 | 56 | −1,168 | [−4,318, +1,659] | 0.0032 |

The correlation effect itself is real and economically large, and its sign contradicts the
common-information hypothesis. Realised correlation falls monotonically with earnings activity,
from 0.4064 in windows averaging 1.4 reporters to 0.2783 in windows averaging 106, a drop of
0.128. Earnings are firm-specific information events; names move on their own news and index
correlation falls during earnings season.

**But the driver is the reporter count, not the earnings load.** Regressing realised correlation
on the count alone gives R² 0.0393; adding the load leaves R² at 0.0393 to four decimal places
with a slope indistinguishable from zero. The load quintiles reproduce the count quintiles only
because the two are nearly the same variable, the heaviest-load quintile averaging 94 reporters
against 1.8 in the lightest. That is the pre-registered kill condition, stated before the run:
an effect carried purely by how many names report leaves no scheduled-quantity signal beyond
the calendar itself. Note what this does **not** establish: visibility does not imply correct
pricing, and most scheduled-announcement risk premia rest on publicly known event timing. The
reason to park the count-pricing question is not that the calendar is public but that the
direction is a crowded trade with paid data behind it, addressed below. The bellwether test
agrees with the count reading. Windows in the top quintile of
reporting weight share, where the common-information story should be strongest, give an interval
containing zero and an R² of 0.0032.

Independently, the direction found is the one already traded. Falling implied correlation into
earnings season is the standard long-dispersion expression, and practitioner commentary treats
it as routine; no academic confirmation of the earnings-season index-correlation effect was
located, so that reading is labelled practitioner-sourced. An option-stage test would have to
establish that the market moves implied correlation by the wrong *amount*, against a crowded
trade, which is a far higher bar than the physical test this was designed to precede. Per the
pre-registration, no index or ETF option data is acquired and the relative-variance
implementation is not built.

### 7.6 The forward-variance reset: terminated at the measurement stage, not at the result

The last single-name earnings-option candidate asked whether the announcement jump cancels
from the difference of two total variances, `W_b - W_f`, leaving a forward variance whose
announcement-day change predicts its own subsequent reversal. It is terminated because the
object it is built from cannot be measured on any data obtainable without payment. No return
was predicted, no position was scored, and no trial is charged. Full record:
`outputs/research/fvr_verdict.md`.

Two measurement objections were raised against the first pass and both are conceded. Stage
zero used `W(T) = T * sigma_ATM^2`, which is a summary of one point on the smile rather than
the integral the decomposition `W(T) = C(T) + J` assumes; around an announcement the density
is strongly non-Gaussian and that additivity fails at the measurement rather than in the
economics. And the +0.42 to +0.44 within-name loading did not establish failed cancellation:
under the literal decomposition the same `J` cancels algebraically, so the loading is equally
consistent with true covariance between event magnitude and forward volatility. That reading
is withdrawn. The first objection is now sized rather than argued: where the strip is wide
enough to integrate, model-free variance is a median **1.33 times** the BS ATM total variance.

Rebuilt on the standard model-free strip, the cached chains fail outright. The cache holds a
+/-20%-of-spot band fetched for straddle marking, which is a median **0.56** and **0.84**
units of `sigma*sqrt(T)` on the back leg across the two blocks, and the measure recovers
0.721 of the BS back-month variance against 1.043 on the front. The truncation is
event-size-dependent, which is fatal here rather than merely noisy: corr(coverage, implied
move) −0.669 and corr(recovery, implied move) −0.619, with back-leg recovery falling 0.888 to
0.541 across implied-move quartiles. The model-free diagnostics duly flip against the BS
versions in exactly the direction that bias would push them, so they overturn nothing.

The free feed is materially wider and still short. `scripts/research_fvr_feed_probe.py` fetched
full listed chains for 80 megacap events, 75 resolved, 224 expiries measured: a median 18 to 19
reliable strikes spanning roughly −0.31 to +0.20 in log-moneyness, three expiries inside 120
days and no weeklies. Coverage runs 2.4 to 3.1 units on the put side and **1.7 to 2.1 on the
call side**, which binds everywhere. On the 26 expiries clearing 3.0 units on both sides, the
2.5-unit estimate sits a median **9.55%** from the all-reliable estimate and only 2 of 26 come
inside 5%; the strikes beyond 3.0 units carry a median 7.44% of total variance, which is the
fat tail the non-Gaussian objection predicts, confirmed directly. Events supplying two expiries
alive through +7 that clear 3.0 units on both sides *and* converge: **0 of 75**, a 95% upper
bound of about 4% on the pass rate. The size dependence survives the wider feed at
corr(coverage, implied move) −0.399. The sample is megacap, so this is an upper bound on the
free feed rather than a typical case.

The distinction worth carrying: the FVR is **untestable on obtainable data**, not falsified.
Nothing has been shown about whether the jump cancels. The question was never reached, and
paying for wider chains would buy the ability to establish whether the signal can be
*measured*, one stage before establishing whether it exists. What is carried forward instead is
delayed back-month and post-earnings implied-volatility reversal, as a separately named modern
executable replication rather than a novelty claim, inheriting none of the FVR's
pre-registration.

---

## 8. Screening beyond the crush: results in hand

A successor programme scores candidates through **one common contract** with a
**pre-registered trial ledger** written before anything is run. That ledger is the single
control that would have caught this project's original false positive, and it cannot be
assembled honestly in retrospect. The harness is validated by re-scoring the settled crush book
through it and reproducing N = 391, pooled Sharpe +0.055992 and the interval [−0.0421, +0.1803]
exactly, before any unknown candidate is scored. A gross-first gate establishes whether a signal
exists before any cost model is applied, because the cross-market work established that this
ordering is what separates "no signal" from "signal inside the spread".

### Index variance risk premium timing: negative out of sample

**Fifteen specifications pre-registered before any was run.** Variance risk premium as squared
VIX minus realised variance, monthly, following Bollerslev, Tauchen and Zhou (*RFS*, 2009),
regressed against forward cumulative excess returns at horizons of 1, 3, 6, 12 and 24 months
over a 420-month panel, 1990-01 to 2024-12.

Two deviations stated in advance. Realised variance is built from **daily** rather than
five-minute returns, which the authors state their results depend crucially on, so the
replication is attenuated by construction. Standard errors are Newey-West at lag equal to the
horizon rather than Hodrick, which is the less conservative choice, so the t-statistics should
be read as an upper bound.

| Window | h = 1m | h = 3m | h = 6m | h = 12m | h = 24m |
|---|---|---|---|---|---|
| Original 1990-2007 (N = 216) | +1.69 | **+3.67** | +3.20 | +1.80 | +1.53 |
| Extended 1990-2024 (N ≈ 415) | +0.36 | +0.70 | +0.54 | −0.50 | −1.04 |
| Post-sample 2008-2024 (N ≈ 195) | +0.24 | +0.50 | +0.30 | −1.03 | −1.42 |

Newey-West t-statistics. Adjusted R-squared at the quarterly horizon across the three windows:
5.41%, 1.18%, 0.72%.

**The original window replicates**, at t = +3.67 and adjusted R-squared 5.41% against the
paper's reported t = 2.86 and 6.82%, attenuated exactly as the daily-realised-variance
substitution predicts, with a matching horizon profile. That is the harness validation: the
screen recovers a documented effect on the window where it was documented.

**The effect does not survive.** Nothing is significant at any horizon post-sample and the slope
turns **negative** at 12 and 24 months. Sign instability rather than mere attenuation is the
strongest evidence against a surviving effect: a decayed but real premium shrinks towards zero,
it does not flip.

**Placebo check.** Boudoukh, Richardson and Whitelaw argue that R-squared rises with horizon by
construction when a persistent predictor meets overlapping returns, and the original paper
acknowledges this without neutralising it. Each cell was therefore re-run against 200 AR(1)
placebo predictors matched to the variance risk premium's own persistence but independent of
returns. On the original window the real R-squared clears the placebo 95th percentile at every
horizon except 24 months, so the in-sample finding is not merely an overlap artefact. **On the
post-sample block no horizon clears its placebo band.** One apparent exception, the
extended-window three-month cell where R-squared of 1.18% exceeds a placebo 95th percentile of
0.90% while the t-statistic is only +0.70, is a reminder that R-squared and slope significance
can disagree under overlap, and the insignificant slope is the figure to believe.

**Disposition: do not pursue as a standalone strategy.**

### PEAD on standardised unexpected earnings: directionally positive, not established

Primary specification frozen before the programme began: long the top decile and short the
bottom decile of standardised unexpected earnings, with breakpoints from the four completed
calendar quarters strictly before the event's own quarter, entered at day zero plus one, held
60 trading days, overlapping cohorts, equal-weighted, net of round-trip equity costs. The fit
period 1996-2011 sets nothing; the holdout 2012-2024 is the only test that counts.

| Basis | Period | N | Hit | Mean trade | Calendar-time Sharpe | Carhart alpha | NW t |
|---|---|---|---|---|---|---|---|
| net | fit 1996-2011 | 19,214 | 50.5% | −0.000936 | −0.201 | −2.52% | −1.61 |
| net | **holdout 2012-2024** | 19,620 | 51.1% | +0.006267 | **+0.545** | +2.51% | +1.65 |
| gross | holdout 2012-2024 | 19,620 | 51.6% | +0.008232 | +0.692 | +3.39% | +2.23 |

**Here the √252 factor is correct**, unlike the event-book case: overlapping 60-day cohorts
produce a genuine daily calendar-time return series with 3,269 daily observations in the
holdout. Same factor, applied to a case where it is right, and the difference is worth
internalising.

**Three tests disagree, and the disagreement is the finding.** The date-clustered bootstrap on
mean net return gives a holdout interval of [+0.00306, +0.00960], **excluding zero**. The
Carhart four-factor alpha on the calendar-time series gives t = +1.65 net, which does **not**
clear 5%, reaching +2.23 gross. The Deflated Sharpe against the 16 trials in the sweep is
**0.0597**.

The bootstrap treats each trade as a unit and overstates precision on a book with overlapping
60-day holds and heavy announcement-date clustering. The calendar-time alpha is the more
appropriate test because it prices factor exposure and handles the overlap, and it does not
clear. The DSR settles it: against the search actually made, a holdout Sharpe of this size is
consistent with the best of a no-edge family.

**What is genuinely unusual: the sign flips the right way.** The fit period is negative and the
holdout positive, which is the **opposite** of the classic overfitting signature where the fit
sample looks good and the holdout collapses. Nothing was tuned on the fit sample, so this is not
a fitted result that failed to generalise; it is a specification that did nothing for fifteen
years and then did something for thirteen. Either the anomaly genuinely strengthened post-2012,
against the published consensus that it decayed, or the holdout block is a lucky draw, which a
DSR of 0.0597 says is entirely plausible. The honest position is the second with the first left
open. Costs also nearly halved between periods, 28.1 to 16.2 basis points median round trip,
which is a real feature of US equity execution over that span, so some of the improvement is
cost compression rather than signal.

**Disposition: attack the DSR, not the point estimate.** The trial count of 16 is what is
killing it. A single pre-declared specification tested once on data not yet touched would carry
far less deflation. Freeze the 60-day horizon and the surprise construction now, and test only
that, once, on a future block.

### The de-eventised term slope: blocked as specified

Vasquez defines the volatility term-structure slope as long-dated minus one-month at-the-money
implied volatility, and finds it predicts straddle returns with a long-short of +16.5% per month
at t = 10.02. This project's gate is the **event-conditional special case** of that signal, and
it sold straddles on exactly his short leg.

Testing the de-eventised version on free data is blocked. The available free option database
carries **exactly three expiries per snapshot**, consistently at roughly 14, 28 and 49 days,
verified directly across multiple tickers and dates. There is no long-dated leg, so the widest
constructible spread is a short-dated one and must not be reported as a replication of the
published result.

The builder and scorer were nonetheless written and validated end to end against the 14/28/49-day
reality, with mid-priced and full-touch arms scored side by side so that the literature's cost
assumption is tested rather than inherited. A smoke test verified the two non-obvious
constructions the free path requires rather than assuming them. Spot recovered by put-call
parity, since the free adapter returns no underlying price, gave AAPL 172.5 and MSFT 111.0 on
2019-02-28, both within about a dollar of the actual closes. And the slope measures what it
should: AAPL on its 2019-04-30 reporting date shows front implied volatility of 33.4% against
back of 23.8%, a slope of −9.5%, which is exactly the inverted term structure the crush gate
triggered on, now measured off the event calendar rather than on it.

The full 70-name, 70-month panel is roughly 4,900 requests at about 0.2 per second, so about
seven hours. Free, checkpointed and resumable.

**This is the highest-information experiment identified anywhere in this record**, because it is
the only test that separates two hypotheses this project cannot currently distinguish: **the
term signal is empty**, or **the earnings event was the problem**. Same signal, same direction,
same construction, event removed.

---

## 9. Assumptions still open

Sixteen assumptions are registered with what was assumed, why, what was done to test it, and
what remains unaddressed. Ranked by what a sceptic should attack first:

**The stale entry spot.** Measured, unrepaired beyond one channel, and it touches the gate. The
only open item that could move a headline by a material fraction. See 5.4.

**The margin convention.** The `0.20 × spot + premium` approximation has never been validated
against a broker. Portfolio margin, which most institutional accounts use, would give a
materially smaller requirement and therefore a higher return on margin without changing any
P&L. Since return on margin is the headline unit, **every return level in this document is
contingent on an unvalidated margin convention.** Relative comparisons against the control are
unaffected, because both use the same convention, so this can change every level but not the
sign of anything.

**Market impact and capacity.** Absent entirely. The execution study measures **prevailing
spreads**, not what happens when this strategy's own order arrives. On a two-contract position
in a mega-cap weekly that is probably immaterial; at any size an allocator would care about it
is not, and no capacity analysis exists.

**No intraday path.** The position is observed exactly twice, at entry close and exit close.
This is why the hard stop cannot be tested, why intraday entry timing is untested, and why the
overnight gap being unhedgeable is an assumption rather than a measurement. For an after-close
announcement it is close to a fact; for a **before-open** announcement there is a
post-announcement session in which some of the move is genuinely tradeable, and the book does
not distinguish the two cases in its risk treatment.

**The term statistic is model-derived.** The strategy's P&L never passes through Black-Scholes,
being the difference of two observed straddle marks, but the **gate statistic is a difference of
two inverted volatilities**. A model misspecification affecting the two expiries differently
would bias the gate. This has never been separately tested, and the natural test, recomputing
the gate under an alternative pricing model, has not been run.

**Independence across concurrent trades.** The cluster bootstrap resamples whole announcement
dates, which handles same-day clustering. Cross-name correlation beyond that is not accounted
for: two technology names reporting three days apart in the same earnings season are not
independent draws.

**Integer position sizing.** Events on the highest-priced names size to zero contracts and
vanish from the book. That is a selection on price level, which correlates with volatility
level. It is small, and it is a real reporting gap.

**Return on margin is not a portfolio return.** A book committing 5% of the account per position
and holding a handful concurrently is nowhere near fully invested, so the return on account is
far lower than the return on margin, and idle capital's return is not modelled. The annual
return on account is **0.99%**, and it is reported alongside the return on margin precisely
because the two are so different.

**What is deliberately not on this list: more events, and better fills.** Both were the obvious
objections, both were treated as decisive by earlier versions of this work, and both were closed
by direct measurement: N = 391 against a demanded 356, and an execution study worth 0.007 of
per-trade Sharpe.

---

## 10. What this record suggests for new ideas

Three findings, not preferences, constrain the search.

**One. Do not pivot back into single-name idiosyncratic variance.** Carr and Wu found
single-name variance risk premia insignificant for 32 of 35 stocks. This project is the purest
possible short of exactly that, at event frequency. **It did not fail; it replicated a known
result.** Any candidate whose economic content is "sell single-name volatility" is already
answered.

**Two. The measured execution constraint should select the next trade rather than be
rediscovered by it.** Median price improvement of zero, with 54% of prints paying the full
touch, is a measurement most researchers do not have. It disqualifies **in advance** any
candidate requiring many single-name option legs. Dispersion trading proper is the clearest
casualty: its whole construction multiplies the one thing known to be binding.

**Three. The term gate is the event-conditional special case of an anomaly that works.**
Vasquez's slope predicts straddle returns at +16.5% per month and t = 10.02, and this book sold
straddles on exactly his short leg. **The direction was right.** What the project added was the
earnings event, and with it the gap risk that makes single-name event variance fairly priced.
Whether removing the event is what makes the signal pay is the open question this entire record
points at.

### The candidate landscape

**Free, decades of history, full cross-section:** post-earnings announcement drift on
standardised unexpected earnings (Ball and Brown 1968; Bernard and Thomas 1989) , *result in
hand, section 8*; the earnings announcement premium, that scheduled announcers earn more
(Frazzini and Lamont); index variance risk premium timing (Bollerslev, Tauchen and Zhou 2009) ,
*result in hand, negative*; analyst dispersion and revision (Diether, Malloy and Scherbina
2002); a volatility-managed portfolio overlay (Moreira and Muir 2017, with the real-time
implementability critique).

**Free and broad but limited to roughly 2019-2024:** the de-eventised term slope (Vasquez) ,
*blocked as specified, section 8*; the implied-minus-realised volatility sort (Goyal and
Saretto, *JFE* 2009); put-call parity deviations (Cremers and Weinbaum, *JFQA* 2010); the
volatility smirk (Xing, Zhang and Zhao, *JFQA* 2010); implied-volatility changes (An, Ang, Bali
and Cakici, *JF* 2014); delta-hedged gains (Bakshi and Kapadia, *RFS* 2003); risk-neutral
moments (Bakshi, Kapadia and Madan 2003).

**Free but narrow, or needing a new data adapter:** volatility information transfer across
industry peers (Hann, Kim and Zheng, *RAS* 2019); announcement-density-conditioned implied
correlation expressed in index options only (Driessen, Maenhout and Vilkov, *JF* 2009) ,
*physical stage now run, section 7.5, and it narrows the question rather than settling it*; the
pre-announcement implied-volatility run-up (Patell and Wolfson; Dubinsky et al.); crush
completeness conditional on the surprise; the variance term premium via calendar spreads
(Dew-Becker, Giglio, Le and Rodriguez, *JFE* 2017); the skew premium around earnings; VIX
futures term-structure carry.

**Blocked or disqualified.** Dealer gamma and hedging demand (Baltussen, Da, Lammers and
Martens, *JFE* 2021; Ni, Pearson, Poteshman and White, *RFS* 2021) requires open interest by
strike, which the free database does not carry and which would be metered otherwise: blocked by
budget, not by merit. Tail and jump risk premium (Bollerslev and Todorov 2011) is real and
large, but short out-of-the-money index puts is the most crowded position in finance and the
payoff shape is the one this project's drawdown work already flagged as unallocable.
Demand-based option pricing (Garleanu, Pedersen and Poteshman 2009) is the least crowded of the
set and the most data-differentiated, through public exchange customer-class data, but it
explains the **level** of option prices better than it **times** them, so it is best used as a
robustness check on the implied-correlation candidate. Dispersion trading is disqualified by the
measured touch cost. Lottery demand is heavily decayed. Deep hedging is a hedging method, not a
source of edge.

### Four observations for whoever picks this up

**The unrun candidates that would settle the most.** The de-eventised slope separates "the term
signal is empty" from "the earnings event was the problem". Implied correlation against
announcement density is the only candidate whose execution is **unambiguously survivable**,
because it expresses everything in index options where the measured single-name touch cost does
not bind, and it asks whether implied correlation prices the known, scheduled quantity of
upcoming idiosyncratic variance or only the quarterly seasonal. **Its physical stage has now
been run and the answer changes the question.** Realised correlation does fall with announcement
density, monotonically and by 0.128 from the quietest to the busiest windows, but the effect is
carried entirely by the *count* of reporters and not at all by their expected event variance
(section 7.5). So there is no scheduled-quantity signal to be mispriced beyond the calendar
itself, and the surviving option-stage question is the narrower and harder one of whether
implied correlation prices the reporter count by the wrong *amount*, against a crowded
long-dispersion trade that already expresses the direction. That is worth asking, but it is no
longer the clean two-stage test it looked like. And the **pre-announcement
run-up removes the gap risk entirely**: own the vega ramp into the print and exit **before** the
announcement. If this project's diagnosis is right, that the crush is real and the gap is what
makes it unprofitable, then the leg of the trade that does not carry the gap is the one worth
examining, and it has never been tested.

**Volatility information transfer is the least crowded idea on the list, and the reason is a gap
between two literatures.** Hann, Kim and Zheng establish, on 3,030 firms and 217 industries from
1996 to 2017, a significantly positive association between a first announcer's implied-volatility
change and its industry peers'. That is an accounting paper about information transfer: it tests
**no trading strategy and no return predictability**. The tradeable question, whether the implied
move charged to a later reporter is stale with respect to peer information already revealed, is
not asked. The mechanism is established and the options literature has not absorbed it into a
return prediction. One detail from that paper is worth carrying regardless: between 25% and 35%
of first announcers show **increases** in implied volatility, so the transfer is not uniformly
uncertainty-resolving.

**Sample-period overlap is severe and it cuts both ways.** Goyal and Saretto run 1996 to
mid-2005, Vasquez from 1996, Hann-Kim-Zheng 1996 to 2017, Bollerslev-Tauchen-Zhou 1990 to 2007.
The free option data available here, 2019 to late 2024, overlaps **none** of them. Every options
test is therefore an out-of-sample test on a later regime rather than a replication, which is a
strength for inference and a weakness for power.

**Two of the candidates are not independent tests.** Vasquez reports that his slope is 46.3%
correlated with the Goyal-Saretto measure and 29.2% with idiosyncratic volatility minus
one-month implied volatility. Those two are close to the same bet and must be tested jointly
with the incremental contribution of each reported, or the trial ledger will overstate how many
independent shots were taken.

**The differentiation answer for the whole options-anomaly family.** These would not be
replications. The contribution is re-scoring documented option anomalies on **measured rather
than assumed execution**, using a 34,672-print measurement the original authors did not have,
against an assumption those papers rely on and this project has directly contradicted. A
negative result is publishable and a positive one is a genuine finding.

---

## 11. Concrete next steps, ranked by information per unit of effort

1. **Run the de-eventised term slope on the 14-versus-49-day construction**, labelled as what it
   is rather than as a replication. About seven hours of free, resumable requests, and it
   answers the question the whole record points at.
2. **Test conditional hold-to-expiry as a cost lever rather than a risk lever.** Crossing the
   spread once instead of twice takes the round-trip break-even from 11.6% to roughly 5.8%,
   which is the largest single available attack on the binding constraint. Requires no new data.
3. **Filter on measured spread rather than on signal.** All 1,476 trials gated on signal
   variables; **not one gated on cost**, despite a 34,672-print spread measurement being
   available to build a per-name spread percentile from. The obvious counter-argument, that
   tight-spread names are the liquid mega-caps which may also be the most efficiently priced, is
   testable rather than assumed.
4. **Finish the stale-spot repair.** Rebuild the event set and re-mark so that strike selection,
   marks and sizing all use the corrected entry spot, not only the gate statistic. Needs a
   modest metered pull.
5. **Re-test the curvature gate on consolidated-quote surfaces.** It failed for a measurable
   data-quality reason, and the data that would fix it is now known to exist back to 2013.
6. **Point-in-time universe reconstitution.** Only needed to defend a positive result; the
   direction argument in section 2 suffices for a negative one.

**Closed since this list was written.** Sequential earnings-season state (section 7.4) and the
physical earnings-covariance mechanism (section 7.5) were both proposed as cheap pivots away
from single-name selection, and both are now run and negative. Neither should be re-attempted in
the form specified. The forward-variance reset (section 7.6) is closed on a different footing:
untestable rather than negative, because no obtainable option strip is wide enough to measure a
converged model-free variance at the back expiry. Anyone tempted to revive it should read that
section first, since the failure is a strike-width constraint that no amount of additional
events relieves. Its successor, a separately named replication of delayed back-month and
post-earnings implied-volatility reversal, is not yet specified or run. The frozen strategy constants and the two baseline reconciliation targets now
live in one module, and a research harness that cannot reproduce N=198 / +0.087393 on 2019-2024
or N=193 / −0.005337 on 2013-2018 raises rather than returning a plausible-looking number.

---

## References

Alexiou, L., Goyal, A., Kostakis, A., and Rompolis, L. (2025). Pricing event risk: evidence from
concave implied volatility curves. *Review of Finance*.

Bakshi, G., and Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk
premium. *Review of Financial Studies*, 16(2), 527-566.

Bernard, V. L., and Thomas, J. K. (1989). Post-earnings-announcement drift: delayed price
response or risk premium? *Journal of Accounting Research*, 27, 1-36.

Bollerslev, T., Tauchen, G., and Zhou, H. (2009). Expected stock returns and variance risk
premia. *Review of Financial Studies*, 22(11), 4463-4492.

Carr, P., and Wu, L. (2009). Variance risk premiums. *Review of Financial Studies*, 22(3),
1311-1341.

Goyal, A., and Saretto, A. (2009). Cross-section of option returns and volatility. *Journal of
Financial Economics*, 94(2), 310-326.

Hann, R. N., Kim, H., and Zheng, Y. (2019). Intra-industry information transfers: evidence from
changes in implied volatility around earnings announcements. *Review of Accounting Studies*, 24,
927-971.

Khan, S., and Khan, Z. (2024). Trading the implied volatility crush after earnings
announcements. Working paper.

Muravyev, D., and Pearson, N. D. (2020). Options trading costs are lower than you think. *Review
of Financial Studies*, 33(11), 4973-5014.

Patell, J. M., and Wolfson, M. A. (1981). The ex ante and ex post price effects of quarterly
earnings announcements reflected in option and stock prices. *Journal of Accounting Research*,
19(2), 434-458.

Vasquez, A. (2017). Equity volatility term structures and the cross-section of option returns.
*Journal of Financial and Quantitative Analysis*, 52(6), 2727-2754.
