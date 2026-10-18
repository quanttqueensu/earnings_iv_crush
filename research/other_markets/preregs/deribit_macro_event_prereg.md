# Pre-registration: the macro-release crush in BTC options (Deribit pilot)

Frozen before any Deribit trade for this test is pulled. SHA-256 recorded in
`outputs/research/prereg_deribit_macro_event.json`. A pilot in a new market under section 2.0 of
the state of record.

## Question and mechanism

Does a short BTC straddle that spans a scheduled US macro release (CPI, payrolls, FOMC) earn more
than the same straddle on a matched ordinary day? The mechanism is the one the earnings work
confirmed: scheduled event variance is priced in advance and the implied distribution collapses at
the release. BTC options carry a general variance risk premium (implied exceeds realised most of
the time), so the test is **incremental**: the event premium over an ordinary day, not the level.

Demand pressure is the secondary channel: Deribit trades record the initiator's side, so net
taker buying before the release is observable for free (prior work on Deribit demand pressure in
general, not event-conditional: Journal of Financial Markets 2022, "Net buying pressure and the
information in bitcoin option trades").

## Events

Release timestamps from the close times of settled Kalshi events in series `KXCPI`, `KXPAYROLLS`
and `KXFED` (each closes minutes before its release), for every event at or after 2023-01-01.
Entry at `close_time - 60 minutes`.

## Instrument and pricing

- Expiry: the first BTC daily expiry (08:00 UTC) after the release.
- Strike: among strikes of that expiry with both a call and a put trade in the four hours before
  entry, the one nearest the index price on the last trade before entry.
- Entry value per leg: the `mark_price` on that leg's last trade before entry, less an event-specific
  seller's discount `h`: the median of `(mark - price) / mark` over taker-sell trades on that expiry
  in the four-hour window (fewer than 5 such trades: event dropped and counted).
- Fees: `min(0.0003 * index, 0.125 * option_price)` per leg at entry; no delivery fee on dailies.
- Settlement: `|delivery_price - K|`, Deribit `btc_usd` delivery price on the expiry date.
- Return: `(premium - fees - settlement) / index_at_entry` per straddle (return on notional), and
  per unit of premium as a second basis.

## Control

For each event, the same weekday seven days earlier at the same clock time, built identically,
provided no event in the list falls within one calendar day of it; otherwise fourteen days earlier;
otherwise the event is unpaired and excluded from the paired test (counted).

## Success criterion

The mean paired difference (event minus control) in return on notional is positive with an
event-clustered 95% bootstrap CI (5,000 draws, seed 0) excluding zero.

**Mechanism check**: implied event variance exceeds realised event variance. Implied total variance
from the straddle, `V = (premium / (sqrt(2/pi) * index))^2`; the implied excess is the event's `V`
minus its control's `V`, and the realised excess is the event's squared log return from entry index
to delivery price minus the control's. The mean of implied excess minus realised excess must be
positive with an event-clustered CI excluding zero. A pass without it is reported as unexplained.

Secondary, reported either way: per-release-type split; Spearman of event-day return on net taker
buying (contracts bought minus sold by takers on that expiry in the window, over total).
