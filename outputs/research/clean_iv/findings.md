# Event-cleaned implied volatility: construction, convergence, drivers, and the calendar

Three questions raised by the event-cleaning method (strip the announcement jump out of
front-month variance, treat the remainder as the level post-event IV converges to). None of
the work below sorts events on a candidate selector, so the section 2.1 candidates remain
unfitted. Scripts: `scripts/research_clean_iv.py` (sections 1 to 3, megacap panel),
`scripts/research_calendar_cost.py` (section 4, 2025-26 broad block, spreads and entry
prices only).

## 1. The panel's event variance assumes an event-free back month

`reverse_alpha_panel.add_derived` sets `event_var = (f^2 - b^2) t_f`. The back expiry is the
first listed at least 21 days beyond the front (`features.nearest_expiries`), so it always
lies after the announcement and carries the same jump. With a flat diffusive variance across
both expiries the consistent estimator is

    E = (f^2 - b^2) t_f t_b / (t_b - t_f)

so the stored figure is low by `t_b / (t_b - t_f)`: median 1.381, p10 1.143, p90 1.429 in
variance units, taking `t_b = t_f + 21/365`.

The defect does not change any tested result. Rebuilt with the corrected numerator,
`jump_richness` ranks at Spearman 0.990 (2019-2024) and 0.970 (2013-2018) against the stored
version, top-quintile Jaccard 0.856 and 0.789. The out-of-sample failure of `rich_rank`
(per-trade Sharpe -0.1843, CI [-0.3255, -0.0326], N=157) stands.

Two further variants were built at entry only, to inform the section 2.1 decision:

| variant | Spearman vs `jump_richness` (disc / hold) | top-quintile Jaccard | Spearman vs `term_rank` (disc / hold) |
|---|---|---|---|
| corrected, mean-abs denominator | 0.990 / 0.970 | 0.856 / 0.789 | 0.358 / 0.163 |
| corrected, RMS denominator | 0.744 / 0.933 | 0.413 / 0.731 | 0.391 / 0.140 |
| corrected, RMS shrunk to cross-section (k=4) | 0.743 / 0.643 | 0.399 / 0.382 | 0.518 / 0.502 |

Shrinkage changes membership materially, but it does so by moving toward `term_rank`: as
the denominator pulls toward a common cross-sectional value the ratio becomes the priced
jump alone, which is what the term gate already selected.

## 2. Post-event IV does not settle at the cleaned level

Target: IV of the sold contract at the exit close. That is post-event ATM IV only when the
stock finishes near the strike; after a gap the strike sits in the wing days from expiry,
and the smile dominates (median log exit-over-front IV rises from -0.21 to +0.50 across
exit-moneyness bins). The measurable sample restricts to `|log(S_exit/K)| <= 1%`, which
conditions on the realised move and is not a tradeable subset.

Discovery block, 2019-2024, N=137 events on 125 dates, date-clustered 95% CIs (5,000
draws):

| forecast of exit ATM IV | mean log error | CI | MZ slope | MZ R^2 |
|---|---|---|---|---|
| front IV unchanged | -0.211 | [-0.268, -0.154] | 0.975 | 0.569 |
| back IV | +0.180 | [+0.122, +0.240] | 1.105 | 0.531 |
| two-expiry diffusive baseline | +0.409 | [+0.343, +0.478] | 0.904 | 0.390 |
| history-cleaned (method as practised) | +0.158 | [+0.077, +0.251] | 0.496 | 0.286 |
| trailing 20-day realised | +0.473 | [+0.402, +0.544] | 0.691 | 0.441 |

Every cleaned baseline sits below where IV actually lands one session after the print, by
17% (history-cleaned) to 51% (two-expiry) in level terms, and the history-cleaned forecast,
though closest on average, carries the least information (slope 0.50). The restriction to
small moves is the sample where residual uncertainty should be lowest, so the shortfall on
the full population is unlikely to be smaller. Treating cleaned IV as the convergence level
overstates the crush, which is the residual-value drag already visible in the reverse-alpha
decomposition (-0.0401 of margin per event). Why the short-dated post-event level stays
elevated (post-announcement realised volatility, short-tenor term structure, or quote-width
inflation of near-expiry mid IVs) is not separated here.

