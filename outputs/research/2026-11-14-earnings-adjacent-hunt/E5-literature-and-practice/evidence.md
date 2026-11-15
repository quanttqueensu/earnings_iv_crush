# E5 evidence map: return sources attached to earnings events and the option calendar

## Question, scope and standard

Question: which documented return sources attached to US single-name earnings events, or to the
equity option market's own calendar, are not on the project's closed list, and which of them
survive (or were ever measured against) costs at the touch? Scope: delta-hedged and day-night
option returns, weekly and sub-weekly single-name expiries, retail demand into earnings, dealer
positioning, post-earnings implied-volatility decay, report timing (pre-open against post-close,
day of week, order in the season, notice of the date), guidance, analyst and investor days, index
inclusion, and the stock-side announcement anomalies that sit on the same event clock. Success
criterion: a map with sample, effect size, cost treatment and event-time structure per row, the
closest closed study, the zero-cost test the caches allow, exploratory screens where one fits in
an hour, and a ranked five.

Labels: **V** verified at the source in this lane (full text, slides or filing text read; the
location is in `sources.csv`), **V2** verified only at an abstract, bibliographic record or
secondary summary, **R** recalled and not checked, **C** conjecture or arithmetic done here. The
earlier map for other asset classes is `../../2026-11-13-niche-hunt/N18-literature-map/evidence.md`.

## 1. Headline reading

1. **The best-documented earnings-option premium in the recent literature is the project's own
   finding, with the beneficiary named.** De Silva, So and Smith (Review of Finance 2025; slides
   read, V) show retail buying options before earnings with high expected announcement
   volatility, mostly from market makers, over about 32,000 announcements in 2010-2021. The
   announcement-day short straddle return rises from 7% to 18% across quintiles of AbnormalIV
   (short-minus-long-dated implied variance), long-short 11 points, t 19.6; the straddle keeps
   decaying for two weeks after high-EAV announcements (long-short 9 points, t 8.3). Retail pays a
   half-spread of 8 to 9.5% of the midpoint. AbnormalIV is the project's closed term gate, which
   selects jump size and fails at the touch; the retail proxy (small-lot share, lane5 trial 1,769)
   failed on 2025-26. The paper's own reading is that the premium accrues to the liquidity
   provider, which is the project's open line, not a new source.
2. **No earnings-option paper read here measures returns at the touch.** Every option row below
   uses OptionMetrics closing midpoints or end-of-day prices (V where read: Lyle et al., Hollstein
   and Wese Simen, Yan, de Silva et al.). The one cost-aware statement is negative: Muravyev and
   Ni's day-night pattern is swamped by daily option spreads (V2).
3. **The strongest option-side lead found, report timing (pre-open against post-close), fails here.**
   Lyle, Rigsby, Stephan and Yohn (2018, V) find more abnormal volatility on days 2 to 5 after
   pre-open reports, which options do not price: a long ATM straddle from the close of day 1 to
   the close of day 5 earns 1.74 points more after pre-open than post-close reports (with
   controls, t 6.8, N=51,759, 2006-2015, at the mid). Tested here as trial 2,805 on the hedged
   hold under HEDGED_NET: it fails on both blocks, and the post-event variance gap the paper
   reports is absent on the project's events (section 3).
4. **The market structure changed in 2026.** Since the SEC approved ISE's filing on 2026-01-16,
   single stocks with market capitalisation above USD 700bn (plus volume, position-limit and
   penny-program tests) list Monday and Wednesday expiries; the rule text (Cboe's competitive
   filing, V) forbids an expiry on a day with an after-close report but not the day after. In the
   project's 2026 events every such name still used the Friday weekly (checked on
   `events_confirm_2025_26.parquet`, 27 events), because their reports fell on Wednesday or
   Thursday after the close. The new expiries help only Tuesday after-close and Wednesday or Monday
   pre-open reporters among about nine names.
5. **The stock-side announcement anomalies do not clear a stock round trip on the project's
   events (exploratory, trials 2,802 to 2,804).** The earnings announcement premium keeps its
   published sign but is about the size of 10 bp of cost; the So and Wang reversal is absent; the
   option-expiration-week effect has the wrong sign on a broad optioned basket.

## 2. The map

Columns: topic; work; sample and N; effect with basis; costs measured; event time; closest closed
study here; zero-cost test on the caches; label.

### 2.1 Option returns around the earnings event

