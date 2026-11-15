# Pre-freeze review: resting entry confirmation (trials 1,629 and 1,630)

Reviewer: quant-reviewer agent, fresh context, no outcome access. No tick for the declared block
exists on disk (`data/cache/flow/broad_2023_2024/` absent), no data was pulled, the scorer was not
run, and no outcome column of `outputs/research/2026-11-02-hedged-event-hold/events.parquet` was
opened for 2023-24 (only ticker, entry_date, expiry, status, strike, m0). Checks on the 2025-26
block used files already viewed by 53aa4898 and are descriptive.

## 1. Power and minimum detectable effect

Verified. Recomputed from `outputs/research/2026-11-02-maker-entry-hedged-hold/events.parquet`:
N 1,136 on 192 dates, mean 0.00890 of m0, SD 0.02049, CR1 date-clustered SE 0.000617 (t 14.4),
matching prereg.md:89-91. Scaled to N 1,650 the SE is 0.000512, so the MDE at t of 3 with 80% power
is (3 + 0.84) x 0.000512 = 0.0020 of m0, as stated (prereg.md:92). The prior effect 0.0089 comes
from a partly seen, attrition-biased block and should be expected to shrink, but it sits 4.5 MDEs
above the bar, so A stays powered under a large winner-curse discount. The trial B range of 0.003 to
0.006 is conjecture (prereg.md:93-95); at 0.003 power is about 85%, at 0.002 about 50%. Acceptable,
and the prereg labels it as an implication rather than a measurement. The scaling assumes the
2023-24 per-event SD and date structure resemble 2025-26 (266 dates against 192, which helps).

Event counts verified: 1,956 events in the window, 1,712 with status ok on 266 dates and 276
tickers (prereg.md:37-38). m0 has no NaN and no non-positive value (minimum 2.26).

## 2. Metric validity

Paired design, identical positions. Both arms sell the same contracts in the same quantity, so the
event outcome cancels and the statistic is the entry price difference, readable whatever the sign
of the book (prereg.md:95-96). This holds. The intra-hour P&L of a leg that fills early (an unhedged
delta of about one half from fill time to the baseline clock) is inside the statistic, as the
prereg says; it adds variance and carries the adverse selection, which is what should be measured.

Finding 2a (caveat-required, must be in the prereg before the freeze): the contract is chosen with
information from after the resting order is placed. The strike is the listed strike nearest the
parity forward on the 15:59 chain (`earnings_iv_crush/research/hedged_hold.py:146-150`, called from
`research/timing/2026-10-20-hedged-hold/build_features.py:86` on `data/cache/backfill_chains`), but
the resting arm commits at 15:00. Conditioning on the strike being at the money at 15:59 selects
paths on which the stock moved towards the strike during the hour. To second order the leg whose
price rises (the one a sell limit fills on) rises less, and the falling leg falls more, by about
Gamma_leg x (hourly move)^2 relative to a strike chosen at 15:00. Both favour the resting arm. A
rough size on a 100-dollar name with a 6.75% implied move is 0.03 dollars per straddle, about 0.001
of m0: half the MDE and roughly a tenth of the 53aa4898 effect; discrete strike spacing reduces it.
53aa4898 carries the same bias, so A remains a faithful replication, but the claim must say the
paired improvement is an upper bound for this reason, and the scorer should report a pre-declared
diagnostic: the 15:00 parity offset |C_mid - P_mid| per event and the mean improvement by tercile
of that offset over m0. If the improvement rises with the offset, the look-ahead carries part of it.

m0 from the chain file. A fair scale: fixed at entry, identical in both arms, independent of the
outcome. It differs from the tick-rebuilt m0 of 53aa4898 only through the 15:59 chain bid against
the tick bid, which F1 reconciled at that instant with a median gap of zero
(`research/execution/findings/flow_liquidity.md`, addendum 03). For trial B it is a 15:59 quantity
scaling a 15:45 trade; harmless as a denominator.

Strict fill rule. A print above the limit or a bid at the limit counts as a fill at the limit
(`research/execution/research_flow_liquidity.py:276-293`). OPRA `cmbp-1` here carries no condition
codes, so complex-order legs and auction prints count as fills, and queue position at the mid is
ignored. The prereg handles this: quote-only is reported, and a pass that holds only under the
strict rule cannot be promoted (prereg.md:117-119). The fill audit counts only prints above the
prevailing ask (study.py:216-222), narrower than the concern: a complex-leg or auction print between
the limit and the ask is the common case. The strict-minus-quote-only gap is the better audit and is
already computed. `_print_outside_nbbo` takes `.iloc[0]` among records sharing the fill timestamp
(study.py:218), so it can read a quote row and undercount; minor.

