# Freeze: long QQQ straddle 10:00 to 15:59 on the session after a mega-cap release

Frozen 2026-11-13, before the held-out read of trials 1980 and 1984. Nothing below changes after
that read.

## Provenance

Discovery-derived. The idea came from the round-3 mid decomposition (`mid_vs_touch_qqq.csv`), which
showed the short losing through the session after a release in every block, P, M and C. The gap
condition in 1980 was formed after a diagnostic split that printed the C mean of 18 big-gap events
(+3.1% of debit against controls). The C block is therefore not clean for 1980, and only partly
clean for 1984 (its regression coefficient on C has not been computed). Every result here is
exploratory whatever the held-out read shows. No block is clean for any QQQ event outcome in any
case, because the frozen index study's family B2 viewed P, M and C.

## Rules (frozen)

- Day d: the NYSE session after an after-close release by AAPL, MSFT, NVDA, AMZN, GOOGL, META,
  TSLA or AVGO (`data/cache/index_events/megacap_amc_releases_2016_2026.csv`), known weeks ahead.
  Days that carry a CPI, payrolls or FOMC release are excluded.
- Entry at the 10:00 ET snapshot of d at the asks: the shortest QQQ expiry strictly after d with a
  two-sided call and put, strike minimising |C mid - P mid|. Exit at the 15:59 snapshot of d at
  the bids. Commission USD 0.65 per contract per side. Unit: debit paid at the asks.
- 1980 adds: |log(F 10:00 d / F 15:59 t)| >= 0.6094% (the discovery event-day median), known at
  10:00. Controls: days without a release, same weekday, same dte, prior-close VIX within 15%,
  within 60 sessions; at least five. Statistic: mean event-minus-control, date-clustered 95%
  interval, placebo null percentile; plus the event book's own level.
- 1984: OLS of the long on [release flag, |gap| in pp, prior VIX / 10, weekday and dte dummies],
  day-resampled bootstrap for the release coefficient.

## Discovery numbers (M, 2019-01-02 to 2024-12-31)

- 1980: N=42, +8.27% of debit vs controls [+0.01, +17.34], t 1.84, null 97th percentile; book
  level +5.76% [-2.38, +14.91].
- 1984: N=1,302 days, release coefficient +5.89% of debit [+0.48, +12.22], t 2.00.
- Right-driver caveat: on days without a release the same gap rule earns +3.89% vs small-gap days
  (1983, t 2.25), so volatility clustering carries part of the effect.

## Held-out criterion (C, 2025-01-02 to 2026-10-30; P read beside it)

- 1980 passes held-out if the C event-minus-control mean > 0 with its interval above zero AND
  the C book level > 0. 1984 passes if the C release coefficient > 0 with its interval above
  zero. Neither can be confirmatory: t >= 3 was not met on M, and provenance is discovery-derived.
- A pass with the level at or below zero is cost recovery relative to other days, not alpha.
