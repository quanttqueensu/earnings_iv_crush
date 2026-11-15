# N09 VIX complex: evidence dossier

## Question, scope and pass rule

Can a trader at Interactive Brokers harvest a scheduled-event volatility premium in the VIX
complex (VX futures, VIX options) around FOMC statements, CPI and payrolls, or at the monthly VIX
settlement (the special opening quotation, SOQ), net of the touch? The rules, cost model, splits
and pass rule were written in `diagnosis.log` before any outcome was computed. In short, a
configuration passes if its mean net return per trade at the touch has a date-clustered 95% lower
bound above zero, and so does its surplus over matched controls (non-event days with the same
weekday, within 35 days). Discovery runs 2008-2016 for FOMC and the SOQ, and 2016-2020 for CPI and
NFP. The held-out blocks are 2017 to 2026-11-12 and 2021 to 2026-11-12, and each was read once,
after `freeze_heldout.md`.

All figures are real data (free Cboe and CFE files). Trial numbers are 2,322 to 2,332 from the
lane block. Every scored configuration is listed in `trials.csv`.

## Prior work: this trade is published and has been for a decade

- **Closest paper:** Fernandez-Perez, Frijns and Tourani-Rad, "When no news is good news", *Journal
  of Empirical Finance* 41 (2017) 187-199 (full text read from the AUT repository). It uses
  Thomson Reuters tick data for 2004-2013, about 80 FOMC days. Shorting the front VX at the bid at
  09:35 and buying it back at the ask at 15:30 on FOMC days, less a further 0.10% per trade, earns
  125 bp per FOMC day (114 bp from 2008 on), with a daily Sharpe of 0.37. Non-announcement days
  lose money. The paper measured costs at the touch. Verified.
- Krieger, Mauck and Chen (2012, *Financial Markets and Portfolio Management* 26(3)): VIX falls on
  FOMC days, and short-VIX derivative positions earn significant returns after bid-ask spreads.
  Verified from the abstract only.
- Krieger, Mauck and Vazquez (2014, MPRA 52959): VIX changes by -0.70 points (-2.78%) on FOMC days
  over 1999-2012. Verified. The same finding runs back through Nikkinen and Sahlstrom (2004), Chen
  and Clements (2007) and Vahamaa and Aijo (2011), and the theory is Ederington and Lee (1996).
  These are recalled through the papers that cite them.
- Wright (2020, NBER w28306): one-day options carry a positive variance risk premium on the eve of
  FOMC and payrolls. This is the SPX and Treasury side of the question, which belongs to N05, N08
  and laneG. Verified from the abstract.
- The idea is crowded. The FOMC VIX decline has been in the literature since 2004 and the VX trade
  has been published since 2012 and 2017. I found no paper on SOQ settlement bias as a return
  (Griffin and Shams 2018 study manipulation, not returns; recalled), and none on VIX-option event
  premia.

## Mechanism, and why VX is a structurally poor event vehicle

VIX is a 30-day SPX variance swap rate. One FOMC day is about 1 of 21 sessions in that window, so
removing its extra variance moves VIX by a few per cent, not by the tens of per cent seen in
single-name earnings crush. The VX future is worse placed still. The front contract's underlying
is the VIX at its own expiry, and that VIX covers the 30 days after expiry. Today's FOMC is
therefore never inside the front future's variance window. A move in VX on an FOMC day is a
revision of expected future volatility (the uncertainty-resolution story), not a mechanical crush.
A contract whose window does contain a coming FOMC settles at an SOQ struck before that meeting,
so the holder never collects the crush. This follows from the contract definitions and is labelled
conjecture as a statement about prices. The data agree with it: after 2017 the event shows up in
VIX1D (one-day) and VIX9D, not in VIX or VX (see below).

Timing: the FOMC statement comes at 14:00 ET and the VX daily settlement at 15:00 Chicago (16:00
ET), so the settle-to-settle window brackets the statement. CPI and NFP come at 08:30 ET, inside
VX's overnight session, which runs from 17:00 CT the previous day.

## Pilot results (per trade, returns on the futures price at the entry settle, 95% date-clustered)

