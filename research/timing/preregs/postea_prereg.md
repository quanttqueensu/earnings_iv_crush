# Pre-registration: post-earnings volatility overpricing, incremental to the same name's ordinary options

Frozen before any post-announcement straddle is priced. One test, two control estimands,
no variants. This is the final trial in the single-name earnings-volatility family.

## 1. Hypothesis

After an earnings announcement the information event is over, but earnings-related option
demand may persist. Retail buyers concentrate purchases ahead of high-expected-volatility
announcements and do not close positions until weeks afterwards (de Silva, Smith and So,
*Review of Finance* 2026), and option traders overestimate future volatility after recent
announcements, increasingly so with the size of the surprise (Chung and Louis, *Journal of
Empirical Finance* 40, 2017, 220-235). If residual demand leaves ordinary post-event
volatility rich, a short straddle entered after the event and held to expiry earns more
than the same name's ordinary short-volatility opportunity.

The competing explanation is that post-event implied volatility is elevated because
realised risk genuinely remains elevated. Alexiou, Goyal, Kostakis and Rompolis (*Review of
Finance*, 2025) show pre-announcement surface characteristics predict higher realised
volatility for ten days after the announcement, so elevated post-event implied volatility is
not automatically irrational. The test is therefore explicitly incremental, not a level test.

**This is not a novelty claim.** It is a modern, executable replication of a documented
anomaly, asking whether it survives real spreads for a liquidity taker.

## 2. Estimand

The primary quantity is the incremental short-straddle return, not the level:

    Delta_i = R_short(post-EA, i) - R_short(matched control, i)

Short options carry a volatility premium in general, so a positive level would establish
nothing. Two control estimands are computed and **reported separately**. They are not
averaged, pooled, or combined into a single headline under any outcome.

* **Control A, same name, non-event.** The same ticker, entered on a date at least 25
  business days from any announcement of that name, with no announcement inside the option's
  life. Isolates the post-event effect from the name's own ordinary volatility pricing.
* **Control B, same calendar date, cross-name.** A different name entered on the same
  calendar date, outside its own announcement window (defined as 5 business days before to
  25 business days after any of its announcements). Neutralises the calendar-regime
  asymmetry that Control A cannot: post-event windows fall inside earnings season by
  construction, while a same-name non-event window falls between seasons, when single-name
  volatility and index correlation are both in a different regime.

If A and B disagree in sign, that disagreement is the reported finding and no combined
estimate is produced.

## 3. Data

* **Calendar.** Compustat `fundq.rdq` for the announcement date, session from the I/B/E/S
  `act_epsus` announcement time. **Only events whose session comes from a real I/B/E/S
  timestamp are eligible**; events with a defaulted session are dropped, not carried. On the
  2019-01-01 to 2024-10-31 window above a $2,000m peak market-cap floor this leaves 45,606
  events over 2,412 names, 80.9% of the raw calendar.
* **Chains.** The free DoltHub `dolthub/options` database, which carries real bid and ask
  rather than a close stamped on both sides. Window ends 2024-10-31 because the feed's
  coverage does, verified by direct probe: a liquid name resolves on 2024-10-15 and returns
  nothing on 2024-11-15. Chains list a monthly ladder, no weeklies.
* **Equity.** Free daily bars for settlement, dividends and the announcement-day move.
* No metered data is used anywhere in this test.

The window is chosen for executability over recency. The alternative free feed reaches 2026
but serves bars only, so every spread would be zero by construction and the test could not
address whether the effect survives for a liquidity taker, which is its entire point.

## 4. Construction

**Announcement session.** `t0` is the first regular session close that fully reflects the
announcement: `announce + 1` business day for `amc`, the announce date itself for `bmo` and
`dmh`. In the convention used in correspondence, `t0` is "+1".

**Entry.** Close of `t0 + 1` business day, that is "+2". Fixed and causal; no signal is
computed and no event is selected on anything observable at entry.

**Contract.** Short ATM straddle, one call and one put at the single strike closest to the
forward recovered from put-call parity at that expiry, `r = 0` by project convention. Fixed
strike; the strike is never re-picked.

**Expiry.** The listed monthly expiry falling in the frozen 20 to 45 calendar-day band.
Where more than one qualifies, the nearer. Where none qualifies, the event is dropped and
counted in the funnel.

**Exit.** Expiration settlement at `|S_T - K|`, de-adjusted to the strike's raw price scale.
No exit transaction and therefore no exit spread, which is the reason Chung and Louis used
settlement and the reason this design does.

