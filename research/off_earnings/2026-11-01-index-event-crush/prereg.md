# Pre-registration: index ETF straddles across scheduled events, held one session or overnight

Frozen before any return, P&L or price change is computed from the quotes this study uses. The
quotes were pulled before this text was frozen (`scripts/build/pull_index_chains.py`, capped at
USD 20 with the team lead's go-ahead); no field of them has been read into any calculation. The
only rows seen are four 15:59 SPY call quotes on 2024-07-31, fetched to test the request format.
Record: `outputs/research/prereg_2026-11-01-index-event-crush.json`. Scorer:
`research/off_earnings/2026-11-01-index-event-crush/study.py`. Companion amendment:
`research/off_earnings/preregs/spy_macro_and_runup_amendment_03.md` (executes the frozen SPY macro
families A1 and A2 on this data).

## Why this study exists

Every lever on the single-name earnings straddle fails at the touch for one reason: a premium
visible at the mid that one crossing of a single-name spread (4 to 6% of premium per half-spread
on the hedged books, 11.6% round trip on the next-session book) takes away. Index ETF options cross
for a far smaller share of premium. If any scheduled-event or overnight variance premium exists in
SPY, QQQ or IWM, this is the venue where it can survive execution. The study asks three questions,
each with its own family.

## Hypotheses

- **B1, generic one-session premium.** A short at-the-money SPY straddle sold at 15:59 ET and
  bought back at 15:59 ET on the next session earns a positive mean return net of the touch and
  commissions. Mechanism: the index variance risk premium (Carr and Wu 2009; Bakshi and Kapadia
  2003), which at a horizon of one to a few sessions has been measured at the mid only.
- **B2, mega-cap earnings spillover into QQQ.** A short QQQ straddle held across a night on which
  at least one of AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA or AVGO reports after the close earns
  more than matched ordinary nights. Mechanism: these names are 40 to 50% of the Nasdaq-100, their
  announcement jumps enter QQQ variance, and single-name event premia (Dubinsky et al. 2019; de
  Silva, So and Smith, Review of Finance 2025, on retail-driven overpricing before announcements)
  may transmit into the index option. No published test of this transmission was found.
- **B3, overnight split.** A short at-the-money SPY straddle sold at 15:59 ET and bought back at
  10:00 ET on the next session earns a positive mean net of the touch and commissions. Mechanism:
  Muravyev and Ni (JFE 2020) find delta-hedged S&P 500 option returns of about -1% per close-to-open
  period and +0.3% per open-to-close period, because option prices decay in calendar time while
  variance arrives in trading hours. Their returns are at the mid; they note spreads swamp the
  overnight strategy for most investors. B3 tests it at the touch on the tightest US options.

## Closest prior work and closed studies

Wright (NBER w28306, 2021): significant event-day variance risk premia in S&P 500 futures options
on FOMC and payroll days, measured against five-minute realised variance, not as a traded straddle.
Londono and Samadi (Fed IFDP 2023): SPX straddles lose across data releases, gain across FOMC.
Vilkov (2023): unconditional 0DTE SPX rules held to expiry show a tiny premium that costs remove;
B1 and B3 differ by holding across the close, where Muravyev and Ni locate the premium. Closed in
this project: Deribit BTC macro events (ordinary premium, no event surplus, N=116); index VRP timing
(does not survive post-2008, a timing rule rather than an unconditional book); SPY macro on DoltHub
(data-infeasible, no returns computed). None of those computed a return from a daily US index option
contract history.

## Data and blocks

- Quotes: Databento OPRA `cbbo-1m`, minutes beginning 15:59:00 ET and 10:00:00 ET, every NYSE
  session (`engine.stats.nyse_sessions`) 2016-01-04 to 2026-10-30, SPY, QQQ and IWM, whole-dollar
  strikes within 5% of the reference close, every weekday expiry within ten calendar days. Cache
  `data/cache/index_chains/`.
- Calendars (frozen here): `data/cache/index_events/macro_releases_2016_2026.csv`
  SHA-256 78f52e297f34c3e52ebe9a70e53d33849fa875830eaf430802bdd43ca3b9082a (CPI: latest FRED
  release-10 date per month, which drops February seasonal-factor revisions; payrolls: earliest
  FRED release-50 date per month; FOMC: second day of every scheduled meeting from the Federal
  Reserve calendar pages, unscheduled meetings and notation votes excluded; reconciles exactly with
  the frozen 2019-2024 SPY macro calendar for FOMC, and contains it for CPI and payrolls).
  `data/cache/index_events/megacap_amc_releases_2016_2026.csv`
  SHA-256 860aa6093bb9ddcb7fb8e520e77c5c281ae25e96a76b792cd3e2af5cc839fc44 (EDGAR 8-K Item 2.02
  releases accepted after the close, 360 releases on 274 nights; AVGO before its June 2018 change
  of registrant from the IBES calendar; before-the-open Tesla filings are delivery reports and are
  excluded; EDGAR matches the IBES calendar on 278 of 288 events 2016-2024, every miss explained).
- Blocks: **P** 2016-01-04 to 2018-12-31, **M** 2019-01-02 to 2024-12-31 (discovery),
  **C** 2025-01-02 to 2026-10-30. No index option return has been computed on any block for any
  earlier study in this project.

## Trade construction (all families)

- A trade is indexed by its entry session t. Entry snapshot: 15:59 on t. Exit snapshot: 15:59 on
  the next NYSE session t+1 (B1, B2), or 10:00 on t+1 (B3).
- For each contract the snapshot quote is the last `cbbo-1m` record in the minute. A quote is
  two-sided when 0 < bid <= ask; mid = (bid + ask) / 2.
- Expiry: the shortest expiry, strictly later than the date of t+1, that has at least one strike
  with both legs two-sided at entry. Strike: within that expiry, the strike with both legs
  two-sided at entry minimising |call mid - put mid| (put-call parity locates the forward).
- Exit uses the same two contracts. The short buys back at each leg's ask; a leg with no positive
  ask at exit drops the trade (funnel; dropped trades are compared with kept trades on the
  absolute log move of the parity forward, and the comparison is reported).
- Entry mid premium P0 = call mid + put mid at entry. Returns per unit of P0:
  - short, touch, net: (call bid + put bid at entry - call ask - put ask at exit - 4c) / P0, with
    c = USD 0.0065 per share (USD 0.65 per contract per side) for commissions;
  - short, mid, gross: (call mid + put mid at entry - call mid - put mid at exit) / P0 (descriptive;
    needs two-sided exit quotes).
- Return on margin, secondary: the same dollar P&L divided by P0 + 0.15 x F, F = strike + call mid
  - put mid at entry (a broad-based index short-straddle approximation); per-trade Sharpe is
  reported on both bases.
- Sessions whose snapshot is empty (half-day closes before 15:59, gaps in the vendor feed) yield no
  trade; the count is in the funnel.

## Family B1: generic one-session SPY premium

- Book: every SPY trade, 15:59 to next 15:59.
- Statistic: mean short-touch-net return per trade (unit: P0), and per-trade Sharpe.
- Interval: circular moving-block bootstrap of the trade series in session order, block 10 sessions,
  5,000 draws, seed 0, 95% percentile. The block bootstrap replaces the date-clustered default
  because each date carries one trade and returns are serially dependent through volatility
  clustering; the date-clustered (i.i.d.) interval is reported beside it.
- **Pass:** on M, mean > 0 with the block interval excluding zero; and on P and C, each mean > 0,
  with the block interval of P and C pooled excluding zero.
- **Kill:** M mean <= 0 or its interval includes zero. A pass on M with a validation failure is
  recorded as "in-sample only" and does not pass.

## Family B2: mega-cap spillover into QQQ

- Event trade: a QQQ trade whose entry session t is the release date of at least one mega-cap
  after-close release in the calendar, and whose exit session t+1 is not a macro release date.
  Event trades whose t+1 is a macro release date are excluded and counted.
- Control trade: a QQQ trade whose t carries no mega-cap after-close release, whose t+1 carries no
  macro release, and which is not an event trade.
- Matched control for an event: the mean short-touch-net return of control trades with the same
  calendar days to expiry at entry and the same entry weekday, entered within 60 sessions either
  side of the event. Events with fewer than five matched controls are dropped (funnel).
- Statistic: mean paired difference (event minus matched control), unit P0; date-clustered interval
  (`protocol.date_clustered_ci`, 5,000 draws, seed 0, 95%).
- **Pass:** on M, mean difference > 0 with the interval excluding zero; and on P and C pooled, the
  interval excluding zero, with each block's mean > 0. Also required: the event book's own mean
  short-touch-net return > 0 on M (an event surplus on a losing book is not a strategy).
- **Kill:** M difference <= 0 or its interval includes zero.
- Mechanism check, descriptive: mean |log(F_exit / F_entry)| on event nights against the implied
  one-night move from matched-control-adjusted premia.

## Family B3: overnight SPY

- Book: every SPY trade, 15:59 to 10:00 on t+1, same contract rule as B1 (so B1 and B3 hold the same
  contracts and differ only in the exit time).
- Statistic, interval, pass and kill: as B1.
- Descriptive: the paired difference B3 minus B1 (the 10:00-to-15:59 leg), and its sign against
  Muravyev and Ni.

## Secondary, descriptive only (cannot rescue a failed primary)

- B1 and B3 on QQQ and IWM (sign consistency with SPY).
- Results by year, by days to expiry at entry, at the mid, and on margin.
- Tail: worst five trades, maximum drawdown of a one-straddle-per-trade book in units of mean P0,
  skewness, and the share of total P&L from the worst 1% of trades. A passing book is reported with
  its tail stated beside its Sharpe, because a short-volatility book's Sharpe understates its risk.
- Annualisation, where shown: per-trade Sharpe x sqrt(trades per year inferred from the book's own
  cadence), stated beside the number.
- Deflated Sharpe ratio against the programme trial count below.

## What is not allowed

No change to the snapshot times, expiry rule, strike rule, cost basis, blocks, control matching or
calendars after any return is seen. Any amendment is dated, hashed and reported beside the original.

## Trial accounting

This study declares three trials (B1, B2, B3); amendment 03 re-executes the two SPY macro families
on new data and counts them again (two). The count after this study is 1,544 + 5 = 1,549, with the
1,532 base inheriting the disagreement recorded in `docs/RESEARCH_STATE.md` section 1.
