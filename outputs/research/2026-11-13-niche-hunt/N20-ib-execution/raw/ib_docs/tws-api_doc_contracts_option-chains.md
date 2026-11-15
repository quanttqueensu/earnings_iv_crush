> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Option Chain

## Introduction

The option chain for a given security can be returned using the function `EClient.reqContractDetails`. If an option contract is incompletely defined (for instance with the strike undefined) and used as an argument to `EClient.reqContractDetails`, a list of all matching option contracts will be returned.

One limitation of this technique is that the return of option chains will be throttled and take a longer time the more ambiguous the contract definition. The function `EClient.reqSecDefOptParams` was introduced that does not have the throttling limitation.

* It is not recommended to use `EClient.reqContractDetails` to receive complete option chains on an underlying, e.g. all combinations of strikes/rights/expiries.
* For very large option chains returned from `EClient.reqContractDetails`, unchecking the setting in TWS Global Configuration at API -> Settings -> "Expose entire trading schedule to the API" will decrease the amount of data returned per option and help to return the contract list more quickly.

`EClient.reqSecDefOptParams` returns a list of expiries and a list of strike prices. In some cases, it is possible there are combinations of strike and expiry that would not give a valid option contract.

---

## Request Option Chains

`EClient.reqSecDefOptParams(reqId, underlyingSymbol, futFopExchange, underlyingSecType, underlyingConId)`

Requests security definition option parameters for viewing a contract's option chain.

**`reqId`** `int`

The ID chosen for the request.

---

**`underlyingSymbol`** `string`

Contract symbol of the underlying.

---

**`futFopExchange`** `string`

The exchange on which the returned options are trading. Can be set to the empty string "" for all exchanges.

---

**`underlyingSecType`** `string`

The type of the underlying security, i.e. STK.

---

**`underlyingConId`** `int`

The contract ID of the underlying security.

---

\


#### Python

```python
self.reqSecDefOptParams(0, "IBM", "", "STK", 8314)
```

#### Java

```java
client.reqSecDefOptParams(0, "IBM", "", "STK", 8314);
```

#### C++

```cpp
m_pClient->reqSecDefOptParams(0, "IBM", "", "STK", 8314);
```

#### C\#

```csharp
client.reqSecDefOptParams(0, "IBM", "", "STK", 8314);
```

#### VB.NET

```vbnet
client.reqSecDefOptParams(0, "IBM", "", "STK", 8314)
```

---

## Receive Option Chains

`EWrapper.securityDefinitionOptionParameter(reqId, underlyingConId, tradingClass, multiplier, exchange, expirations, strikes)`

Returns the option chain for an underlying on an exchange specified in `reqSecDefOptParams`. There will be multiple callbacks to `securityDefinitionOptionParameter` if multiple exchanges are specified in `reqSecDefOptParams`.

**`reqId`** `int`

ID of the request initiating the callback.

---

**`underlyingConId`** `int`

The conID of the underlying security.

---

**`tradingClass`** `string`

The option trading class.

---

**`multiplier`** `string`

The option multiplier.

---

**`exchange`** `string`

Exchange for which the derivative is hosted.

---

**`expirations`** `HashSet`

A list of the expiries for the options of this underlying on this exchange.

---

**`strikes`** `HashSet`

A list of the possible strikes for options of this underlying on this exchange.

---

\


#### Python

```python
def securityDefinitionOptionParameter(self, reqId: int, exchange: str, underlyingConId: int, tradingClass: str, multiplier: str, expirations: SetOfString, strikes: SetOfFloat):
  print("SecurityDefinitionOptionParameter.", "ReqId:", reqId, "Exchange:", exchange, "Underlying conId:", underlyingConId, "TradingClass:", tradingClass, "Multiplier:", multiplier, "Expirations:", expirations, "Strikes:", strikes)
```

#### Java

```java
@Override
public void securityDefinitionOptionalParameter(int reqId, String exchange, int underlyingConId, String tradingClass, String multiplier, Set expirations, Set strikes) {
	System.out.println("Security Definition Optional Parameter: " + EWrapperMsgGenerator.securityDefinitionOptionalParameter(reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes));
}
```

#### C++

```cpp
void TestCppClient::securityDefinitionOptionalParameter(int reqId, const std::string& exchange, int underlyingConId, const std::string& tradingClass,
                                                        const std::string& multiplier, const std::set& expirations, const std::set& strikes) {
    printf("Security Definition Optional Parameter. Request: %d, Trading Class: %s, Multiplier: %s\n", reqId, tradingClass.c_str(), multiplier.c_str());
}
```

#### C\#

```csharp
public void securityDefinitionOptionParameter(int reqId, string exchange, int underlyingConId, string tradingClass, string multiplier, HashSet expirations, HashSet strikes)
{
	Console.WriteLine("Security Definition Option Parameter. Reqest: {0}, Exchange: {1}, Undrelying contract id: {2}, Trading class: {3}, Multiplier: {4}, Expirations: {5}, Strikes: {6}", reqId, exchange, Util.IntMaxString(underlyingConId), tradingClass, multiplier, string.Join(", ", expirations), string.Join(", ", strikes));
}
```

#### VB.NET

```vbnet
Public Sub securityDefinitionOptionParameter(reqId As Integer, exchange As String, underlyingConId As Integer, tradingClass As String, multiplier As String, expirations As HashSet(Of String), strikes As HashSet(Of Double)) Implements EWrapper.securityDefinitionOptionParameter
            Console.WriteLine("securityDefinitionOptionParameter: " & reqId & " tradingClass: " & tradingClass & " multiplier: ")
End Sub
```