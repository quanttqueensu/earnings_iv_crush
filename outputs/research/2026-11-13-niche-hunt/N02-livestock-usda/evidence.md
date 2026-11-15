# N02 livestock-usda: evidence dossier

Lane question: is there a scheduled-event volatility premium in CME lean hog, live cattle or
feeder cattle options around USDA livestock reports (Cattle on Feed, Hogs and Pigs, Cold
Storage, Livestock Slaughter) that survives the touch and can be paper traded at IB?

Hypothesis tested in principle: options load more variance onto the release than it delivers,
by more than the round trip at the touch. Success criterion (from the brief): a real-data
pilot net at the touch against matched non-event windows, or a sourced case for or against a
metered pull, with the pull priced. Outcome: no pilot was possible at zero cost; this is the
case and the pull specification. Labels: verified (read at source), recalled (secondary or
memory), conjecture. Every row of evidence is in `sources.csv`.

## 1. Status in one paragraph

Not testable at zero cost, and the priors lean against the short side. The release timing is
the best structural analogue to after-close earnings the hunt is likely to find (3:00 pm ET,
55 minutes after the 1:05 pm CT livestock close, usually on a Friday, so the information lands
over a closed weekend), and since 22 September 2025 CME lists Monday-expiry live cattle weekly
options built to straddle exactly that gap. But the event itself is small. In the only
published variance decomposition with usable numbers, a Cattle on Feed release adds about 0.4
of an ordinary session's variance to live cattle, and Hogs and Pigs adds about 1.4 sessions to
lean hogs (1985-2003; reactions shrank after 2003). An earnings release is typically several
sessions or more. A small event inside a thin options market means the premium per trade is
small next to a fixed tick, and the one straddle study found the profitable side was the long
side. Worth one priced Databento pull only if the team wants a cheap, decisive read; otherwise
park.

## 2. Prior work

| Paper | Sample, data | Finding | Costs measured |
|---|---|---|---|
| McKenzie, Thomsen and Phelan (2007), *Applied Financial Economics* 17, 511-520. Closest paper. | Hog options around Hogs and Pigs; sample period not read (paywalled) | Abstract (verified): "Both changes in underlying futures prices and implied volatility are mispriced." Per Urcola and Irwin's description (recalled), long straddles entered before and exited on report days were profitable only at low transaction costs | Yes, as a break-even, not at observed quotes |
| Urcola and Irwin (2010), *JAAE* 42(4), 773-790 | Hog options, live-hog and lean-hog periods | Market efficient; excess returns in the live-hog period only; lower transaction costs later help explain lower returns (abstract, verified) | Partly |
| Isengildina, Irwin and Good (2006 JARE; 2005 NCCC version read) | Daily close-to-open futures returns 1985-2003; 970 reports | Hogs and Pigs raises lean hog conditional SD 118.6%; Cattle and Hogs and Pigs raise live cattle SD 44.8%. Table 2: mean squared close-to-open return 3.946 (hogs, Hogs and Pigs days) vs 0.431 non-report; 0.538 (cattle, COF days) vs 0.126 (verified) | No (futures only) |
| Karali, Isengildina-Massa and Irwin (2018 NCCC; JARE 2019) | Surprises vs analyst expectations, to 2016-17 | Price reaction to COF and Hogs and Pigs surprises smaller in 2003-2016; surprises smaller after 2000; reports still move prices (verified) | No |
| McKenzie, Thomsen and Adjemian (2015 NCCC; 2022 AJAE) | CME time-and-sales tick data, live cattle options 2005-2014 | Strong leftward skew; the implied volatility function is amplified in the last hour before COF, otherwise little changes (2015 version, verified); IVs drop after reports (2022, recalled) | No |
| Vizcarrondo, Serra and McKenzie (2026 NCCC) | Barchart daily settlements, 2019 | Cattle options price about 25% more expected variance for downside asymmetry than history justifies; live cattle option volume about a tenth of corn's, feeder cattle about a tenth of live cattle's (verified) | No |

Crowding: thin academically and on the sell side nobody has published a net-at-touch test. The
recent work (2022, 2026) studies skew and downside risk premia, not event variance. CME's own
2025 article markets the live cattle weeklies for exactly this report trade (recalled), so the
idea is visible to every livestock options desk; with a handful of market makers, any event
load is likely priced by the people who set the quotes. No paper reports quoted spreads in
livestock options.

## 3. Mechanism and timing

- **Release time (verified).** Cattle on Feed and Hogs and Pigs are "typically released at
  3:00pm" ET, with pre-holiday exceptions at noon or 1:00 pm ET (Karali et al. 2018, through
  2017). Livestock futures and options trade 08:30 to 13:05 CT (recalled), so the release lands
  55 minutes after the close and is first traded at the next open.
