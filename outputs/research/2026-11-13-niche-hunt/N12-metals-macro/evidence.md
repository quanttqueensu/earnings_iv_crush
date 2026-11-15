# N12 metals-macro: evidence dossier

Gold and silver options (COMEX GC and SI options, GLD and SLV options) around US CPI, payrolls
and FOMC releases. Labels: [V] verified at the source, [R] recalled or read only in a search
snippet, [C] conjecture. Every figure below traces to a file in this folder or to a row of
`sources.csv`. The verdict is the analyst's to write; this file gathers the evidence.

## 1. Evidence in one paragraph

Gold options do not measurably overprice US macro releases. On the frozen held-out block
(2022-01-03 to 2026-10-30, read once) the event surplus of GLD implied over realised variance is
+0.017 ordinary-day equivalents [-0.611, +0.607], N=147 events, gross, at the index mid (trial
2,412, `logs/s02_heldout.log`); discovery 2016-2021 gave +0.056 [-0.409, +0.500], N=180. The
structural reason is that the event is small in gold: on a close-to-close basis GLD realises
only 0.07 (discovery) and 0.16 (held-out) ordinary days of extra variance on a release session,
and GVZ releases 0.13 and 0.17 days. Against single-name earnings, where the event is several to
tens of ordinary days, there is little event variance for a premium to sit on. The touch is not
the obstacle: a one-session GLD ATM straddle quoted a half-spread of about 1.2% of mid on
2026-11-13, a quarter of the single-name figure. The test cannot resolve a surplus small enough
to matter at that cost (minimum detectable mean about 0.9 day-equivalents on the held-out N,
against a break-even near 0.03 to 0.04), so a short-dated quote pull (USD 8 to 11 on N19's
estimate) is the only way to settle the residual question, and the event itself gives little
reason to expect a surplus.

## 2. Prior work

| Work | Sample and method | Effect | Costs measured | Label |
|---|---|---|---|---|
| Wright, NBER w28306 (2020) | CME Wednesday and Friday weekly options on Treasury and E-mini S&P 500 futures, settlement prices on the eve of expiry, 2011 or 2017 to 2020; event-day implied variance regressed on an event dummy against non-event Tuesdays and Thursdays; variance risk premium against five-minute realised variance | implied variance rises significantly before FOMC and payrolls; event-day variance risk premia positive and mostly significant, about half the implied increase on FOMC days for 5 and 10-year futures, a small share on payroll days | no (settlement prices) | [V] full text |
| Fernandez-Perez and Lopez, JFM 43(11), 2023 | implied volatility of crude oil, gold and silver around US macro releases | scheduled official releases lower implied volatility (uncertainty resolution); survey releases raise it | no, not a trading test | [V] abstract |
| Gu, Kurov and Stan, FRL 55, 2023 | intraday gold and crude implied volatility around FOMC statements | significant drop from just before to just after the statement, larger at SEP meetings | no | [V] abstract; magnitudes not read |
| Elder, Miao and Ramchander, JBF 36(1), 2012 | intraday gold, silver and copper futures around US macro surprises | fast, significant reaction; 08:30 releases, payrolls first, matter most | no | [R] |

Closest paper: Wright (2020), which is this test on Treasury and equity futures options with
one-day options. No study of an event-day variance premium in gold or silver options was found
by this lane or by N18 (`N18-literature-map/evidence.md`, row "Gold and silver options, FOMC or
CPI: none found"). The idea is not crowded in print. Two lanes of this hunt tested it (N17
trials 2,563 to 2,571 with a synthetic-straddle design, N12 trials 2,412 to 2,417 with a
variance decomposition); both find no surplus on discovery.

How it differs from closed work: the closed Deribit BTC macro test (`docs/RESEARCH_STATE.md`
section 2) is a different asset; the SPY macro tests are equity index options. Nothing on the
closed list touches gold or silver.

## 3. Mechanism and event timing

- Who would pay: hedgers of bullion and miner exposure and directional macro traders buying
  short-dated gold options into a release; dealers short gamma across a jump. Gold reprices on
  real yields and the dollar, so the channel exists [R]. Whether it is large enough to carry a
  premium is the question, and the realised side says it is small (section 6).
- Why it might persist: the variance risk premium is a compensation for jump and volatility risk
  that dealers cannot hedge continuously (Wright 2020 [V] for Treasuries and equities).
- When information arrives: CPI and payrolls at 08:30 ET, one hour before GLD and SLV options
  open (09:30 ET). A GLD option seller carries the release overnight, like an after-close
  earnings seller, but COMEX gold futures trade on Globex through the release, so a delta hedge
  can be adjusted [R]. COMEX gold options trade on Globex nearly 23 hours, so on COMEX the 08:30
  release lands inside the session and a seller can enter minutes before it [R]. FOMC at 14:00 ET
  lands inside both sessions.

