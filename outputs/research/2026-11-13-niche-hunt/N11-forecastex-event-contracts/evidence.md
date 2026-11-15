# N11 ForecastEx event contracts: evidence dossier

## Hypothesis, scope and success criteria

ForecastEx is Interactive Brokers' own CFTC-registered event-contract exchange. The lane asked
whether its contracts on scheduled US releases (CPI, FOMC, payrolls, unemployment) carry a
premium that survives costs: either a gap to a better-informed reference price on the same
question, or a favourite-longshot bias specific to this venue. Both were tested on free data
with a pre-registered discovery and held-out split (`diagnosis.log`, `freeze_2026-11-13.md`).

- H1, cross-venue gap: where ForecastEx and Kalshi price the identical question differently,
  Kalshi is the better forecast, so buying on ForecastEx the side Kalshi says is cheap earns a
  positive net return held to resolution.
- H2, favourite-longshot: buying the favourite (print 0.90 or more, or the NO side at 0.10 or
  less) earns a positive net return.
- Pass: mean net P&L per contract with a date-clustered 95% interval above zero on the held-out
  block (releases from 2026-01-01), with at least 30 bets (H1: contracts) on at least 10 release
  dates.

## Verdict

Not viable. Both hypotheses passed discovery and failed the single held-out read. The closed
Kalshi results do not change on this venue, and capacity is in the tens of dollars per release
even where an edge appeared. No metered pull would change this, because ForecastEx publishes its
full trade history free; the data is not the constraint.

## The venue (verified at source unless marked)

- Market structure: a buy-only book. A contract exists when a Yes bid and a No bid sum to 1.00;
  bids run 0.01 to 0.99; positions are closed by buying the opposite side (Rulebook Rule 401(d)).
  Price-time priority, with bids of IB-affiliated participants filled last at every price level
  (Rule 405). There is no ask; the exchange defines the spread as 1.00 minus the best Yes bid
  minus the best No bid (Liquidity Retainer Program).
- Liquidity provision: at most three paid market makers per product under the Liquidity
  Retainer Program, rewarded for presence within a maximum spread; daily reward pools are
  published (for example core CPI 7.26 dollars and Fed decision 23.69 dollars on 2026-11-12,
  `liquidity_rewards/` in the public bucket).
- Timing: macro contracts trade until the release instant (CPI and employment 07:30 CT, FOMC
  13:00 CT); delayed releases move the resolution time (contract terms). Trading runs around the
  clock (IB ForecastTrader page). All information arrives at a single scheduled instant, so the
  position carries the whole release jump; there is no overnight-gap analogue and no exit after
  the event, because the contract settles at 0 or 1.
- Size of the macro segment: economic indicators were 2.58% of ForecastEx contracts traded from
  2025-01-01 to 2026-11-12 (daily summaries; median 14,534 contracts a day). Weather, sports,
  financial-market and election contracts make up the rest. Fed decision (FFDEC) is the largest
  macro product (10.6 million contracts since June 2025).

## Prior work

- Diercks, Katz and Wright, "Kalshi and the rise of macro markets", FEDS 2026-010 and NBER
  w34702 (verified). Kalshi FOMC median and mode forecasts had zero absolute error on FOMC day
  since 2022 against 0.010 for fed funds futures (Diebold-Mariano p below 0.05); core CPI MAE
  0.070, equal to the Bloomberg consensus; densities "fairly well calibrated", with some risk
  premium overstating higher inflation and unemployment. They note SOFR options map to specific
  meetings only under strong assumptions, and that IB's venue has fewer contracts, lower
  liquidity and smaller position limits. No trading costs are measured.
- Bürgi, Deng and Whelan, "Makers or takers: the economics of the Kalshi prediction market",
  GWU CER WP 2026-001 (verified). Over 300,000 contract prices: contracts under 10 cents lose
  over 60% of the stake; contracts above 50 cents earn small positive returns; the bias is
  stronger for takers. Economics-category slope of pre-fee profit on price 0.034 (s.e. 0.010).
- Closed in this project: Kalshi tail selling -2.03% per bet [-4.07%, +0.21%], N=383; Kalshi maker
  -1.37% on unseen series (`research/other_markets/findings/`).
