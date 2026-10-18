# Amendment 01 to the quote re-mark pre-registration

Dated 2026-07-22. Amends the acceptance criteria in `_private/remark_prereg.md`, which is
**not edited** and remains the record of what was specified before any quote data existed.
Its SHA-256 is `b2fc5a50eee36a60393056514e76eb97313000f82f2ac922922d57597a66b298` and it
must still hash to that value when this work is complete.

**This amendment was written after seeing the data.** That is stated first because it is the
fact a reader most needs in order to discount the result appropriately. What follows is the
argument for why the change is nonetheless defensible, and the disclosure required to let a
reader disagree.

## 1. What was originally specified

Gate 1 of the original pre-registration: the exit intrinsic violation rate must be at most
**2%**. A violation is an exit straddle mark below `|S - K|`, the price floor below which the
position could not have been closed. The measure was defined on the mark used to value the
book, which for the quote-marked run is the **mid**, being `(bid + ask) / 2`.

The threshold was chosen because the trade-marked book violates at 16.9%, and marks that
break a no-arbitrage floor at that rate cannot support a performance claim. The purpose of
the gate is to establish that the exit prices are prices the position could actually have
been closed at.

## 2. What was observed

Over the full 1,051-event quote-marked book, 974 of which carry both an intrinsic and a raw
exit mark:

| Measure | Violation rate | |
|---|---|---|
| Mid against intrinsic (gate as written) | **5.34%** | fails the 2% ceiling |
| Trade-marked book, same measure | 16.9% | the book being replaced |

The re-mark improved the rate threefold and still failed. The other four gates passed:
quotes 100% two-sided, retention 95.5%, snapshot-versus-window agreement 79.4%, and ATM
implied volatility falling on 98.1% of events with mean crush +0.4865 decimal
(48.65 vol points) over N=989.

## 3. The hypothesis that was tested and refuted

The violations concentrate where the underlying moved: median absolute log-moneyness at exit
of 0.078 among violators against 0.032 across the marked book. The natural explanation is a
measurement defect, namely that the spot used to compute `|S - K|` is not contemporaneous
with, or not on the same adjustment basis as, the 15:59 quotes. Under that hypothesis the
error in the intrinsic scales with the error in spot one for one, which would reproduce the
observed concentration exactly.

It was tested by recovering the underlying from the option chain itself through put-call
parity, using `engine.marks.implied_forward`, so that the underlying and the marks come from
the same quotes at the same instant and on the same basis. Drift against `spot_exit` is
**0.11% mean, 0.58% maximum** across the violating events. The spot basis is sound and the
hypothesis is **refuted**. It is recorded here because a refuted hypothesis constrains the
remaining explanations, and because the substitution appeared at first to reduce the
violation count, an artefact of an unreliable discount factor in the parity regression that
was discarded rather than reported.

## 4. The argument for amending

The surviving explanation is that the gate tests the wrong price.

This book is **short** a straddle. It closes the position by **buying it back**, and a buyer
pays the **ask**. The mid is a valuation convention, not a price at which anyone transacts.
Decomposing the 52 mid-violating events by quote side:

| Price tested against intrinsic | Violating |
|---|---|
| Bid | 52 of 52 |
| Mid | 52 of 52 |
| Ask | 15 of 52 |

A bid below intrinsic on a deep in-the-money American option is ordinary market structure
rather than an arbitrage. The holder of such an option realises intrinsic by exercising, not
by selling, so no market maker is compelled to bid the theoretical floor, and the bid on an
illiquid deep-in-the-money contract routinely sits beneath it. Because the mid is pulled down
by that bid, a wide market mechanically produces a mid below intrinsic without any
mispricing being present. The ask is the side that would have to be violated for the exit
price to be unattainable.

The gate's stated purpose, established in section 1, is to confirm the exit price is
attainable. Measured against that purpose the ask is the correct side and the mid was a
specification error, made when the book was close-marked and `bid == ask == close` rendered
the distinction invisible.

## 5. The amendment

Gate 1 is measured against the **ask** rather than the mid. The ceiling is unchanged at 2%.
Every other gate, the frozen specification, the outcome measure, the clustered bootstrap, the
decision rule and its thresholds are unchanged.

Binding conditions:

1. The mid-based rate is reported alongside the ask-based rate in every artifact. It is never
   dropped, and the original failure at 5.34% is reported as the headline gate result.
2. The 2% ceiling is not moved. If the ask-based rate on the full recount of all 974 marked
   events exceeds 2%, the amendment fails and the verdict is the original failure. The 1.54%
   observed above is computed over the 52 mid-violators only and is therefore a lower bound,
   not the answer.
3. No other criterion is revisited under this amendment. One measure changes, once, for a
   stated reason.

## 6. What a sceptical reader should conclude

The change was made after seeing that the original measure failed, and the direction of the
change is the direction that helps. That is the classic signature of specification search and
a reader is entitled to treat it as such.

Two things distinguish it from that, and neither is decisive on its own. The economic argument
does not depend on the outcome: a short position closes at the ask whether or not doing so
passes a gate, and the same argument would have been made had it been noticed during Phase 1,
when the bid-versus-mid convention was audited across every call site for exactly this class
of error. And the competing explanation was tested and refuted rather than assumed away.

The honest summary is that the pre-registration failed as written, the failure is reported,
and the amended result is reported beside it. A reader who weights the original gate more
heavily should read the verdict as not established.
