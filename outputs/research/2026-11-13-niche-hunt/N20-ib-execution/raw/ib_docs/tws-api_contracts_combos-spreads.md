> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Combos & Spreads

> **Info**
>
> From a programmatic perspective, terms like "BAG", "Combo", and "Spread" are synonymous and may be used interchangeably.

## Combos and Spreads

As with standard contracts, you will continue to define the standard values such as symbol, secType, exchange, and currency. However, with combo orders, the "ComboLegs" field must be added and the ComboLeg objects should be attached. The example provided will showcase more detail of behavior; however, these require a conid, exchange, ratio, and an action for every ComboLeg on the order.

Spread contracts combine two or more instruments. To define a combination contract it is required to know the conId of the contract in question.

The conId of an instrument can easily be obtained via the [EClientSocket.reqContractDetails](/docs/tws-api/doc/contracts/details) request or the [/iserver/secdef/search endpoint](/docs/web-api/v1/endpoints/contract/search-contract-by-symbol).

> **Note**
>
> Even though a contract can be created with any pair of instruments,  not all instruments are as actively traded as others. If you are unsure why data may not be retrieved, or why an order may not be executed, it is considered best practice to confirm data against the Trader Workstation or Client Portal market data.

###### ComboLeg()

**ConId:** integer. The conId, or contract Identifier, should be used to specify the exact contract. Symbols or local symbols can not be used for ComboLegs.

**Ratio:** integer. Specify the ratio for the specific leg. The ratio will be multiplied by the totalQuantity field for of the order object.

**Action:** String. Specify what to do with the order. Users may choose Buy or Sell for these orders.

**Exchange:** String. Specify the routing exchange for the contract. SMART may be used.

#### Python

```python
contract = Contract()
contract.symbol = "IBKR,MCD"
contract.secType = "BAG"
contract.currency = "USD"
contract.exchange = "SMART"

leg1 = ComboLeg()
leg1.conId = 43645865#IBKR STK
leg1.ratio = 1
leg1.action = "BUY"
leg1.exchange = "SMART"

leg2 = ComboLeg()
leg2.conId = 9408#MCD STK
leg2.ratio = 1
leg2.action = "SELL"
leg2.exchange = "SMART"

contract.comboLegs = []
contract.comboLegs.append(leg1)
contract.comboLegs.append(leg2)
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("IBKR,MCD");
contract.secType("BAG");
contract.currency("USD");
contract.exchange("SMART");

ComboLeg leg1 = new ComboLeg();
ComboLeg leg2 = new ComboLeg();
List addAllLegs = new ArrayList();

leg1.conid(43645865);//IBKR STK
leg1.ratio(1);
leg1.action("BUY");
leg1.exchange("SMART");

leg2.conid(9408);//MCD STK
leg2.ratio(1);
leg2.action("SELL");
leg2.exchange("SMART");
addAllLegs.add(leg1);
addAllLegs.add(leg2);

contract.comboLegs(addAllLegs);
```

#### C++

```cpp
Contract contract;
contract.symbol = "IBKR,MCD";
contract.secType = "BAG";
contract.currency = "USD";
contract.exchange = "SMART";

ComboLegSPtr leg1(new ComboLeg);
leg1->conId = 43645865;
leg1->action = "BUY";
leg1->ratio = 1;
leg1->exchange = "SMART";

ComboLegSPtr leg2(new ComboLeg);
leg2->conId = 9408;
leg2->action = "SELL";
leg2->ratio = 1;
leg2->exchange = "SMART";

contract.comboLegs.reset(new Contract::ComboLegList());
contract.comboLegs->push_back(leg1);
contract.comboLegs->push_back(leg2);
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "IBKR,MCD";
contract.SecType = "BAG";
contract.Currency = "USD";
contract.Exchange = "SMART";

ComboLeg leg1 = new ComboLeg();
leg1.ConId = 43645865;//IBKR STK
leg1.Ratio = 1;
leg1.Action = "BUY";
leg1.Exchange = "SMART";

ComboLeg leg2 = new ComboLeg();
leg2.ConId = 9408;//MCD STK
leg2.Ratio = 1;
leg2.Action = "SELL";
leg2.Exchange = "SMART";

contract.ComboLegs = new List();
contract.ComboLegs.Add(leg1);
contract.ComboLegs.Add(leg2);
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "MCD"
contract.SecType = "BAG"
contract.Currency = "USD"
contract.Exchange = "SMART"

Dim leg1 As ComboLeg = New ComboLeg
leg1.ConId = 43645865
leg1.Ratio = 1
leg1.Action = "BUY"
leg1.Exchange = "SMART"

Dim leg2 As ComboLeg = New ComboLeg
leg2.ConId = 9408
leg2.Ratio = 1
leg2.Action = "SELL"
leg2.Exchange = "SMART"

contract.ComboLegs = New List(Of ComboLeg)
contract.ComboLegs.Add(leg1)
contract.ComboLegs.Add(leg2)
```