The 15:00 quote lookup given a 14:55 pull start. The 53aa4898 files began at 09:30 two sessions
earlier, so their 15:00 quote was never truncated. On the 2025-26 files, 16 of 1,136 events (1.4%)
have a leg with no record in [14:55, 15:00]; these would be excluded here and were scored there.
Small, and it does not bias the sign (it depends on quote activity before the order exists), but it
is an eligibility difference from the rule being replicated and must be disclosed.

The status filter. In this window `status != ok` is exactly the 42 megacap tickers (243 events,
all `no_front_quote`) plus one `no_hedge_vol`. The filter is not outcome-dependent here, and it is
what makes the claim of no ticker overlap with the W1 megacap block true (prereg.md:47-49). The
prereg should state that mechanism rather than "checked".

## 3. Mechanism

Stated in advance and economic (prereg.md:18-32): takers pay the touch, resting sellers earn part of
the half-spread when inventory rather than information drives the counterparty (Muravyev 2016),
with informed volatility demand (Ni, Pan and Poteshman 2008) and stale limits as the stated risks,
both inside the statistic. The trial B re-peg is motivated by the W1 one-minute markouts, a
falsifiable microstructure mechanism. The 34,672-print figure comes from 27 megacap tickers
(`data/cache/fills_et/`), none of whose events are in this block (checked), so the mechanism does
not descend from the numbers of this block.

Recommended, not required: report the decomposition of filled-leg improvement into (limit minus
baseline mid) and (baseline mid minus baseline bid). The first is drift and markout, the second the
half-spread. A pass carried by the second is the claimed driver; one carried by the first is price
drift, which the look-ahead in 2a feeds.

## 4. Block cleanliness

No resting-order fill or entry tick for these events has been viewed. Evidence: a scan of
`data/cache/` and `data/processed/databento/` for files keyed on (ticker, entry date) of the 1,712
events finds no tick file. `fills_et` (27 megacaps) and the 39 `_nbbo.parquet` files from
`scripts/build/measure_spread.py` overlap none of them; the W1 `megacap_2023_2024` tickers are all
outside the ok set.

Disclosures missing from the prereg:

- `data/cache/entry_1545_chains/` holds 15:45 OPRA `cbbo-1m` chains for 729 of the 1,712 events,
  pulled by `outputs/research/2026-11-10-entry-time-descriptive/pull_1545.py` for the entry-clock
  history plan (`_private/reports/entry_clock_history_plan_2026-11-10.md`), which says no outcome
  was computed on them. These are the trial B baseline prices. No ledger row is needed if nothing
  was computed, but the prereg must state the pull. The descriptive grid that motivated the 15:45
  clock (`outputs/research/2026-11-10-entry-time-descriptive/grid.parquet`, 1,220 rows) is 2025-26
  only.
- `block_is_clean` is vacuous here: it matches panel names exactly
  (`earnings_iv_crush/research/protocol.py:578-583`) and `broad_entry_ticks` is a new name, so it is
  clean by construction (prereg.md:100-103). The real evidence is the cache scan above, which the
  prereg should cite. This weakness matches no class in the failure-mode ledger: a cleanliness check
  keyed on a string the trial itself chooses always passes on a new name.

The alpha-hunt descriptive row (blocks.csv, 2026-11-13, `w1_passive_fill_ledger`, 2025-26) does not
touch this block.

## 5. Scorer against the prereg

Trial A against `fills()` of 53aa4898
(`research/execution/2026-11-02-maker-entry-hedged-hold/study.py:55-88`): same instants (15:00 and
15:59:00, `_at(day, 900)` and `_at(day, 959)`), same `_quote_at`, `_round_limit(..., "sell",
"penny")`, `_first_fill(..., "strict")`, and the same improvement, the sum over filled legs of the
limit minus the 15:59:00 bid. The logic is faithful. Differences are in eligibility and data:

- Finding 5a (required): an event is dropped from both trials if any leg of either trial is
  unquoted (study.py:283-287), so A loses events whose legs lack a 15:45 quote, which 53aa4898
  never required. Score each trial on its own eligible set with its own funnel.
- Data window, contract source and m0 source differ as in section 2; disclose.
- Clustering is on entry date here and exit date there; for one-night events these map one to one.

Trial B as written, with one gap. Finding 5b (required, cheap): each minute window is
[m:00, m:59] inclusive (study.py:254), so records after m:59.000 and before (m+1):00 are never
tested, while the prereg says "within that minute" (prereg.md:65-66). Use a half-open window to the
next minute. The limit comes from the quote at or before the minute start (causal), the cross is at
the 15:45:00 bid, and both rules are tracked separately. The carry-forward branch can trigger only
before the first quote, which the 15:00 check excludes; harmless.

