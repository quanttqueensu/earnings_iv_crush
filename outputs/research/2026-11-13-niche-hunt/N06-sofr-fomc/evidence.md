# N06 SOFR options around FOMC decisions: evidence dossier

## Hypothesis, scope and success criteria

Hypothesis: buyers of CME SOFR options pay a premium for protection against FOMC surprises, so
selling short-rate variance across a scheduled decision earns more than selling it across an
ordinary day, and enough more to clear the spread at the touch. Scope: CME options on 3-month
SOFR futures (quarterly, serial and mid-curve, including weekly mid-curves) around scheduled FOMC
decisions, 2023-2026, at zero data cost. Success, per the brief: a tested candidate on real data,
or a sourced case for or against a priced metered pull.

Outcome: the free-data pilot fails its frozen held-out read and is underpowered by construction.
The closest prior work finds a large premium at settlement on Eurodollar options and says the
spread would eat most of it. Viable pending a priced data pull, for one vehicle only (below).

## 1. Prior work

**Closest paper: Bauer, Lakdawala and Mueller**, "Market-based monetary policy uncertainty",
FRBSF WP 2019-12, published in the Economic Journal 132(644), 2022, 1290-1308 (verified, working
paper read). Appendix C, Table C.3 covers 197 scheduled FOMC meetings, 1994 to September 2020,
excluding July 2007 to June 2009. An at-the-money Eurodollar straddle held from the close before
the meeting to the close of the meeting day loses on average:

| Contract | ED1 | ED2 | ED3 | ED4 | ED5 | ED6 |
|---|---|---|---|---|---|---|
| Mean, % of premium | -9.1 | -4.5 | -3.0 | -2.3 | -2.1 | -1.6 |
| SD, % | 11.9 | 6.1 | 4.5 | 4.1 | 3.7 | 3.3 |
| t | -10.8 | -10.5 | -9.2 | -7.8 | -8.0 | -6.8 |

In absolute terms the loss is 1.3 to 1.4 bp per meeting (t -7.9 to -10.2). The seller's
per-trade Sharpe is about 0.76 for ED1 (9.1 / 11.9). The paper's √8-annualised figures are not
quoted here. Prices are daily settlements. The authors do not net costs, and write that quoted
spreads "on the order of 0.5 to 1.0 basis points ... would seem to eat up most of the returns".
They also report that the implied FOMC jump volatility (9 to 20 bp) is far above the realised
FOMC-day volatility of 3-month LIBOR (about 1.5 bp), and that uncertainty falls by 1.6 bp on
average at 82% of 229 announcements.

**Wright, "Event-day options"**, NBER WP 28306, published in the Journal of Time Series Analysis
46(6), 2025 (verified). It uses Wednesday and Friday weekly options on Treasury and S&P futures,
2017 to 2020 for FOMC. Of the FOMC-induced implied variance, about half is variance risk premium
for 5- and 10-year futures, and most of it for 30-year. Settlement prices, no costs. Two-year
weeklies were too illiquid to use (2019 ADV 142, settlements at the minimum tick). SOFR is not
covered.

**Crowding.** The FOMC uncertainty decline is well documented (Bauer et al.; Beber and Brandt
2006, recalled; Ederington and Lee 1996, recalled). The straddle-return evidence on STIR options
is one appendix in one paper, on the LIBOR-era contract, at settlement. No paper found measures
it on SOFR options or at the touch, so the trade is not crowded in the literature. That is weak
evidence about the market, because the desks that trade STIR vol around FOMC do not publish.

## 2. Mechanism and timing

