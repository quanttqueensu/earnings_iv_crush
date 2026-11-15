# N16 country ETF options around foreign political and central-bank events: evidence dossier

## Hypothesis, scope and success criteria

Hypothesis: option sellers on country exposures are paid a scheduled-event premium for foreign
elections and emerging-market central-bank decisions, large enough to survive the touch on the
vehicle Interactive Brokers offers. Scope: Brazil (EWZ, the only country ETF with a free daily
implied-volatility history, Cboe VXEWZ, 2011 to 2026) for Copom decisions and presidential
elections; European national elections and referendums on the Euro Stoxx 50 (STOXX's free VSTOXX
history), as the home-index comparison and the only way to reach a usable N of elections at zero
cost. Success criterion, fixed in `diagnosis.log` before any outcome: event-minus-control short
variance P&L positive with a date-clustered 95% lower bound above zero, and, for EWZ, a mean
above the round-trip cost of a weekly at-the-money straddle at the touch (8.96% of premium).

Result in one line: no event surplus at the mid in either block for any of the four
pre-registered trials (2532 to 2535), so no touch-level pull can rescue it. The median election
is priced richly, as Kelly, Pastor and Veronesi (2016) found; the tail pays it back.

## 1. Prior work

- **Kelly, Pastor and Veronesi (2016, JF 71(5); NBER WP 19812).** Closest paper. 20 countries,
  271 political events (national elections and economic summits), OptionMetrics closing mids, to
  2012. For Brazil, Canada, Mexico, Singapore and South Africa they used exactly this lane's
  vehicle, the US-listed iShares country ETF options (Brazil: EWZ, 2006-05-25 to 2012-01-31,
  elections 2006 and 2010, both rounds). Effect: options whose lives span a political event carry
  IV higher by 1.43% per year (t 4.43), about 5.1% dearer ATM puts; the variance risk premium is
  higher by 0.0107 per year (t 2.61). No transaction costs, no trading strategy, and the VRP
  measure is over the whole option life, not a P&L across the event. Verified in the NBER text.
- **Bialkowski, Gottschalk and Wisniewski (2008, JBF)**: country index variance rises around
  national elections (27 OECD countries). **Goodell and Vahamaa (2013, JBF)**: VIX rises with US
  election uncertainty. Both recalled; the web-search budget was exhausted before they could be
  opened.
- The idea is not crowded as a cost-measured trade: no paper found measures the election premium
  net at the touch. It is crowded as a pricing fact (KPV is widely cited). Copom and other
  emerging-market central-bank decisions have no option-premium literature that this lane found.

How this lane differs from KPV: out of sample (2013 to 2026, after their sample ends); P&L across
the event window against matched non-event windows on the same instrument, rather than an IV
level difference; and the touch of the IB vehicle measured.

## 2. Mechanism and event timing

- Copom statements come in the Brazilian evening after the B3 close (recalled for the hour; the
  BCB page confirms same-day release). For EWZ, which closes at 16:00 ET, that is near or after
  the US close depending on daylight-saving offsets, so the window used spans the close before
  the decision day to the close after it, which contains the release whichever side of the close
  it falls.
- Elections fall on Sundays (UK on Thursdays with an overnight count, the Netherlands on
  Wednesdays with an evening exit poll), so the risk sits in a weekend or overnight gap, as with
  US earnings after the close.
- Who would pay: hedgers of country exposure buying protection into binary political outcomes,
  which is KPV's story. The data say they pay for the median event and are paid back in the
  tail: the measured premium is an insurance premium that covers its own claims.

## 3. Results (real data, gross at the mid)

Measure (all trials): short 30-day variance held across the window, marked from the model-free
index, `PnL = V0*tau - V1*(tau - delta) - RV`, minus the mean of matched controls (same entry
weekday, same session count and calendar span, within 40 sessions, no Copom, FOMC or election
inside). Per event, total variance x1e-4, date-clustered 95% intervals. Discovery 2011 (or 2013)
to 2019; held-out 2020 to 2026-11-12, read once under `freeze_heldout.md` (self-hash and both
scorer hashes recorded). Source files: `result_<trial>_<block>.json`, `trials.csv`.

| Trial | Events | Discovery surplus | Held-out surplus |
|---|---|---|---|
| 2532 | Copom, no FOMC in window (EWZ) | -0.85 [-6.89, +4.87], N=55 | -17.59 [-65.84, +12.36], N=23 |
| 2533 | Copom with FOMC in window (EWZ) | -2.00 [-9.98, +5.83], N=13 | +0.79 [-5.92, +7.63], N=30 |
| 2534 | Brazil presidential rounds (EWZ), descriptive | +51.1 [-31.4, +150.0], N=4 | -57.5 [-218.5, +63.9], N=4 |
| 2535 | European elections and referendums (SX5E) | -0.20 [-11.09, +6.89], N=22 | -0.42 [-4.89, +3.57], N=16 |

As a share of a weekly ATM straddle premium (first-order conversion), the primary trial 2532 is
-3.9% [-15.9, +7.5] on discovery against a break-even of +8.96% per round trip. Per-event Sharpe
of the surplus lies between -0.16 and +0.04 for the three trials with a pass rule. Attrition:
3 of 170 event windows dropped for fewer than three controls; none in the election trials.

