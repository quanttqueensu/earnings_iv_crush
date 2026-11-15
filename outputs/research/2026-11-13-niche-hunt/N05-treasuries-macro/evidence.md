# N05 treasuries-macro: evidence dossier

Market: CBOT options on Treasury futures (ZN 10-year, ZB 30-year, ZF 5-year, ZT 2-year), weekly
and daily expiries, around NFP, CPI and FOMC. Every claim is labelled verified, recalled or
conjecture; sources are in `sources.csv`; computations trace to `logs/`.

## 1. Where this leaves the lane

The one paper that measures the exact trade, Wright (2020), finds a large, significant event
variance risk premium in one-day CBOT Treasury options on NFP and FOMC eves (2011-2020,
settlement prices, no costs). Converted to a one-day 10-year straddle, that premium is about 11%
of premium on NFP and 8% on FOMC (conjecture: my conversion of verified inputs). The CBOT tick is
fixed at 1/64 per option, so at a one-tick quote the touch plus IB fees costs about 5% (NFP) and
7% (FOMC) of a one-day 10-year straddle held to expiry (conjecture: the quoted width is not
verified). The only free real-data test I could run, on a 30-day long-bond implied-variance
index, finds no event surplus after 2020: both frozen held-out tests fail (section 6). That test
is blunt and underpowered for the size that matters. The lane's status is therefore viable
pending a priced data pull, with a weak prior: the published gross edge is only about twice the
estimated touch on NFP, about equal to it on FOMC, and unmeasured since 2020.

## 2. Prior work

| Paper | Sample | Effect | Costs? | Label |
|---|---|---|---|---|
| Wright (2020), NBER w28306, "Event-day options" | CBOT weekly options on 5y, 10y, 30y futures and E-mini; NFP Jan 2011-Aug 2020 (about 100 reports), FOMC Jun 2017-Aug 2020 (24 meetings); settlement prices on the eve of expiry | Event VRP (Table 5, pct^2 per day, Newey-West s.e.): 10y NFP 0.077 (0.018), FOMC 0.031 (0.015); 30y NFP 0.177 (0.046), FOMC 0.116 (0.034). FOMC: about half the event's implied-variance increase is premium for 5y and 10y, most of it for 30y. NFP: a small share of a larger increase. | No | verified |
| Londono and Samadi (FRB, 2023) | SPX daily expiries 2017-May 2023; 5y and 10y Treasury option implied vols as an explanatory variable | ATM SPX options spanning releases up to 7.5% dearer than neighbours; FOMC VRP 44% above controls | No | verified |
| Choi, Mueller and Vedolin (2017), RoF 21(3) | Treasury futures options panel | Short Treasury variance swap, annualised Sharpe almost two, significant after costs and margin. Unconditional, not event-specific | Yes | verified (abstract) |
| Beber and Brandt (2006), JME 53(8) | CBOT T-bond futures options, five years | Implied uncertainty falls after releases whatever the sign of the news | No | verified (abstract) |
| Ederington and Lee (1996), JFQA 31(4) | T-bond, Eurodollar, DM options | Implied SD rises before scheduled releases and falls after | No | verified (abstract) |
| Li and Engle (1998) | Treasury futures | No significant risk premium on release dates (GARCH, futures only) | No | recalled |

Closest paper: Wright (2020). Nobody I found measures the event-day Treasury option trade at the
touch, and nobody covers 2021-2026, when CPI became the dominant rates event and CME listed
Tuesday and Thursday weeklies (16 June 2025), so every weekday release now has its own expiry
(verified, CME page via search extract). Academically the net-of-cost question is open.
Practically the trade is crowded: weekly Treasury option volume rose from about 125,000 to
347,000 contracts a day between 2020 and 2023 (verified, CME), and selling event vol in weeklies
is a standard rates-desk trade (conjecture). Crowding is the strongest counter-argument: a
premium documented in 2011-2020 settlements may have been competed down since.

## 3. Mechanism and event timing

Buyers are hedgers who need protection over a known jump: asset managers, mortgage convexity
hedgers, macro funds. Dealers who sell a one-day option that spans a release cannot hedge the
jump with futures, so they charge for it; Wright attributes the FOMC premium to monetary policy
uncertainty. NFP and CPI land at 08:30 ET (07:30 CT), inside the CBOT Globex session (recalled:
Sunday-Friday 17:00-16:00 CT) and before the cash-equity open, so unlike earnings the option
market is open across the release; a seller can enter at Thursday's 14:00 CT settlement or any
time overnight. FOMC lands at 14:00 ET (13:00 CT), inside the session; the 14:00 CT expiry cuts
the press conference short (verified, Wright). Weekly options stop trading at 14:00 CT on expiry
(verified) and exercise into the quarterly future, so a held-to-expiry seller pays one
option half-spread plus one futures half-spread on the exercised leg.

## 4. Tradability at IB

