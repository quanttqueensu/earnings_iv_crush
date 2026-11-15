> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Delayed Market Data

## Introduction

Interactive Brokers provides 15-minute delayed market data for US Network exchanges, which includes NYSE and NASDAQ listed stocks. By default, requests for [Streaming Data](/docs/tws-api/doc/md/streaming-data) will attempt to return Live data. In the event a [valid market data subscription](/docs/general/market-data-subscriptions/popular-market-data-subscriptions/introduction) is not active for the user, delayed market data may be requested. Alternatively Trader Workstation setting may be modified to retrieve delayed data by default.

> **Error**
>
> Live market data in Trader Workstation is not always available through the API. See our [Market Data page](/docs/general/market-data-subscriptions/tws-data-vs-api-data) for more details.

## Market Data Types

The API can request Live, Frozen, Delayed and Delayed Frozen market data from Trader Workstation by switching market data type via the [EClient.reqMarketDataType](#request-md-type) before making a market data request. A successful switch to a different (non-live) market data type for a particular market data request will be indicated by a callback to [EWrapper.marketDataType](#receive-market-data-type) with the ticker ID of the market data request which is returning a different type of data.

| Market Data Type | ID | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------- | -- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Live             | 1  | Live market data is streaming data relayed back in real time. Market data subscriptions are required to receive live market data.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Frozen           | 2  | Frozen market data is the last data recorded at market close. When you set the market data type to Frozen, you are asking TWS to send the last available quote when there is not one currently available.If a market is closed and real time data is requested, -1 values will commonly be returned for the bid and ask prices to indicate there is no current bid/ask data available. To receive the last know bid/ask price before the market close, switch to market data type 2 before requesting market data. API frozen data requires the same market data subscriptions necessary for real time streaming data. |
| Delayed          | 3  | Free, delayed data is 15 – 20 minutes delayed. Delayed market data is returned with delayed [Tick Types](/docs/tws-api/doc/md/streaming-data#available-tick-types) (Tick ID 66\~76).                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Delayed Frozen   | 4  | Requests delayed "frozen" data for a user without market data subscriptions. If requested during the trading session, the previous days data will be returned. Data for the current day's trading session is not avialable until 15 minutes after market close.                                                                                                                                                                                                                                                                                                                                                        |

> **Info**
>
> The most recent data available with the user's subscriptions will be returned regardless of the requested market data type.

---

## Request Market Data Type

`EClient.reqMarketDataType(marketDataType)`

Switches data type returned from reqMktData request to Live (1), Frozen (2), Delayed (3), or Frozen-Delayed (4).

**`marketDataType`** `int`

Type of market data to retrieve. See [Market Data Types](#market-data-types) for details.

---

\


#### Python

```python
self.reqMarketDataType(3)
```

#### Java

```java
client.reqMarketDataType(2);
```

#### C++

```cpp
m_pClient->reqMarketDataType(3);
```

#### C\#

```csharp
client.reqMarketDataType(3);
```

#### VB.NET

```vbnet
client.reqMarketDataType(4)
```

---

## Receive Market Data Type

`EWrapper.marketDataType(reqId, marketDataType)`

Indicates the type of market data being returned. Even if [EClient.reqMarketDataType()](#request-market-data-type) is not called, `EWrapper.marketDataType()` will be returned, indicating the type of market data being received.

**`reqId`** `int`

Request identifier used to track data.

---

**`marketDataType`** `int`

Type of market data to retrieve.

---

\


#### Python

```python
def marketDataType(self, reqId: TickerId, marketDataType: int):
	print("MarketDataType. ReqId:", reqId, "Type:", marketDataType)
```

#### Java

```java
@Override
public void marketDataType(int reqId, int marketDataType) {
	System.out.println("MarketDataType: " + EWrapperMsgGenerator.marketDataType(reqId, marketDataType));
}
```

#### C++

```cpp
void TestCppClient::marketDataType(TickerId reqId, int marketDataType) {
    printf( "MarketDataType. ReqId: %ld, Type: %d\n", reqId, marketDataType);
}
```

#### C\#

```csharp
public virtual void marketDataType(int reqId, int marketDataType)
{
	Console.WriteLine("MarketDataType. "+reqId+", Type: "+marketDataType+"\n");
}
```

#### VB.NET

```vbnet
Public Sub marketDataType(reqId As Integer, marketDataType As Integer) Implements IBApi.EWrapper.marketDataType
	Console.WriteLine("MarketDataType - ReqId [" & reqId & "] MarketDataType [" & marketDataType & "]")
End Sub
```