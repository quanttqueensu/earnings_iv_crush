# Idea slate, 2026-11-14: fifty candidates after the earnings-adjacent hunt

## Question, scope and standard

Which untested ideas could close the gap between the hedged hold and break-even, and which
add-ons the project needs whatever the answer is. Scope: the single-name US earnings vehicle and
its execution, scheduled single-name events, and cross-product trades reachable through an
Interactive Brokers paper account.

Every idea was checked against `docs/RESEARCH_STATE.md` section 2, the November hash records
(`outputs/research/prereg_2026-11-*.json` and the texts they point to), the lane reports of the
three 2026-11-13 and 2026-11-14 hunts, and E5's evidence map
(`2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/evidence.md`). Ideas found closed
are listed in the last section instead of being proposed. Nothing here is tested and nothing here
is a finding. Citations marked "recalled" were not re-read for this note and must be checked
before a pre-registration cites them.

## The arithmetic every idea is ranked against

- **The book.** The hedged hold nets about -1% of m0 per trade on 2019-24: -1.05% on all events
  with a timed session label, -0.78% [-1.44, -0.13] on after-close events (E5,
  `session_heldout.json`; m0 is 0.20 times the forward plus the 15:59 bid).
- **Levers measured so far**, each on its own block, per trade, net, in m0:
  - assignment netting +0.22% [+0.21, +0.23] (adopted as `HEDGED_NET`);
  - resting entry against the 15:59:00 cross +0.217% [+0.154, +0.278] (trial 1,779, N=1,703,
    2023-24);
  - tightest of the three central strikes +0.21% [+0.14, +0.28] (trial 1,819, confirmatory
    status contested);
  - spread-aware strangle +0.55% [+0.40, +0.71] (trial 1,826, exploratory, not re-valued under
    netting).

  Two of the four pick cheaper contracts and two move the entry clock, so they overlap and do
  not add.
- **Selection's record.** About 1,500 hash-recorded trials and about 550 exploratory ones since.
  No selector on price or non-price information has survived a held-out block. Under no edge, the
  best per-trade Sharpe expected from a search this size is about +0.43.

An idea is worth a trial number only if it does one of two things. Either it removes a measured
cost of about 0.1% of m0 or more, or it brings a mechanism and a data source the record has never
had. Selection ideas start with a low prior.

**A descriptive read made for this note.** It is not a trial: it reads a cost component, not an
outcome. The stock hedge's modelled half-spread cost (`equity_cost`, `hedged_hold.py` line 460) is
read from the `outputs/research/2026-11-02-hedged-event-hold/` panels:

| Panel | N | Mean, % of m0 | Median, % of m0 | Median hold |
|---|---|---|---|---|
| broad 2013-24 | 7,753 | 0.163 | 0.109 | 3 sessions |
| megacap | 1,183 | 0.098 | 0.085 | 2 sessions |
| broad 2025-26 | 1,597 | 0.233 | 0.232 | 3 sessions |

This sets the ceiling for B1. The valuation also charges no financing anywhere
(`hedged_short_straddle`, lines 413 to 486), which A3 sizes.

## The slate

The prior column is the judgement that an idea moves the book by at least 0.1% of m0 net, or
answers a decision the project must take. It is not a probability estimate.

The cost column uses four labels:

| Label | Meaning |
|---|---|
| free | can be done on data on disk |
| forward | needs paper-book time |
| pull | needs metered or paid data |
| you | needs the team lead's decision |

### A. Valuation corrections: what the current numbers are

| # | Idea | Why it matters | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| A1 | Re-strike the 2025-26 ledger on the 15:59 parity forward and re-score it as a dated correction | sold strike sits a mean ln(F/K) +188 bp below the forward, N=1,220; headline effect and sign unmeasured | `oos_2026_ledger.csv`; hunt SUMMARY "Defects found" | free | high |
| A2 | Early call exercise before ex-dates in the hold, or the paper book's ex-date skip | credit to the writer up to about +0.08 to +0.11% of m0 per trade (upper bound) | Hao, Kalay and Mayhew (RFS 2010) | free | high |
| A3 | Financing in the hold: interest on a long stock hedge, rebate less borrow on a short one, interest on premium, and early exercise of deep in-the-money puts | none is charged today; at a 2% broker spread on half the peak hedge notional the asymmetric part is about 0.03 to 0.09% of m0 on the panels above, small because the median hold is 3 sessions | `hedged_hold.py`; put early exercise is conjecture | free | medium |
| A4 | Settlement on OCC-adjusted contracts after special dividends of USD 12.50 or more | unadjusted strike would mis-settle; three such events found in 2019-24 | E4 review | free | low |
| A5 | Re-value 1,826 and 1,819 under `HEDGED_NET`, and print 1,826's wing-quote attrition funnel | the largest exploratory lever has not been re-valued under the adopted netting | lane B report | free | high |
| A6 | Audit the spot source of every 2025-26 panel, including the hedged-hold confirmation and the 53aa4898 and 15:45 panels | if any 2025-26 panel shares the adjusted-spot path, its strike centring and its lever sizes inherit the A1 defect | `chains.py::_spot_table` | free | high |
| A7 | One tracked trial ledger and a refreshed deflation input | the deflation bar every verdict is read against is still "about 1,500" | `RESEARCH_STATE.md` section 1 | free | (bookkeeping) |