- Product: CBOT 10-year note weekly options, IB exchange CBOT, futures-option class by expiry
  weekday: VY (Mon), GY (Tue), WY (Wed), HY (Thu), ZN1-ZN5 (Fri) (verified, CME codes). ZB and ZF
  have the same structure. 2-year weeklies are illiquid (2019 Friday ADV 142; settlements at the
  minimum tick) and are excluded (verified, Wright).
- Tick: 1/64 of a point = $15.625 per contract; strikes every 1/4 point (verified).
- Fees per contract per side: IB commission USD 0.85 (up to 1,000 contracts a month), CBOT
  exchange fee USD 0.85 (non-member, Treasury options), regulatory USD 0.01, so about USD 1.71
  (verified, IB pages saved under `raw/ib/`).
- Market data: CBOT Real-Time (L1) USD 1.55 a month non-professional; without it IB delays CBOT
  quotes 10 minutes (verified, IB market-data page), so paper fills without it are not evidence.
- Paper account: IB paper accounts trade futures options and inherit the live account's
  subscriptions (recalled; lane N20 owns the confirmation).
- Margin: SPAN. ZN futures maintenance is about USD 2,000 to 3,000 (recalled); a short one-day
  ATM straddle should need roughly that less the premium (conjecture).

## 5. Data

| Source | What | Cost | Use here |
|---|---|---|---|
| Treasury option quotes or settlements, any free source | none found | n/a | the gap |
| TYVIX (CBOT 10y options, VIX method) | discontinued 2020; Cboe CDN returns AccessDenied | n/a | not obtainable |
| CME website | blocks automated access (IP block citing its Data Terms of Use) | n/a | not scraped |
| VXTLT (Cboe 30-day TLT implied vol) | daily 2004-2026, free CSV | 0 | pilot |
| TLT daily (Cboe public chart history) | split-adjusted closes, not dividend-adjusted | 0 | pilot realised leg (replaces Yahoo, whose robots.txt disallows all agents; Yahoo files deleted) |
| Project event calendar | NFP, CPI, FOMC 2016-2026 | on disk | pilot events |
| Databento GLBX.MDP3 | CME/CBOT futures and options on futures from 2010-06-06, tick-level and sampled BBO | usage $/GB; "from $0.50/GB" (recalled from a search extract); $125 new-user credit | the decisive pull |

Settlement-only data cannot show what a taker pays; only intraday quotes can. Sizing for the
pull (conjecture, to be replaced by Databento's free cost call under a hard cap and the team
lead's go-ahead): the expiring weekly's 9 strikes nearest the money, calls and puts (18
instruments), `bbo-1m` from 13:00 CT on the eve to 14:00 CT at expiry (about 1,500 records each
at about 80 bytes) is about 2 MB per event; 330 event expiries (NFP 2011-2026 on Fridays, FOMC
2017-2026 on Wednesdays, CPI where an expiry matches) plus as many same-weekday controls is about
1.5 GB; daily `definition` records for the ZN option parent add about 1.3 GB. Total about 3 GB,
so of order USD 2 to 10 at USD 0.50 to 2 per GB, inside the free credit if the credit is unused.
A tick-level `mbp-1` read of the same instruments would be of order 40 GB (USD 20 to 80) and is
only needed to check queue position for a resting order.

## 6. Pilot on free data (real data, index-level, gross: not a tradeable level)

Pre-registration, iteration and the held-out read are in `diagnosis.log` entries 1 to 4; the
freeze note `freeze_N05_vxtlt.md` hashes itself, the scorer, the library and the inputs.

Design. Event surplus in Treasury implied variance on NFP, CPI and FOMC dates against
same-weekday non-event controls within 35 days, from VXTLT and TLT closes. The frozen run took
TLT closes from Yahoo, which breached the brief's robots rule; the replication on Cboe's public
TLT history (`scripts/vx_cboe.py`, first trading day of each month blanked as an ex-dividend
proxy, trials 2218 to 2221) reproduces every figure below to within 0.2 points. Discovery
2016-2020; held-out 2021-01-01 to 2026-11-12, read once. Intervals are month-clustered
percentile bootstraps (5,000 draws, seed 0, `protocol.date_clustered_ci`).

Discovery. The pre-registered variance metric failed (2202: +0.27 days of implied variance
[-1.72, +1.50], N=150) because one event, 2020-03-06, contributed d = -106. The diagnosed fix
replaced it with the one-day return of a short 30-day ATM TLT straddle (Black, zero rates):
pooled 2208 +0.69% of premium [-1.65%, +2.35%], N=150, fails; FOMC 2211 +1.98% [+0.26%, +3.76%],
N=39, per-event Sharpe +0.345.

Held-out, frozen co-primaries at 97.5%:

| Trial | Cut | Event minus control, share of 30-day straddle premium | N | Result |
|---|---|---|---|---|
| 2212 | FOMC | +0.19% [-2.48%, +2.55%] | 47 | fail |
| 2213 | NFP, CPI, FOMC pooled | +0.60% [-0.69%, +1.79%] | 181 (70 months) | fail |
| 2216 | NFP (95%, descriptive) | +0.23% [-1.80%, +2.00%] | 66 | |
| 2217 | CPI (95%, descriptive) | +1.31% [-0.47%, +3.01%] | 69 | |

Cboe replication, held-out (descriptive, block already read): pooled +0.69% (97.5% [-0.65%,
+1.91%]), N=174; FOMC +0.18% (97.5% [-2.86%, +2.77%]), N=44.

Attrition: 3 of 184 held-out and 3 of 153 discovery event dates had no close on the day or the
day before (calendar-driven, outcome independent). Median d is about +2% in every cut while the
means sit near zero: the ordinary short-volatility shape, not an event surplus.

What it can and cannot say. One event day is a small part of a 30-day option's variance. With
event-day implied variance about twice an ordinary day's (Wright, Figure 2), a one-day event
straddle is worth about 1/3.9 of a 30-day straddle, so the pooled 97.5% half-width of about 1.2%
of 30-day premium is about 4.7% of a one-day event straddle (conjecture: approximate scaling).
The pilot excludes a large post-2020 event surplus and gives no support to FOMC specifically; it
cannot exclude one of the 5 to 10% of one-day premium that Wright's numbers imply.

## 7. Half-spread as a share of premium, and why it might beat equities

`scripts/wright_cost_bar.py` (`logs/wright_cost_bar.json`) converts Wright's event VRP into the
share of a one-day ATM straddle's value a seller keeps under normal returns (a lower bound: it
counts only the event part of the premium), at an assumed ZN price of 110 (recalled 2025-26 level), and charges entry at
the touch, the exercised future's half-spread (1/128) and USD 1.71 a contract each way.