| Topic | Work | Sample, N | Effect, basis | Costs | Event time | Closest closed | Zero-cost test | Label |
|---|---|---|---|---|---|---|---|---|
| Retail demand into high-EAV earnings | de Silva, So and Smith (RoF 2025) | about 32K EAs, 2010-2021; Nasdaq and PHLX clientele trade outline; OptionMetrics | EA-day short straddle return 0.07 (Q1) to 0.18 (Q5) by AbnormalIV, 5-1 0.11 (t 19.55); implied variance rises about 40% more before top-quintile retail buying; retail half-spread 8-9.5% of mid; retail losses 5-9% (10-14% high EAV) | Retail's half-spread modelled, not the seller's touch | Positions built t-5 to t-2; held over a week after | Term gate (selects jump size, fails 2025-26); lane5 small-lot share 1,769 fails | None new: both proxies already scored | V (slides; published version not read) |
| Post-EA straddle decay after high-EAV reports | same | same | Post-EA straddle short 5-1 0.09 (t 8.26), dissipating over two weeks | No | t+1 onward | Post-announcement straddle to expiry fails net (-1.41% RoM, N=1,888); lane C post-event VRP about zero net | None new | V |
| Pre-open vs post-close reports | Lyle, Rigsby, Stephan and Yohn (2018 WP) | 2006-2015 WSH timestamps; 48% PO, 52% PC | Long ATM straddle day 1 close to day 5 close: PO minus PC +2.23 (no controls, t 8.86), +1.74 (controls, t 6.80), N=51,759; delta hedge +0.24 (t 5.30), N=56,273; % of option price, midpoints | No | Days 2-5 after the report | No trial uses the amc/bmo split on the hold; lane5 cut it descriptively on the event night only (diag1.log, discovery); lane A's perfect-foresight hold-or-buy-back ceiling (-0.13% and +0.10% of m0) caps any hold-versus-buy-back use | Run as 2,805: fails on both blocks; no post-event variance gap on these events | V |
| Late reporters | Adams and Neururer (JFM 2020) | OptionMetrics 1996-2017 | Higher implied uncertainty and VRP for later reporters in short-dated delta-hedged ATM straddles held -1 to +1; growth firms | Not stated in abstract | -1 to +1 | lane5 late_in_industry 1,749, early_in_industry 1,759/1,770 (fails held-out), early_calendar_position 1,765 | Closed | V (abstract) |
| Historical vs implied move on weeklies | Milian (JRFM 2023) | weekly options, sample not read | Straddle returns higher when past EA moves exceed the implied move | Not read | expiry near the EA | Move gate, own-history richness, R5 (all fail out of sample) | Closed | V2 |
| Volatility-shock overreaction | Yan (2022 WP) | 1996-2020 monthly, midpoints | High variance-change straddles underperform by 5.30% a month; corrected at earnings | Spread-ratio robustness only | monthly | HAR/GARCH selectors on the hedged hold | Not an event trade | V |
| Option-led price discovery on macro days | Eberbach, Uhrig-Homburg and Yu (2021 WP) | high-frequency option trades | Option flow predicts the stock reaction more when EAs coincide with macro releases, mostly where option spreads are low | No | t-1 | P1 skew, parity forward (closed); E2 owns flow | E2's lane | V |
| Pre-earnings straddle run-up | Gao, Xing and Zhang (JFQA 2018) | (N18 row) | +3.34% from t-3 to t, larger where spreads are wider | Mid only | t-3 to t | Vega run-up loses at the touch (-11.72% of premium, N=922) | Closed | V (N18) |

### 2.2 The option market's own calendar

