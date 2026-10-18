# Amendment 01 to the Deribit macro-event pre-registration

Dated 2026-10-09, after the first scoring run and before any change that depends on its returns.

## Defect

The delivery-price download paged with a fixed offset step of 1,000 while the API returns at most
100 records per page, so only 300 of 2,633 daily `btc_usd` delivery prices were cached. Events whose
expiry date fell in the gaps could not be settled and were dropped as "unbuildable": 99 of 118 in
the first run, which left 16 pairs.

## Fix

Page by the number of records actually returned, rebuild the delivery cache, and re-score. The rule,
pricing, control, criterion and mechanism check are unchanged. The first run's output (16 pairs,
paired difference +0.00199 of notional, CI [-0.00621, +0.01025]) is retained in this file as the
superseded result.