## 3. The event move carries the P&L; the residual-value term is not clean of it

Return on margin rebuilt exactly (max reconciliation error below 1e-6) as premium + gap +
residual value + cost, and regressed on standardised event surprise (realised over implied
move) and diffusive surprise (log exit IV over two-expiry baseline). Discovery block,
N=832.

| target | event surprise beta/sd [CI] | diffusive surprise beta/sd [CI] | R^2 event alone | R^2 joint |
|---|---|---|---|---|
| return on margin | -0.1109 [-0.1191, -0.1022] | +0.0085 [+0.0036, +0.0135] | 0.827 | 0.831 |
| gap | -0.1236 [-0.1325, -0.1137] | -0.0100 [-0.0157, -0.0046] | 0.795 | 0.798 |
| residual value | +0.0203 [+0.0159, +0.0253] | +0.0064 [+0.0025, +0.0101] | 0.377 | 0.394 |

The event move explains 83% of per-trade P&L variance; diffusive repricing adds 0.35
percentage points. The residual-value term rises with the event surprise (Spearman +0.81)
for a mechanical reason: a contract pushed deep into the money keeps little time value. A
selector scored on raw residual value is therefore partly rewarded for choosing events that
gap, the opposite of what a seller wants. The section 2.1 outcome variable needs the
moneyness effect removed before it can identify mispricing.

## 4. The calendar hedges the minor driver at 1.7x the cost per unit of premium

2025-26 broad block, 15:59 ET quoted touch, same strike, back expiry by the feature rule.
949 of 1,221 events measured: 223 lack a quoted back straddle at the strike on entry and 39
on exit, so the measured set tilts toward more liquid names.

| | median | IQR |
|---|---|---|
| hedge ratio (back straddles per front, neutral to a parallel diffusive shift) | 0.237 | 0.160 to 0.483 |
| event premium retained, hedged calendar | 0.869 | 0.665 to 0.902 |
| event premium retained, 1:1 calendar | 0.375 | 0.302 to 0.457 |
| round trip, % of front premium: naked | 14.1% | 7.9% to 22.3% |
| round trip, % of front premium: hedged calendar | 20.7% | 11.8% to 31.7% |
| cost per unit of event premium: naked | 0.310 | 0.147 to 0.555 |
| cost per unit of event premium: hedged calendar | 0.540 | 0.225 to 1.237 |
| cost per unit of event premium: 1:1 calendar | 1.901 | 0.970 to 3.908 |

Quoted touch overstates effective cost (the megacap book measured 1.7871% per side), but
the overstatement applies to every leg, so the ratios hold. The hedged calendar keeps most
of the event premium but pays 1.74 times as much to harvest each unit of it, and what it
buys is protection against diffusive repricing, which section 3 shows is about 0.4% of P&L
variance. It does not hedge the gap, because the back leg's gamma is a fraction of the
front's. This agrees with the earlier P&L comparison on the 158-trade execution sample
(`exec_vehicle_compare.csv`): per-trade Sharpe +0.0043 for the straddle, -0.1524 for the
vega-balanced calendar, -0.5686 for 1:1. The calendar was already closed there; this section
adds the cost-per-unit-of-premium reason.

## Artefacts

| File | Content |
|---|---|
| `richness_construction.csv` | rank agreement of corrected and shrunk ratios with the tested one |
| `convergence.csv` | five forecasts of exit IV, all events and near-ATM |
| `drivers.csv` | component regressions on event and diffusive surprise |
| `panel_clean_iv.parquet` | panel with every construction attached |
| `../calendar_cost/calendar_cost_events.csv` | per-event calendar measurement |
| `../calendar_cost/calendar_cost_summary.csv` | distribution of every ratio |

## References

Dubinsky, A. and Johannes, M. (2006). Fundamental Uncertainty, Earnings Announcements and
Equity Options. Working paper, Columbia University.

Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option Pricing of Earnings
Announcement Risks. *Review of Financial Studies* 32(2), 646-687.

Mincer, J. and Zarnowitz, V. (1969). The Evaluation of Economic Forecasts. In *Economic
Forecasts and Expectations*, NBER.
