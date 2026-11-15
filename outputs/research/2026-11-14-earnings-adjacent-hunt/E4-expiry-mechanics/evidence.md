# E4 expiry mechanics: evidence dossier

Lane E4 of the earnings-adjacent hunt. Two questions about the option market's own calendar on
the trade the project already holds (the front ATM straddle sold at the 15:59 bid before an
after-close report, delta-hedged at closes, held to the post-earnings expiry, settled under
`HEDGED_NET`). Everything here is exploratory: trial numbers come from the lane's reserved block,
and freeze notes are self-hashed but not filed as pre-registrations.

## Verdict

Neither part yields a source of return. (a) Closes do not pin to listed strikes on the
post-earnings expiry, and choosing the strike by an open-interest proxy does not change
hold-to-expiry P&L on either block. (b) The failure-to-exercise windfall is real in the
literature, but the dividend play hands it to the parties who trade on the last cum-dividend day,
not to earlier writers, and at the touch a covered write rarely breaks even. A small IB account
cannot capture it. Part (b) turned up a valuation issue instead: the hedged-hold model holds the
short call through ex-dividend dates, and on about 4% of broad events, where early exercise is
optimal, it credits the writer with a dividend that rational holders take.

## Hypothesis, scope and success criteria

Declared in `diagnosis.log` entry 2 before any outcome was computed.

- Trial 2,772 (mechanism): on the post-earnings expiry session, the CRSP close lands within
  USD 0.125 of a listed strike more often than on the adjacent sessions of the same stock with the
  same grid. Pass: the date-clustered 95% lower bound above zero.
- Trial 2,773 (P&L): selling the straddle at whichever of K-1, K0, K+1 has the largest causal
  open-interest proxy earns more than the ATM hold, per trade in m0, net at the touch under
  `HEDGED_NET`, event-night delta matched. Pass: the lower bound above zero, the matched
  random-switch null at or above the 95th percentile, and a positive gain after removing the entry
  half-spread saved, so that a pass cannot be lane B's spread effect.
- Part (b): a literature and feasibility case, plus two descriptive measurements on disk.

## How this differs from closed work

- Alpha hunt 2 lane B (trials 1,811 to 1,826) chose among the same three strikes on the 15:59
  quoted spread; its gain is entry half-spread saved (1,819: +0.21% of m0 [+0.14, +0.28], broad
  2019-24). Here the choice is on positioning, whose claimed channel is the settlement price, and
  the driver condition rules out a spread-carried pass. The panel is the megacap hedged hold, which
  no study has viewed for strike choice.
- The netting correction (trial 1,856) is applied to every leg; K0 rebuilt under the old
  convention reproduces the stored megacap H on all 998 built events (maximum gap 0.0 of m0).
- No closed study touched pinning or ex-dividend exercise.

## Data

No cache on disk carries historical open interest: the Databento chains have no OI field, the
DoltHub and strip `open_interest` columns are entirely null, and Alpaca's OI is today's snapshot
(`diagnosis.log` entry 1). The only causal proxy is cumulative Alpaca daily option volume per
contract before the entry date (`data/cache/alpaca_legacy`, 49 megacap names, 2014-06 to 2026-07).
It overstates open interest by every closing trade and could not be validated against true OI.
Strike grids come from the reaction-session chains (`backfill_chains` broad, `databento_quotes`
strips megacap). Stock closes and dividends come from `crsp_paths.parquet` (2011 to 2024, 332
permnos), dividends recovered as (1 + ret) times the previous close minus the close. No network
data source was used for any number; CRSP on disk ends 2024, so no 2025-26 block exists for a
CRSP hedged hold.

## Part (a): pinning and open interest on the post-earnings expiry

### Trial 2,772, pinning (one configuration scored)

| Block | N (expiry sessions) | pin_E | pin_C | Difference, points | 95% CI | t |
|---|---|---|---|---|---|---|
| 2013-18 discovery | 3,188 (255) | 24.7% | 24.6% | +0.17 | [-1.24, +1.66] | 0.23 |
| 2019-24 held-out, frozen | 5,649 (293) | 20.7% | 19.8% | +0.91 | [-0.32, +2.15] | 1.45 |