## Smart-Routed Futures Spreads

Futures spreads can also be defined as Smart-routed (non-guaranteed) combos. When placing an order for a non-guaranteed combo from the API, the non-guaranteed flag must be set to 1. Historical data for smart-routed futures spreads is generally available from the API with the requisite market data subscriptions.

#### Python

```python
contract = Contract()
contract.symbol = "WTI" # WTI,COIL spread. Symbol can be defined as first leg symbol ("WTI") or currency ("USD")
contract.secType = "BAG"
contract.currency = "USD"
contract.exchange = "SMART"

leg1 = ComboLeg()
leg1.conId = 55928698 # WTI future June 2017
leg1.ratio = 1
leg1.action = "BUY"
leg1.exchange = "IPE"

leg2 = ComboLeg()
leg2.conId = 55850663 # COIL future June 2017
leg2.ratio = 1
leg2.action = "SELL"
leg2.exchange = "IPE"

contract.comboLegs = []
contract.comboLegs.append(leg1)
contract.comboLegs.append(leg2)
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("WTI");  // WTI,COIL spread. Symbol can be defined as first leg symbol ("WTI") or currency ("USD").
contract.secType("BAG");
contract.currency("USD");
contract.exchange("SMART"); // smart-routed rather than direct routed

ComboLeg leg1 = new ComboLeg();
ComboLeg leg2 = new ComboLeg();
List addAllLegs = new ArrayList();

leg1.conid(55928698);// WTI future June 2017
leg1.ratio(1);
leg1.action("BUY");
leg1.exchange("IPE");

leg2.conid(55850663);// COIL future June 2017
leg2.ratio(1);
leg2.action("SELL");
leg2.exchange("IPE");

addAllLegs.add(leg1);
addAllLegs.add(leg2);
contract.comboLegs(addAllLegs);
```

#### C++

```cpp
Contract contract;
contract.symbol = "WTI"; // WTI,COIL spread. Symbol can be defined as first leg symbol ("WTI") or currency ("USD").
contract.secType = "BAG";
contract.currency = "USD";
contract.exchange = "SMART";

ComboLegSPtr leg1(new ComboLeg);
leg1->conId = 55928698; // WTI future June 2017
leg1->action = "BUY";
leg1->ratio = 1;
leg1->exchange = "IPE";

ComboLegSPtr leg2(new ComboLeg);
leg2->conId = 55850663; // COIL future June 2017
leg2->action = "SELL";
leg2->ratio = 1;
leg2->exchange = "IPE";

contract.comboLegs.reset(new Contract::ComboLegList());
contract.comboLegs->push_back(leg1);
contract.comboLegs->push_back(leg2);
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "WTI"; // WTI,COIL spread. Symbol can be defined as first leg symbol ("WTI") or currency ("USD").
contract.SecType = "BAG";
contract.Currency = "USD";
contract.Exchange = "SMART";

ComboLeg leg1 = new ComboLeg();
leg1.ConId = 55928698;//WTI future June 2017
leg1.Ratio = 1;
leg1.Action = "BUY";
leg1.Exchange = "IPE";

ComboLeg leg2 = new ComboLeg();
leg2.ConId = 55850663;//COIL future June 2017
leg2.Ratio = 1;
leg2.Action = "SELL";
leg2.Exchange = "IPE";

contract.ComboLegs = new List();
contract.ComboLegs.Add(leg1);
contract.ComboLegs.Add(leg2);
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "WTI" ' WTI,COIL spread. Symbol can be defined as first leg symbol ("WTI") or currency ("USD")
contract.SecType = "BAG"
contract.Currency = "USD"
contract.Exchange = "SMART"

Dim leg1 As ComboLeg = New ComboLeg
leg1.ConId = 55928698 ' WTI future June 2017
leg1.Ratio = 1
leg1.Action = "BUY"
leg1.Exchange = "IPE"

Dim leg2 As ComboLeg = New ComboLeg
leg2.ConId = 55850663 ' COIL future June 2017
leg2.Ratio = 1
leg2.Action = "SELL"
leg2.Exchange = "IPE"

contract.ComboLegs = New List(Of ComboLeg)
contract.ComboLegs.Add(leg1)
contract.ComboLegs.Add(leg2)
```

## Inter-commoddity Futures Spread