Who pays: hedgers of policy-path risk (mortgage servicers, liability hedgers, macro funds) buy
SOFR options before meetings. Dealers who are short gamma into a binary-like decision demand
compensation (Bauer et al.'s jump-risk-premium reading; conjecture as to who holds which side).
The FOMC statement is released at 14:00 ET and the press conference starts at 14:30 ET (recalled).
SR3 futures settle on Globex activity between 13:59 and 14:00 CT, i.e. 14:59 to 15:00 ET, and
options settle off them (CME settlement procedures, secondary). So the meeting-day settlement sees
the statement and the first half hour of the press conference, and the rest falls into the next
day. Unlike earnings after the close, the event lands mid-session in a market open nearly 23 hours
a day. A seller can be in at the touch minutes before 14:00 ET and out after the press conference.

## 3. Tradability at IB

- Products (CME Submission 19-366 to the CFTC, January 2020, verified). Quarterly options are
  listed on the nearest 16 quarterly months, plus serials and mid-curves. Weekly 1, 2 and 3-year
  mid-curves expire on any Friday not used by a standard expiry. Standard expiries fall on the
  Friday before the third Wednesday, so the Friday after an FOMC Wednesday is in practice always
  a weekly, and a weekly expiring two days after the decision exists. American style, last trade
  typically 16:00 on the last day, USD 2,500 per point (1 bp = USD 25).
- Premium tick (same filing). 0.0025 points (0.25 bp) for the nearest quarterly on the nearest
  monthly expiry, and for premiums of 0.05 or less on near contracts. 0.005 points (0.5 bp)
  otherwise, and on all 1-5-year mid-curves including the weeklies, with a 0.0025 cabinet.
- IB data (IB market-data pricing page, verified). CME Real-Time (L1) costs USD 1.55 a month for
  a non-professional. Without it, CME data is delayed 10 minutes and fills on it are not evidence.
- IB commission (IB futures commissions page, verified). USD 0.85 per contract up to 1,000 a
  month, plus exchange and regulatory fees. That is 0.034 bp per leg per side, small beside the
  tick.
- Margin: SPAN for futures options (recalled). Not priced here.
- Not verified: that IB lists the weekly SOFR mid-curves and the full serial strip, and that they
  are tradeable on a paper account. The N20 lane or a contract-details query on the paper gateway
  can settle it.

**Half-spread as a share of premium.**
- Front quarterly straddle, the Bauer et al. template. Gross is about 1.35 bp on a straddle of
  about 14 bp (1.3 / 0.091). One half-spread on two legs is 0.25 bp at a quarter-tick market and
  0.5 bp at a one-tick market, i.e. 1.8% to 3.6% of premium per side. The project's measured
  equity cost is 1.79% per side. The difference is the gross: Bauer et al.'s +9.1% of premium in
  one day against a round trip of 3.6% to 7.2%, so the front contract would net +2% to +5.5% if
  the LIBOR-era premium survives into SOFR at quarter-tick markets. On the deferred contracts
  (ED3 onwards, +3.0% or less) a one-tick round trip takes all of it.
- Weekly 1-year mid-curve straddle expiring the Friday after the meeting, sold one tick wide and
  held to expiry. Cost is 0.85 bp: two option half-spreads, closing the exercised futures leg
  (half-tick, recalled 0.005 points), and fees. From the realised two-day FOMC moves in this
  lane's data (29 meetings, windows 300-500 days out: mean 254, median 100 bp²) the fair straddle
  is 8 to 13 bp. Cost is therefore 6.7% to 10.7% of premium, and the break-even share of implied
  event variance that must be premium is 12% to 18% (`breakeven_weekly.py`,
  `logs_breakeven_weekly.txt`; Gaussian increments, a projection). Wright's estimate for 5- and
  10-year Treasury weeklies is about 50%. No one has measured it for SOFR.

## 4. Data

- **In hand, free (used).** Atlanta Fed Market Probability Tracker historical file (verified, read).
  It gives daily risk-neutral statistics of 3-month average SOFR fitted to CME SOFR option prices
  (quartiles, mean, mode, 25 bp bins), 913 business days from 2023-03-29 to 2026-11-12, and 27
  quarterly reference windows from 6 to 1,311 days ahead. It is derived from end-of-day option
  prices: no quotes, no strikes, no weeklies, and the fitting noise is large (below). Copy and
  hash in `data/`; the source URL is in `sources.csv`.
- **Not free.** Intraday SOFR option quotes, and settlements for the weekly mid-curves on FOMC eves.
  Databento GLBX.MDP3 has CME options with settlement statistics and top-of-book (recalled). Its
  public page gives a USD 125 credit for new accounts and a Standard plan at USD 199 a month that
  includes one year of L1 history (verified). Per-GB historical rates appear only through the
  vendor's cost call, which this lane may not make. The pull needed is small: for 31 meetings
  (2023-01 to 2026-10), the eve and decision day, the nearest four quarterly SR3 options and the
  Friday weekly 1y and 2y mid-curves, at-the-money plus or minus three strikes, the settlement
  statistics plus 1-minute top-of-book from 13:30 to 15:30 ET, and matched control Tuesdays and
  Wednesdays. CME DataMine is an alternative; its price could not be checked because CME pages
  timed out.
- **Caches.** Nothing in `data/cache/` covers STIR options. `index_events/macro_releases_2016_2026.csv`
  supplied the FOMC, CPI and payroll dates; its FOMC dates match the Fed's calendar exactly.

## 5. Pilot (real data, settlement-derived, synthetic marks)

Design (`diagnosis.log` entry 1, written before any outcome). By the law of total variance under
the pricing measure, V(t-1) − V(t+1) − ΔF² has zero mean for a window whose option expiry is
fixed. Its realised mean is the premium for selling the window's quadratic payoff for two rows,
which a strip of options replicates. The straddle form: an at-the-money Bachelier straddle is
sold at row t-1 and repriced at row t+1, using V from the published quartiles and F from the
published mean, averaged over windows 30 to 730 days ahead within each date. Controls are clean
Wednesdays with no FOMC, minutes, CPI or payrolls from d-2 to d+1. Both arms use the same
two-row structure, so they are symmetric whichever way the file's dates align with settlement.
Discovery runs to 2024-12-31 and held-out from 2025-01-01. Every number below is per trade,
return on straddle premium unless in bp², gross, from settlement-derived model marks, which are
not tradeable levels.

Funnel: 29 meetings, all kept. 187 Wednesdays, 178 with consecutive rows, 93 clean controls.

| Trial | Block | Measure | Point | 95% interval | N (FOMC / control) |
|---|---|---|---|---|---|
| 2,232 | discovery | FOMC minus control | -0.46% | [-5.02, +3.32] | 14 / 47 |
| 2,233 | discovery | same, V from bins | -1.12% | [-4.87, +2.28] | 14 / 47 |
| 2,234 | discovery | premium, bp² per window | -130 | [-585, +290] | 14 / 47 |
| 2,234 | discovery | realised FOMC excess, bp² | +220 | [+58, +437] | 14 / 47 |
| 2,238 | held-out, frozen | FOMC minus control | -3.60% | [-11.51, +3.01] | 15 / 46 |
| 2,238 | held-out, frozen | FOMC net of half-tick hurdle | -7.71% | [-15.53, -1.08] | 15 |
| 2,239 | held-out | premium, bp² | +51 | [-399, +435] | 15 / 46 |
| 2,240 | held-out, post-read | premium-weighted FOMC minus control | -0.89% | [-5.31, +2.88] | 15 / 46 |

Trials 2,235 to 2,237 split 2,234 into horizon bands. None differs from zero; see `trials.csv`.
Intervals for differences come from independent bootstraps over dates (5,000 draws, seed 0, from
the protocol module); single-arm means use `date_clustered_ci`.

**Verdict of the pilot: P1 and P2 fail; the kill criterion fires for the quarterly-surface test.**
The reasons were diagnosed before the read (`diagnosis.log` entry 2):
- The implied side cannot be resolved. The two-row change in fitted variance has noise SD 514 to
  525 bp² per date on controls, against an event signal of 100 to 300 bp². The minimum
  detectable premium on 15 meetings, about 390 bp², exceeds the whole implied event variance.
- On a quarterly option 30 to 730 days from expiry, one meeting's realised excess variance is
  0.6% (held-out) to 2.1% (discovery) of the option's total variance. A two-day straddle could
  earn at most half of that against a 2.3% to 3.0% hurdle.

The 2023-26 point estimates lean against the seller. The intervals still contain the +2% to +4.5%
Bauer et al. found on ED2 to ED4. Read conservatively, this data neither confirms nor rejects the
premium in the SOFR era.

Attrition: no meeting dropped. Windows outside 30 to 730 days are excluded by design, not by
outcome. Process: freeze note and scorer hashes in `freeze_2026-11-13_fomc-variance-premium.md`
(scorer 14:43:42, note 14:44:00 local). One held-out read; the scorer refuses a second.

## 6. Verdict

**Viable pending a priced data pull, for one vehicle; not viable as tested.** The quarterly two-day
straddle marked off the free option-implied distribution is dead: the event is too small a share
of a long-dated option's variance and the data too noisy to see it. Two candidates survive on the
strength of prior work, not this lane's data:
1. The Bauer et al. trade on the nearest-expiry SOFR option, entered just before 14:00 ET and
   bought back after the press conference. The January 2020 filing grants the quarter tick at any
   premium only to the nearest quarterly when it is also the nearest monthly expiry. Serials and
   later quarterlies priced above 5 bp per leg trade in 0.5 bp ticks, where the one-tick round
   trip (7.2%) leaves at most +1.9% of the ED1-sized premium.
2. The weekly 1-year mid-curve straddle expiring the Friday after the meeting, held to expiry,
   needing 12% to 18% of event variance to be premium.

**Kill criterion for the pull.** On 2023-2026 SOFR settlements, either of the following kills both:
the front-contract one-day short straddle averages under +3.6% of premium (one quarter-tick round
trip), or the weekly's implied event variance exceeds realised by less than 18%, with intervals
that exclude the thresholds. Either also dies if median quoted spreads at 13:55 ET on FOMC eves
exceed one tick.

**Forward paper test.** Subscribe to CME Real-Time L1 (USD 1.55 a month). At each meeting from
December 2026, record bid, ask and size at 13:55 ET on the decision day, and at the prior day's
close, for the front SR3 at-the-money straddle and the Friday weekly 1-year mid-curve straddle.
Paper-sell at the bid and, separately, rest at the mid. Mark the front straddle at the ask at
15:30 ET and at the next day's 15:00 ET; hold the weekly to expiry. That gives eight meetings a
year, against the same clock on matched non-FOMC Wednesdays. It is slow, which is why the
historical pull comes first.

## 7. Could not verify

- Whether IB lists weekly SOFR mid-curves and serials, and their paper-account availability.
- Current CME tick and listing rules after the January 2020 filing (CME pages timed out, and the
  session's web-search budget ran out before a second source could be found).
- Actual quoted SOFR option spreads around FOMC. Bauer et al. give 0.5 to 1.0 bp for Eurodollars;
  no SOFR figure was found.
- The SR3 futures tick for deferred contracts, the CME exchange fee for SOFR options, and SPAN
  margins.
- The Databento per-GB price for the pull (vendor cost call only) and the CME DataMine price.
- Whether each tracker row is the settlement of its own date or of the prior day. The design is
  symmetric between arms either way.
- The lane prompt's second question, whether options overpay for outcomes futures already price,
  was not tested. The tracker's cut and hike probabilities could do it on the front window, but
  that window's average spans later meetings too.

C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N06-sofr-fomc\evidence.md