Basis: share of events with the close within USD 0.125 of a listed strike, expiry session minus
the mean over control sessions, per event; broad plus megacap hedged-hold events; date-clustered
on the expiry session. Sources: `results_pin_discovery.json`, `results_pin_heldout.json`.

By grid on the held-out block: USD 5 +0.16 [-1.36, +1.73] (N 1,147), USD 2.5 +0.31 [-1.45,
+2.08] (N 1,438), USD 1 +0.65 [-2.02, +3.38] (N 1,536), USD 0.5 +3.7 [-0.04, +7.3] (N 950). A
scale-free band (within 5% of the local spacing) gives +0.30 [-0.59, +1.15]. For comparison,
Zhang, Chen and Cai (2015) report 6.9% against 5.4 to 6.2% on USD 5 grids for weekly expiries in
2010-12 (verified, p. 65), a gap of roughly one point that this sample's interval cannot exclude
but does not detect. NPP (2005) found clustering on monthly expiries in 1996-2002; the effect the
earnings book could use is absent or below about two points on these expiries. The conservative
reading of the contrary prior: dealers are likely net short gamma after the earnings demand, which
predicts no pinning, and that is what the data show.

### Trial 2,773, open-interest-proxy strike choice (one configuration scored)

| Block | N | Switched | Gain vs ATM hold, % of m0 | 95% CI | t | Null pct | Settlement intrinsic change on switched |
|---|---|---|---|---|---|---|---|
| 2014-18 discovery | 432 | 61% | +0.057 | [-0.161, +0.268] | 0.52 | 45.8 | +0.14% (worse) |
| 2019-24 held-out, frozen | 552 | 58% | -0.071 | [-0.199, +0.059] | -1.07 | 25.0 | +0.20% (worse) |

Basis: per trade, in the base trade's m0 (0.20 times forward plus the 15:59 bid), net at the
touch, `HEDGED_NET`, including the event-night stock hedge of the strike step's delta; paired
against the ATM hold on the same events; reaction-date clusters. Sources:
`results_oi_2773_discovery.json`, `results_oi_2773_heldout.json`.

The chosen strike finishes nearer the expiry close on 48% and 51% of switched events, no better
than a coin, and the rule does no better than switching the same number of events to a random
neighbour. Attrition: 4 and 10 events with no buildable neighbour dropped; their ATM hold averages
-7.0% and -11.4% of m0, so the kept sample flatters the book level but not the paired effect,
because the rule never drops an event the base book trades. The megacap stale-spot landmine does
not enter: the front contract and forward come from the strip and the stock from CRSP, and 0 of
984 events show |log(F/S)| above 2%.

Search count: one configuration per trial, discovery t 0.23 and 0.52. No variant was scored after
the mechanism test failed, because a variant without a pinning effect to exploit would be a search.

## Part (b): ex-dividend exercise failure

### The literature (verified at the source)

Hao, Kalay and Mayhew (2010, RFS 23(1)) study 438,269 call series-events, 1996-2006: more than
40% of calls that should be exercised before the ex-date are not (40.7% to 54.3% across
open-interest deciles; 33% even where exercise is worth USD 0.84 a share). The windfall to writers
does not stay with them. In the dividend play, two market makers cross a large offsetting call
trade on the last cum-dividend day and exercise their longs; the clearinghouse assigns exercises
across all short positions, so the new short open interest absorbs most assignments and the
pre-existing writers are assigned at a rate close to one. The authors conclude that only a small
fraction of the benefit accrues to parties who sold before the last cum-dividend day, that
volume reaches up to 2,000 times normal, and that the trade depends on exchange fee caps adopted
in 2003 and clearing costs under 1.5 cents a contract. NYSE's 2019 note shows the trade alive,
crowding out the natural short open interest, with PHLX and BOX treating it as a capped strategy;
NYSE Arca and BOX extended dividend-strategy fee caps in 2023 (recalled from the Federal Register
summary). The windfall is a market-maker trade: it needs fee-capped crossing at size, which a
retail account at USD 0.65 a contract does not have.