| Trial | Configuration | Block | N | Net at touch | Surplus vs controls | Verdict |
|---|---|---|---|---|---|---|
| 2322 | FOMC, short F1, settle D-1 to D | disc 2008-16 | 72 | +1.01% [-0.25, +2.23] | +1.30% [+0.02, +2.54] | fails (a) |
| 2323 | FOMC, short F2 | disc | 72 | +0.78% [-0.14, +1.68] | +1.04% [+0.11, +1.98] | fails (a) |
| 2329 | FOMC, entry D-2 | disc | 72 | +1.35% [-0.20, +2.79] | +0.94% [-0.65, +2.46] | fails |
| 2330 | FOMC, F1 sized 1/trailing SD | disc | 72 | +0.294 SD [+0.025, +0.557] | +0.311 SD [+0.054, +0.565] | passes |
| 2331 | FOMC, only when VIX9D/VIX is rich | disc (2012-16) | 34 | +0.15% [-1.72, +1.91] | +0.47% [-1.52, +2.33] | fails |
| 2324 | CPI, short F1 | disc 2016-20 | 58 | +0.67% [-0.69, +1.96] | +0.80% [-0.60, +2.17] | fails |
| 2325 | NFP, short F1 | disc 2016-20 | 60 | +0.87% [-0.49, +2.13] | +0.93% [-0.50, +2.27] | fails |
| 2332 | Pooled FOMC+CPI+NFP | disc 2016-20 | 157 | +0.65% [-0.12, +1.42] | +0.72% [-0.07, +1.50] | fails |
| 2326 | Expiring VX, prior settle to SOQ | disc 2008-16 | 108 | gross -0.18% [-1.15, +0.83] | n/a | fails both sides |
| **2330** | **held-out read** | **2017-26** | **78** | **-0.028 SD [-0.339, +0.244]** | **-0.080 SD [-0.397, +0.209]** | **fails, closed** |
| 2322 | held-out, declared secondary | 2017-26 | 78 | +0.16% [-1.01, +1.28] | -0.13% [-1.36, +1.06] | exploratory |

Sources: `logs/discovery_round1.json`, `logs/discovery_round2.json`, `logs/heldout.json`. The basis
is net at the touch with 0.055 VIX points round trip (a one-tick market crossed on both sides plus
fees). T2330 is in units of the trailing 20-session daily standard deviation of front-month
returns (median 4.4%). Per-trade Sharpe for T2330 was +0.26 [+0.02, +0.52] on discovery and -0.02
[-0.21, +0.25] held-out.

Reading:
- On 2008-16 the published FOMC effect is visible gross and against controls, but net at the touch
  it sits just inside zero. Only the risk-scaled variant passed, and it was the fifth FOMC
  configuration tried, at the stress cost its interval spans zero, and without 2008-09 it falls to
  +0.17 SD [-0.14, +0.46]. All three caveats were recorded before the held-out read.
- On the held-out block, which is entirely after the publication sample, the effect is gone.
  Post-publication decay was already visible in discovery: the 2013-16 annual means were
  +0.6%, +0.1%, -1.9% and +0.9% against about +2.5% in 2008-09.
- **Comparison asymmetry, which matters here.** Over 2017-26, unconditional short-F1 settle
  returns average +0.18% a day, but Wednesdays average +0.58% and Thursdays -0.39%
  (`logs/exploratory_unconditional_carry.log`; exploratory). Most FOMC days are Wednesdays. Against
  all days, the held-out FOMC trade (+0.47% gross) would look like a +0.29% event surplus. Against
  same-weekday controls it is -0.13%. The weekday-matched control is the right comparison. The
  Wednesday effect itself was found by looking at the data, and it is not a finding.
- SOQ: no settlement bias. The expiring contract's last settle predicts the SOQ without bias in
  either direction, and the last trade on the expiry morning sits -0.26% [-1.69, +1.15] from the
  SOQ (N=27, diagnostic).

## Where the event premium went (SPX-VIX relationship; exploratory, read after the held-out)

These are log changes in index closes on event days minus matched controls, at the mid, not
tradeable (`logs/exploratory_postread_indices.json`):

| Index | FOMC 2017-26 | CPI 2021-26 | NFP 2021-26 |
|---|---|---|---|
| VIX (30-day) | +0.8% [-1.5, +3.3], N=78 | -2.0% [-3.9, +0.1], N=69 | +1.0% [-1.4, +3.6], N=66 |
| VIX9D | +0.8% [-2.9, +5.0] | -5.4% [-8.5, -2.1] | +0.2% [-3.4, +4.3] |
| VIX1D | -12.0% [-22.4, -0.6], N=36 | -29.0% [-36.0, -22.0], N=52 | -10.7% [-17.5, -3.1], N=50 |

