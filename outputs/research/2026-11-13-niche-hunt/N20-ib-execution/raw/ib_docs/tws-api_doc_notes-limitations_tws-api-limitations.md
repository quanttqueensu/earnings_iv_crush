> This page is for TWS API.

> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://ibkrcampus.com/docs/llms.txt.

# TWS API Limitations

## Limitations of the API

Our programming interface is designed to automate manual operations within the Trader Workstation (TWS) software such as: placing orders, monitoring your account balance and positions, viewing an instrument's live data… etc.

There is no logic within the API other than to ensure the integrity of the exchanged messages. Validation and checks for requests occur within TWS and our servers.

Because of this, developers should familiarize themselves with the TWS in order to gain a better understanding what information is expected for requests. Before beginning development work, it is expected to first experiment with the TWS directly.

**Remember:** If a certain feature or operation is not available in the TWS, it will not be available on the API side either!

## C++ DLLs and Static Linking

Following the TWS API's recent migration to Protobuf, clients developing in C++ should prioritize static linking over the use of DLLs.

This recommendation is based on the Google Protobuf documentation. For more information on the reasoning behind it, or questions on enabling DLLs for use with Protobuf, please see [DLLs vs static linking](https://chromium.googlesource.com/external/github.com/google/protobuf/+/HEAD/cmake/README.md#dlls-vs_static-linking).

## Paper Trading

If your regular trading account has been approved and funded, you can use your Account Management page to open a [Paper Trading Account](https://www.ibkrguides.com/clientportal/papertradingaccount.htm) which lets you use the full range of trading facilities in a simulated environment using real market conditions. Using a Paper Trading Account will allow you not only to get familiar with the TWS API but also to test your trading strategies without risking your capital.

Please be aware that the Paper Trading Environment relies on more simulated technologies than the Live trading environment. As a result, certain behavior such as order execution may vary

Note the paper trading environment has inherent [limitations](https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm).

## C# for MacOS

The TWS API C# source files are not available through the Mac and Unix distribution download as the language is built around Dynamic Link Library (DLL) files for execution. This is because DLL files are exclusively supported through Windows platforms.

## Canadian Residents Restricted From Programmatically Trading Canadian Products

Interactive Brokers Canada Inc. (IBC) does not allow users to use your own trading application to electronically submit order for products traded on a Canadian exchange or other marketplace through API, which would include Third Party Integrations. This decision was made through multiple and extensive communications between IBC compliance and personnel and senior management of the Canadian Investment Regulatory Organization (CIRO), formerly the Investment Industry Regulatory Organization of Canada (IIROC), our self-regulatory organization.

CIRO has implemented [IIROC Dealer Member Rule (DMR) 3200](https://www.ciro.ca/sites/default/files/legacy/2021-09/RulesCollated_090121_en.pdf) A. 1. (b) (i) which prohibits CIRO registrants, including IBC, from allowing its clients to use their own automated order systems to generated orders.

Unfortunately, these restrictions would be also applicable with third-party applications like TradingView, NinjaTrader, or other such groups as they use an API connection.