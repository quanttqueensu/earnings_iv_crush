> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Options

**Symbol:** String. Specify the underlying symbol of the option.

**SecType:** String. Specify OPT.

**Exchange:** String. SMART routing may be specified. May use direct routing such as BOX.

**Currency:** String. Specify the base currency of the option.

**LastTradeDateOrContractMonth:** String. Enter the month the contract expires. In the event there are multiple expiries in the same month, exact date must be specified.

**Strike:** float. Enter the strike price of the derivative.

**Right:** String. Enter the right, "C" for Calls and "P" for Puts.

**Multiplier:** String. Enter the multiplier of the derivative.

#### Python

```python
contract = Contract()
contract.symbol = "GOOG"
contract.secType = "OPT"
contract.exchange = "BOX"
contract.currency = "USD"
contract.lastTradeDateOrContractMonth = "20190315"
contract.strike = 1180
contract.right = "C"
contract.multiplier = "100"
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("GOOG");
contract.secType("OPT");
contract.exchange("BOX");
contract.currency("USD");
contract.lastTradeDateOrContractMonth("20190315");
contract.strike(1180);
contract.right("C");
contract.multiplier("100");
```

#### C++

```cpp
Contract contract;
contract.symbol = "GOOG";
contract.secType = "OPT";
contract.exchange = "BOX";
contract.currency = "USD";
contract.lastTradeDateOrContractMonth = "20190315";
contract.strike = 1180;
contract.right = "C";
contract.multiplier = "100";
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "GOOG";
contract.SecType = "OPT";
contract.Exchange = "BOX";
contract.Currency = "USD";
contract.LastTradeDateOrContractMonth = "20190315";
contract.Strike = 1180;
contract.Right = "C";
contract.Multiplier = "100";
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "GOOG"
contract.SecType = "OPT"
contract.Exchange = "BOX"
contract.Currency = "USD"
contract.LastTradeDateOrContractMonth = "20190315"
contract.Strike = 1180
contract.Right = "C"
contract.Multiplier = "100"
```