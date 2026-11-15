# Lanes

Each lane is a starting point, not a cage: follow the evidence, but stay inside your market so
lanes do not duplicate each other. Seeds marked "recalled" are leads to verify at the source,
not facts.

## N01 grains-usda

CBOT corn, soybean and wheat options (including weeklies and short-dated new-crop options)
around USDA reports: WASDE, Grain Stocks, Prospective Plantings, Acreage, Crop Production. Several
are released at 12:00 ET during the session; check whether any are released while the market is
closed. Recalled leads: Isengildina-Massa, Irwin, Good and Gomez on implied volatility around
WASDE; McKenzie, Thomsen and Dixon on report-day option returns; CME's own notes on report-day
vol. Key questions: the size of the report-day implied-vol drop, the bid-ask on front options,
and whether the pre-report premium exceeds realised report-day variance after costs.

## N02 livestock-usda

CME lean hog and live and feeder cattle options around Hogs and Pigs and Cattle on Feed, which
are released after the close (often Friday 15:00 ET), the closest structural analogue to
after-close earnings. Liquidity is thin: measure it. Also Cold Storage and Livestock Slaughter.

## N03 natgas-storage

NYMEX Henry Hub natural gas options, including weekly options, around the EIA weekly storage
report (Thursday 10:30 ET). Recalled lead: Linn and Zhu (2004) on natural gas volatility and
storage announcements. Weekly options expiring around the report make the event share of
variance large.

## N04 crude-eia-opec

NYMEX WTI and Brent options, weekly options included, around the EIA Weekly Petroleum Status
Report (Wednesday 10:30 ET), the API report (Tuesday after the close), OPEC and OPEC+ meetings,
and the monthly IEA and OPEC reports. Also options on USO if useful as a vehicle.

## N05 treasuries-macro

CBOT Treasury futures options (ZN, ZB, ZF, ZT, including weekly and Wednesday and Friday
expiries) around CPI, payrolls, FOMC and refunding and auction days. Recalled lead: Beber and
Brandt (2006) on implied volatility falling after macro announcements in Treasury options. 08:30
releases fall before the cash open but inside the Globex session: map the session.

## N06 sofr-fomc

CME SOFR futures options and mid-curve options around FOMC decisions, minutes and the dot plot.
Compare option-implied event variance with realised; look at whether the market overpays for
FOMC outcomes it has already priced in futures.

## N07 fx-central-banks

CME FX futures options (euro, yen, sterling, Australian and Canadian dollar, including weeklies)
and any FX options IB offers, around ECB, BoJ, BoE, RBA and BoC decisions and US releases. In OTC
FX, dealers quote explicit event vols for central-bank dates (verify). BoJ and RBA decisions land
while US markets are closed.

## N08 index-macro-cached

SPY, QQQ and IWM options around FOMC, CPI, payrolls and PCE, using the cached Databento 15:59 and
10:00 snapshots in `data/cache/index_chains` (2016-2026, already paid for, zero spend). The
DoltHub SPY macro test failed for lack of data (N=5); this cache removes that limit. Test the
straddle sold at the 15:59 close before an 08:30 release and bought back at 10:00, against matched
non-event nights, and FOMC days (14:00 release) where the hold is intraday. Recalled leads on
zero-days-to-expiry options and macro announcements (Bandi and co-authors; Beckmeyer, Branger and
Gayda): verify. This lane can produce a real backtest today: run it to the frozen held-out read.

## N09 vix-complex

Cboe VIX options and VIX futures around FOMC, CPI and the monthly VIX settlement (the special
opening quotation). Also the SPX-VIX relationship on event days. Free data: Cboe's historical VIX
futures settlements and any free VIX options history you can find.

## N10 crypto-scheduled

CME bitcoin and ether options (including micro and weekly contracts) and options on spot bitcoin
ETFs (IBIT and peers), around crypto-native scheduled events rather than macro releases, which
are closed: network upgrades, ETF decisions, token unlocks, the halving, large Deribit quarterly
expiries. `data/cache/deribit` holds earlier pulls; Deribit's public API is free and needs no key
for market data. Measure the event premium on Deribit, then ask whether the IB-tradable vehicle
carries it.

