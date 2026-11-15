# Freeze: WASDE report-day variance in ICE softs futures (N13, held-out read)

Written 2026-11-13 after discovery (trials 2,442 to 2,445, 2,450, 2,451) and before any held-out
outcome was computed. The held-out scorer and the module it calls were written before this note.

## Hypothesis and mechanism

H1: on WASDE release dates (12:00 ET, inside every ICE US softs session), the Cotton No. 2
front-month settle-to-settle squared log return exceeds that of same-weekday control sessions
one week either side. WASDE, with NASS Crop Production from August to January, is the scheduled
public revision of the US and world cotton balance sheet. Coffee and cocoa are placebos (WASDE
carries neither); world sugar is a near-placebo (WASDE carries US sugar only).

## Construction

Exactly as in diagnosis.log entries of 2026-11-13: stale and roll-window filters fixed from ICE
contract rules, one WASDE date per month (closest to the 10th), controls at plus and minus seven
calendar days, per-event excess squared return x_i with a date-clustered 95% interval
(protocol.date_clustered_ci, stat mean), variance ratio R with a 2,000-draw event bootstrap
(seed 7). Held-out block: release dates 2014-01-01 to 2026-11-13.

## Pass rule (trial 2,446, CT)

R >= 1.5, and the lower end of the interval on mean x_i above zero, and neither placebo (KC 2,447,
CC 2,448) with an interval on mean x_i above zero. SB (2,449) is reported, not gated. Discovery
gave CT R 1.633 [1.114, 2.436], N=125; the expected held-out result stated now is R between 1.3
and 2.0 with the pass uncertain because the bar was set close to the discovery point.

## What a pass does and does not mean

A pass establishes that cotton has a measurable scheduled report-day variance bump on real data,
the necessary condition for an event-volatility trade. It says nothing about whether the options
overprice it; that needs option quotes (Databento IFUS.IMPACT, priced in evidence.md). A fail
means the event is too small to be told apart from ordinary sessions at the held-out N and the
lane's premium question becomes moot for WASDE.

## Fingerprints

- `scripts/heldout_scorer.py` sha256 b4371e013b54c9c0da1f1a08c1f4a373215e054dc6568ae9ab6a4d1aaaba76ba
- `scripts/event_variance.py` sha256 3060237837481ed42b05e14983ddef627ef0fae3140bba013992f182ea018101
- `raw/softs_daily.csv` sha256 833508d153018c7c5c32cae4dbfc4286b8b789b84d6dd8da1539bba4a4416658
- `raw/wasde_dates.csv` sha256 54b0d50181bd3c9e54f0b1f8ed0288eb78b2739cac97185aa1c929b9e0f75ee9

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N13-softs-ice\freeze_2026-11-13_wasde-event-variance.md

Self hash (SHA-256 of every line above this one): e5b006428085fea45d1bd7aa592dd13cfa2a7c657c72ab2fec9b45bd68cdf3f8