- Cross-venue law of one price: arXiv 2601.01706 finds Polymarket and Kalshi 2024 election prices
  diverge after execution costs, attributing it to resolution wording and limits to arbitrage
  (recalled from a search summary, not read). Gürkaynak and Wolfers (NBER w11929) on the
  2002-2007 Goldman Sachs and Deutsche Bank economic-derivative auctions: 153 auctions, market
  forecasts slightly more accurate than the survey, not significantly; risk premium small
  (recalled from the NBER digest).
- No academic study of ForecastEx was found. IB's own economist publishes daily "Mispricing in
  tomorrow's US forecast trades" notes on ForecastEx contracts (verified), which is commentary,
  not a tested strategy.
- Crowding: the favourite-longshot question is crowded (Kalshi, Polymarket, and this project's
  closed study). The ForecastEx-against-Kalshi gap had no direct prior test that I could find.

## Why Kalshi, not FedWatch, SOFR options or CPI swaps, as the reference

The lane named CME FedWatch, SOFR options, CPI swaps and Treasury options as references. Kalshi
dominates them for this purpose, on published evidence: it beat fed funds futures on FOMC
accuracy, and SOFR options need strong assumptions to isolate one meeting (Diercks, Katz and
Wright). CPI fixings and swaps give point estimates, not the probability of a threshold, and I
know of no free intraday history (recalled). Kalshi also lists the identical questions on the
same release with identical resolution sources, its full hourly bid and ask history is free
through a public API, and it is itself tradeable at IB (USD 0.01 commission plus USD 0.01
exchange fee per contract, IB pricing page). Fed decision contracts add little: on the day
before the meeting they are near-certain, and none survived the H1 funnel in discovery.

## Tradability at IB (verified unless marked)

- Product: ForecastEx contracts, TWS API secType OPT, exchange FORECASTX, Yes = call, No = put,
  symbol = product code (FFDEC, FF, CPIC, CPIY, UNR, PREMP, IJC, PCEY). No sell orders.
- Costs: IB commission USD 0.00 plus ForecastEx exchange fee USD 0.01 per contract, charged on
  both sides of every execution (IB pricing page; ForecastEx fee schedule). Held to resolution
  there is no exit fee. Full collateral (the price paid); no SPAN or Reg-T leverage. IB pays a
  3.38% APY incentive coupon on the closing market value, which is negligible over one day.
- Paper account: not confirmed. IB promotes a free "Prediction Market Simulator", but I found no
  IB page stating that ForecastEx trades in a paper account (unverified; the web search budget
  ran out before this could be settled).
- Market data: whether ForecastEx quotes at IB need a paid subscription is not confirmed
  (unverified).

## Data (verified)

- ForecastEx publishes, free and without login, daily CSVs in a public bucket behind
  https://data.forecastex.com: pairs (every matched trade, Yes and No price, quantity, nanosecond
  timestamp) from 2024-08-01; daily prices (open, high, low, close, settlement, open interest,
  VWAP); and daily product summaries from 2025-01-01. There are no quotes and no aggressor flag,
  so the touch is not observable historically. Cost: zero.
- Pulled for this lane: 838 pair files (7.9 million rows, cut to 602,541 macro and index rows),
  834 price files cut to economic products (6.9 million rows), 683 summaries; plus 1,899 Kalshi
  twin markets and 65,130 hourly candles from the Kalshi public API. On disk 29 MB under
  `data/`. Rebuild: `python scripts/fetch_forecastex.py daily_summary pairs` then
  `python scripts/fetch_forecastex.py prices --econ-only`, and `python scripts/fetch_kalshi.py`
  (about 60 minutes in total at one request a second per host).
- Touch estimate: the Roll estimator (the spread implied by negative autocorrelation of
  consecutive price changes) gives 4.0 cents for core CPI and 0.65 cents for Fed decision over
  the last 72 hours before release; it is undefined for the other products because price changes
  trend. The pilot charges 2 cents against each fill print plus the 1-cent fee, and reports 1 and
  3 cents.

## Pilot

