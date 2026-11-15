> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# Exercise Options

Options are exercised or lapsed from the API with the function EClient.exerciseOptions.

* Option exercise will appear with order status side = "BUY" and limit price of 0, but only at the time the request is made
* Option exercise can be distinguished by price = 0

#### EClient.exerciseOptions (

**tickerId:** integer. Exercise request's identifier

**contract:** Contract. the option Contract to be exercised.

**exerciseAction:** integer. Set to 1 to exercise the option, set to 2 to let the option lapse.

**exerciseQuantity:** integer. Number of contracts to be exercised

**account:** String. Destination account

**ovrd:** integer. Specifies whether your setting will override the system's natural action.\
Set to 1 to override, set to 0 not to.

For example, if your action is "exercise" and the option is not in-the-money, by natural action the option would not exercise. If you have override set to "yes" the natural action would be overridden and the out-of-the money option would be exercised.

**manualOrderTime:** String. Specify the time at which the options should be exercised. An empty string will assume the current time.
)

Exercises an options contract.

**Note:** this function is affected by a TWS setting which specifies if an exercise request must be finalized.

#### Python

```python
self.exerciseOptions(5003, contract, 1, 1, self.account, 1, "")
```

#### Java

```java
client.exerciseOptions(5003, contract, 1, 1, "", 1, "");
```

#### C++

```cpp
m_pClient->exerciseOptions(5003, contract, 1, 1, "", 1, "");
```

#### C\#

```csharp
client.exerciseOptions(5003, contract, 1, 1, null, 1, null);
```

#### VB.NET

```vbnet
client.exerciseOptions(5003, contract, 1, 1, Nothing, 1, Nothing)
```