## 4. Tradability at Interactive Brokers

| Item | GLD and SLV options | COMEX gold (OG) and silver options |
|---|---|---|
| Venue and root | US equity options, OCC-cleared, American, physically settled into shares | COMEX options on GC and SI futures, American, physically settled into futures [R] |
| Short-dated expiries | GLD lists every weekday; snapshot of 2026-11-13 shows expiries on 16, 17, 18, 19 and 20 November [V]; Wednesday expiries since 2023-11-21, Monday later [R] | weekly options every business day since 2024-01-22 (Monday and Wednesday since May 2023, Friday earlier) [V]; codes OG1-5, G1M-G5M, G1W-G5W [R] |
| Hours against the event | 09:30 to 16:00 ET; 08:30 releases land before the open | Globex about 23 hours; 08:30 releases inside the session |
| Paper account | equity options available on IB paper (N20) | futures options need futures permissions; the project's harness would need changes (N20 section on FOPs) |
| Market data | OPRA top of book; without it quotes are 15 minutes late (N20 [V]) | COMEX Real-Time L1 USD 1.55 a month non-professional, waived above USD 20 of commissions; delayed 10 minutes without it (N20 [V]) |
| Commission | project basis USD 0.65 per contract per side | USD 0.85 + 1.65 exchange + 0.01 regulatory = 2.51 per contract (N20 [V]) |
| Margin | Reg-T short straddle on an ETF (or portfolio margin) | SPAN; GC future initial margin quoted at USD 36,408 by N20, so one GC straddle ties up far more capital than a GLD straddle [V via N20] |

IB's own pricing pages returned HTTP 403 to this lane's fetcher; the IB figures above are N20's
verified readings, cited rather than re-read. GLD is the practical vehicle: daily expiries,
cheap touch (section 6.6), small contract, and the project's existing equity-option harness.

## 5. Data

