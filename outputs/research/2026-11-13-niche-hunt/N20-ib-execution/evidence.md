# N20 ib-execution: what it takes to paper trade each candidate at IB

Lane dossier. Pages were read on 2026-11-13. Every claim carries one of three labels: **[V]**
means read at the source (the URL is in `sources.csv`, and a text extract of the page is under
`raw/`). **[R]** means recalled and not read at the source in this session. **[C]** means
conjecture or an illustrative input. All money figures are USD. Commission and fee figures are
**per contract, per side** (one fill). A short straddle round trip is four fills.

## 1. Scope, question and success criterion

**Question.** For every market in `LANES.md`, what does it take to paper trade a one-lot short
straddle (or the nearest equivalent) around the scheduled event at Interactive Brokers? That
covers the product, paper availability, the market-data subscription and its cost, commissions,
margin, trading hours against the event time, combo support and exercise rules. Then: what must
change in `earnings_iv_crush/live/` to trade a futures option (FOP) and a ForecastEx contract?

**Success criterion.** Every cell of the final table is sourced, or it is labelled and its
verification route is named. No pilot was run, so no trial IDs from block 2,652 to 2,681 were
consumed.

**Access limits met during the work.** IB's pages refuse the WebFetch tool (HTTP 403) but serve
plain `curl` with a generic User-Agent, so they were read that way at one request every 1.5 s.
cmegroup.com refused both routes (HTTP 403 or a timeout). I did not try to get round that, so
CME contract specifications, trading hours and SPAN 2 scope are **[R]** below. The session's
web-search budget ran out part way through. After that, only known primary URLs were fetched.

## 2. Account-level facts that apply to every market

1. **The paper account inherits the live account's permissions and data [V].** "Trading
   permissions, market data subscriptions, base currency, and other account configurations are
   the same as specified for your regular account." So a futures option can be paper traded only
   if the live account holds US futures permissions. A paper account starts with USD 1,000,000
   of equity. (Source: ibkrguides `aboutpapertradingaccounts.htm`.)
2. **Paper limitations IB publishes [V].** The list reads: "Fills are simulated from the top of
   the book; no deep book access"; "Limited combo trading"; "Stops and other complex order types
   are always simulated"; "**Penny trading for US Options is not supported. Orders can be
   submitted but will not receive a penny fill.**" It does not exclude futures options or event
   contracts, and it does not confirm them either.
3. **A finding for the existing equity book (outside this lane, flagged for the lead).** The
   ladder rounds sub-3.00 limits to 0.01 (`ib_orders.round_to_tick`, `ladder.LegQuote.limit`).
   On the paper account those penny prices cannot receive a penny fill [V, IB text]. Mid and
   partial rungs on penny-class legs therefore measure the simulator, not the market. The
   paired-improvement evidence in `FORWARD_TEST_SPEC.md` section 10 is exposed to this, in
   addition to the delayed-data problem in section 11. Neither the repository nor the specification
   mentions it: a grep for "penny fill" and "penny trading" finds nothing.
4. **Delayed data on futures is 10 minutes, on OPRA 15 minutes [V].** IB's delayed-data table
   lists CBOT, CME, COMEX, NYMEX, ICE US (NYBOT) and CFE at 10 minutes and OPRA at 15. The
   `CLAUDE.md` landmine (fills on delayed quotes are not evidence) applies to every market here.
5. **Subscriptions are not pro-rated [V]**: "charged at the full month rate". A real-time
   forward test of N markets costs the sum of the listed fees from the first month.
