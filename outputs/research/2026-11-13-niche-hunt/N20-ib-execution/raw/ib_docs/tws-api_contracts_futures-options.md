> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Futures Options

**Symbol:** String. Specify the underlying symbol of the futures option.

**SecType:** String. Specify FOP.

**Exchange:** String. Specify the exchange where the underlying is traded.

**Currency:** String. Specify the base currency of the futures option.

**LastTradeDateOrContractMonth:** String. Enter the month the contract expires. In the event there are multiple expiries in the same month, exact date must be specified.

**Strike:** float. Enter the strike price of the derivative.

**Right:** String. Enter the right, "C" for Calls and "P" for Puts.

**Multiplier:** String. Enter the multiplier of the derivative.

#### Python

```python
contract = Contract()
contract.symbol = "GBL"
contract.secType = "FOP"
contract.exchange = "EUREX"
contract.currency = "EUR"
contract.lastTradeDateOrContractMonth = "20230224"
contract.strike = 138
contract.right = "C"
contract.multiplier = "1000"
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("GBL");
contract.secType("FOP");
contract.exchange("EUREX");
contract.currency("EUR");
contract.lastTradeDateOrContractMonth("20230224");
contract.strike(138);
contract.right("C");
contract.multiplier("1000");
```

#### C++

```cpp
Contract contract;
contract.symbol = "GBL";
contract.secType = "FOP";
contract.exchange = "EUREX";
contract.currency = "EUR";
contract.lastTradeDateOrContractMonth = "20230224";
contract.strike = 138;
contract.right = "C";
contract.multiplier = "1000";
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "GBL";
contract.SecType = "FOP";
contract.Exchange = "EUREX";
contract.Currency = "EUR";
contract.LastTradeDateOrContractMonth = "20230224";
contract.Strike = 138;
contract.Right = "C";
contract.Multiplier = "1000";
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "GBL"
contract.SecType = "FOP"
contract.Exchange = "EUREX"
contract.Currency = "EUR"
contract.LastTradeDateOrContractMonth = "20230224"
contract.Strike = 138
contract.Right = "C"
contract.Multiplier = "1000"
```