| Tenor, event | Gross edge, share of premium | Premium (USD) | Cost at 1-tick quote | Net | Net at 2-tick quote |
|---|---|---|---|---|---|
| 10y NFP | 11.4% | 525 | 5.4% | +6.0% | +3.0% |
| 10y FOMC | 8.3% | 387 | 7.4% | +0.9% | -3.1% |
| 30y NFP | 9.8% | 857 | 3.3% | +6.4% | +4.6% |
| 30y FOMC | 10.7% | 663 | 4.3% | +6.4% | +4.1% |

All rows use the ZN price for scale and Figure 2 vols read by eye; 30y rows overstate ZB costs
slightly because ZB trades above ZN. The reason this market could clear the bar where equities
did not: the CBOT tick is a fixed 1/64 of a point while a one-day event straddle's premium grows
with the event variance, so the half-spread share falls as the event gets bigger, and ZB's
premium is about 1.6 to 1.7 times ZN's at the same tick. On single-name equity options one
half-spread is 4 to 6% of premium against a smaller event premium at the touch. The reason it
may not: the 1-tick quote is unverified; CME's own 2019 material says weekly quotes tighten after
a request for quote, which implies the screen is often wider; and the gross edge is pre-2021.

The equity-option vehicle on the same exposure is worse. Lane N17 reports (its `evidence.md`
and `trials.csv`, not re-derived here) a TLT option round trip of 6.4% to 10.3% of a 7-day ATM
straddle on two snapshots and, from VXTLT marks net of that touch, a pooled CPI, NFP and FOMC
7-day short straddle of -7.46% of premium [-12.36%, -2.79%], N=172 (2021-26, descriptive). TLT
options are not the route; CBOT futures options are the only candidate left in this market.

## 8. Verdict and kill criterion

Viable pending a priced data pull. Kill if, on Databento GLBX.MDP3 quotes for 2021-2026 with the
test frozen before the outcome: selling the expiring ZN (and separately ZB) weekly ATM straddle
at the bid at 13:55 CT on the eve, held to the 14:00 CT expiry, net of the exercised future's
half-spread and USD 1.71 a contract each way, has a mean return on premium at or below zero or a
95% date-clustered lower bound below zero on the pooled NFP, CPI and FOMC set; or if the median
quoted ATM width at entry is two ticks or more per leg on ZN (cost then at or above 8.4% of a
525-dollar premium). Matched control: the same trade on non-event expiries of the same weekday.
Forward paper test: one ZN or ZB straddle per NFP, CPI and FOMC eve (about 32 a year), limit
order at mid then the bid, CBOT L1 subscription on, fills logged against the real-time touch.
That book reaches N=32 in a year and measures fills, not significance.

## Not verified

The ATM quoted width on weekly ZN and ZB options; whether Wright's 2011-2020 event VRP survived
2021-2026; the annualisation behind Wright's Figure 2; Databento's per-GB rate for GLBX.MDP3
L1 schemas; SPAN margin on a one-day short straddle; IB paper-account access to CBOT options;
CBOT Globex hours (recalled); Li and Engle (1998) (search summary only); TLT's exact ex-dividend
dates (proxied by the first trading day of each month); the ZN price scale (assumed 110).