| Source | What it holds | Cost | Used for |
|---|---|---|---|
| Cboe GVZ and VXSLV histories | 30-day constant-maturity implied vol of GLD and SLV options at the mid, daily close; VXSLV has no prints from 2022-03 to 2025-05 | free | implied side of the pilot |
| Cboe public price history, GLD and SLV | daily OHLC from 2004 | free | realised side (rebuild, trials 2,418 to 2,422) |
| Yahoo chart API, GLD and SLV | daily OHLC; robots.txt disallows automated clients | free | realised side of trials 2,412 to 2,417; a breach, files hashed and deleted (diagnosis.log entry 4) |
| Project calendar `macro_releases_2016_2026.csv` | CPI, payrolls, FOMC dates 2016-2026, frozen with SHA-256 78f52e29 | in hand | event flags |
| Cboe public delayed quotes, GLD and SLV | the current chain with bid, ask, IV, about 15 minutes delayed | free | today's touch only |
| DoltHub `option_chain` | no GLD or SLV [V] | free | not usable |
| Databento OPRA cbbo-1m, GLD and SLV | every listed contract, minute quotes, 2016 onward | USD 7.61 to 10.66 for a full 15:59 and 10:00 panel 2016-2026 (N19's estimate from the project ledger); event-only designs a quarter to a tenth of that | the test this pilot cannot run |
| Databento GLBX (COMEX) | COMEX options quotes; Standard plan USD 199 a month gives 12 months of L1 | USD 199 (N19) | COMEX vehicle, 12 months only |
| iVolatility EOD | close-of-day option quotes | USD 0.40 per ticker-day, about USD 1,090 for GLD 2016-2026 | dominated by Databento |

The pilot's implied side is a 30-day index. It sees the event only as the drop in 30-day total
variance and cannot see how a one-session option prices the event. Settlement-style daily index
closes are not tradeable levels; everything in section 6 is gross, at the mid.

## 6. Pilot

### 6.1 Pre-registration and freeze

Hypothesis, mechanism, statistic, pass rule and economic gate were written in `diagnosis.log`
(entry 1) before any event-versus-control outcome was computed. Discovery was read and diagnosed
(entry 2). The freeze note `freeze_heldout.md` records the SHA-256 of the held-out scorer
(`scripts/s02_score.py`, da11b484...), the gate script, the builder, both data files, the
diagnosis log at freeze and the calendar, and its own hash (b59abfe6...). The scorer refuses the
held-out block unless its own hash is in the note. The held-out block was read once.

### 6.2 Construction

For each GLD session t: W_t = (GVZ_t/100)^2 x 30/365, dW_t = W_t - W_{t-1}, r_t the close-to-close
log return, u_t = (GVZ_{t-1}/100)^2/252. For an event session, eQ = -(dW - mean dW over matched
controls), eP = r^2 - mean r^2 over matched controls, S = (eQ - eP)/u. Controls: non-event
sessions with the same weekday and calendar gap, within 60 sessions either side (median 18 per
event). S x u is the event-minus-control one-session P&L of a short 30-day variance position at
the index mid, so S is a gross, mid-level event surplus in ordinary-day equivalents.

### 6.3 Funnel and attrition (`logs/s01_build.log`)

GLD: 337 calendar event dates; 6 not NYSE sessions (payrolls on Good Friday and similar); 331
event sessions; 2 dropped for a stale GVZ print, 2 for fewer than 5 controls; 327 kept
(discovery 180, held-out 147). SLV: 213 kept (discovery 165, held-out 48), most losses in the
VXSLV gap.

Outcome dependence: three of the four dropped GLD sessions moved more than the kept mean (|r|/√u
of 2.66, 1.43 and 1.02 against a kept mean of 0.76; 2022-11-04, payrolls, +3.0% with an
unchanged GVZ print). Their inclusion would lower the held-out mean, so the reported S is, if
anything, flattered by attrition. Four events cannot move the verdict.

### 6.4 Results

Gross, at the index mid, ordinary-day equivalents, date-clustered 95% intervals
(`protocol.date_clustered_ci`, mean). One event per date; month-clustered intervals in the logs
agree.

| Trial | Set | Discovery 2016-2021 | Held-out 2022-2026 | Status |
|---|---|---|---|---|
| 2,412 | GLD, all releases | +0.056 [-0.409, +0.500], N=180 | +0.017 [-0.611, +0.607], N=147 | primary, FAIL (kill) |
| 2,413 | SLV, all releases | -0.213 [-0.706, +0.255], N=165 | +0.844 [-0.045, +1.655], N=48 | secondary, FAIL |
| 2,414 | GLD FOMC | -0.144 [-0.920, +0.582], N=47 | -0.576 [-1.890, +0.611], N=39 | descriptive |
| 2,415 | GLD CPI | -0.058 [-0.842, +0.660], N=64 | +0.559 [-0.272, +1.334], N=56 | descriptive |
| 2,416 | GLD payrolls | +0.298 [-0.545, +1.089], N=69 | -0.122 [-1.356, +1.018], N=52 | descriptive |
| 2,417 | GLD, cell controls | +0.116 [-0.318, +0.520], N=180 | not read | exploratory |

Decomposition for GLD (eQ/u implied released, eP/u realised excess): discovery +0.129
[-0.210, +0.456] and +0.072 [-0.159, +0.312]; held-out +0.172 [-0.260, +0.572] and +0.155
[-0.134, +0.460]. FOMC is the only release with a realised excess clear of zero, on discovery:
+0.459 [+0.080, +0.886], N=47, matched by +0.315 implied, so the options price it about fairly.

The SLV held-out near miss sits on 48 events in 2025-26 after a sign-reversed discovery read;
under the pre-registered rule it fails and it is not a finding.

The median S is positive in every block (+0.66 discovery, +1.11 held-out) while the mean is near
zero: most releases pass quietly and a few real surprises (2018-10-11 CPI +2.5%, 2021-08-06
payrolls -2.5%, 2021-01-08 payrolls -3.5%) take it back. That is the short-gamma profile with no
excess carry.

### 6.5 Power

The per-event standard deviation of S is 3.1 (discovery) and 3.9 (held-out) day-equivalents,
almost all from the daily GVZ change. The minimum detectable mean at 80% power is about 0.66 and
0.89 day-equivalents. The pilot can rule out a surplus of a full ordinary day or more on
held-out; it cannot rule out the small surplus that would pay a one-session GLD straddle
(section 6.6).

### 6.6 Touch and economic gate

Touch from three Cboe public delayed snapshots on 2026-11-13 with the options session open
(quotes at 19:37, 20:29 and 20:55 UTC, that is 14:37 to 15:55 ET; `logs/s03_gate.log`). ATM
straddle, strike where call and put mids are closest; commissions USD 0.65 per contract per side.

| | GLD one session (exp 16 Nov) | GLD three sessions (exp 18 Nov) | SLV one session | SLV three sessions |
|---|---|---|---|---|
| straddle mid, USD | 4.43 to 4.46 | 7.28 to 7.30 | 0.97 to 1.00 | 1.60 |
| quoted spread, both legs, USD | 0.10 to 0.11 | 0.15 to 0.20 | 0.05 to 0.09 | 0.05 to 0.10 |
| cost share used by the gate (median) | c_1 1.53% (one half-spread plus 2 commissions, held to expiry) | c_3 2.42% (full spread plus 4 commissions) | c_1 5.30% | c_3 4.76% |

For comparison, one half-spread on the project's single-name hedged books is 4 to 6% of premium
(`docs/RESEARCH_STATE.md` section 2). GLD's touch is about a quarter of that at one session.

Gate (pre-registered, descriptive): GLD pi_1 -5.93% of premium against c_1 1.53%, pi_3 -1.89%
against c_3 2.42%: **FAIL**, because the held-out surplus converted to premium is negative.
SLV pi_1 +45.3% against 5.30%, pi_3 +18.2% against 4.76%: the arithmetic passes, but it rests
on a held-out mean whose interval includes zero (trial 2,413 failed), on 48 events, and two
thirds of its dollar surplus comes from three 2026 releases during the silver volatility spike
(2026-02-13 CPI, 2026-04-10 CPI, 2026-03-06 payrolls, VXSLV 75 to 100), where the 30-day index
collapsed after quiet prints (`logs/x_slv_gate_concentration.log`, exploratory). That is vega
mean reversion in one regime, not a release premium a one-session straddle would collect.

Break-even, for scale: with eQ about 0.15u, a one-session GLD straddle covers c_1 with a surplus
of about 0.035 ordinary days. The hurdle is low. The measured surplus is indistinguishable from
zero, and the minimum detectable effect is about 25 times the hurdle, so the free data cannot
settle whether a surplus that small exists.

### 6.7 Provenance and the compliant rebuild

The realised side of trials 2,412 to 2,417 was built from Yahoo chart data, whose robots.txt
disallows automated clients; one request to Stooq returned no data. Both are logged as breaches
in `diagnosis.log` entry 4, and the Yahoo files were hashed and deleted. A rebuild on Cboe's
public GLD and SLV price history (`scripts/s04_rebuild_cboe.py`, trials 2,418 to 2,422,
exploratory, held-out already read) reproduces the same 540 events with identical event-session
returns. GLD held-out is +0.017 [-0.611, +0.607], N=147, and SLV is +0.844 [-0.045, +1.655],
N=48. Every figure in section 6.4 is unchanged to the third decimal.

### 6.8 Context, not a trial

GLD's ordinary 30-day variance premium (W_t against realised GLD variance over the next 30
calendar days, all sessions, mid, variance basis): realised over implied 0.73 (ratio of means,
N=1,503 start dates, 2016-2021) and 0.95 (N=1,190, 2022-2026). The generic gold variance premium
has thinned in the high-volatility 2022-2026 regime; any short-dated GLD book would lean on it
rather than on the releases. Overlapping 30-day windows make these start dates far from
independent; no interval is claimed.

