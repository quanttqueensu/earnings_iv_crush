# Option-implied forward premium and the earnings-window stock return

## Hypothesis, scope and success criteria

Informed demand for calls (puts) before an announcement lifts (lowers) the option-implied forward
relative to the cash-and-carry forward, so a high forward premium should predict a higher
market-adjusted return over the announcement window (Cremers and Weinbaum, JFQA 2010; Atilgan,
JBF 2014, who finds the effect concentrated around earnings; Ofek, Richardson and Whitelaw, JFE
2004, for the short-sale-constraint reading with the same sign).

Signal: fp = log(F_parity / F_cc), with F_parity the mean of K + (C - P) e^(rt) over the three
strikes nearest the money on the front expiry spanning the event (15:59 ET consolidated quotes,
entry session), and F_cc = (S - PV(dividends to expiry)) e^(rt) with S the 15:59 IEX one-minute bar
(Alpaca free feed) and r the 3-month bill (FRED DTB3). Outcome: stock return from S to the close two
sessions later, minus SPY built the same way, per event. Block: the 2025-2026 S&P 500 earnings
events (`events_broad_oos_2025.parquet`), one block, scored once.

Pre-registration `_private/parity_spread_prereg.md` (SHA-256 0657a745...) and amendment 01
(SHA-256 17a3fe0b..., outcome built on a consistent price basis), both frozen before any signal or
outcome was computed. Pass required Spearman of decile means at or above +0.60, the decile 10 minus
decile 1 gap net of 0.20 points with a date-clustered 95% interval above zero, and the gross gap at
or above the 95th percentile of a within-month permutation null.

## Funnel

| Step | Events |
|---|---|
| Event file | 2,037 |
| Exact duplicate rows | -2 |
| No chain / empty chain | -32 / -2 |
| Fewer than three strikes with both legs usable | -276 |
| Parity inputs formed | 1,725 |
| EDGAR release before the 15:59 snapshot | removed as in P1 |
| No 15:59 IEX bar, price-basis mismatch above 10%, or no outcome | removed |
| **Scored** | **1,654** (251 entry dates) |

The signal is well behaved: median fp +4.9 bp, interquartile range -6.1 to +16.6 bp, consistent
with the early-exercise value of American puts and small borrow costs.

## Results

Per event, market-adjusted, [0, +2] sessions from the 15:59 price, decimal (0.01 = one point).

| Decile | N | Mean fp (bp) | Mean return | SD |
|---|---|---|---|---|
| 1 (calls cheapest) | 171 | -28.1 | +0.0007 | 0.080 |
| 2 | 165 | -12.0 | -0.0171 | 0.080 |
| 3 | 164 | -6.2 | -0.0172 | 0.053 |
| 4 | 166 | -1.5 | +0.0009 | 0.067 |
| 5 | 163 | +3.0 | +0.0021 | 0.081 |
| 6 | 169 | +7.1 | -0.0064 | 0.072 |
| 7 | 166 | +11.5 | +0.0012 | 0.074 |
| 8 | 164 | +17.0 | -0.0032 | 0.070 |
| 9 | 165 | +24.5 | +0.0030 | 0.080 |
| 10 (calls richest) | 161 | +41.7 | +0.0007 | 0.075 |

**Primary statistic.** Decile 10 minus decile 1: -0.0001 gross, date-clustered 95% CI
[-0.0172, +0.0172]; net -0.0021, CI [-0.0192, +0.0152]. Spearman +0.358. Permutation null: the
observed gap sits at the 50th percentile (null 95th percentile +0.0132). Long-short per-event series
net of costs: per-trade Sharpe -0.014, N=332, deflated Sharpe 0.40 against 1,503 trials.

**Secondary, descriptive only.** Pooled deciles, the [0, +1] window, the dividend-free signal, and
the BMO and AMC subsets all have intervals spanning zero (BMO: +0.0125 [-0.0077, +0.0334], N=962;
AMC: +0.0019 [-0.0292, +0.0334], N=660). The placebo window ending at the 15:59 price shows no
relation (+0.0037 [-0.0049, +0.0122]).

## Verdict

**FAIL** on every criterion. The forward premium, measured directly from the 15:59 chain against a
same-minute stock price, does not predict the earnings-window return on this block. Together with P1
(put skew, failed on the same block), the two classic option-to-stock information channels show
nothing in liquid S&P 500 names around 2025-2026 announcements.

## First objections

**Power.** The interval is about plus or minus 1.7 points per event, so an effect below about 1.5
points is not excluded. The published effects are of that order or smaller in large caps, so the
block cannot rule them out; it rules out an effect large enough to trade on its own after costs.
**Price basis.** The IEX bar is a subset of consolidated trading; its last print can sit a few cents
from the consolidated 15:59 price, which adds noise to both signal and outcome but no bias in sign.
**Dividends.** Dividends are taken from realised ex-dates up to expiry, which are announced in
advance for these names; the dividend-free variant gives the same answer.
**Crowding.** The effect has been published since 2010, so decay in large caps is the expected
outcome.

## Reproduction

```
python scripts/research_parity_spread.py --signal --prices --score
```
