> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Market Data Limitations

## Introduction

Interactive Brokers offers market data for our users to manage their trading behavior. Market data can be retrieved in many forms, including tick data, historical bars, and more.

The [Market Data Page](/docs/general/market-data-subscriptions/introduction) should be thoroughly reviewed prior to implementing any Live or Historical data functionality. The API behavior is heavily dependent upon user permissions and account settings.

## Live Data Limitations

* Unless requesting [Delayed Watchlist Data](/docs/tws-api/doc/md/delayed-data), a paid data subscription is required to receive market data through the API.
* **OSE** exchange data is only available as 15 minute delayed streaming data through API platforms.

## Historical Data Limitations

Historical market data has it’s own set of market data limitations unique to other requests such as real time market data. This section will cover all limitations that effect historical market data in the Trader Workstation API.

### Unavailable Historical Data

The other historical data limitations listed are general limitations for all trading platforms:

* Bars whose size is 30 seconds or less older than six months
* Expired futures data older than two years counting from the future's expiration date.
* Expired options, FOPs, warrants and structured products.
* End of Day (EOD) data for options, FOPs, warrants and structured products.
* Data for expired future spreads
* Data for securities which are no longer trading.
* Native historical data for combos. Historical data is not stored in the IB database separately for combos.; combo historical data in TWS or the API is the sum of data from the legs.
* Historical data for securities which move to a new exchange will often not be available prior to the time of the move. For example, SOXX stock moved to NASDAQ exchange on 15 Oct 2010, so no SOXX data before 15 Oct 2010 can be retrieved despite SOXX was listed in 2001. This limitation also applied to contract which specifies `SMART` as the exchange.
* Studies and indicators such as Weighted Moving Averages or Bollinger Bands are not available from the API.
* Time & Sales data beyond 3 years.

### Pacing Violations for Small Bars (30 secs or less)

Interactive Brokers is not a specialised market data provider and maintains limitations not directly associated to trading. A Pacing Violation occurs whenever one or more of the following restrictions is not observed:

> **Note**
>
> These limitations apply to all clients and cannot be modified. If your trading strategy requirements are not met by our market data services please consider contacting a specialized provider.

* Making identical historical data requests within 15 seconds.
* Making six or more historical data requests for the same Contract, Exchange and Tick Type within two seconds.
* Making more than 60 requests within any ten minute period.

> **Info**
>
> BID_ASK historical data is counted twice.

### Historical Data Filtering

Historical data is filtered for trade types that occur away from the NBBO, such as combo legs, block trades, and derivative trades. For that reason the daily volume from the (unfiltered) real time data functionality will generally be larger than the (filtered) historical volume reported by historical data functions. Differences are expected in other fields such as the VWAP between the real time and historical data feeds.

As historical data at IB gets adjusted, compressed and filtered by default, there may be historical data differences if you request historical data at different time points.

See our FAQ for more insight, [here](https://www.interactivebrokers.com/lib/cstools/faq/#/content/102546341).