| Topic | Work | Sample, N | Effect, basis | Costs | Event time | Closest closed | Zero-cost test | Label |
|---|---|---|---|---|---|---|---|---|
| Monday/Wednesday single-stock expiries | ISE approval 34-104624 (2026-01-16); Cboe SR-CBOE-2026-007 | Qualifying: market cap above USD 700bn, monthly volume above 10m sides, position limit at least 250,000, penny program; up to two Monday and two Wednesday expiries | Structure, not a return: no expiry on a day with an after-close report; nine names at launch (V2) | n/a | A Tuesday-amc or Wednesday-bmo report gains a 0-1 day expiry | Lane B contract choice; HEDGED_NET hold to the Friday expiry | Count eligible events and record nearest-expiry quotes forward | V (rule text), V2 (names, launch date) |
| Option-expiration week | Stivers and Sun (JBF 2013) | S&P 100, 1988-2010 | Higher weekly returns in expiration week for high option-activity names (summary: 68 to 71 bp spreads, 1996-2008) | Not reported | Monday to third Friday | None | Run here as 2,804 on a broad basket: fails, wrong sign | V2 |
| Nontrading periods | Jones and Shemesh (JF 2018) | | Option returns lower over weekends: mispriced variance while closed | Not in abstract | Weekends | lane5 weekend_gap 1,758, friday_reaction 1,754 | Closed | V2 |
| Day vs night | Muravyev and Ni (JFE 2020) | S&P 500 and equity options | Delta-hedged -0.7%/day: -1% close to open, +0.3% open to close; option prices too high at the close | Spreads swamp the effect (summary) | Overnight vs session | The core trade is the overnight short; E1 owns the intraday long | E1's lane | V2 |
| Dealer gamma | Ni, Pearson, Poteshman and White (RFS 2021) | | Positive net gamma of hedgers lowers stock volatility, negative raises it | n/a | Continuous | E4 pinning; F2 demand pressure (fails) | Pre-event signed flow (flow files) against post-event realised variance of the hold | V2 |
| Who is net long options | Christoffersen, Goyenko, Jacobs and Karoui (RFS 2018) | | Illiquid options earn more; market makers net long on average, end users net sellers | Illiquidity premium is the cost | | | Contrast: before earnings, retail makes market makers net short (de Silva) | V2 |
| Retail and wholesalers | Bryzgalova, Pavlova and Sikorskaya (JF 2023) | | Retail over 60% of option volume; prefer weekly options with 12.6% average spread; lose on average | Spread measured | Short-dated | | | V2 |

### 2.3 Report timing and other corporate events

| Topic | Work | Sample, N | Effect, basis | Costs | Closest closed | Zero-cost test | Label |
|---|---|---|---|---|---|---|---|
| Notice of the report date | Boulland and Dessaint (JBF 2017) | | Late notice signals bad news; stock strategy 1.5% a month | Not in abstract | Johnson and So date shifts (sign reversed; advanced dates +2.24% on 174 events, secondary) | Only if the project's calendar snapshots stamp when a date first appeared (not checked) | V2 |
| Friday reports | DellaVigna and Pollet (JF 2009) | 1984-2006 | 15% lower immediate response, 70% higher delayed; about 1.1% of reports are Friday evening (Lyle et al.) | No | lane5 1,754, 1,758 | Closed, too few | V2 |
| Guidance | Rogers, Skinner and Van Buskirk (JAE 2009); Neururer and Papadakis (2025) | | Management forecasts raise short-term IV; bundled revenue guidance lowers uncertainty | No | Post-event hold selectors (HAR, GARCH, slope) | Guidance flags not in cache (IBES guidance not mirrored locally) | V2 |
| Analyst and investor days | Kirk and Markov (TAR 2016); Cabrera, Kolokolova and Zhang (2025 WP) | 3,802 days 2004-2013; over 1,000 days 2011-2022 | Volatility and turnover 4 to 6 times conference presentations; run-up to the day, reversal after hyped days; alpha 0.13% a day (reinforcement-learning strategy) | No | Lane H product events (fail, N=16) | No free dates; DoltHub chains too sparse (lane H) | V2, V |
| S&P 500 inclusion | Hollstein and Wese Simen (2021 WP) | 1996-2015 | Delta-hedged calls +1.10% AD-1 to AD (1.04% adjusted); +2.87% AD to ED+126; midpoints | No | none | Not tradeable ex ante (announcement unscheduled); post-announcement leg needs chains not cached | V |

### 2.4 Stock-side anomalies on the same clock

| Topic | Work | Effect, basis | Costs | Closest closed | Here | Label |
|---|---|---|---|---|---|---|
| Earnings announcement premium | Beaver (1968, R); Frazzini and Lamont (2007, R); Barber et al. (JFE 2013); Savor and Wilson (JF 2016) | Announcers earn an abnormal 9.9% a year annualised (Savor and Wilson); global but in 9 of 20 countries; a later paper claims it has disappeared in the US | Barber et al. note turnover cost; none measured | PEAD on SUE (not established) | 2,803 fails at 10 bp | V2 |
| Pre-announcement reversal | So and Wang (JFE 2014) | Reversal six times larger around EAs; low-minus-high 1.45% per three-day window vs 0.22% pseudo, 1996-2011; gross | No; out-of-sample summary slightly negative | none | 2,802 fails | V, V2 |
| Pre-announcement run-up of past winners | Aboody, Lehavy and Trueman (RAS 2010) | Top-percentile 12-month winners +1.58% market-adjusted in five days before, -1.86% after | No | none | Not run (top percentile is about 1% of events, N too small) | V2 |

