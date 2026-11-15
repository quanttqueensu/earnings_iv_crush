# N17 commodity and rates ETF options: evidence dossier

## Hypothesis, scope and success criteria

Hypothesis: options on commodity and rates ETFs (USO, UNG, GLD, SLV, TLT and the agricultural
ETFs) overprice the variance of the scheduled reports that move their underlyings, by enough
that a short straddle sold at the close before the report and bought back at the close after it
clears the round-trip touch. The lane question is the vehicle: whether US equity options on these
ETFs are a cheaper or more accessible way to sell the report premia that lanes N01 to N05 and N12
study in futures options.

Scope: USO with the EIA Weekly Petroleum Status Report (WPSR, Wednesday 10:30 ET); GLD, SLV and
TLT with CPI, payrolls (NFP) and FOMC; UNG, DBA, CORN, WEAT and SOYB on cost only, because no free
implied-volatility history exists for them. All option prices come from free Cboe sources.

Success criterion (pre-registered in `diagnosis.log`): on a held-out block after 2020, the
report-day short straddle shows a surplus over matched non-report days at the mid (S1) and its
report-day P&L at the mid exceeds today's measured round-trip touch plus commission (S2), both
with date-clustered 95% lower bounds above zero.

Outcome: the criterion fails. The one clean held-out test (USO, WPSR) fails both legs, and the
descriptive held-out rows for GLD, SLV and TLT fail S2 everywhere. The touch on GLD options is
cheaper per side than on single-name earnings straddles, but the report premium is close to zero
at the mid, so a cheaper vehicle has nothing to carry.

## 1. Prior work

| Work | Sample and instrument | Effect | Costs measured | Status |
|---|---|---|---|---|
| Nikkinen and Rothovius (2019), Energy 166, 131-141 | OVX (USO options) and VIX around the WPSR, VARX-DCC-GARCH | OVX falls after the WPSR; larger when internet interest in crude is high; no effect size on the abstract page | no | verified (abstract) |
| Ederington and Lee (1996), JFQA | Treasury, Eurodollar and DM futures options | implied vol falls after scheduled releases | no | recalled, cited in NBER w12270 |
| Beber and Brandt (2006), JME; (2009), Review of Finance | Treasury futures option state-price densities | releases reduce implied uncertainty regardless of content; larger drop when ex-ante uncertainty is high, strongest for long bonds | no | verified (abstract pages) |
| Wright (2025), J. Time Series Analysis 46(6) (NBER w28306, 2020) | Wednesday and Friday expiries on Treasury and stock futures, eve-of-expiry implied vol | event-day variance risk premia large and significantly positive, especially FOMC | no | verified (abstract) |
| Energy Economics (2018) on energy volatility indices around scheduled news, with variance-swap implications | OVX and the XLE volatility index | not read (publisher 403; search budget exhausted) | unknown | conjecture on content |

The closest paper to this lane is Nikkinen and Rothovius (2019): it uses exactly the USO-option
index and the WPSR, finds a post-release fall in OVX, and measures neither the premium against
realised variance nor costs. No paper found here prices the event premium in commodity ETF
options net of the touch. The idea is not crowded as a published trade, but within this hunt the
event-premium measurement on these indices is already owned: N04 (OVX with WTI settlements),
N05 (VXTLT with TLT) and N12 (GVZ with GLD, VXSLV with SLV) ran near-identical constructions,
and all three find nothing that survives (section 5).

## 2. Mechanism and event timing

Who would pay: holders of commodity and bond exposure who buy protection into a known release,
and directional option buyers; market makers short gamma across a jump would charge for it. Why
it might not exist here: the reports are small relative to ordinary variance. Measured on
2016-2026 (log_describe.txt), report days carry 0.05 to 0.43 ordinary trading days of extra
realised variance in these ETFs, and the median report-day squared return is 0.44 to 0.80 of the
median control day: the excess is a minority of large moves, not a broad lift. Single-name
earnings, by contrast, carry several to tens of ordinary days (N12's comparison; the project's
crush averages 48.65 vol points).

Timing against the ETF option session (09:30 to 16:00 ET; TLT to 16:15 since 2024-08-12, Cboe
notice C2024080201, verified):

- CPI and payrolls (08:30 ET) land while ETF options are closed, as earnings do; futures options
  trade through them on Globex. An ETF seller cannot exit before the open.
- WPSR (Wednesday 10:30 ET), EIA natural gas storage (Thursday 10:30 ET), FOMC (14:00 ET) and
  WASDE (12:00 ET) land mid-session.
- The API survey (Tuesday 16:30 ET) lands after the ETF option close, so the Tuesday-close to
  Wednesday-close window carries both API and WPSR.

## 3. Tradability at Interactive Brokers

