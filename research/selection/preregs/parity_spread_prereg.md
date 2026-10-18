# Pre-registration: option-implied forward premium and the earnings-window stock return

## Hypothesis

Informed traders who expect good (bad) news buy calls (puts), pushing the option-implied forward
above (below) the cash-and-carry forward. The deviation is the call-minus-put implied-volatility
spread of Cremers and Weinbaum (JFQA 2010), who find it predicts weekly stock returns; Atilgan
(Journal of Banking and Finance 2014) finds the effect concentrated in earnings-announcement
windows. Ofek, Richardson and Whitelaw (JFE 2004) tie negative deviations to short-sale constraints,
which also predict low returns. All three readings imply the same sign: a high forward premium
predicts a higher market-adjusted return over the announcement window.

Closest prior work and the difference: the papers above use OptionMetrics end-of-day implied
volatilities with a model forward. This test measures the deviation directly as
log(parity forward / cash-and-carry forward) from the 15:59 ET consolidated quotes of the front
expiry spanning the event, against a 15:59 stock price, on the 2025-2026 S&P 500 earnings block,
after publication. It is a separate trial from P1 (put skew, failed on the same block); the two
signals use different parts of the chain.

## Scope and data

- Events: `outputs/research/events_broad_oos_2025.parquet` (2,037 events), with the P1 exclusions
  applied unchanged (exact duplicate rows; EDGAR release before 15:59 on the entry day; no price
  history).
- Options: the 15:59 chain in `data/cache/backfill_chains` for the entry session, front expiry
  spanning the event (the expiry P1 used), usable quotes under P1's rule (both sides positive,
  relative spread at most 50%).
- Parity forward: from the three strikes nearest the money with both legs usable,
  F_parity = K + (C_mid - P_mid) * exp(r t), averaged over the three, as in P1's `parity_forward`
  but recomputed here with the rate.
- Stock price S: the close of the 15:59 ET one-minute bar from Alpaca's free IEX feed on the entry
  session; if absent, the last IEX bar from 15:50 to 15:59 inclusive; else the event is dropped.
- Rate r: the 3-month Treasury bill (FRED DTB3) on the entry date, converted to a continuously
  compounded rate. Dividends: every cash dividend with ex-date after the entry session and on or
  before expiry (yfinance), discounted at r.
- Cash-and-carry forward: F_cc = (S - PV(dividends)) * exp(r t).
- Signal: fp = log(F_parity / F_cc).

## Outcome

Stock return from S (15:59 entry session) to the close two sessions later (yfinance adjusted close,
the P1 price file), minus the same for SPY using SPY's 15:59 IEX bar. Per event, nothing annualised.

## Primary rule and decision

Deciles of fp within calendar-month buckets of at least 50 events (P1's bucketing).
Pass requires all of:
- Spearman(decile, decile mean outcome) at or above +0.60;
- decile 10 minus decile 1 mean outcome, net of 5 bp per side on each leg (0.20 points), with a
  date-clustered 95% interval above zero (5,000 draws, seed 0, clusters = entry date);
- the gross gap at or above the 95th percentile of 1,000 within-bucket permutations.
Kill if Spearman is below +0.60 or the net interval includes zero. DSR against 1,503 trials.

## Secondary, descriptive only

Pooled deciles; BMO and AMC separately; [0, +1]; placebo [-3, 0] ending at S; signal with dividends
ignored. None can rescue a failed primary.

## What is not allowed

No change to the signal, the forward construction, the price source, buckets, window or cost after
any outcome is seen. Amendments are dated, hashed and reported beside the original.