## 3. Exploratory screens (trials 2,802 to 2,804)

Declared in `diagnosis.log` before any outcome; scorer `screens.py`, freeze note
`freeze_e5_screens.md` (self-hashed, scorer hash recorded, `block_is_clean` True). Events:
the hedged-hold panel's 11,257 report events, of which 5,940 fall in the CRSP close window
2019-2024 (15 dropped as calendar mismatches, none for splits). Holding from the close of s-2 to
the close of s+1 (s = report session), market-adjusted by the S&P 500 total return, net of 10 bp a
round trip (3 bp project half-spread plus 1 bp per side on the stock, 1 bp per side on the hedge).
Per trade, % of stock notional, date-clustered 95% intervals. All exploratory.

| Trial | Rule | Block | N | Net mean | Event gross vs pseudo | Verdict |
|---|---|---|---|---|---|---|
| 2,802 | So and Wang reversal, causal extreme quintiles | 2019-21 | 1,035 | -0.013% [-0.420, +0.406] | +0.087 vs +0.231 | fail |
| 2,802 | same, frozen | 2022-24 | 1,315 | +0.155% [-0.204, +0.521] | +0.255 vs +0.120 | fail |
| 2,803 | Long every reporter | 2019-21 | 2,736 | +0.124% [-0.109, +0.358] | +0.224 vs -0.129 | fail |
| 2,803 | same, frozen | 2022-24 | 3,204 | +0.037% [-0.181, +0.264] | +0.137 vs -0.040 | fail |
| 2,804 | Option-expiration week, broad basket, per week | 2019-21 | 36 weeks | -0.256% [-0.780, +0.253] | -0.156 vs +0.254 (other weeks) | fail, wrong sign |

Trial 2,805 (requested by the team lead; scorer `selector_session.py`, freeze note
`freeze_session.md`): the report session as an entry selector on the hedged hold. Treated =
after-close (amc) events with a timed IBES session label agreeing with the panel's `is_amc`
(every 2013-24 event labelled; no dmh or conflicts). Outcome: causal cell residual of
y_net = H_net m0 / mid0 under HEDGED_NET, in % of entry-mid premium, per trade, net at the touch.

| Block | amc N (of labelled) | amc mean residual | Matched null pct | Continuation amc-bmo | Post-event RV ratio amc-bmo | Verdict |
|---|---|---|---|---|---|---|
| 2013-18 (viewed before by lane5) | 712 (2,059) | +2.09% [-1.96, +6.10] | 89.4 | +1.95 [-1.04, +5.08] | -0.016 [-0.061, +0.030] | fail |
| 2019-24 (clean, read once) | 1,955 (5,113) | +1.54% [-1.14, +4.20] | 76.5 | +0.18 [-1.48, +1.87] | -0.001 [-0.029, +0.028] | fail, kill |

The selected amc book still loses at the level (H_net -0.78% of m0 [-1.44, -0.13] against a pool
of -1.05%, 2019-24). Within cell, amc events carry a higher implied move and premium per m0 and
0.32 fewer post-event sessions, yet show no post-event variance difference: the paper's driver is
not present on these events.

Search count: four configurations, no variants (2,805's amendment 01 changed only its driver
check, after a coverage defect, before the freeze). The held-out reads of 2,802 and 2,803 came after
failed discovery and cannot become findings. 2,804's held-out block was not read, so 2022-24
stays unviewed for a test on the paper's own S&P 100 high-activity subset.

Reading. The announcement premium is present in both blocks at about +0.14 to +0.22% gross
over three sessions (event minus pseudo +0.35 and +0.18 points), which is the published sign,
but at a per-trade Sharpe of 0.01 to 0.02 it is about one stock round trip wide and would need
roughly 10,000 trades for a t of 2 (C). In 2,802 both legs rise on discovery (losers +0.52%
gross, winners a further +0.37%), so what the long-short sees is the common announcement drift,
not a reversal. Cost basis caveat: the 3 bp half-spread is the 2024
90th percentile on hedged-hold names; earlier years were wider, which only strengthens the
negative reading.

## 4. Cross-cutting readings