On 2008-16 VIX fell 3.2% more on FOMC days than on controls [-5.1, -1.3]. Since 2017 the 30-day
index no longer moves, while one-day implied volatility collapses after every release, CPI most of
all. The event premium now lives in 0DTE and 1DTE SPX options, not in the VIX complex. A VIX1D drop
measures the event leaving the window, not mispricing. Whether one-day SPX options overprice the
event is Wright's question, and it belongs to the SPX lanes (N08, laneG).

## VIX options: half-spread against the premium

From one public Cboe delayed snapshot (2026-11-13, about 14:38 ET, VIX 19.11, VIX-option 30-day
implied volatility 90.3; `logs/vix_option_spreads.json`): the Dec-16 at-the-money straddle has a
mid of 4.925, a half-spread of 0.085 (1.7% of premium) and vega of 0.046 per vol point. Near-money
half-spreads run 1.3-3% on the monthly expiries and 6-8% on thin weeklies. On 2008-16, VVIX fell
1.9% more on FOMC days than on controls [-3.3, -0.5], which is about 1.7 vol points, or 0.078 on
that straddle (1.6% of premium). That is less than the 3.4% round-trip half-spread, so the trade
loses at the touch even in the period when the effect existed. On 2017-26 the VVIX surplus is
-0.2% [-1.7, +1.4], N=78, so there is nothing left to harvest. These are one snapshot set against
an index figure, so the comparison is exploratory.

For VX the spread is small relative to the move. A one-tick round trip is 15% of the mean gross
FOMC-day move on 2008-16 (0.055 against 0.363 points) and 40% on 2017-26 (against 0.138). Cost is
not why VX fails. It fails because the event surplus over ordinary days is zero after 2017.

## Tradability at IB (largely unverified: IB pages return 403 to this client)

- VX monthly and weekly futures and VXM minis trade on CFE, almost 24 hours. VIX options trade on
  Cboe (monthly, and weeklies tagged VIXW), are cash settled at the SOQ, and have a 100 multiplier.
  That IB offers these on paper accounts is recalled, not verified.
- Market data: VIX options are covered by OPRA top of book (USD 1.50 a month on the linked live
  account, per the project's `docs/DATA.md`). VX needs a separate CFE subscription, whose fee is
  recalled, not verified. Without it, quotes are about 15 minutes late and fills are not evidence.
- Commissions, exchange fees and SPAN margin for VX: not verified. The cost model assumes about $5
  of fees per round trip, and a one-tick spread is the dominant cost.

## Data route and cost

- Free and used here: the CFE VX daily files 2004-2026 (open, high, low, close, settle, volume,
  open interest), Cboe index histories (VIX, VIX9D, VIX3M, VIX1D, VVIX, VRO), Fed FOMC pages, and
  one Cboe delayed option snapshot. All of this lives in `raw/` (7.9 MB). Rebuild with
  `scripts/fetch_cboe.py`, then `scripts/build_panel.py`.
- Not free: intraday VX quotes (Cboe DataShop; not priced, because no search budget was left and IB
  and vendor pages were blocked) and a VIX option quote history. VIX options are on OPRA, so the
  project's existing Databento OPRA licence could pull them. I do not recommend pricing either
  pull: the held-out read shows no event surplus to measure.
- The settle is a 15:00 CT VWAP or mid (CFE Rule 1202(p)), so every net figure above adds an
  assumed touch. The one-tick front-month width is recalled and was not measured. VX also lists
  trade-at-settlement, which would make the settle itself the fill. That is noted, not assumed.

## Verdict

Not viable. The published FOMC short-VX effect does not survive out of sample. The one variant
that passed discovery fails on 2017-26 with a point estimate below zero. CPI, NFP and the SOQ fail
discovery. The VIX-option version loses to the spread even in-sample. Kill criterion: the frozen
held-out read failed both legs of the pass rule. Reopen only with a new mechanism, for example a
VX or VIX-option trade whose underlying window actually contains the event and which is held
through the event's exit from that window. The forward test that would settle it is to paper-trade
T2330's rule on real-time CFE data for the next 16 FOMC meetings (two years), against same-weekday
controls. I do not recommend it, because the expected surplus is zero.