- Products (verified from the 2026-11-13 Cboe chain snapshot): GLD lists Monday to Friday
  expiries (an expiry on every report day); SLV, TLT and GDX list Monday, Wednesday and Friday;
  USO and UNG list Wednesday and Friday, so a USO Wednesday expiry spans exactly one WPSR; DBA,
  CORN, WEAT and SOYB list monthlies only. American exercise, physical delivery of 100 ETF shares.
  TLT pays a monthly dividend, so short in-the-money calls carry early-exercise risk around the
  ex-date; GLD, SLV, USO and UNG pay none.
- Paper account: the project's paper book already trades US equity options at IB, so the route
  exists with no harness change beyond the event calendar (verified by the project's operation).
- Market data: OPRA top of book, USD 1.50 a month on the linked live account; without it quotes
  are about 15 minutes late (project `docs/DATA.md`, verified as project documentation).
- Commission: USD 0.65 per contract, IBKR Pro fixed (recalled; IB's page returns 403 to
  automated reads; the project config uses the same figure). That is USD 2.60 per straddle round
  trip: about 0.3% of a 7-day GLD straddle, 1.3% for SLV, 2.7% for TLT and 3.8% for UNG.
- Margin: Reg-T on a naked short straddle is premium plus about 20% of underlying less any
  out-of-the-money amount, on the riskier leg (recalled from IB's US options margin page, 403 to
  automated reads). On a 7-day GLD straddle that is roughly USD 7,000 to 8,000 of margin against
  about USD 900 of premium (conjecture arithmetic), so return on margin is about a tenth of
  return on premium. Portfolio margin needs USD 110,000 equity (recalled).

## 4. The vehicle: touch as a share of premium

Round trip (call spread plus put spread at the nearest-to-spot strike, as a share of the straddle
mid) plus commission, from Cboe delayed quotes on 2026-11-13 at 14:33 ET (USO, UNG, GLD, SLV,
TLT, DBA, GDX, IAU, XLE, SPY) and about 14:55 ET (the rest). One afternoon, so a level, not a
history. The table shows the 14:33 values; `vehicle_cost_summary.csv` and `spread_table.csv`
also pool the 14:57 snapshot of the core ETFs (section 5).

| ETF | 7-day round trip incl. commission | 30-day | Note |
|---|---|---|---|
| SPY (reference) | 0.73% | 0.51% | |
| GLD | 2.88% | 2.82% | cheapest commodity vehicle |
| USO | 5.51% | 7.53% | |
| SLV | 6.52% | 3.47% | |
| TLT | 10.34% | 4.50% | 7-day straddle is about USD 0.97, so commission bites |
| XLE | 11.61% | 4.65% | |
| IEF | 13.87% | 7.03% | |
| UNG | 15.01% | 13.28% | |
| BOIL, KOLD, TMF, TBT | 18% to 43% | 17% to 41% | leveraged |
| CORN, WEAT, DBA, DBC, SOYB | 54% or more, or no two-sided ATM quote | 70% to 84% | not tradeable |

Per side this is about 1.4% of premium for GLD and 2.8% for USO at 7 days, against one
half-spread of about 4 to 6% of premium on single-name earnings straddles (closed hedged-hold
study, `docs/RESEARCH_STATE.md`). So the vehicle is cheaper than the project's equity book for
GLD and USO. What it lacks is the premium.

## 5. Pilot (zero cost, ceiling test at the mid)

Data: Cboe daily closes of OVX, GVZ, VXSLV and VXTLT (30-day model-free implied vol of the ETF
options, computed from mids) and Cboe daily ETF closes. Statistic: the one-day P&L of a short
30-day variance swap from the close before the report to the report-day close, expressed as a
share of an ATM straddle premium at 30 days and, rescaled, at 7 days. Event minus matched
controls (same weekday, non-report days; Tuesday and Thursday for the WPSR). These are
index-based marks at the mid, not tradeable levels; S2 subtracts the frozen touch above. Full
definitions in `diagnosis.log`; scorer `event_scorer.py`; freeze `freeze_n17.md` (SHA-256 of the
note and scorer in `diagnosis.log`); 26 trials, 2,562 to 2,587, in `trials.csv`.

Held-out, 2021-01-01 to 2026-10-30, per trade, share of straddle premium, date-clustered 95%:

| Family | Tenor | N | Event at mid | Surplus over controls | Net of touch | Status |
|---|---|---|---|---|---|---|
| USO, WPSR | 30d | 187 | -0.63% [-1.65, +0.30] | -0.80% [-1.86, +0.14] | -8.16% [-9.18, -7.23] | clean test, fails |
| USO, WPSR | 7d | 187 | -2.70% [-7.06, +1.27] | -3.41% [-7.96, +0.60] | -8.21% [-12.57, -4.24] | clean test, fails |
| GLD, CPI/NFP/FOMC | 7d | 179 | -0.92% [-6.13, +3.80] | -2.07% [-7.55, +3.11] | -3.80% [-9.01, +0.92] | viewed block |
| SLV, CPI/NFP/FOMC | 7d | 79 | +1.60% [-4.52, +7.32] | +0.90% [-5.70, +7.22] | -4.92% [-11.04, +0.81] | viewed block |
| TLT, CPI/NFP/FOMC | 7d | 172 | +2.88% [-2.02, +7.55] | +1.21% [-3.95, +6.04] | -7.46% [-12.36, -2.79] | viewed block |
| TLT, FOMC | 7d | 43 | +0.41% [-8.84, +8.28] | -1.96% [-11.59, +6.84] | -9.93% [-19.18, -2.06] | viewed block |

Cost sensitivity: a second snapshot at 14:57 ET gives 7-day round trips of USO 5.30%, GLD
2.92%, SLV 4.71% and TLT 6.41%; net under it is USO -8.00% [-12.36, -4.03], GLD -3.84%
[-9.05, +0.88], SLV -3.11% [-9.23, +2.61], TLT -3.53% [-8.43, +1.14]. No verdict changes. The
near-close spread (into 15:59) was not measured.

"Viewed block": lanes N05 and N12 read this block with near-identical constructions, and their
results were read here before the freeze, so these rows are descriptive replications. The 30-day
rows for GLD, SLV and TLT are in `trials.csv` and fail S2 by 3 to 4 points. Discovery (to 2020)
showed one surplus, TLT FOMC (7d surplus +12.88% [+5.25, +20.45], N=29); it did not carry
forward, matching N05 (held-out FOMC +0.0019 [-0.0248, +0.0255] of 30-day premium, 97.5%).

The WPSR result has a specific shape: OVX does not fall on report Wednesdays relative to Tuesdays
and Thursdays (implied excess -0.02 ordinary days on discovery, -0.30 on held-out), while
realised Wednesday variance is higher (+0.20 and +0.05 days). The USO-option market does not
price the WPSR as a lump at all. N04, on WTI settlements, finds the same sign (implied excess
below realised excess, N=302 weeks, 2009-2019), and reports by message that its held-out reads
on 2021-24 C1 settlements (N=98) and 2021-26 Cushing spot (N=178) are null as well (not checked
against N04's files here).

Attrition: report Wednesdays drop for federal-holiday weeks (EIA moves the release) and for
coinciding CPI, NFP or FOMC days; TLT drops first-of-month sessions (ex-dividend proxy, closes are
not dividend-adjusted); SLV loses dates in the VXSLV publication gap (2022-03 to 2025-05, per
N12). All drops are fixed by the calendar or by data availability before outcomes, not by
outcome.

Limitations, stated plainly. (1) The marks are index-level, from mids, and the straddle
translation is a delta-hedged approximation; the true touch history is not in hand. (2) The cost
is one afternoon's spreads applied to six years. (3) The 7-day rescaling uses a discovery-fixed
lump estimate. (4) Close-to-close holds a full session after the 08:30 releases; the earnings
template (sell at 15:59, buy at 10:00) cannot be built from daily index closes. None of these
biases would turn a near-zero mid surplus into one that clears a 3 to 10% round trip.

Process failure, disclosed: the first price download used a Yahoo endpoint whose robots.txt
disallows all agents. The files were deleted and replaced by Cboe's public historical closes
before the freeze; discovery was re-run on the new source (`diagnosis.log`).

## 6. Data route and cost

- Free and in hand: Cboe volatility index closes (mid-level ceiling only), Cboe ETF closes,
  one day of Cboe delayed chains. Cboe's terms allow one personal copy; a standing quote
  collector would need Cboe's consent (N19).
- No project cache holds options on these ETFs; the free DoltHub `option_chain` table carries SPY
  and XLE but none of USO, UNG, GLD, SLV, TLT, DBA (`probe_dolthub.py`, four dates).
- Paid, priced by N19 from the project's own Databento ledger (`N19-data-access/evidence.md`,
  `cost_model.log`): OPRA `cbbo-1m` snapshots at 15:59 and 10:00 ET for USO, UNG, GLD, SLV and TLT
  on every session 2016-2026, 27,240 requests, USD 19.03 to 26.64. Cboe DataShop Option EOD
  Summary (NBBO at 15:45 and the close, from 2012) quotes its price only in a basket builder.

## 7. Verdict

Not viable. The kill criterion fires: the only clean held-out family (USO, WPSR) fails at the
mid and net of the touch at both tenors, and no GLD, SLV or TLT macro family clears its touch on
any block. The vehicle answer is useful on its own: GLD and USO options are cheaper to cross than
single-name earnings options, and everything agricultural or leveraged is untradeable at 18% to
over 80% of premium round trip.

A metered OPRA pull (USD 19 to 27) is not recommended for this hypothesis: the mid-level ceiling
is already near zero, and a touch history can only lower it. The one question it could still
answer is whether a GLD or TLT event-day expiry, sold at 15:59 before an 08:30 release and bought
at 10:00, behaves differently from the close-to-close translation here; that is worth buying only
if lane N08 finds a net-of-touch surplus in the same template on SPY, whose touch history the
project already holds.

Forward paper test: none proposed. A kill-or-continue forward check would cost nothing but
would need a mid-level surplus to exist first.