## 7. Verdict inputs, kill criterion and a forward test

- Pre-registered primary (2,412): fails held-out; kill rule fires. No pre-registered pass in
  this lane.
- Kill criterion for any follow-up: on a GLD quote pull (OPRA, 15:59 entry, the shortest expiry
  after the release, matched non-event sessions on the same weekday and tenor), the event-minus-
  control short-straddle return net at the touch must exceed zero with the date-clustered lower
  bound above zero on a block not used for design; otherwise close the lane.
- What a forward paper test would look like, if a pull ever justified one: sell one GLD ATM
  straddle at 15:45 to 15:59 ET before each CPI and payrolls release, expiring at the next
  session close, with a resting limit at the mid less a tick, and a matched non-event straddle on
  the same weekday as the control; about 24 events a year, so a year of paper trading is still
  underpowered for the effect sizes in section 6.5.

## 8. What could not be verified

- How short-dated GLD and COMEX options price the event itself: no free short-dated quote
  history exists (GVZ is 30-day only; DoltHub has no GLD).
- Historical GLD spreads: the touch figures are one day of delayed quotes in a high-price,
  high-volatility regime (GLD about USD 355); spreads in 2016-2021 as a share of premium may
  differ in either direction [C].
- IB's own pages (403 to this fetcher); COMEX contract details beyond the CME press release
  reprint; Gu, Kurov and Stan's magnitudes; Elder, Miao and Ramchander's per-metal results.
- The SLV held-out rests on 48 events because VXSLV stopped printing from 2022-03 to 2025-05.
- Copper (HG) options: no free implied-volatility series exists, so copper was not tested.
- Web searches ran out partway through (session budget); IB market-data figures come from N20.