For Inter-Commodity futures, the 'Local Symbol' field in TWS is used for the 'Symbol' field in the API contract definition, e.g. "CL.BZ". They are always guaranteed combos, which is the default in the API.

In some instances, a generic symbol must be provided instead. For example, a inter-commodity future containing ZF and ZN will require that the symbol be set to "FYT".

Please be mindful that inter-commodity spreads are offered by the exchange directly, and so they are direct-routed though the legs have different underlyings. Only real time, and not historical, data is offered for inter-commodity spread contracts through the API.

It is also possible in many cases to create a spread of the same future contracts in a inter-commodity spread which is smart-routed and non-guaranteed. Historical data for this spread would generally be available from the API. Also, historical data for expired spread contracts is not available in TWS or the API.

#### Python

```python
contract = Contract()
contract.symbol = "COL.WTI" #symbol is 'local symbol' of intercommodity spread. 
contract.secType = "BAG"
contract.currency = "USD"
contract.exchange = "IPE"

leg1 = ComboLeg()
leg1.conId = 183405603 #WTI�Dec'23�@IPE
leg1.ratio = 1
leg1.action = "BUY"
leg1.exchange = "IPE"

leg2 = ComboLeg()
leg2.conId = 254011009 #COIL�Dec'23�@IPE
leg2.ratio = 1
leg2.action = "SELL"
leg2.exchange = "IPE"

contract.comboLegs = []
contract.comboLegs.append(leg1)
contract.comboLegs.append(leg2)
```

#### Java

```java
Contract contract = new Contract();
contract.symbol("COIL.WTI");
contract.secType("BAG");
contract.currency("USD");
contract.exchange("IPE");

ComboLeg leg1 = new ComboLeg();
ComboLeg leg2 = new ComboLeg();
List addAllLegs = new ArrayList();

leg1.conid(183405603); //WTI�Dec'23�@IPE
leg1.ratio(1);
leg1.action("BUY");
leg1.exchange("IPE");

leg2.conid(254011009); //COIL�Dec'23�@IPE
leg2.ratio(1);
leg2.action("SELL");
leg2.exchange("IPE");
addAllLegs.add(leg1);
addAllLegs.add(leg2);

contract.comboLegs(addAllLegs);
```

#### C++

```cpp
Contract contract;
contract.symbol = "COIL.WTI";
contract.secType = "BAG";
contract.currency = "USD";
contract.exchange = "IPE";

ComboLegSPtr leg1(new ComboLeg);
leg1->conId = 183405603; //WTI Dec'23 @IPE
leg1->action = "BUY";
leg1->ratio = 1;
leg1->exchange = "IPE";

ComboLegSPtr leg2(new ComboLeg);
leg2->conId = 254011009; //COIL Dec'23 @IPE
leg2->action = "SELL";
leg2->ratio = 1;
leg2->exchange = "IPE";

contract.comboLegs.reset(new Contract::ComboLegList());
contract.comboLegs->push_back(leg1);
contract.comboLegs->push_back(leg2);
```

#### C\#

```csharp
Contract contract = new Contract();
contract.Symbol = "COIL.WTI";
contract.SecType = "BAG";
contract.Currency = "USD";
contract.Exchange = "IPE";

ComboLeg leg1 = new ComboLeg();
leg1.ConId = 183405603; //WTI Dec'23 @IPE
leg1.Ratio = 1;
leg1.Action = "BUY";
leg1.Exchange = "IPE";

ComboLeg leg2 = new ComboLeg();
leg2.ConId = 254011009; //COIL Dec'23 @IPE
leg2.Ratio = 1;
leg2.Action = "SELL";
leg2.Exchange = "IPE";

contract.ComboLegs = new List();
contract.ComboLegs.Add(leg1);
contract.ComboLegs.Add(leg2);
```

#### VB.NET

```vbnet
Dim contract As Contract = New Contract
contract.Symbol = "COIL.WTI"
contract.SecType = "BAG"
contract.Currency = "USD"
contract.Exchange = "IPE"

Dim leg1 As ComboLeg = New ComboLeg
leg1.ConId = 183405603 ' WTI Dec'23 @IPE
leg1.Ratio = 1
leg1.Action = "BUY"
leg1.Exchange = "IPE"

Dim leg2 As ComboLeg = New ComboLeg
leg2.ConId = 254011009 ' COIL Dec'23 @IPE
leg2.Ratio = 1
leg2.Action = "SELL"
leg2.Exchange = "IPE"

contract.ComboLegs = New List(Of ComboLeg)
contract.ComboLegs.Add(leg1)
contract.ComboLegs.Add(leg2)
```