### What a small writer gets at the touch (descriptive, `exdiv_touch.py`)

On the 104 name-days where the last cum-dividend session has a cached 15:59 chain (selected by
earnings timing, not random; 2013-24), across 5,243 exercise-optimal call series within 60 days:
median dividend USD 0.54 (0.78% of the stock), median call half-spread USD 0.80, and 96% of bids
below parity. A covered write (buy stock, sell the call at the bid) breaks even only if the share
of open interest left unexercised exceeds u*. Choosing the best series per name-day, u* has a
median of 0.49 where it is finite, and on 31% of name-days no series breaks even even if never
assigned. With the dividend play pushing a pre-existing writer's non-assignment chance towards
zero, the edge is not reachable. About a quarter of name-days show a bid above parity plus costs,
which points at the one-minute gap between the 15:59 quotes and the 16:00 CRSP close rather than
an arbitrage; the measurement is exploratory and should not be quoted as a level.

### What part (b) means for the existing book (descriptive, `exdiv_audit.py`)

The hedged-hold builder holds the short call to expiry and credits the stock hedge with dividends
through total returns. When an ex-date falls inside the hold and early exercise is optimal, an
exercising holder takes the dividend from the writer; the model instead credits the writer D minus
the put value. Broad book: an ex-date inside the hold on 286 of 2,640 events (2013-18) and 530 of
5,113 (2019-24), the call in the money on the cum day on 169 and 319, exercise optimal on 127 and
211. The model's credit averages +0.110% of m0 per trade [+0.088, +0.133] (2013-18) and +0.094%
[+0.075, +0.115] (2019-24) across the whole book, about 2.9% of m0 on each affected event; the
bound with any in-the-money call is +0.19% and +0.17%. Megacap: the upper bound only (no hedge
volatility stored), +0.10% [+0.06, +0.15] and +0.08% [+0.04, +0.12]. Because the dividend play
makes a writer's assignment near certain where exercise is optimal, the conservative reading is
that the full credit is overstated. That is about half the size of lane B's strike lever and of
the netting correction (+0.22%), with the opposite sign. Basis: per trade, m0, date-clustered on
the reaction date; stock data and strikes only, no P&L outcome read. Source: `results_exdiv.json`.

The broad book's long holds drive this (median 22 days for affected events, where the front expiry
is a monthly); the megacap book, with weekly front expiries, is exposed less.

## What it would take at IB

Nothing in (a) is worth implementing. For (b), the harness should know about early assignment:
under `HEDGED_NET` an assigned call nets against the stock hedge, but an assignment the night
before an ex-date removes the call leg early and leaves the put and residual hedge. The live
ledger would need to recognise that event (an assigned short call before expiry) rather than treat
it as an orphan; that is a check, not a strategy.

## Not verified

The magnitudes inside NPP (2005) (only the abstract and secondary summaries were read); the
original Avellaneda and Lipkin (2003) paper; Pool, Stoll and Whaley (2008) and Jensen and
Pedersen (2016) beyond abstracts; whether the 2013 OCC rule change restricting dividend plays took
effect; the 2023 NYSE Arca and BOX filings' text; IBKR's no-fee assignment page (search summary
only). The open-interest proxy could not be checked against true open interest.

## Files

`diagnosis.log`, `trials.csv`, `sources.csv`, `freeze_2026-11-14_pinning.md`,
`freeze_2026-11-14_oi-strike.md`, `build_pin.py`, `score_pin.py`, `build_oi.py`, `score_oi.py`,
`exdiv_audit.py`, `exdiv_touch.py`, their logs and `results_*.json`, `block_views.csv` (to be
merged into `research/ledger/blocks.csv` by the team lead; this lane writes only in its folder).

C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-earnings-adjacent-hunt\E4-expiry-mechanics\evidence.md
