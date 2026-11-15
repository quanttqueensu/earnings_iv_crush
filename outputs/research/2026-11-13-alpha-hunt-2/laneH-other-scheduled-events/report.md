# Lane H: scheduled events other than earnings

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `feasibility.log`,
round logs and freeze note. The freeze note re-hashes to its recorded SHA-256 (ee2c167f), was
written (13:39:59 local) before the held-out read (13:40:37), and every earlier scorer filters to
the discovery block.

## Verdict

Neither FDA advisory committee meetings nor mega-cap product events carry a richer option premium,
relative to cost, than ordinary weeks on the same names, where free data can price them. Nothing
survived the held-out read and no book is net positive at the touch. Every result is a descriptive
pilot: the samples are 6 to 19 events per block. The one category where option buyers plainly pay
for a jump, small and mid-cap biotech at advisory committees, has no free option history. Trials
1,991 to 2,017; 2,018 to 2,020 unused. Of the 27, ten (1,991 to 2,000) are logged as invalid or
superseded measurements.

## Data at zero spend

Advisory committee dates come from the Federal Register API (notices appear at least 15 days
ahead, a median of 36 days here) and product-event dates from Wikipedia; both fetched with a
generic client name. Options come from DoltHub, about three snapshots a week, 2019-02 to
2024-11, essentially the S&P 1500 with rotating short expiries. The traded contract is therefore
usually the monthly, 45 to 63 days out, which dilutes a one-day event.

Funnel, advisory committees: 328 notices, 311 with a parseable date, 142 ticker-meetings in
2019-01 to 2024-11, 114 after requiring two days' notice and collapsing multi-day meetings. Of
those, 47 are on symbols DoltHub does not carry (all small and mid biotechs), 25 have no snapshot
in the week before and 6 no shared expiry, leaving 36 priced and 34 without an earnings date in
the window. Product events (Apple events and WWDC, Google I/O, Microsoft Build, Nvidia GTC): 35,
30 with snapshots on both sides, 20 priced.

Attrition: the uncovered advisory-committee events moved 28% on average (median 15%, N=15 with
CRSP closes) against 3.1% for the priced ones. Inside DoltHub the unpriced events moved less than
the priced (1.6% against 3.1%), so the drops do not flatter the seller, but the excluded universe
is where the jump lives.

Controls: windows on the same name 28 and 56 days earlier, priced the same way, with no earnings
or other listed event inside. Discovery 2019-21; held-out 2022-01 to 2024-11.

## Held-out results (frozen, read once)

| Trial | Test | N | Effect | 95% CI | Null pct | Basis | Label |
|---|---|---|---|---|---|---|---|
| 2,016 | Short straddle over advisory committees | 18 | -0.058 | [-0.138, -0.009] | n/a | per trade, share of m0, net at touch | Fail |
| 2,017 | Advisory committee minus controls | 16 | +0.004 | [-0.052, +0.040] | 54 | per trade, share of m0, gross at mid, paired | Fail |
| 2,014 | Long straddle over product events minus controls | 11 | -0.021 | [-0.184, +0.170] | 36 | per trade, share of premium paid, net at touch, paired | Fail; discovery-derived |
| 2,015 | Same, level | 13 | -0.041 | [-0.174, +0.151] | n/a | per trade, share of premium paid, net at touch | Fail |

Trial 2,014 reversed a failed short after discovery showed product events realising about three
times the control move; on discovery it beat controls by +0.070 of premium (null 95.5, N=6) with a
level of -0.036, so it was cost recovery even then. Pooled over both blocks, product events realise
2.3% against 2.5% for controls: the premise did not hold.

Mechanism, pooled: for diversified pharma the traded contract's implied vol barely moves through
the meeting, and the realised-to-implied move ratio is 0.49 for events against 0.55 for controls,
so there is no event premium beyond the ordinary variance premium. Material sponsors lose: the
term structure prices a jump of about 5.3%, the stocks moved 11.2%. The one earnings-like event,
CYTK in December 2022, crushed 137 vol points on a four-day contract and earned +0.23 of m0 at the
mid, but lost 0.19 at the touch to the spread.

## Iteration story

Round 1 was a measurement defect: DoltHub's strike grid moves with each snapshot, so after a large
move the only strike common to entry and exit was far from the money (BIIB aducanumab booked a gain
on a 40% fall with a strike 30% from the forward). Round 2 searched for snapshot pairs with a
common near-the-money strike, which selects against large moves, the same bias as a ledger that
drops events with no exit bid; its numbers favoured the seller and were superseded. Round 3 fixed
the calendar windows in advance and bounded unquoted exits from above, which penalised event
windows more than controls. Round 4 marked unquoted exits on the interpolated exit smile. Every
version failed discovery, and the mechanism was absent rather than mismeasured.

## Use for the project

No transfer of the earnings crush to these events on free data. Testing the biotech advisory
committee tail would need option history for small and mid-cap names, which is a metered pull,
and the jump there is under-priced, which favours a buyer, not the project's seller.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneH-other-scheduled-events\report.md