### B. Execution and cost: the only family with passes

| # | Idea | Why it could pay | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| B1 | Hedge at the closing auction (market-on-close) instead of paying a half-spread at each close | the hold already marks the hedge at the close print, which an MOC order trades at; ceiling is `equity_cost`, 0.10 to 0.23% of m0. Counter: auction impact, IB MOC fees, and a hedge ratio fixed before the cutoff from a pre-close price adds tracking error | Bogousslavsky and Muravyev, on who trades at the close (recalled) | free | high |
| B2 | Minimum-variance delta in place of Black-Scholes delta | lowers hedge-error variance with near-zero mean effect, so it lifts per-trade Sharpe through the denominator; nothing in the repository uses it. Counter: a 3-session hold has few rebalances and the jump is unhedgeable | Hull and White (JBF 2017, recalled) | free | medium |
| B3 | Make the confirmed resting entry the paper book's actual order (re-pegged midpoint order from 15:30, cross at 15:59:00 if unfilled) | the one confirmed lever is not in the live order path | 1,779, 1,780 | you | high |
| B4 | Capacity of the passing levers: re-run 1,779 and 1,819 fills against displayed size at 1, 5, 10 and 25 contracts | decides whether the levers survive any real size | cached quote sizes, if stored (unchecked) | free | medium |
| B5 | Entry minute chosen by causal spread state inside 15:00 to 15:59 (first minute the spread falls below the name's causal median, else 15:59) | differs from fixed clocks (lane 4) and event-level spread gates (closed). Counter: drift gave back 60 to 69% of the half-spread in 1,779 | lane 4; 1,779 review | free | medium |
| B6 | Per-event expiry choice: sell the expiry with the lowest touch per unit of event variance | lane B chose strikes; later expiry closed as a fixed rule (2026-11-02), never as a per-event cost choice | Dubinsky et al. (RFS 2019) two-expiry split | free | medium |
| B7 | Monday and Wednesday single-stock expiries for the few names that list them | one session shorter hold, less hedge cost; small N | E5 idea 2 (exchange filings) | forward | medium |
| B8 | Strangle width set by the move-size forecast (1,623, which passed on term-structure information) | monetises size through contract choice rather than as a selector. Counter: 1,623's information is already in the implied move; width may only reshuffle premium | crush forecasting closed (skill, no monetisation) | free | medium |
| B9 | Straddle as a package order on the complex order book | lane 4 could not measure package fill probability; only a fill rate of 1 brought the package arm to zero. Paper fills are simulated, so evidence needs G4 | lane 4 report | forward | medium |
| B10 | Commission schedule: IB tiered pricing and exchange rebates for resting customer orders against the assumed USD 0.65 per contract per leg | the assumed fees are about 0.05% of m0 on a USD 100 stock, so the lever is small | `HedgedHoldConfig.fee_per_contract_leg` | free | low |

### C. Selection: new mechanism or new data only

| # | Idea | Why it could pay | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| C1 | Implied borrow from the 15:59 parity forward as a hedge-cost screen | hard-to-borrow names make the short-stock hedge expensive and their puts rich; also a cost the hold omits (A3) | parity-forward premium as a reaction predictor (closed, different target); Ofek, Richardson and Whitelaw (JFE 2004); Muravyev, Pearson and Pollet (JF 2022, recalled) | free | medium |
| C2 | Short interest (FINRA, published twice a month; terms and robots.txt to check) | squeeze risk fattens the right tail the short straddle pays | lottery and ivol selectors (closed); distress T2, T3 (closed) | free | low |
| C3 | First reports after listing (fewer than four prior reports in CRSP) | the implied move is set without own history | own-history richness, R5, name persistence (closed); no options paper verified | free | low |
| C4 | Share-class siblings (GOOG against GOOGL): same event, two straddles; sell the richer, buy the cheaper, hedge | a pure relative-value read with no fundamental difference; lane 5 left it untested. Counter: N about 50 over 13 years and two touches | de Jong, Rosenthal and van Dijk (RoF 2009) on dual-listed companies (recalled) | free | low |
| C5 | Supplier and customer links | lane 5 left it untested; E3's industry peers failed | Cohen and Frazzini (JF 2008); data not on disk | pull | low |
| C6 | Notice length of the report date | differs from the closed date-shift test, which used the move, not the notice | Boulland and Dessaint (JBF 2017); needs first-seen stamps in calendar snapshots (unchecked) | free | low |
| C7 | Dealer gamma from customer-signed, open/close-flagged flow | the caches lack open/close flags; demand pressure F2 failed without them | Ni, Pearson, Poteshman and White (RFS 2021); Cboe Open-Close data is paid (recalled) | pull | low |
| C8 | Option-to-stock volume ratio on D-1 as a hedged-hold selector, D-1 volume only so the Alpaca end-of-day leak rule holds | volume level, not the flow sign E2 tested | Roll, Schwartz and Subrahmanyam (JFE 2010); Johnson and So (JFE 2012) | free | low |
| C9 | Passive (ETF) ownership share | ETF ownership raises underlying volatility, which may lower the event's relative richness | Ben-David, Franzoni and Moussawi (JF 2018); holdings not on disk | pull | low |

### D. Other scheduled single-name events

| # | Idea | Why it could pay | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| D1 | FDA action (PDUFA) dates | far more numerous than advisory committees (lane H, N=18) | no options paper verified; calendars mostly paid; biotech spreads wide | pull | low |
| D2 | Pending merger targets with scheduled vote or close dates | option volatility against the deal-break jump. Counter: a crowded trade, short volatility into a binary break | Subramanian (2004) jump model and Barraclough et al. (RFS 2013), both recalled; deal dates paid | pull | low |
| D3 | IPO lock-up expiries | stock drift documented; options untested here | Field and Hanka (JF 2001); dates need prospectuses (EDGAR is off-limits) | pull | low |
| D4 | S&P 500 addition effective dates | delta-hedged calls +2.87% to ED+126 at the mid in the paper | Hollstein and Wese Simen (2021 WP, E5); post-announcement chains not cached | pull | low |
| D5 | Investor and analyst days | volatility 4 to 6 times conference presentations | Kirk and Markov (TAR 2016, E5); no free dates | pull | low |
| D6 | Monthly sales releases by the few retailers that still publish them | small scheduled jumps on liquid options | none found | free | low |

### E. Cross-product and other venues

| # | Idea | Why it could pay | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| E1 | Leveraged single-stock ETF options against the underlying's options on its earnings night | the ETF's implied variance should sit near leverage squared times the underlying's, less a path term; trade the richer. Counter: wide touch, small capacity | Leung and Sircar (AMF 2015) and Ahn, Haugh and Jain (2015), both recalled; chains not cached | pull | low |
| E2 | Concentrated sector ETFs on megacap nights (SMH on NVDA, XLK on AAPL and MSFT) | a different product from QQQ | QQQ priced fairly (lane G, closed) | free | low |
| E3 | Canadian cross-listed reporters: Montreal Exchange options against US options on the same event | different hours and liquidity on the same event | none; MX quotes not cached | pull | low |
| E4 | Kalshi company-KPI and mention markets against option-implied distributions | an event contract tied to the same report | Kalshi tails and maker (closed) | free | low |
| E5 | ForecastEx daily index contracts against digitals implied by the cached SPY and QQQ chains | listed open in `RESEARCH_STATE.md` section 3 | N11 (ForecastEx against Kalshi, closed) | free | low |

### F. Capital, risk and monitoring

| # | Idea | Why it matters | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| F1 | Return on margin under portfolio margin instead of Reg-T | same P&L, smaller denominator; IB requires about USD 110,000 of equity (recalled). Changes RoM, not edge, so quote both | none | you | (reporting) |
| F2 | Interest on short-sale proceeds and idle margin cash in the book's accounting | pairs with A3 | none | free | low |
| F3 | Same-session concentration cap on the book's vega | earnings covariance is carried by reporter count (closed finding), so a count cap is the natural rule | earnings covariance study | free | (risk) |
| F4 | Sequential monitoring of the forward book with a pre-declared stop and promote rule | lets the paper book be stopped or promoted without peeking bias | Wald's sequential probability ratio test; always-valid inference, Johari et al. (OR 2022, recalled) | free | (protocol) |

### G. Forward tests and infrastructure

| # | Idea | Why it matters | Nearest closed or prior work | Cost | Prior |
|---|---|---|---|---|---|
| G1 | Forward pre-registration of the stacked execution book (15:45 or resting entry, tightest strike or spread-aware strangle, hedged hold with netting) | every historical block is viewed for it; a forward block is the only route from exploratory lever to finding | `RESEARCH_STATE.md` section 3; 2026-11-09 combined-levers record | forward | high |
| G2 | Forward test of the empirical-Bayes jump model's richest tercile | passed held-out 2013-18, failed its 2025-26 replication | lane D report | forward | low |
| G3 | Real-time option quotes on the paper account | IB's delayed quotes make paper fills non-evidence (landmine) | `CLAUDE.md` landmines | you | high |
| G4 | Small live pilot measuring real fills of the resting entry and the package order | paper fills are simulated; real money and an outward action | none | you | high |
| G5 | Daily P&L attribution in the paper book: premium, crush, gamma, hedge cost, half-spreads paid | shows which cost the forward book actually pays | `engine/pnl.py::build_trade` reconciliation | free | (tooling) |
| G6 | A fourth calendar source that allows automated access, to lift coverage under the two-of-three rule | more tradeable events at the same rule | `CLAUDE.md` landmines | free | (coverage) |
| G7 | Replace the Yahoo ex-dividend lookup in `earnings_iv_crush/live/session.py` | Yahoo's robots.txt disallows automated access; live-path change needs fake-gateway tests | hunt SUMMARY | you | (compliance) |
| G8 | CME tests: weekly Treasury options into payrolls, CPI and FOMC; grain options into USDA; SOFR into FOMC | the fixed 1/64 tick is a structural argument; no real-data evidence yet | niche hunt N05, N06 | pull | low |
| G9 | Exits in the Cboe pre-market session (07:30 to 09:25 ET) | open in section 3, but the hedged hold already beats every buy-back | lane F | forward | low |

## Ideas that look new but are closed

The following were checked and found already tested; each needs a new mechanism and a new
pre-registration before it is reopened:

- dispersion against the index, or an index hedge of the overnight move (lane 4: correlation -0.03, at most 0.1% of variance removable; lane G);
- weekend and Friday effects (1,754, 1,758);
- crowded or thin reporting days (lane 5);
- analyst disagreement (2026-11-07);
- later expiry as a fixed rule, smile strike, parity leg choice and open hedge (all 2026-11-02);
- delta bands and stops (lane A);
- wings, iron fly and calendars;
- early entry (lane I);
- revision breadth and earnings seasonality (2026-11-10);
- distress scores, peer shocks and own tail history (2026-11-12);
- pre-announced 8-Ks (2026-11-10, lane 5);
- Wikipedia attention, 10-K language and consumer demand (2026-11-10);
- implied correlation in earnings season (E5);
- day-against-night option returns (E1, E5).

## Recommendation

Run at most six of these, each as a dated study with a hashed pre-registration, and start with
the corrections, because they move the bar every lever is read against. In order:

1. A1 with A6.
2. A5.
3. B1.
4. A2 with A3.
5. B6.
6. B2.

G1 is the single forward step that can turn the execution levers into a finding, and B3 with G3
is what makes its fills mean anything.

The strongest objection to this slate is that it is almost entirely cost-side. The largest
ceiling identified here, B1, is 0.10 to 0.23% of m0, and the measured levers overlap, so whether
any combination reaches zero is unknown. Opening fifty lanes would raise the deflation bar for
every later verdict while selection's record predicts failure; most of section C should stay
parked until a new data source arrives.

C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-idea-slate\IDEAS.md

## Status after the slate tests (2026-11-15)

Results are in `outputs/research/2026-11-14-slate-tests/SUMMARY.md`. Everything is exploratory.

**Run:**

| Group | Ideas and outcome |
|---|---|
| A, corrections | A1 to A7 done. Netting, early call exercise and financing are now in `H_corr`. |
| B, levers that fail | B2, B5, B6, B8. |
| B, cost recovery | B1 (like-for-like), B10, which found the stock commission `H_corr` omits, and the new B11 delta band. |
| B, descriptive | B4: the levers shrink with size. |
| C, fail | C1 and C8. |
| C, underpowered | C3. |
| E | E5 fails discovery. |
| F | F2 is folded into A3. F3: the cap lowers risk only by trading less. F4, the sequential monitor, was built: the gauge must be stated on the mean. |
| G | G5 is partly built, as L4's per-trade cards. |

**Blocked:**

| Reason | Ideas |
|---|---|
| No free source | C2 |
| Data absent | C4, C6, D6, E2, E4, G6 |
| Paid data | C5, C7, C9, D1 to D5, E1, E3, G8 |
| Forward only | B7, B9, G1, G2, G9 |
| Needs the team lead | B3, F1, G3, G4, G7 |