1. **The earnings-option literature has converged on the project's mechanism.** Demand pressure
   from retail (de Silva et al.), inventory risk (So and Wang on stocks; de Silva et al. on
   options) and wide spreads before high-expected-volatility reports (Gao, Xing and Zhang; de
   Silva et al.) are three descriptions of one fact: the premium is a payment to the liquidity
   provider. The project's open liquidity-provider line is the literature's answer, not a gap in
   it.
2. **Option-return papers on earnings are at the mid, and their long-short spreads are a few
   points of option price.** Lyle et al.'s 1.74 points over four days and Adams and Neururer's
   late-reporter premium are smaller than one half-spread on the project's names (4 to 6% of
   premium, `RESEARCH_STATE.md` section 2). They can only work as selectors on a trade the book
   already takes, never as stand-alone trades that pay the touch twice.
3. **Event timing within the session matters for which leg pays.** Pre-open reports crush at the
   open of the report day, post-close at the next open; Lyle et al. find the post-event
   volatility tail lasts longer after pre-open reports. For a book that holds the hedged short to
   the Friday expiry, that tail is paid by the hold. On the project's
   events that tail is not reproduced (trial 2,805: post-event variance amc minus bmo about zero).
4. **New listings change the contract set, not the premium.** Monday and Wednesday expiries
   matter only for a handful of mega-cap events a year; their value to the project is a shorter
   hold (one half-spread, settlement at intrinsic) on events it already trades.

## 5. Ranked ideas not already closed, each with its cheapest test

Idea 1 of the first ranking, pre-open against post-close as an entry selector (Lyle et al.
2018), was run as trial 2,805 and failed on both blocks; it is removed from the list.

1. **Dealer-gamma state from pre-event signed flow against the hold's post-event variance**
   (Ni et al. 2021; de Silva et al. on retail holding for a week after). Cheapest test: net
   customer-signed gamma from `flow/*_pre.parquet` against realised variance of days 1 to 4 on
   the same hedged-hold events, 2023-24 discovery; coordinate with E2, whose flow features
   overlap.
2. **Monday and Wednesday single-stock expiries for 0-1 day holds** (ISE and Cboe filings, V).
   Cheapest test: list 2026 and 2027 reports of qualifying names that fall on Tuesday after the
   close or Monday/Wednesday before the open, and record nearest-expiry quotes on those nights in
   the dry-run book; historical analogue is the existing Thursday-amc to Friday-expiry events
   against 2-4 day tenors on the hedged-hold panel (a contract-choice read, lane B's family).
3. **Notice length of the report date** (Boulland and Dessaint 2017, V2). Cheapest test: check
   whether the project's calendar snapshots record when each date first appeared; if they do,
   score notice length (causal tercile) on residual value. Differs from the closed Johnson and So
   shift test, which used the date's move, not its notice.
4. **Option-expiration week on the paper's own subset** (Stivers and Sun 2013, V2). Cheapest
   test: the S&P 100 names with the highest option-to-stock volume, CRSP closes, 2019-21 as a new
   trial with 2022-24 still unviewed. Low prior: the broad basket failed with the wrong sign
   (2,804), and weekly listings since 2010 dilute the monthly expiry.

Left out: the announcement premium and the So and Wang reversal (failed here), AbnormalIV and
retail proxies (closed via the term gate and 1,769), late reporters and Friday reports (lane5
family), index inclusion (unscheduled; chains not cached), investor days (no free dates;
lane H's product-event analogue failed), guidance (no cached flags), implied correlation in
earnings season (practitioner commentary only, and the index side was closed by lane G).

## 6. What this lane could not verify

- The published Review of Finance version of de Silva et al.: the price basis of their straddle
  returns (midpoint assumed, not confirmed) and whether the slides' numbers changed.
- So and Wang's tables (the MIT PDF fetch returned a firewall page); numbers are from a
  practitioner summary, which also disagrees with an earlier working-paper summary (1.08%, 1990-2009).
- "The Disappearing Earnings Announcement Premium" (authors, sample): the host blocks automated
  clients. Milian (2023) full text: MDPI blocks automated clients.
- The list of the nine qualifying names and the 2026-01-26 launch date (news and broker
  summaries only); whether Cboe's, MIAX's and NYSE's parallel filings took effect.
- Christoffersen et al.'s effect size (abstract and working-paper figures disagree: 3.4% a day
  against 23 bp a day for calls).
- Whether the project's calendar stamps first-seen dates (idea 4) and how many hedged-hold
  events carry a bmo flag (idea 1); neither was opened.