**Execution.** Entry sells both legs **at the bid**, as a liquidity taker crossing the full
half-spread. No midpoint anywhere. The quoted relative spread at entry is recorded per
observation and reported separately from the return.

**Return unit.** Return on Reg-T straddle margin, `0.20 * spot + premium`, consistent with
the rest of this project. Per-trade, never annualised by a trade-count factor.

## 5. Frozen strata

The feed lists monthlies only, so which expiry falls in the 20 to 45 day band is determined
by where the announcement sits in the monthly cycle rather than chosen. DTE is therefore a
calendar-cycle variable and is frozen into three strata now, before any result is seen:

    S1: 20 <= DTE < 28      S2: 28 <= DTE < 36      S3: 36 <= DTE <= 45

Results are reported within stratum as well as pooled. A result carried by one stratum is
reported as such.

## 6. Matching

Controls are matched within the same DTE stratum, then on nearest Mahalanobis distance over:

1. log-moneyness of the strike against the parity forward;
2. straddle premium as a fraction of spot;
3. quoted relative bid-ask spread of the straddle at entry.

Matching on the spread is deliberate: without it, the post-event arm could differ from its
control purely because attention makes post-earnings options more liquid, which would be a
liquidity result wearing a volatility label. Match quality is reported as the standardised
mean difference on each variable, before any return is read.

## 7. Exclusions, applied before any return is computed

* Any announcement of the same name inside `[entry, expiry]`. The test is about the period
  after an event, not across the next one.
* Non-standard deliverables, proxied because the feed carries no deliverable flag: the strike
  ladder must be regular, and the parity forward must sit within 5% of the equity close.
  Failures are counted, not silently dropped.
* Fewer than 5 reliable strikes at the expiry, or no strike within 5% of the forward.
* Ex-dividend inside the option's life is **flagged, not excluded**. The full result and the
  ex-dividend-free subset are both reported.
* Early-assignment exposure on the short call is flagged where an ex-dividend falls inside
  the life. The affected share is reported, and a bound is reported assuming assignment on
  the ex-dividend date for that subset.

Every filter reports a funnel count. A filter that silently empties the sample raises.

## 8. Inference

Positions entered at `t0 + 1` and held 20 to 45 days overlap heavily, so event-level
inference alone would overstate precision.

* **Event level.** Mean `Delta` with 95% intervals from a cluster bootstrap, 5,000 draws,
  seed 0, clustered on entry date, on name, and two-way via `V_a + V_b - V_iid`. The widest
  of the three is the reported interval.
* **Calendar time.** An equal-weight portfolio holding every live position each session,
  daily return on aggregate margin. Because this series is genuinely daily, its Sharpe is
  annualised by `sqrt(252)` and is labelled as annualised; the event-level Sharpe is
  per-trade and is never annualised by a trade-count factor. Both are reported; they measure
  different things and are never compared as if they were the same number.

## 9. Decision rule, fixed in advance

**Primary.** `E[Delta] > 0` with the reported interval excluding zero, under **both** control
estimands, and in the same direction.

* Passes under both: the effect is established at this sample size and the trade is costed
  and taken to a capacity and sizing assessment.
* Passes under one only: reported as unresolved, with the disagreement as the finding. It
  does **not** count as support and no further variant is run to break the tie.
* Fails under both: **single-name earnings volatility is closed.** No further filter,
  threshold, structure, or universe is tried in this family. The programme is written up as
  a negative.

**Secondary, one only.** Does `Delta` increase with the magnitude of the preceding earnings
shock? The shock is `|day-0 excess return| / trailing 20-day realised volatility`,
standardised within the sample. Reported as a single continuous slope with its clustered
interval. **No threshold is fitted and no cut is optimised.** A positive secondary result
does not rescue a failed primary.

## 10. Trial accounting

One trial, charged against the recorded count of 1,476 regardless of outcome. The Deflated
Sharpe is reported against 1,477 on the primary result.

## 11. Sample

1,200 post-announcement events drawn at random from the 45,606 eligible, seed 0, before any
pricing. The draw is fixed at this size by the free feed's per-query cost, not by any
inspection of results. Power: with a paired standard deviation near 0.17 in return on
margin, 1,200 pairs detect a mean `Delta` of about 0.014 at 80% power and 5% two-sided
before clustering, and materially less after. A wide interval on this sample is to be read
as low power, not as evidence of absence, and that reading is fixed here in advance.
