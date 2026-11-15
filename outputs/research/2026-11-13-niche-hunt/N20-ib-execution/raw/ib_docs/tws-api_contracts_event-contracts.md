> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Event Contract

Event contracts utilize the same contract structure as Options with a few exceptions.

* Exchange may be set to `FORECASTX`, `KALSHI`, and `CME`.
* SecType should be set to "OPT"
* "Yes" or "No" contracts are "Call" and "Put" respectively.

## ForecastEx Contract Example

#### Python

```python
# Event Contract for 2025 Global Carbon Dioxide Emissions reaching 40,5000.
contract = Contract()
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
// Event Contract for 2025 Global Carbon Dioxide Emissions reaching 40,5000.
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
// Event Contract for 2025 Global Carbon Dioxide Emissions reaching 40,5000.
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
// Event Contract for 2025 Global Carbon Dioxide Emissions reaching 40,5000.
Contract contract = new Contract();
contract.Symbol = "GCE";
contract.SecType = "OPT";
contract.Currency = "USD";
contract.Exchange = "FORECASTX";
contract.LastTradeDateOrContractMonth = "20251231";
contract.Right = "C";
contract.Strike = 40500;
```

#### VB.NET

```vbnet
' Event Contract for 2025 Global Carbon Dioxide Emissions reaching 40,5000.
Dim contract As Contract = New Contract
contract.Symbol = "GCE"
contract.SecType = "OPT"
contract.Currency = "USD"
contract.Exchange = "FORECASTX"
contract.LastTradeDateOrContractMonth = "20251231"
contract.Right = "C"
contract.Strike = 40500
```

## CME Contract Example

#### Python

```python
# Event Contract for Ether close above 2,670 on September 24, 2026
contract = Contract()
contract.symbol = "CCE16"
contract.secType = "OPT"
contract.currency = "USD"
contract.exchange = "CME"
contract.lastTradeDateOrContractMonth = "20260924"
contract.right = "C"
contract.strike = 2670
```

#### Java

```java
// Event Contract for Ether close above 2,670 on September 24, 2026
Contract contract = new Contract();
contract.symbol("CCE16");
contract.secType("OPT");
contract.currency("USD");
contract.exchange("CME");
contract.lastTradeDateOrContractMonth("20260924");
contract.right("C");
contract.strike(2670);
```

#### C++

```cpp
// Event Contract for Ether close above 2,670 on September 24, 2026
Contract contract;
contract.symbol = "CCE16";
contract.secType = "OPT";
contract.currency = "USD";
contract.exchange = "CME";
contract.lastTradeDateOrContractMonth = "20260924";
contract.right = "C";
contract.strike = 2670;
```

#### C\#

```csharp
// Event Contract for Ether close above 2,670 on September 24, 2026
Contract contract = new Contract();
contract.Symbol = "CCE16";
contract.SecType = "OPT";
contract.Currency = "USD";
contract.Exchange = "CME";
contract.LastTradeDateOrContractMonth = "20260924";
contract.Right = "C";
contract.Strike = 2670;
```

#### VB.NET

```vbnet
' Event Contract for Ether close above 2,670 on September 24, 2026
Dim contract As Contract = New Contract
contract.Symbol = "CCE16"
contract.SecType = "OPT"
contract.Currency = "USD"
contract.Exchange = "CME"
contract.LastTradeDateOrContractMonth = "20260924"
contract.Right = "C"
contract.Strike = 2670
```

## Kalshi Contract Example

#### Python

```python
# Event Contract for the September 24th, 2026 LA Temperature staying below 78 degrees.
contract = Contract()
contract.symbol = "KXHIGHLAX"
contract.secType = "OPT"
contract.currency = "USD"
contract.exchange = "KALSHI"
contract.lastTradeDateOrContractMonth = "20260925"
contract.right = "P"
contract.strike = 78
```

#### Java

```java
// Event Contract for the September 24th, 2026 LA Temperature staying below 78 degrees.
Contract contract = new Contract();
contract.symbol("KXHIGHLAX");
contract.secType("OPT");
contract.currency("USD");
contract.exchange("KALSHI");
contract.lastTradeDateOrContractMonth("20260925");
contract.right("P");
contract.strike(78);
```

#### C++

```cpp
// Event Contract for the September 24th, 2026 LA Temperature staying below 78 degrees.
Contract contract;
contract.symbol = "KXHIGHLAX";
contract.secType = "OPT";
contract.currency = "USD";
contract.exchange = "KALSHI";
contract.lastTradeDateOrContractMonth = "20260925";
contract.right = "P";
contract.strike = 78;
```

#### C\#

```csharp
// Event Contract for the September 24th, 2026 LA Temperature staying below 78 degrees.
Contract contract = new Contract();
contract.Symbol = "KXHIGHLAX";
contract.SecType = "OPT";
contract.Currency = "USD";
contract.Exchange = "KALSHI";
contract.LastTradeDateOrContractMonth = "20260925";
contract.Right = "P";
contract.Strike = 78;
```

#### VB.NET

```vbnet
' Event Contract for the September 24th, 2026 LA Temperature staying below 78 degrees.
Dim contract As Contract = New Contract
contract.Symbol = "KXHIGHLAX"
contract.SecType = "OPT"
contract.Currency = "USD"
contract.Exchange = "KALSHI"
contract.LastTradeDateOrContractMonth = "20260925"
contract.Right = "P"
contract.Strike = 78
```