Design (pre-registered, `diagnosis.log` entry 1, revised once on discovery in entry 2). One
observation per ForecastEx contract on six products with an exact Kalshi twin (Fed decision bins,
fed funds level with ForecastEx strike k against Kalshi k + 0.125, CPI and core CPI year on year,
unemployment, payrolls; jobless claims excluded because ForecastEx says "exceed" and Kalshi "at
least"). Signal at a ForecastEx print between 24 hours and 1 hour before the release, against the
Kalshi mid from the last two-sided hourly candle at or before it; bet when the gap is at least 4
cents; fill at the next ForecastEx print. ForecastEx and Kalshi settlements agreed on 100% of
matched contracts in every product, which validates the mapping. Discovery is releases before
2026-01-01; held-out is 2026-01-01 to 2026-11-13. All numbers are dollars per contract (a
contract pays at most one dollar), net of the fee and a 2-cent adverse fill, held to resolution,
date-clustered 95% intervals. Source: `logs/` files named in `trials.csv`.

| Trial | Rule | Discovery | Held-out |
|---|---|---|---|
| 2,386 (H1 primary) | every qualifying print, averaged within contract | +0.101 [+0.000, +0.191], 56 contracts, 21 dates | -0.039 [-0.154, +0.077], 58 contracts, 19 dates |
| 2,387 (H1 support) | first print per contract | +0.101 [+0.023, +0.182], N=29, 17 dates | +0.030 [-0.141, +0.175], N=21, 12 dates |
| 2,385 (H2) | favourite at 0.90 or more | +0.019 [+0.015, +0.023], N=141, 53 dates | -0.007 [-0.061, +0.029], N=91, 47 dates |

Mechanism checks. In discovery, Kalshi was the better forecast (Brier score of the ForecastEx
print minus that of the Kalshi mid +0.0056 [+0.0010, +0.0104], 77 observations) and the gross gap
capture was +0.131 [+0.052, +0.212]. In held-out both lose significance: Brier gap +0.0019
[-0.0063, +0.0090] over 91 observations, gross gap capture +0.060 [-0.111, +0.205]. Why the gap
stopped being informative is not established; more cross-venue market making in 2026 is one
explanation (conjecture).

Exploratory, not findings: the H1 sign depends on weighting (held-out per bet +0.149 [-0.064,
+0.277] on 628 bets, per contract -0.039), so a few heavily traded contracts decide the result.
H2's discovery pass came from 149 favourites without a single loser at a mean price of 0.953,
where fair pricing implies about seven; in held-out 3 of 94 lost (two payroll contracts at
-0.965 each). That is the closed Kalshi pattern: cents per bet against a tail the sample may or
may not contain.

Cost against premium. Where the gap was informative (discovery), the 3 cents of cost was 23% of
the 13-cent gross capture; for H2 the same 3 cents was about 70% of the 4.4-cent edge over the
fill print. The half-spread is not the binding problem on ForecastEx. Instability and size are.

Capacity. The median fill print is 10 contracts (N=50 H1 bets). A typical release trades 410 (core
CPI) to 1,016 (fed funds level) contracts in its last 24 hours. Even the discovery edge would
earn about one dollar per bet.

Attrition. Of 2,456 contracts in the H2 products with any print, 799 had an entry print in the
window, 645 a later fill print and 635 a 0 or 1 settlement. Every contract dropped as unsettled
on its expiration date belongs to an October to December 2025 CPI, unemployment or claims
release, the window in which the federal shutdown delayed or cancelled data (shutdown timing
recalled, not checked); they are excluded from both blocks. In held-out, H1 drops
(no two-sided Kalshi quote) settled YES at 0.50 against 0.45 for kept observations; in discovery
0.56 against 0.42. Drops are not neutral in base rate; they are small in number (18 of 109
matched held-out contracts).

## Kill criterion and a forward test

Pre-registered kill: held-out interval including zero, or a negative mean with non-positive gap
capture. H1 meets the first and H2 both; the line is closed on this evidence. A forward paper test
would only be worth running if the per-release volume on ForecastEx macro contracts rose by an
order of magnitude, and it would need to record quotes on both venues, not prints. The free
ForecastEx feed refreshes every ten minutes, so a quote-free forward log costs nothing.

## Open and not verified

- Whether ForecastEx trades in an IB paper account, and whether its market data needs a
  subscription (no IB page found; web search budget exhausted).
- The ForecastEx order book: no historical quotes exist publicly, so every cost here is an
  allowance against prints, not a measured touch.
- An untested, related idea with the project's own data: ForecastEx FES and FNQ contracts are
  daily digitals on S&P 500 and Nasdaq-100 futures (22.8 million and 12.3 million contracts from
  2025-01-01 to 2026-11-12, daily summaries). On CPI and FOMC days they could be compared with digitals implied by the cached SPY and
  QQQ 15:59 chains (`data/cache/index_chains`). It is a scheduled-event comparison against
  listed options, as the lane asked, but it is not tested here.

Files: `C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N11-forecastex-event-contracts\`
