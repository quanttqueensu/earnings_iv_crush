> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Futures

## Index Futures

Index futures are typical futures contracts derived from an Index, such as "ES" or "DAX". Futures contracts may be generally defined with `Symbol`, `SecType`, `Exchange`, `Currency`, `LastTradeDateOrContractMonth`, `Multiplier`, and `TradingClass`.

#### Python

```python
contract = Contract()
contract.symbol = "ES"
contract.secType = "FUT"
contract.exchange = "CME"
contract.currency = "USD"
contract.lastTradeDateOrContractMonth = "202809"
contract.multiplier = 50
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("ES");
contract.secType("FUT");
contract.exchange("CME");
contract.currency("USD");
contract.lastTradeDateOrContractMonth("202809");
contract.multiplier(50);
```

#### C++

```cpp
Contract contract;
contract.symbol = "ES";
contract.secType = "FUT";
contract.exchange = "CME";
contract.currency = "USD";
contract.lastTradeDateOrContractMonth = "202809";
contract.multiplier = 50;
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "ES";
contract.SecType = "FUT";
contract.Exchange = "CME";
contract.Currency = "USD";
contract.LastTradeDateOrContractMonth = "202809";
contract.Multiplier = 50;
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "ES"
contract.SecType = "FUT"
contract.Exchange = "CME"
contract.Currency = "USD"
contract.LastTradeDateOrContractMonth = "202809"
contract.Multiplier = 50
```

## Continuous Futures

Users may choose to use Continuous Futures as well, which automatically presents the front future contract for customers to request historical data.

This security type can only be used in the TWS API to request historical data.

Continuous Futures can **not** be used:

* For placing orders
* For live market data
* For **specific** historical data. Please be aware that endDateTime must be left as an empty string when requesting historical data for continuous futures contracts.
* In the Web API

#### Python

```python
contract = Contract()
contract.symbol = "ES"
contract.secType = "CONTFUT"
contract.exchange = "CME"
contract.currency = "USD"
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("ES");
contract.secType("CONTFUT");
contract.exchange("CME");
contract.currency("USD");
```

#### C++

```cpp
Contract contract;
contract.symbol = "ES";
contract.secType = "CONTFUT";
contract.exchange = "CME";
contract.currency = "USD";
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "ES";
contract.SecType = "CONTFUT";
contract.Exchange = "CME";
contract.Currency = "USD";
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "ES"
contract.SecType = "CONTFUT"
contract.Exchange = "CME"
contract.Currency = "USD"
```

## Expired Futures

While they can not be traded, TWS API users can refer to expired Futures contracts by including the ["IncludeExpired"](/docs/tws-api/ref/contract) field. This will permit users to review historical market data for contracts that have expired within the last 2 years.
This functionality is not supported in the web api.

#### Python

```python
contract = Contract()
contract.symbol = "ES"
contract.secType = "FUT"
contract.exchange = "CME"
contract.currency = "USD"
contract.lastTradeDateOrContractMonth = "202309"
contract.includeExpired = True
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("ES");
contract.secType("FUT");
contract.exchange("CME");
contract.currency("USD");
contract.lastTradeDateOrContractMonth("202309");
contract.includeExpired(true);
```

#### C++

```cpp
Contract contract;
contract.symbol = "ES";
contract.secType = "FUT";
contract.exchange = "CME";
contract.currency = "USD";
contract.lastTradeDateOrContractMonth = "202309";
contract.includeExpired = true;
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "ES";
contract.SecType = "FUT";
contract.Exchange = "CME";
contract.Currency = "USD";
contract.LastTradeDateOrContractMonth = "202309";
contract.IncludeExpired = true;
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "ES"
contract.SecType = "FUT"
contract.Exchange = "CME"
contract.Currency = "USD"
contract.LastTradeDateOrContractMonth = "202309"
contract.IncludeExpired = True
```