Quote-only rule (study.py:204-207): fills only when the NBBO bid reaches the limit. As written.

Statistics: `date_clustered_ci` and `date_clustered_pvalue` on entry dates, 5,000 draws, seed 0;
`cluster_t` is CR1 (study.py:313-319); a pass needs the lower bound above zero, t of at least 3 and
BH at 5% (study.py:399), matching prereg.md:107-110. BH is implemented correctly
(study.py:353-360). LOND alphas check: 0.05 x 6/pi^2 = 0.0304, and a quarter of that, 0.0076.

Staged scoring: one block, so `staged_scoring(..., lambda r: True)` (study.py:393) is a formality.
Acceptable.

Blinding: per-date random sign flips (study.py:322-328) hide the mean and keep the cluster
structure. Finding 5c (required, cheap): the blind run still prints both-leg and any-leg fill
rates, the fill audit and the mean 15:59 half-spread (study.py:403-408); fill rate times half-spread
approximates the answer. Print only the funnel and blinded statistics until `--unblind`.

Block ledger: `log_block_view` runs only under `--unblind` (study.py:409-418). Correct.

Finding 5d (required): fail loudly on the pull. A request that raises leaves no file and is later
counted as `no_tick_file_or_empty` (study.py:159-163, 274-277), the same bucket as a genuinely empty
session; a pull halted at the cap writes a manifest of the partial set, which the scorer then scores
(study.py:172-181, 184-194); events whose symbols cannot be built are skipped without a count
(study.py:98-100). Record failed, unrequested and symbol-less events in the manifest, have the
scorer refuse a halted or failed pull, and split the funnel into no symbols, pull failure and empty
file.

Finding 5e (required): freeze the inputs. Pass `inputs=` to `freeze_prereg` with the events
parquet, `research/execution/research_flow_liquidity.py` and
`research/execution/research_fills_study.py`. The fill logic is imported from them, and
`verify_prereg` checks only the scorer and the listed inputs (`protocol.py:342-345`).

## 6. Closed list

The prereg does not name the nearest closed rows of `docs/RESEARCH_STATE.md` section 2. Two apply:
"Resting orders (maker F1), fails the markout gate in both blocks" and "Better fills on the fixed
15:59 book, worth about +0.007 Sharpe". This study differs from the first in the cancel clock
(15:59:00 against 15:59:59), a single paired statistic with the markout inside it, the hedged-hold
vehicle and an unseen block; from the second in testing a resting order rather than re-scoring taker
print locations. State both. 53aa4898 itself appears in neither the closed nor the open list; add it
when these trials are entered. Numbering starts at the next free number, 1,629, as section 1 states.

## Required changes before the freeze

1. Prereg: state the strike look-ahead (15:59 strike against a 15:00 order), its sign in favour of
   the resting arm and rough size, that any pass is an upper bound for this and the fill-model
   reasons, and declare the diagnostic of improvement by tercile of the 15:00 parity offset.
2. Scorer: per-trial eligibility and funnels, so trial A does not depend on 15:45 quotes.
3. Scorer: trial B minute windows half-open to the next minute.
4. Scorer: blind mode prints no fill rates, fill audit or half-spread.
5. Scorer and pull: failed, halted and symbol-less requests recorded and counted separately; the
   scorer refuses a halted or failed pull.
6. Freeze with `inputs=` covering the events parquet and the two imported research modules.
7. Prereg disclosures: the 15:45 `cbbo-1m` chains for 729 of these events; the status filter as
   exactly the exclusion of the W1 megacaps; the vacuous `block_is_clean` result and the cache scan
   that replaces it; the 14:55 window exclusion (1.4% of events on 2025-26), chain m0 and the
   hedged-hold contract as differences from 53aa4898; the two nearest closed rows and how this
   differs.

Recommended: the drift and half-spread decomposition of filled-leg improvement; take the matching
trade row in the fill audit rather than `.iloc[0]`.

Decision: go with changes (items 1 to 7 above)

## Changes applied before the freeze (2026-11-13, by the designing agent)

Items 1 to 7 applied: strike look-ahead stated with sign, size and the upper-bound reading, and the
parity-offset tercile diagnostic declared (1); per-trial eligibility and funnels (2); half-open
minute windows in trial B (3); fill rates, audit, decomposition and terciles withheld in blind runs
(4); pull status file with failures and cap halt recorded, scorer refuses an incomplete pull, and
missing and empty tick files counted apart (5); events parquet and both imported fill modules frozen
as inputs (6); disclosures of the 15:45 chains, the status filter, the empty-by-construction ledger
check, the differences from 53aa4898 and the two nearest closed rows (7). Recommended items also
applied: drift and half-spread decomposition, and the fill audit reads the matching trade row.