- **2026 calendar (verified, NASS).** Cattle on Feed: Fridays, except Thursday 18 June. Hogs
  and Pigs moved off Fridays in 2026: Thursday 26 March, 25 June, 24 September, Wednesday 23
  December. Next events: Cattle on Feed Friday 20 November and Friday 18 December; Cold Storage
  Tuesday 24 November; Hogs and Pigs Wednesday 23 December.
- **Who pays.** The literature's story is hedging demand: feedlots and packers buy puts against
  supply shocks, which is why cattle skew is steep (McKenzie et al.; Vizcarrondo et al.). That
  is a standing downside premium, not an event premium. Nothing in the record says the event
  variance itself is overbought, and the one straddle paper points the other way.
- **Event size, the decisive fact.** Converting Isengildina et al. Table 2 into units of an
  ordinary close-to-close session (assumed 1.0 %^2 for live cattle, about 16% annualised, and
  2.56 %^2 for lean hogs, about 25%): COF adds about 0.41 sessions of variance to live cattle;
  Hogs and Pigs adds about 1.37 sessions to lean hogs. These are 1985-2003 sizes and later
  reactions are smaller. The conversion uses assumed session variances and is approximate.
- **Price limits.** Limit-locked opens after a large report truncate the first-session move
  (verified that limits applied in the study periods; current dynamic-limit rules not
  verified). For a Monday-expiry option this caps the settlement move, which helps a seller
  and hurts a buyer of a one-session option.

## 4. The cost bar against the event size (synthetic arithmetic)

`scripts/breakeven_grid.py` (output `breakeven_grid.log`, SYNTHETIC, inputs labelled in the
docstring) computes the seller's edge at the mid when the event variance is overpriced by a
share o, against one-side entry cost at a conjectured half-spread of h ticks per leg plus IB
commission (USD 2.96 per contract per side, verified).

| Vehicle | Premium (USD per straddle) | Event share of variance | Edge at mid, o = 0.5 | o = 1.0 | Entry cost, h = 1 | h = 2 |
|---|---|---|---|---|---|---|
| LE Monday weekly sold Friday, COF at 1985-2003 size | 855 | 29% | 6.6% | 12.0% | 3.0% | 5.4% |
| Same, COF halved (post-2003) | 789 | 17% | 3.9% | 7.4% | 3.3% | 5.8% |
| LE serial or regular option, about 15 sessions left | 2,826 | 2.7% | 0.7% | 1.3% | 0.9% | 1.6% |
| HE option, Hogs and Pigs, about 15 sessions left (no hog weeklies) | 1,761 | 8.4% | 2.0% | 3.9% | 1.5% | 2.6% |

Basis: per trade, as a share of premium received, entry side only (holding to expiry adds the
futures exit after exercise; buying back adds a second spread). Read: only the live cattle
weekly gives the event enough weight to matter, and even there the market must overprice the
event variance by half or more just to pay a two-tick entry. The equities lesson (premium
visible at the mid, eaten at the touch) carries over unless spreads are a single tick. Quoted
spreads are the unknown that the pull would settle.

## 5. Tradability at IB

- **Products.** CME live cattle (LE), feeder cattle (GF) and lean hog (HE) options; live cattle
  Monday weeklies L1C to L5C, expiring 1:00 pm CT Monday, listed from 22 September 2025 (OSU
  extension verified; codes and cut-off from CME SER-9595 via search summary, recalled). No
  lean hog or feeder cattle weeklies found (recalled). IB trading-class names for the weeklies
  not verified.
- **Commissions (verified).** USD 0.85 per contract (IBKR Pro, up to 1,000 a month) plus CME
  agricultural options exchange fee USD 2.10 plus USD 0.01 regulatory recovery: USD 2.96 per
  contract per side, USD 5.92 per straddle side.
- **Market data (verified).** CME Real-Time (L1), USD 1.55 a month non-professional. Without
  it IB's CME data is 10 minutes delayed (IB states 10 minutes for CME, not 15). Paper accounts
  use the live account's subscriptions (recalled).
- **Margin.** SPAN on futures options (recalled). A short Monday weekly straddle's worst case
  is bounded by the daily limit (conjecture on current limit size).
- **Paper.** IB paper accounts can trade CME futures options given US futures permissions
  (recalled).

## 6. Data

