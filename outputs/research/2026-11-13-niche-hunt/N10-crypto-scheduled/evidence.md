# N10 crypto-scheduled: evidence dossier

## Hypothesis, scope and success criteria

Hypothesis: crypto-native scheduled events (protocol upgrades, halvings, ETF decisions, and
Deribit's large monthly and quarterly expiries) carry an implied-volatility premium in BTC and
ETH options that a seller can harvest net of costs, and an Interactive Brokers vehicle (CME
bitcoin and ether options, or options on IBIT) carries the same premium.

Scope: Deribit public data (free) to measure the premium; IB's own pages for the vehicle; the
Cboe delayed IBIT chain for the touch. Macro releases are out of scope: the closed Deribit macro
study (`research/other_markets/findings/deribit_macro.md`) found no event surplus, paired
+0.079% of notional [-0.275%, +0.440%], N=116.

Success: a held-out pass net at the estimated touch against a matched control, on a premium that
reaches an IB vehicle's clock; or a sourced, priced case for a data pull.

## Verdict

Not viable as a crypto-native scheduled-event trade. Pilot B (the monthly-expiry Friday) passed
discovery and failed its frozen held-out read; it never reached the IB clocks even on discovery.
Pilot A (14 catalysts) is underpowered and exploratory. One adjacent candidate, the IBIT onshore
variance premium over Deribit, is viable pending a priced data pull of about USD 1 (section 7);
it is a closely related scheduled premium (the nightly and weekend closure of the vehicle), not a
crypto-native event.

## 1. Prior work

- Closest academic work on crypto event volatility: none found that measures option-implied
  variance around halvings, forks or ETF decisions (three searches; absence of evidence, so
  conjecture). A 22-fork event study uses EGARCH on returns, not options (arXiv 2307.11718,
  recalled).
- Closest on the expiry event: Weiss et al., Finance Research Letters 107 (2026) 110340, Deribit
  2021-2023. Spot falls about one hour before expiry and recovers within about 90 minutes,
  significant only when at-the-money open interest is above its 90th percentile; implied
  wealth transfer about USD 50m a year. No option-strategy returns and no costs (recalled via a
  press summary; the journal page returned 403). Hoang (FRL; SSRN 5689945) finds settlement
  trading concentrated on expiry days (recalled).
- BTC variance risk premium: Almeida, Grith, Miftachov and Wang (arXiv 2410.15195), Deribit
  2017-2022, about 0.14 in annualised variance at a 27-day horizon, no transaction costs
  (verified). Alexander and Imeraj (Journal of Alternative Investments 2021), Deribit 2019-20
  (recalled). Neither measures a one-day premium or costs.
- Practitioner: Paradigm (2022-09-12) put ETH implied about 20 vol points over historical in the
  two weeks before the Merge (verified); Amberdata reported a fall of about 15 points in 30-day
  ETH IV after it (recalled). Volmex (2026-04-24): IBIT 30-day IV (BVUS) minus offshore (BVIV)
  +4.29 and +4.72 vol points, IBIT option open interest USD 27.6bn against Deribit's USD 26.9bn
  (verified, vendor note).
- Crowding: the catalyst trade is well known to crypto desks (Deribit Insights threads on ETF
  deadlines, recalled). The monthly-expiry pin is folklore ("max pain") with one peer-reviewed
  intraday study. The IBIT-offshore gap is published by a vendor but has no academic test found.

## 2. Mechanism

Catalysts: who pays is the hedger or speculator buying protection or convexity into a binary
outcome (ETF approval, Merge execution). Information arrives at a known block height or a
regulator's publication time; crypto trades through it, so there is no closed-market gap on
Deribit, unlike earnings.

Monthly expiry: dealers long gamma near large open interest would pin spot into the 08:00 UTC
settlement (a 30-minute index average), lowering realised variance for a straddle that expires
there; the option price need not reflect it. The discovery data looked like that (same implied,
less realised); held-out did not confirm.

IBIT: the ETF trades 09:30-16:00 New York, five days a week; BTC trades always. On this clock,
63% of weekly BTC variance falls while IBIT is closed (computed in section 6.4), so an IBIT
option maker carries a gap every night, earnings-like, plus the weekend. Gap risk the maker
cannot hedge with the ETF is what earnings options pay for; CME's move to 24/7 crypto trading on
2026-05-29 (recalled) gives a hedge through the gap and should shrink it.

## 3. Tradability at IB

| Vehicle | Contract | Expiries | Hours vs events | Commission (IB) | Data |
|---|---|---|---|---|---|
| CME options on Micro Bitcoin futures (MBT) | 0.1 BTC, European | one Monday, one Wednesday, four Friday weeklies, two monthlies (IB page) | Globex Sunday-Friday 18:00-17:00 ET per IB's page; 24/7 since 2026-05-29 per CME (recalled) | USD 0.85 per contract plus exchange fees, about 2.01 all in (N20) | CME Real-Time L1 USD 1.55/month non-pro; delayed 10 minutes otherwise |
| CME Bitcoin options (BRR) | 5 BTC | weekly to quarterly; weeklies terminate 16:00 London (recalled) | as above | USD 5.00, about 10.01 all in (N20); BRR future margin 107,590 (N20) | as above |
| CME Micro Ether (MET), Ether | 0.1 ETH, 50 ETH | as MBT | as above | MET about 0.31 all in (N20) | as above |
| IBIT options | 100 shares, American, physical | an expiry every weekday (Cboe chain, 2026-11-13) | 09:30-16:00 ET; most crypto events and 63% of BTC variance fall outside | USD 0.65 per contract (IBKR Pro, up to 10,000 a month) plus fees | OPRA L1 USD 1.50/month non-pro; delayed 15 minutes otherwise |

All verified on IB's pages except where marked. Deribit is not reachable through IB and is not
open to US persons (recalled); it is a measurement venue here, not a trading venue.

## 4. Cost at the touch: the half-spread as a share of premium

| Instrument | Tenor | Half-spread / premium | Basis | Source |
|---|---|---|---|---|
| Deribit BTC ATM straddle | 12 h | 7.7% | quoted, one snapshot 2026-11-13 19:45 UTC | `spread_snapshot.csv` |
| Deribit BTC ATM straddle | 36 h | 6.6% | same | same |
| Deribit BTC ATM straddle | 156 h | 2.0% | same | same |
| Deribit, 23-hour pilot B entry | 23 h | 11.8% of mark premium all in (seller's discount 7.2% plus fees) | median over 46 held-out events, trade-based | `pilot_b_pairs_heldout_h9.csv` |
| IBIT ATM straddle | 0DTE, 1.2 h | 5.3% | quoted, delayed 15 minutes, same snapshot | `spread_snapshot.csv` |
| IBIT ATM straddle | Monday expiry, 73 h | 1.6% | same | same |
| IBIT ATM straddle | Friday weekly, 169 h | 0.6% | same | same |
| US single-name earnings straddle | event night | one half-spread 4-6% of premium | project, hedged-hold study | `docs/RESEARCH_STATE.md` section 2 |

IBIT weeklies are quoted three to ten times tighter, per unit of premium, than the earnings
straddles that failed, and than Deribit's one-day options. One snapshot is not a history.

## 5. Data

- Used, free: Deribit trades (`history.deribit.com`), delivery prices, DVOL hourly,
  BTC-PERPETUAL hourly closes, live book summary; mempool.space block times; ethereum.org fork
  times; Cboe delayed IBIT chain (one snapshot, raw not retained, per Cboe terms noted by N19).
  Rebuild: `pull_deribit.py --pilot a|b --delivery --dvol`, `ibclock.py --pull`,
  `weekend_rv.py --pull`. Cache 30 MB in `cache/`.
- Not free: historical Deribit quotes (Tardis; the free first-of-month files were exhausted,
  N19), CME option quotes (automated access refused, N19), IBIT option history (DoltHub has no
  IBIT rows: 0 on 2025-06-04 and 2026-11-06 against SPY's 114 and 216).
- Deribit fills here are the closed study's estimate: last mark less the median taker-sell
  discount to mark on that expiry. It is a median over trades, not a quote, and the mark is
  Deribit's model price, so "at the mark" below is not a tradeable level.

## 6. Pilots (real data; trials 2,352 to 2,372)

Every figure is per event, net at the estimated touch unless stated, 95% intervals from
`date_clustered_ci` (each event date a cluster). Pre-registration, iterations and the held-out
reading are in `diagnosis.log`; all trials in `trials.csv`.

### 6.1 Pilot A, catalysts (2,370, 2,371; exploratory, N=14)

Short ATM straddle on the first Deribit expiry after each event, entered two hours before,
against the same clock time one and two weeks earlier. 14 of 14 built.

| Measure | Point | 95% interval | N |
|---|---|---|---|
| Paired net return on notional, event minus control | +0.665% | [-0.999%, +2.285%] | 14 |
| Event leg net return on notional | +0.563% | [-0.804%, +1.822%] | 14 |
| Implied variance at entry, event minus control | +0.00111 | [+0.00016, +0.00241] | 14 |
| DVOL change, 2 h before to 24 h after, at the event (vol points) | -3.17 | [-6.13, -0.69] | 13 |
| DVOL change, event minus control (vol points) | -3.14 | [-6.62, +0.05] | 13 |

The catalysts are priced (excess implied variance) and 30-day implied falls after them, but no
net profit is established. Fourteen heterogeneous events cannot carry a held-out block, so this
cannot set direction.

### 6.2 Pilot B, the monthly-expiry Friday (2,352 to 2,356 discovery; 2,366, 2,367 held-out)

BTC, Deribit, short ATM straddle sold Thursday 09:00 UTC into the Friday 08:00 UTC expiry, held
to settlement; monthly Fridays against the three preceding Fridays.

| Trial | Block | Statistic | Point | 95% interval | N |
|---|---|---|---|---|---|
| 2,352 (pre-registered) | 2020-22 | paired, on notional | +0.952% | [-0.141%, +2.065%] | 36 |
| 2,353 (frozen config) | 2020-22 | paired, on premium | +0.439 | [+0.063, +0.805] | 36 |
| 2,354 | 2020-22 | normalised move, event minus control | -0.348 sd | [-0.650, -0.054] | 36 |
| 2,355 | 2020-22 | 2,353, legs within 60 minutes | +0.450 | [+0.043, +0.823] | 35 |
| 2,356 | 2020-22 | 2,353, quarterly only | +0.629 | [+0.084, +1.255] | 12 |
| **2,366 held-out** | 2023-26 | paired, on premium | **+0.154** | **[-0.186, +0.469]** | 46 |
| 2,367 held-out | 2023-26 | 2,366, macro windows dropped | +0.088 | [-0.336, +0.457] | 34 |

Held-out: event leg net on premium -0.076 [-0.368, +0.183]; normalised move -0.106
[-0.350, +0.153]. No drops at any stage in either block. Frozen in
`freeze_2026-11-13_monthly-expiry.md` (note SHA-256 6d59e348...; scorers hashed; read once via
`run_heldout.py`). The premium does not replicate. Confound named before the read: the last
Friday sits near month-end.

### 6.3 Does it reach an IB clock? (2,357, 2,358 discovery; 2,368, 2,369 held-out)

Normalised move (realised only, scaled by the Deribit straddle's implied variance per hour)
over the window an IB straddle would hold:

| Clock | Discovery 2020-22 | Held-out 2023-26 |
|---|---|---|
| CME, Thursday to Friday 16:00 London | -0.090 [-0.306, +0.131] | +0.008 [-0.237, +0.273] |
| IBIT, Thursday to Friday 16:00 New York | +0.007 [-0.209, +0.244] | -0.195 [-0.419, +0.031] |

N=36 and 46. Neither clock carried the effect on discovery, which closed the IB route before the
held-out read.

### 6.4 The cost finding and the IBIT clock (exploratory; 2,372 descriptive)

Read after the held-out verdict, so exploratory: ordinary Friday 23-hour straddles in 2023-26
lose -0.321% of notional at the estimated touch [-0.631%, -0.033%] and are flat at the mark,
-0.107% [-0.417%, +0.184%], N=46. A one-day BTC variance premium at the mark is about zero and
the entry cost is about a tenth of the premium.

BTC by IBIT's clock, 2024-11-18 to 2026-11-13 (`logs_weekend_rv.txt`; mean squared log return):
session 0.000252 [0.000203, 0.000308], N=519; weekday overnight 0.000372 [0.000316, 0.000436],
N=416; weekend 0.000702 [0.000515, 0.000913], N=103. The weekend is 20% of weekly variance, all
closed hours 63%. Exchange holidays are ignored.

One snapshot (2026-11-13 19:45 UTC): IBIT implied variance over Deribit's, interpolated to the
same window, is 1.38 to the Monday expiry and 1.31, 1.28, 1.24, 1.22 to the Tuesday to Friday
expiries. IBIT implied to Monday 16:00 ET (0.000902) is 0.97 times the mean realised over that
window in the last 103 weekends (0.000931 [0.000676, 0.001221], median 0.000362); comparing a
current implied with a two-year average is blind to the vol regime, so this says only that IBIT
is not obviously rich against realised, while it is rich against Deribit.

## 7. The adjacent candidate: the IBIT onshore premium

Hypothesis for a pre-registration (not tested): IBIT weekly options carry a variance premium
over BTC realised variance, measured net at the touch, larger over the weekend expiry, because
makers price the closed-hours gap. Evidence so far: Volmex's +4.3 to +4.7 vol points over
offshore (vendor, two readings), this lane's 1.22 to 1.38 variance ratio (N=1), and a quoted
half-spread of 0.6 to 1.9% of premium on non-0DTE expiries (N=1). Strongest counter-argument:
the gap may be fair compensation (realised BTC variance on the IBIT clock is front-loaded into
closed hours, and holders' put demand may be rational), covered-call ETF supply caps it, and
24/7 CME hedging should erode it. Closest prior work: Jones and Shemesh (Journal of Finance
2018) on option returns over non-trading periods (recalled, not verified), and the Volmex note.
Not on the closed list; it is a general variance premium, so it must beat the closed index VRP
result (`off_earnings/findings/pivot_verdicts.md`) on cost, not on concept.

Data route and price: Databento OPRA `cbbo-1m` through the existing
`scripts/build/pull_index_chains.py` with ticker IBIT, two snapshots (15:59 and 10:00 ET) on
about 500 sessions from 2024-11-19. The project's ledger bills about USD 0.0007 per (ticker,
session, snapshot) request (USD 11.07 over 15,848), so about USD 0.70; quote it with the free
`--price-sample` first and pass `--cap 3`. Realised BTC from Deribit is free. Needs the team
lead's go-ahead. Free forward alternative: daily Cboe delayed and Deribit snapshots, but Cboe's
terms bar a retained archive without consent (N19).

Kill criterion: on the first held-out year the short weekly IBIT straddle, entered at Friday
15:45 ET and held to expiry with the touch paid, has a per-trade mean net return on premium whose
interval lies below zero, or the IBIT minus realised variance premium is not larger than the
half-spread.

Forward paper test: weekly, Friday 15:45 ET, sell one IBIT ATM straddle on the Monday and on
the Friday weekly, real-time OPRA L1 (USD 1.50/month), resting at the mid then the touch, held
to expiry, logged against Deribit implied and BTC realised for the same window. About 50 trades
a year per leg; per-trade Sharpe annualised by the square root of 50, not 252.

## 8. Could not verify

Deribit's fee cap and settlement fee (support pages 403); the CME 24/7 launch date and current
weekly termination time (CME pages timed out; IB's MBT page still shows the daily break); the
Weiss et al. and Hoang results beyond press and search summaries; Jones and Shemesh; ETF decision
times; IBIT option margin at IB; CME crypto option spreads (no free quote source).

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N10-crypto-scheduled\evidence.md