What carries it (decomposition). The market does price these events: across Copom windows the
implied variance drop is +6.11 x1e-4 [+2.35, +9.58] (discovery), across European elections
+6.55 [+2.96, +10.39], and across Brazilian rounds +77 to +126. Realised variance matches or
exceeds it: Copom +8.02 [+5.60, +11.13], European elections +6.33 [+1.23, +15.10]. The European
median event is positive (+1.93 discovery); the UK EU referendum alone is -93.8 (Euro Stoxx 50
-11.9% over the window). In Brazil the 2026 runoff was priced at VXEWZ 64.1 and still
under-priced: EWZ fell 22.1% (log, Friday to Monday close), realised 487.8 against an implied
drop of 201.0. The sign of the error is not stable: buying these events does not work either
(Brazil, N=8, mean -3.2 [-96.2, +80.1], exploratory pooled).

Exploratory pooling of both blocks (`pooled_exploratory.log`, not a trial): all elections N=46,
mean -0.80 [-18.59, +14.50], median +1.15 [-0.60, +4.81]; Copom without FOMC N=78, mean -5.79
[-21.48, +4.72].

## 4. The touch (one live snapshot, Cboe delayed quotes, 2026-11-13 about 19:40 UTC)

ATM straddle half-spread as a share of mid (`touch_snapshot.csv`):

| Underlying | 7 days | 14 days | about 35 days |
|---|---|---|---|
| EWZ | 2.1 to 3.1% | 2.6 to 3.0% | 1.0 to 1.4% |
| FXI | 5.9 to 6.5% | 8.3% | 3.2% |
| EEM | 4.1 to 4.6% | 6.1% | 7.5% |
| EWY | 6.1 to 6.6% | 6.0% | 5.1 to 5.3% |
| EWT | 23.2% | n/a | 12.4% |
| EWI | 47.2% | n/a | 49.6% |
| SPY (reference) | 0.26% | 0.24 to 0.27% | 0.21% |

EWG, EWJ, EWP, EWQ, EWU, EWW, EZU, FEZ and INDA were stamped after hours and read 11% to 95%
of mid; indicative only. EWZ is the one country ETF whose options are as cheap to cross as a
single-name earnings straddle (the project's measured cost is 1.79% per side on a different
basis, `docs/RESEARCH_STATE.md`); the rest are wider, and the European and Japanese country ETFs
are not usable vehicles. Commission adds about 1.35% of premium per side on a USD 96 EWZ weekly
straddle at USD 0.65 a contract. The premium is not larger here, so there is nothing for this
cost to eat.

## 5. Tradability at Interactive Brokers

EWZ, FXI, EEM, EWY and the other country ETF options are OPRA-listed US equity options (weekly
expiries on EWZ, FXI, EEM and EWY in the snapshot; monthly only on EWG, EWW, EWT and INDA),
tradeable on an IB paper account, 09:30 to 16:00 ET, Reg-T margin for a short straddle.
Real-time quotes need the OPRA L1 subscription (USD 1.50 a month, project-verified earlier,
`docs/FORWARD_TEST_SPEC.md`); without it IB quotes are about fifteen minutes late. The home-index
vehicles for Europe (Eurex OESX, ODAX) and Japan (OSE Nikkei 225) are offered by IB (recalled);
B3 Ibovespa and NSE Nifty options are not reachable from a non-resident IB account (recalled).
IB's own pricing pages returned HTTP 403 to every fetch, so no IB page was read today.

## 6. Data routes and cost

- Used, free: Cboe VXEWZ, VXFXI, VXEEM, VXEFA daily histories; STOXX VSTOXX and VDAX-NEW; Yahoo
  daily prices; BCB Copom API; Fed FOMC pages; Cboe delayed-quote JSON for the touch.
- Not available free: country ETF option chains. DoltHub's `dolthub/options` carries no country
  ETF (checked on 2022-10-26 and 2024-05-31: SPY and XLF present, EWZ, FXI, EEM, EWW absent).
  No free Nikkei VI history (403).
- Metered route if wanted: Databento OPRA `cbbo-1m` at the 15:59 minute from 2013-04-01. The
  project's last such pull cost USD 20.87 for about 15,500 single-name chains, about USD 0.0013 a
  chain; an EWZ chain is larger (about 2,000 contracts), so assume USD 0.003 to 0.005. Entry and
  exit chains for 8 election rounds and about 108 Copom decisions since 2013-04, with ten controls
  each, is about 2,550 chains: an estimate of USD 8 to 13, to be priced with `get_cost` and capped
  by the team lead. It is not recommended: the gross surplus at the mid is zero, and the touch
  only subtracts.

## 7. Verdict, kill criterion and forward test

Not viable. Kill criterion met: the pre-registered surplus fails in discovery and in the
held-out block for Copom (both splits) and for European elections, and the Brazil election
series, N=8, has no stable sign. The ETF-against-home-index question resolves on cost alone:
outside EWZ (and partly FXI, EEM, EWY) country ETF options are much wider than the home-index
options, but no premium exists to carry to either vehicle.

A forward paper test is not warranted. If the team wanted one anyway, the only defensible form
is a defined-risk one (short weekly EWZ straddle with long wings into Brazilian elections), which
needs wing quotes this lane could not obtain; it would trade twice every four years.

## 8. What could not be verified

The VXEWZ and VSTOXX methodologies (recalled); the exact Copom release hour (design is robust
to it); the European election dates (recalled, not individually re-checked); IB commission,
market-data and product-availability pages (403); whether the Cboe delayed JSON shows NBBO or
Cboe's own book; spreads in 2011 to 2015 (only one 2026 snapshot); and the secondary election
papers (search budget exhausted).

C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N16-country-etf-politics\evidence.md