- **On disk:** nothing for CME agriculture (`data/cache/` checked).
- **Free and permitted:** none found for option quotes or settlements. CME pages time out or
  return 403 to automated clients; Barchart history is script-loaded from disallowed paths;
  Stooq and the Yahoo chart API disallow all robots; MarketWatch serves a CAPTCHA; MacroTrends
  disallows Claude agents by name (all verified on their robots or responses). Not even
  futures closes could be obtained within the rules, so realised event moves could not be
  measured either. StoneX's public pages carry CME CVOL for cattle only from July 2026, with
  gaps and varying timestamps; the registered CVOL study (trials 2,112 and 2,113) found 0 of 5
  discovery pages usable and was abandoned unscored (`diagnosis.log`).
- **Priced route: Databento GLBX.MDP3** (verified: from 2010-06-06; statistics, definition,
  bbo-1m, tbbo, mbp-1, ohlcv schemas; covers CME options on futures). Public pages give no
  per-GB rate. The USD 125 sign-up credit is stated to cover two months of TBBO for the entire
  CME Globex feed, and livestock options are a small fraction of that feed, so a narrowed
  request should cost little (conjecture). Lane N19 (its `evidence.md` sections 4 and 5,
  `data/pull_costs.csv`) brackets the usage rate at USD 0.50, 10 and 280 per GB (only "from
  USD 0.50/GB" is published) and sizes a three-product bbo-1m snapshot design (480
  event-products, 80 series, 4 one-minute snapshots) at 12.3 MB: USD 0.01, 0.12 or 3.44. The
  weeklies add series linearly. N19 found no repo evidence that the project's account covers
  GLBX.MDP3; every past pull is OPRA on usage billing, so entitlement is a team-lead question.
  Alternative: the Standard plan, USD 199 for a month, which per N19's reading of the pricing
  page includes 16+ years of L0 (OHLCV, definitions, statistics including settlements) and the
  last 12 months of L1 (bbo-1m, mbp-1, tbbo, trades), spanning every live cattle weekly since
  about November 2025. Whether bbo-1m exists before 2017 (MDP 2 era) is unverified. On usage
  billing, pull definitions monthly per product, not daily.

**Pull specification** (for the team lead's free cost call; hard cap USD 100):

1. `definition` for parents LE.OPT, GF.OPT, HE.OPT, LE.FUT, GF.FUT, HE.FUT, 2010-06-06 to date,
   to resolve instrument IDs, strikes and expiries (including the L1C to L5C weeklies).
2. `statistics` for the same option parents, daily, 2010 to date: settlement prices and open
   interest. Gives the implied event variance at settlement for about 190 COF and 60 Hogs and
   Pigs releases (settlements are not tradeable levels; implied side only).
3. `ohlcv-1m` for LE.FUT, GF.FUT, HE.FUT on event and control days: realised event moves.
4. `bbo-1m` for the five nearest-ATM strikes, calls and puts, in the two nearest expiries, on
   each event Friday 12:30 to 13:05 CT and the following session 08:30 to 13:05 CT, plus the
   matched control weekends one week either side; 2015 to date. This is the touch.

## 7. What a test and a forward paper trade would look like

- **Historical test after the pull.** Event: COF weekends 2015 to date, LE, nearest expiry
  (weekly where listed). Entry at the 13:00 CT touch on the release day, exit at the touch at
  the next session's 08:35 CT quote and at settlement. Control: the same construction on the
  non-COF Friday-to-Monday weekends (the Monday weeklies list every week, so the control is
  exact in tenor and weekday from September 2025). Statistic: net at the touch per trade on
  premium, event minus control, date-clustered 95% intervals; split 2015-21 discovery, 2022 to
  date held-out. Secondary: the long side, because the closest paper found it.
- **Forward paper.** On each COF Friday, record the L-class weekly ATM straddle touch at 12:45
  CT and its Monday open and settlement marks with CME L1 data, plus a non-COF Friday control;
  dry-run only.
- **Kill criterion.** Kill if the median quoted half-spread at 12:45 CT, summed over both legs,
  exceeds 3% of the ATM weekly straddle premium (about the mid edge if a post-2003-size event
  were overpriced by half, section 4), or if after 12 forward COF events the event-minus-control
  net at the touch is not positive.

## 8. Not verified

CME contract specifications, trading hours, tick sizes, weekly cut-off time and current limit
rules (CME unreachable); the full texts of McKenzie et al. (2007) and Urcola and Irwin (2010);
the 2022 AJAE results; Databento's per-GB rates and schema tiers; IB's trading-class names for
the weeklies; any live quoted spread in livestock options; the current-era size of the report
moves (no permitted futures data).

`C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N02-livestock-usda\evidence.md`