6. **Waivers do not help a paper book [V, with the project's own reading].** The fee for each
   futures L1 feed is "waived if commissions generated are greater than USD 20.00". The US
   Securities Snapshot and Futures Value Bundle (USD 10) is waived at USD 30. Paper trading
   generates no billable commissions, so the live account must generate them or the fee is paid
   (`FORWARD_TEST_SPEC.md` section 11 reads the OPRA waiver the same way).
7. **Combos in the API [V].** A BAG contract carries `ComboLeg`s by conId. A combo routed
   directly to an exchange "is executed as a single transaction". A smart-routed combo "each leg
   may be executed separately". Futures spreads can be smart-routed non-guaranteed. The
   `combos-spreads` page has no futures-option example, so a CME user-defined straddle through
   the API is **[R]**: supported in TWS, and the API exposes whatever TWS exposes. Paper "limited
   combo trading" [V] means combo fills on paper are weak evidence.
8. **Exercise through the API [V].** `EClient.exerciseOptions(... exerciseAction 1 exercise or 2
   lapse, ovrd ...)` exists. A short-straddle harness never needs it, but it must handle being
   assigned (section 6).

## 3. Market by market

**Commission build-up, IBKR Pro, at or below 1,000 contracts a month [V].** The fixed and tiered
rates are both USD 0.85 per contract on US futures and futures options. To that IB adds the
exchange fee (the non-member Tier I column on IB's fee pages) and a regulatory fee of 0.01 (NFA).
The give-up surcharge is waived when IB both executes and carries. Micro futures and FOPs (MCL,
MHNG, MGC and others) carry a 0.25 IB commission. Crypto has its own rates: BRR 5.00, MBT 0.85,
BFF 0.25, ETH 3.00, MET 0.20. US equity and ETF options cost 0.65 at or below 10,000 contracts a
month, plus exchange, ORF and clearing fees that this dossier does not itemise.

**Market data, non-professional, per month [V].** CBOT Real-Time (L1), CME Real-Time (L1), NYMEX
Real-Time (L1) and COMEX Real-Time (L1) each cost 1.55, waived above 20 of commissions. The
alternative is the US Securities Snapshot and Futures Value Bundle at 10.00, which "includes top
of book quotes for CBOT, CME, COMEX, and NYMEX". The other feeds are: ICE Futures U.S. (NYBOT)
(L1, L2) at **142.00** (non-pro and pro alike, and it "includes options"); CFE Enhanced (L1) at
4.50; OPRA (L1) at 1.50, waived above 20. A professional subscriber pays far more, for example
145.00 for CME L1 and L2, because the non-pro L1 product is marked N/A for professionals.

**Margin anchors [V].** These are IB's published overnight maintenance margins for one outright
future (US resident view, read 2026-11-13): ZC 1,557.28; ZS 3,940.74; ZW 2,405.77; ZN 1,988.47;
ZT 1,200.07; ZF 1,250.03; ZB 3,829.22; SR3 725.00; ZQ 907.96; HE 1,835.42; LE 5,141.02;
GF 11,807.16; NG 7,315.86; CL 15,000; HO 29,182.42; MCL 1,500; GC 36,407.82; SI 45,562.59;
HG 16,684.74; KC 17,021.98; CC 11,159.48; SB 2,136.47; CT 1,975.35; 6E 3,526.35; 6J 2,800.22;
6B 2,133.94; 6A 2,238.82; 6C 1,301.44; VIX future (VX) 4,910; MBT 2,151.80; BRR 107,589.86;
ETH 40,598.79; MES 2,663.40. IB's overnight initial margin is 1.15 times maintenance on these
rows. Section 4 turns these into straddle figures.

| Lane | IB product (exchange, root) | Event time vs session | Data needed (non-pro/mo) | All-in fee per contract per side | Notes |
|---|---|---|---|---|---|
| N01 grains | CBOT ZC, ZS, ZW options; weeklies and short-dated new-crop [R] | USDA 12:00 ET falls inside the CBOT day session, which runs 08:30-13:20 CT [R] | CBOT L1 1.55 [V] | 0.85 + 2.16 + 0.01 = **3.02** [V] | American exercise into futures [R]; classic SPAN [R] |
| N02 livestock | CME HE, LE, GF options [R] | Hogs and Pigs and Cattle on Feed at 15:00 ET, after the 13:05 CT close [R, LANES] | CME L1 1.55 [V] | 0.85 + 2.10 + 0.01 = **2.96** [V] | The closest analogue of after-close earnings; check liquidity |
| N03 natgas | NYMEX NG options (monthly, weeklies [R]); micro MHNG options [V fee row] | EIA Thursday 10:30 ET, inside Globex 18:00-17:00 ET [R] | NYMEX L1 1.55 [V] | NG 0.85 + 1.50 + 0.01 = **2.36**; MHNG 0.25 + 0.75 + 0.01 = **1.01** [V] | Energy is on SPAN 2 [R, CME page via search summary]; use what-if |
| N04 crude | NYMEX CL options incl. "Crude Oil Fri Weekly" and "Mon and Wed Weekly" [V fee rows]; MCL options | EIA WPSR Wednesday 10:30 ET in session; API Tuesday about 16:30 ET in Globex [R] | NYMEX L1 1.55 [V] | CL **2.36**; MCL 0.25 + 0.75 + 0.01 = **1.01** [V] | NYMEX BZ options fee row reads "N/A" [V]; ICE Brent options need ICE Europe data (not priced) |
| N05 Treasuries | CBOT ZT, ZF, ZN, ZB, UB, TN options (Mon, Wed, Fri weeklies [R]) | 08:30 ET releases fall inside Globex 17:00-16:00 CT [R] | CBOT L1 1.55 [V] | 0.85 + 0.85 + 0.01 = **1.71** [V] | Cheapest FOP fee in scope |
| N06 SOFR | CME SR3 options and mid-curves [R] | FOMC 14:00 ET in session [R] | CME L1 1.55 [V] | 0.85 + 0.89 + 0.01 = **1.75** [V] | Mid-curve fee not itemised separately |
| N07 FX | CME FX futures options (EUR, JPY, GBP, AUD, CAD) [V fee row] | BoJ and RBA land overnight inside Globex [R] | CME L1 1.55 [V] | 0.85 + 1.60 + 0.01 = **2.46** [V] | IB OTC FX options to retail: not offered [R] |
| N08 index | SPY, QQQ, IWM options (OPRA) | 08:30 ET releases before the 09:30 cash open | OPRA L1 1.50 [V] | 0.65 + exchange fees [V] | **Existing harness, unchanged path** |
| N09 VIX | VIX index options (Cboe, OPRA); options on VIX futures (CFE) [V fee row] | VIX options regular hours 08:30-15:15 CT, global 19:15-08:25 CT [V, Cboe] | OPRA 1.50; CFE Enhanced 4.50 [V] | VIX options 0.65 + Cboe fee [R]; CFE FOP 0.85 + 1.47 + 0.01 = **2.33** [V] | VIX index options are European, AM-settled on the SOQ [R] |
| N10 crypto | CME BRR, MBT, BFF, ETH, MET options; IBIT options (OPRA) | Crypto events are mostly off-hours | CME L1 1.55 [V] | MBT 0.85 + 1.15 + 0.01 = **2.01**; BRR 5 + 5 + 0.01 = **10.01**; MET 0.20 + 0.10 + 0.01 = **0.31** [V] | BRR margin 107,590 per future [V] |
| N11 ForecastEx | ForecastEx contracts (secType OPT, exchange FORECASTX) [V]; also CME event contracts (FOP) and Kalshi [V] | IB states around the clock [V]; each contract stops at a stated last-trade time [V, API doc], which precedes the release [R] | No ForecastEx row on IB's price list [V absence] | ForecastEx 0.00 + **0.01** exchange fee; CME events 0.01 + 0.01; Kalshi 0.01 + 0.01 [V] | Buy-only venue, fully collateralised; section 5 |
| N12 metals | COMEX GC, SI, HG options [V fee row]; GLD and SLV options (OPRA) | 08:30 ET releases inside Globex [R] | COMEX L1 1.55 [V] | 0.85 + 1.65 + 0.01 = **2.51** [V] | Large per-contract margin (GC 36,408 per future) |
| N13 softs | ICE US KC, CC, SB, CT options [V fee row, "NYBOT"] | KC trades 04:15-13:30 NY time [V, ICE]; reports mostly in session [R] | **ICE Futures U.S. 142.00** [V] | 0.85 + 2.10 + 0.01 = **2.96** [V] | Data cost dominates; no L1-only product listed |
| N14-N17 | US single-name, ADR, country ETF and commodity ETF options (OPRA) | As per lane | OPRA L1 1.50 [V] | 0.65 + exchange fees [V] | **Existing harness path**: universe and calendar changes only |

Paper availability. The paper account mirrors live permissions [V]. IB publishes no exclusion
for futures options [V absence], so FOP paper trading is expected to work once the live account
has US futures permissions [R]. Event contracts carry their own permission: "Trading permissions
are requested separately" [R, search summary of IB pages]. Whether ForecastEx can be traded on
the **paper** account is not stated on any page I could read: **unverified**. IB lists eligible
entities as "Interactive Brokers LLC, Interactive Brokers Canada Inc., Interactive Brokers Hong
Kong Limited, Interactive Brokers Ireland Limited and Interactive Brokers Singapore Pte. Ltd.",
21 years and older [V]. Contracts on US election results are restricted to eligible US
residents [V]. IB Canada forbids its clients from submitting API orders on Canadian products
[V, TWS API limitations page]. That does not touch the US products here, but it shows that the
account's entity governs API access, and this dossier does not know which entity holds the
paper account.

## 4. Margin for a one-lot short straddle: a SPAN worked example

IB says futures and FOP margin uses "risk-based algorithms ... a standard set of market outcome
scenarios with a one-day time horizon. A price scanning range is defined for each product by the
respective clearing house" [V]. IB does not publish SPAN risk arrays, volatility scan ranges or
short-option minimums, so an exact figure needs a what-if order. The worked example below uses
the one input IB does publish. Under classic SPAN, the maintenance margin of one outright future
equals the price scan range (PSR) [R].

Method (`scripts/span_straddle_example.py`, output in `logs/span_example.log`):
- PSR = IB's overnight maintenance margin for the outright future [V].
- Black-76 straddle values over the 16 classic SPAN scenarios, one day forward: price moves of 0,
  ±1/3, ±2/3 and ±3/3 of the PSR with volatility up and down by the VSR, plus two extreme moves.
  The extreme-move convention is run both ways, three times the PSR at 33% cover and two times
  at 35%, because I could not read the CME page to settle it [R].
- Futures price, ATM volatility and VSR are illustrative inputs [C]: ZC 4.40 USD/bu, vol 24%;
  ZS 10.50, 18%; ZN 112.0, 5.0% price vol; HE 0.85 USD/lb, 25%. VSR runs over 3, 6 and 10 vol
  points.

Results, illustrative (USD per one-lot straddle, short ATM, 7 days to expiry):

| Root | Premium | Scan risk, range over VSR and extreme convention | Risk / premium | Harness Reg-T model (0.20 × notional + premium) |
|---|---|---|---|---|
| ZC | 583 | 988 to 1,348 | 1.7 to 2.3 | 4,983 |
| ZS | 1,043 | 2,898 to 3,554 | 2.8 to 3.4 | 11,543 |
| ZN | 618 | 1,410 to 1,793 | 2.3 to 2.9 | 23,018 |
| HE | 938 | 975 to 1,506 | 1.0 to 1.6 | 7,738 |

At 30 days the ZC scan risk is 696 to 1,140 against a premium of 1,204 (`logs/span_example.log`).

How to read this:
1. Under classic SPAN a 7-day short ATM straddle's scan risk is about **0.5 to 0.9 times the
   outright future's maintenance margin** across these inputs. At 30 days it rises to as much
   as 1.4 times for ZN with a 10-point VSR (`logs/span_example.log`). SPAN's net option value adds the
   premium to the requirement, but the premium is credited in cash when the straddle is sold, so
   the new cash needed is about the scan risk.
2. The harness's `engine.pnl.regt_straddle_margin` (20% of underlying notional plus premium)
   **overstates FOP margin by about 3 to 16 times** on these inputs. Return on margin would be
   understated by the same factor. It must not be reused for futures options.
3. Energy (NG, CL) and equity products are on CME's SPAN 2, a historical-VaR framework [R: CME
   page summarised by search, not read]. The scenario arithmetic above does not apply to them,
   and the anchor (NG 7,315.86, CL 15,000 per future [V]) is only an order of magnitude.
4. IB may add house margin above the exchange figure [R]. The authoritative number is IB's
   what-if margin on the actual BAG or legs, which ticket T8 in `FORWARD_TEST_SPEC.md` already
   asks for.

ForecastEx has no margin. Contracts "are non-marginable and have no loan value". Each side
posts collateral equal to its price [V, Rulebook 401(d), 401(i)].

## 5. ForecastEx: the facts that decide the trade design

- **Contract model [V, IB API doc].** secType `OPT`, exchange `FORECASTX`, currency USD, right
  `C` = Yes and `P` = No, and the strike is the threshold. The underlier is an artificial index
  "purely an artifact of the option instrument model". Contract details return
  `realExpirationDate` and a last-trade time. CME event contracts are instead secType `FOP` on
  CBOT, CME, COMEX or NYMEX with trading class `EC<root>`, and they permit both buying and
  selling.
- **Buy-only [V, IB API doc and Rulebook 401(c)].** "ForecastEx instruments do not permit Sell
  orders. Instead, ForecastEx positions are flattened or reduced by buying the opposing
  contract." A Yes bid at p pairs with a No bid at 1 − p. The book has bids only, so IB's quoted
  "ask" for Yes is one minus the best No bid [V, Liquidity Retainer Program spread definition].
- **Costs [V].** IB commission 0.00 plus a ForecastEx fee of 0.01 per contract, "charged to each
  side at execution". On a No contract bought at 0.90 the fee is 10% of the maximum gain of
  0.10. Positions earn an incentive coupon on closing market value, currently 3.38% APY [V].
- **Queue priority [V, Rulebook 405(b)].** At each price, affiliated participants (IB is one)
  are "always filled last". A resting customer bid is never behind an IB-affiliated bid at the
  same price.
- **Liquidity [V, Liquidity Retainer Program].** Up to three retained market makers quote a
  "Center Strike Band" (the strike nearest 0.50 and two strikes either side) during 07:00-20:00
  local "Regular Trading Hours" for designated products. Tails outside the band carry no quoting
  obligation, which bears directly on any tail-selling design (the Kalshi tail test is closed;
  `docs/RESEARCH_STATE.md`).
- **The template does not transfer as is [V and C].** A ForecastEx contract stops trading at a
  stated last-trade time [V], which for a data release precedes the release [R], and settles at
  0 or 1 [V]. "Sell the event, buy back after the crush" therefore
  becomes "hold to resolution", or exit before the release (no crush captured). The analogue of
  a short straddle is a range position: Yes on "above the low threshold" plus No on "above the
  high threshold". Its cost is the sum of the two prices and its maximum loss is that cost.
- **Free history [V].** forecastex.com/data publishes daily pairs (refreshed every 10 minutes),
  daily closing prices and summaries as CSV, in a dated archive 83 pages long at ten dates a page,
  so roughly 830 days. That is for
  N11 and N19; I did not download it.

## 6. Harness changes: a futures option

The harness is built around one asset class: US equity options, SMART routing, a multiplier of
100, the penny tick schedule, Reg-T margin, NYSE hours and earnings calendars. The changes below
are listed by file and function. Each live-path change needs fake-gateway tests in
`tests/live/` (`.claude/rules/live-trading.md`).

**Contract and data**
1. `config.py::LiveConfig`. Add a frozen per-product spec (say `FopProductSpec`): root,
   exchange (CBOT, CME, NYMEX or COMEX; not SMART), trading classes (monthly and weekly classes
   differ), currency, market-data type, ladder times relative to the product session, the
   event-calendar source and fee per side. Read multiplier, price magnifier and tick from
   contract details rather than hard-coding them.
2. `ib_market.qualify_underlying`. Hard-codes `Stock(symbol, "SMART", "USD")`. Needs a
   `qualify_future(ib, root, exchange, contract_month)` that returns the future's conId and
   price, with the last-trade date of the future that underlies the chosen option expiry.
3. `ib_market.option_grid` and `snapshot_chain`. They call `reqSecDefOptParams(symbol, "",
   "STK", conId)` and merge every SMART parameter set. For FOPs the call is
   `reqSecDefOptParams(root, exchange, "FUT", fut_conId)` [V, API doc: futFopExchange and
   underlyingSecType]. The returned sets must be kept apart by `tradingClass` and `multiplier`,
   both of which come back per callback [V]. Merging them would mix weekly and monthly series.
4. `ib_market.snapshot_strikes` and `ib_orders.qualify_straddle_legs`. They build
   `Option(symbol, expiry, strike, right, "SMART")`. For FOPs they need
   `FuturesOption(root, yyyymmdd, strike, right, exchange, multiplier, tradingClass=...)`
   (secType FOP [V]).

**Pricing and ticks**
5. `ib_orders.round_to_tick`, `ladder._tick`, `ladder._COARSE_TICK_LOW/HIGH`,
   `LegQuote.sweep_limit` and `under_price_cap`. All hard-code the equity schedule of 0.01 and
   0.05 switching at 3.00, with 0.05 and 0.10 as the coarse pair. FOP ticks are product-specific
   and can be price-dependent. Take `minTick` and the market rule (`reqMarketRule` on
   `marketRuleIds`) from contract details [R]. `LiveConfig.exit_sweep_min = 0.10` "per share"
   must become a number of ticks.
6. `session.plan_entry`. It calls `implied_vol(...)` and `_straddle_value(spot, ...)`, which
   are Black-Scholes on spot (`engine/greeks.py` has no Black-76). FOPs need Black-76 on the
   futures price. The error is second-order at weekly tenors, but the backtest path must match.
   The ex-dividend filter (`exdiv_decision`, `_exdiv_sources`) does not apply and must be
   bypassed explicitly, not left to fail as `exdiv_unknown`.

**Sizing, costs and ledger**
7. `engine.pnl.regt_straddle_margin` and `size_contracts`, as called from
   `session.plan_entry` and `_book_entry`. Replace with the broker what-if margin (ticket T8)
   for FOPs. Section 4 shows the Reg-T model is wrong by a factor of 3 to 16.
8. `session.MULT`, `engine.pnl.CONTRACT_MULTIPLIER` and `forward_test` (`CONTRACT_MULTIPLIER`
   in `mark_to_market_rom`, `forward_ledger_row`, `build_forward_exit`), plus
   `session._book_entry` (`entry_credit = credit_ps * MULT * contracts`). All assume 100. Store
   the multiplier per position and use it everywhere.
9. `forward_test._commission`. Uses 0.65 × 4 fills. It must use the product's all-in fee from
   section 3 (for example 3.02 a side on CBOT grains).
10. `order_events` schema. Add `sec_type`, `exchange`, `trading_class` and `multiplier`. That is
    a schema change to `FORWARD_TEST_SPEC.md` section 6, so it needs a dated amendment.
    `market_data_type` becomes per feed, because futures are delayed 10 minutes and OPRA 15
    minutes [V].

**Safety checks that silently miss FOPs**
11. `ib_orders.broker_option_positions` keeps only `secType == "OPT"`. A FOP leg left by a
    failed flatten, or a futures position created by assignment, would be **invisible** to
    `session._orphan_positions`. This is the most important change: include `FOP` and `FUT`.
12. `ib_orders.broker_short_qty` is keyed by conId and works unchanged.

**Calendar, clock and session**
13. `deploy/session_check.py` classifies the day on the NYSE calendar. CME holidays and early
    closes differ, so it needs a CME calendar per product.
14. `LiveConfig.ladder_rungs` (15:45-15:58 ET) and `LadderSchedule.for_session`. The CBOT ag
    day session closes at 13:20 CT and livestock at 13:05 CT [R]. Rungs must be set per product
    relative to that product's close or settlement window.
15. `session.gather_votes` and `confirm_events` (Finnhub, Nasdaq and Yahoo earnings). Replace
    with the agency's published release calendar (USDA, EIA, BLS, Fed) plus one independent
    calendar, keeping the two-of-N rule.

**Exercise and expiry**
16. American FOPs exercise into futures [R]. An in-the-money short leg at expiry is assigned a
    futures position, and grain futures carry physical delivery after first notice day [R]. The
    `expiry_le_exit` filter already prevents holding to expiry. Add a check that the underlying
    future's first notice day is after the exit date, and alarm on any `FUT` position at the
    broker (item 11). Early exercise of short American FOPs is possible but rare, because a
    future pays no dividend [R]. The harness should still reconcile a sudden futures position
    rather than assume it away.

**Combos (optional second arm)**
17. The specification trades legs and puts combos out of scope. A CME straddle as a BAG of two
    FOP conIds, directed to the exchange, executes as one transaction [V, combo-limit doc]. That
    removes legging risk. It is a separate forward-only arm, and paper "limited combo trading"
    [V] means paper combo fills are weak evidence.

## 7. Harness changes: a ForecastEx contract

Contract construction is close to the equity path: `Option(symbol, date, strike, right,
"FORECASTX")`, secType OPT [V]. Order semantics, booking and risk are not.

1. `session._legs_for_entry`, `_legs_for_exit` and `ladder._flatten`. Every entry is a BUY.
   An exit is a BUY of the **opposite** right at the same strike, never a SELL [V]. Every
   `side == "SELL"` branch is wrong for this venue: `LegQuote.usable_for`, `LegQuote.limit`,
   and the entry walk from mid down to the bid. The "ask" on a contract is one minus the best
   opposite bid [V], so `ib_market.quote_legs` must build the touch from both rights' bids.
2. `ib_orders.round_to_tick`, `LegQuote.sweep_limit` and `under_price_cap`. The tick is 0.01
   from 0.01 to 0.99 [V], so the 3.00 break and the coarse 0.05 sweep tick are wrong. Clamp the
   sweep to 0.99.
3. `plan_exit` and `broker_short_qty`. They test for a short position (`held <= -need`).
   ForecastEx positions are always long. Whether IB nets Yes against No in the position report
   or shows two longs is **unverified**, and it decides how `plan_exit` and `_orphan_positions`
   reconcile.
4. Settlement, not a fill, closes most positions. `_book_exit` and
   `paper_book.forward_exit_from_quote` assume an exit fill. A held-to-resolution contract needs
   a settlement booking path that reads the 0 or 1 outcome.
5. Margin and sizing. Collateral is the full price paid [V], so RoM is return on premium. Remove
   `regt_straddle_margin`.
6. Costs. Use 0.01 per contract per side [V] in `_commission`. Credit the 3.38% APY coupon
   separately, since it is paid monthly on closing value [V].
7. Clock. The venue trades around the clock [V], but market makers commit only 07:00-20:00
   [V]. The ladder needs an event-relative schedule, not 15:45 ET.
8. Paper availability is unverified (section 3). Before any code, confirm in TWS on the paper
   login that a FORECASTX contract can be qualified and that a what-if order is accepted.

## 8. Ranking by effort to a real-time paper test

1. **Equity, ETF and VIX index options (N08, N14 to N17, IBIT in N10, GLD and SLV in N12).**
   These run on the existing harness after universe and calendar changes. The data cost is OPRA
   1.50 a month. The penny-fill limitation in section 2.3 applies.
2. **CBOT and CME FOPs on classic SPAN (N01, N02, N05, N06, N07).** These need the 17 changes
   in section 6, of which 1 to 11 are required. Data is 1.55 a month per exchange, or 10 for the
   bundle. Fees run 1.71 to 3.02 a side.
3. **NYMEX and COMEX FOPs (N03, N04, N12).** These need the same changes. Margin can come only
   from what-if, because energy is on SPAN 2 [R]. The micro contracts (MHNG, MCL) cost 1.01 a
   side.
4. **ForecastEx (N11).** This needs a new order model (buy-only, opposite-contract exit,
   settlement booking), and paper availability is unverified. The data cost appears to be zero.
5. **ICE US softs (N13).** Mechanically these are the same as rank 2, but the data costs 142 a
   month. Each N13 trade must clear that fixed cost before the touch is even considered.

## 9. What I could not verify

- CME contract specifications, trading hours, weekly and short-dated option cycles, the
  exercise style of each class, and the SPAN versus SPAN 2 scope by product. cmegroup.com
  refused automated access (HTTP 403 or timeout), and the search budget ran out. Route:
  `cmegroup.com/markets/...contractSpecs` and the SPAN 2 launch page, read by a person.
- Whether ForecastEx and CME event contracts can be traded on the paper account.
- Whether IB nets Yes and No positions on ForecastEx.
- The Cboe exchange fee for VIX options and a full itemisation of OPRA exchange fees.
- The actual SPAN parameters (VSR, short-option minimum) and any IB house add-on. The section 4
  figures are illustrative.
- Which IB entity holds the project's live and paper accounts. Eligibility for event contracts
  and API restrictions depend on it.

## References

Black, F. (1976). The pricing of commodity contracts. *Journal of Financial Economics* 3,
167-179. The remaining primary sources (IB commission, fee, market-data, margin and paper-account
pages; IB TWS API documentation; ForecastEx Rulebook, FAQ and Liquidity Retainer Program; Cboe
VIX option specifications; ICE Coffee C specifications) are listed with URLs in `sources.csv`.
