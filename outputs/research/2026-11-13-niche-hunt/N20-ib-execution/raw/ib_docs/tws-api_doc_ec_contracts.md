> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Event Contract Definition & Discovery

## Introduction

IB's Event Contract instrument records use the following fields inherited from the options model:

* An **underlier**, which may or may not be artificial:
  * For **CME products**, a tradable Event Contract will have the relevant CME future as its underlier. Therefore, the security type of the CME contract will be a futures option, or "FOP".
  * For **ForecastEx products**, IB has generated an artificial underlying index which serves as a container for related Event Contracts in the same product class. These artificial indices do not have any associated reference values and are purely an artifact of the option instrument model used to represent these Event Contracts. However, these artificial underlying indices can be used to search for groups of related Event Contracts, just as with index options. Therefore, the security type of ForecastEx products are always options, or "OPT".
* An **Exchange** value will reflect the listing exchange of the given Event contract.
  * ForecastEx contracts will always use "FORECASTX" as the exchange value. Note the value does not include the final "E" in "ForecastEx".
  * A CME product may use "CBOT", "CME", "COMEX", or "NYMEX" depending on the contract's listing.
* A **Symbol** value which matches the symbol of the underlier, and which reflects the issuer's product code.
* A **Trading Class** which also reflects the issuer's product code for the instrument, and in the case of CME Group products, is used to differentiate Event Contracts from CME futures options.
  * Note that many CME Group Event Contracts, which resolve against CME Group futures, are assigned a Trading Class prefixed with "EC" and followed by the symbol of the relevant futures product, to avoid naming collisions with other derivatives (i.e., proper futures options listed on the same future).
* A **Put or Call (Right)** value, where Call = Yes and Put = No.
  * Note that ForecastEx instruments do not permit Sell orders. Instead, ForecastEx positions are flattened or reduced by buying the opposing contract. CME Group Event Contracts permit both buying and selling.
* An artificial **Contract Month** value, again used primarily for searching and filtering available instruments. Most Event Contract products do not follow monthly series as is common with index or equity options, so these Contract Month values are typically not a meaningful attribute of the instrument. Rather, they permit filtering of instruments by calendar month.
  * Requesting Contract Details for a given instrument will return a "realExpirationDate", which will correspond with the same values printed in the Prediction Markets page.
* A **Last Trade Date, Time, and Millisecond** values, which together indicate precisely when trading in an Event Contract will cease, just as with index options.
* A **Strike** value, which is the numerical value on which the event resolution hinges. Though numerical, this value need not represent a price.
* An **instrument description (or "local symbol")** in the form `"PRODUCT EXPIRATION STRIKE RIGHT"`, where:
  * `PRODUCT` is the issuer's product identifier
  * `EXPIRATION` is the date of the instrument's resolution in the form `MmmDD'YY`, e.g., "Sep26'24"
  * `STRIKE` is the numerical value that determines the contract's moneyness at expiration
  * `RIGHT` is a value YES or NO

## ForecastEx Contract Example

---

Given the information above, we can establish a working example against the Global Carbon Dioxide Emissions contract on the [Prediction Markets Website](https://www.interactivebrokers.com/predictionmarkets/app/#/).

Reviewing the page to the right, we can see all of the contract details necessary to get started.

1. Above the chart next to the contract name, we can see the Symbol, `"GCE"`.
2. On the left side of the web page, we can find the contract's expiration date, June 30, 2026.
3. Equally important is the value on the right, "Market closes in 287 days."
4. The bolded excess on the top, `405000`, indicates our strike price. This can be corroborated by the table on the left which acts like an Option Chain table users may be more familiar with.

While not explicitly stated in the web page, there are several details that may be inferred based on the information present:

1. All ForecastEx contracts use the `"OPT"` security type, as mentioned in the [Contract Definition & Discovery](/docs/tws-api/doc/ec/contracts) section above.
2. The ForecastEx exchange value is listed as `"FORECASTX"`, `"KALSHI"`, and `"CME"`.
3. All currently offered Event Contracts are hosted in the United States of America, and therefore will always use `"USD"` as their currency value.
4. "Yes" or "No" contracts are based on option rights, `"Call"` and `"Put"` respectively.

![Displays an example of a Forecast Contract being shown in Prediction Markets.](/docs/_fern-files/_img/ad55ea28e5cddc05368783f1245c1f651f424d46b6fcda8410426b9b8f610177.webp)

In order to request our specific contract, we will need to focus on the "Market closes in 287 days" statement. This value indicates the last day the contract may be traded.

This document is written on the 19th of March, 2025. That is the 78th day of the calendar year.

Given the context that this is day 78, and the market will close in 287 days, the contract's last trade date would then be the 365th day of the year, or December 31st, 2025.

Given the TWS API date standards, this will be written as `20251231`.

This information can now be distilled into a standard TWS API contract definition:

#### Python

```python
contract= Contract()
contract.symbol = "GCE"
contract.secType = "OPT"
contract.currency = "USD"
contract.exchange = "FORECASTX"
contract.lastTradeDateOrContractMonth = "20251231"
contract.right = "C"
contract.strike = 40500
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("GCE");
contract.secType("OPT");
contract.currency("USD");
contract.exchange("FORECASTX");
contract.lastTradeDateOrContractMonth("20251231");
contract.right("C");
contract.strike(40500);
```

#### C++

```cpp
Contract contract;
contract.symbol = "GCE";
contract.secType = "OPT";
contract.currency = "USD";
contract.exchange = "FORECASTX";
contract.lastTradeDateOrContractMonth = "20251231";
contract.right = "C";
contract.strike = 40500;
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "GCE";
contract.SecType = "OPT";
contract.Currency = "USD";
contract.Exchange = "FORECASTX";
contract.LastTradeDateOrContractMonth = "20251231";
contract.Right = "C";
contract.Strike = 40500;
```