## N11 forecastex-event-contracts

IB's own event-contract venue, ForecastEx (ForecastTrader), on CPI, FOMC, payrolls and other
releases. Kalshi tail selling and making are closed; the new angle is the gap between
ForecastEx prices and the probabilities implied by listed options or futures on the same release
(CME FedWatch, SOFR options, CPI swaps or Treasury options), and the favourite-longshot bias on
this venue specifically. Check paper-trading availability, fees and any free price history.

## N12 metals-macro

COMEX gold, silver and copper options, weeklies included, and options on GLD and SLV, around
FOMC, CPI and payrolls. Gold reacts to real rates: map which releases move it and whether the
options overprice them.

## N13 softs-ice

ICE US coffee, cocoa, sugar and cotton options around scheduled reports (CONAB and USDA crop
reports, ICO data, certified stock releases). Check IB access to ICE US options and their
liquidity honestly; thin markets may make the touch prohibitive.

## N14 bank-stress-tests-and-regulatory

US single-name options on scheduled non-earnings corporate and regulatory events: Federal
Reserve stress-test results (released after the close in late June) for large banks, capital
plan announcements, and large-cap biotech PDUFA dates where options are liquid. Use the cached
equity option sources the project already holds where they cover these names; the FDA advisory
committee pilot is closed, PDUFA dates on liquid names are not.

## N15 adr-overnight-reporters

US-listed options on ADRs and foreign large caps whose earnings are released while US markets
are closed but outside the usual US after-close window (Europe and Japan before the US open,
Asia overnight). Does the crush, spread and premium differ from US reporters, and is the touch
cheaper? Use cached option data where these names are covered.

## N16 country-etf-politics

Options on country and regional ETFs (EWZ, EWW, FXI, EWJ, EWG, INDA, EWT and peers) around
foreign elections, referendums and emerging-market central-bank decisions. Recalled lead: Kelly,
Pastor and Veronesi (2016) on the price of political uncertainty in options. Also the option on
the ETF against the home-market index option where both are tradable at IB.

## N17 commodity-etf-options

US equity options on commodity and rates ETFs (USO, UNG, GLD, SLV, TLT, and the agricultural
ETFs) around the same scheduled reports as lanes N01 to N05. The question is the vehicle: equity
option spreads and data access may be easier than futures options. Coordinate by reading the
futures lanes' folders before finishing, not by duplicating them.

## N18 literature-map

A systematic map of documented scheduled-event volatility premia across every asset class:
for each, the paper, sample, effect size, whether costs were measured, the event-time structure,
and later replications or failures. Rank by net-of-cost evidence. Include the strongest
counter-evidence (studies finding no event premium after costs). This lane writes the evidence
map the other lanes can cite; finish with a ranked list of the five most promising
market-and-event pairs not already on the closed list.

## N19 data-access

An inventory of every free or scrapable source of historical option quotes outside US single
stocks: exchange settlement archives (CME, Cboe, ICE), free samples (Cboe DataShop, CME
DataMine samples), Nasdaq Data Link free tables, Barchart and similar public pages, academic
datasets, Deribit's public API, and what is already in `data/cache/`. For each: coverage,
granularity (quotes or settlements), history, terms of use, and how to get it. Price the paid
alternatives (Databento CME and OPRA, Cboe DataShop, CME DataMine) from public price lists for
the specific pulls lanes N01 to N13 would need. This lane decides which pilots are feasible.

## N20 ib-execution

What it takes to paper trade each candidate at IB: product permissions, futures-option
availability on paper accounts, market-data subscriptions and their cost, the fifteen-minute
delay landmine, commissions per contract by product, SPAN margin for a short straddle, order
types for spreads (combo orders), event-time trading hours, and early-exercise or assignment
rules for American futures options. Read the project's live harness
(`earnings_iv_crush/live/`, read only, never run it) and say what would have to change for it to
trade a futures option or a ForecastEx contract. Do not connect to anything.
