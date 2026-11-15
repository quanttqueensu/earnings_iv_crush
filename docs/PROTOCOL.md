# Research protocol

The rules every result in this repository follows. A result that breaks one is not comparable to
any number already recorded. Each rule exists because the project once produced a figure it had
to withdraw; the incident is named beside it.

The code that enforces most of them is `earnings_iv_crush/research/protocol.py`,
`engine/screen.py` and the test suite. The workflow for a new study is in
[`../research/README.md`](../research/README.md).

## The rules

**P1. Pre-register before the first data request.** Write the hypothesis, the mechanism, the
exact specification, the blocks, the primary statistic, the success criterion and the kill
criterion, then freeze the file with `protocol.freeze_prereg` so its SHA-256 is recorded before
any outcome exists. Every scorer calls `protocol.verify_prereg` first. A change after an outcome
is viewed is a dated amendment with its own hash, never an edit. Template:
`research/_template/prereg.md`. *A criterion written afterwards can always be read as a pass.*

**P2. Count the trial.** Every configuration declared, run or abandoned adds to the count in
[`RESEARCH_STATE.md`](RESEARCH_STATE.md), in the same commit. *The 1,476-configuration search
was trusted only after it was rebuilt from logs.*

**P3. Causal everything.** Every threshold, quantile and feature at event *i* uses only events
with a strictly earlier announcement date, on an expanding window with a minimum history
(`earnings_iv_crush/research/gates.py`). *A full-sample 80th percentile was worth about 0.05 of
per-trade Sharpe of illusory lift.*

**P4. Score on residual value, not realised P&L, for any selector.** Realised P&L rewards
selling a physically larger option. The outcome for selection work is the residual-value term of
the per-event decomposition (`research/selection/reverse_alpha_lib.py`), normalised by margin;
net RoM is secondary. *91% of the term gate's apparent advantage was premium collected.*

**P5. Disjoint decile sorts, not threshold sweeps.** Report every bin. A cumulative threshold
curve looks monotone whenever one tail carries the book.

**P6. Benchmark against the participation-matched random null.** Same pool, same count, only
the rule differs (`protocol.matched_random_null`). *On 2025-26 random selection beat the term
gate by 3.66 points of RoM.*

**P7. Date-clustered intervals.** 95% percentile bootstrap resampling whole announcement dates,
5,000 draws, seed 0 (`protocol.date_clustered_ci`). Same-day events share the overnight market
move and are not independent.

**P8. Per-trade Sharpe is the primary statistic; state the basis of any scaled number.**
Annualise only by the square root of the book's own trades per year
(`engine.stats.infer_periods_per_year`) and say so. Gross or net, per side or round trip, per
trade or per year: every scaled number states its basis. *The daily square root of 252 on a book
trading 35 times a year once inflated a headline Sharpe 3.2 times.*

**P9. One valuation path.** Every estimator reconciles to `engine/pnl.py::build_trade` on the
same events before it is trusted, and two return series are compared only on the same
denominator. *An exit priced at intrinsic omitted the premium left in the contract and turned a
mean RoM of -0.114 into +0.193.*

**P10. Measured costs, at the touch the strategy would actually pay.** The fixed-time cost basis
is 1.7871% of premium per side, about 11.6% round trip. A cost arm conditioned on trades that
happened is selection-biased and never quoted. A result that passes only at the mid does not
pass.

**P11. Fail loudly.** A gate, filter, join or fallback that can silently produce an empty, NaN or
degenerate result must raise, warn, or print a funnel. *A rolling quantile with no minimum
periods once rejected every event, and the run "worked" with zero trades.*

**P12. Attrition is reported, and tested for outcome dependence.** Count every dropped event by
reason. If drops correlate with the outcome, the surviving sample is biased; re-mark the dropped
events under a stated rule and report both. *The 2025-26 ledger dropped zero-bid exit legs,
which happen after large moves, and its headline moved from +0.043 to -0.087.*

**P13. Data provenance.** Label every result synthetic or real and name its source. Features
built from Alpaca end-of-day last trades are not used for selection: they leak the next day's
information relative to a 15:59 decision. Check a source's sampling before trusting a pair of
snapshots (*DoltHub's default five-day lookback made 54.1% of event pairs reuse the entry chain
as the exit chain*).

**P14. Holdouts are touched once.** Discovery, validation and confirmation blocks are declared
in the pre-registration. A block whose outcomes were viewed for one selector is stated as viewed
when another is tested on it.

**P15. Metered pulls are priced and capped.** Estimate the cost with the vendor's free metadata
call, pass a hard `--cap` in dollars, get the team lead's go-ahead, and reconcile the actual
spend against the estimate afterwards (see [`DATA.md`](DATA.md)).

**P16. Freeze the code and data, not only the words.** `freeze_prereg(..., scorer=, inputs=)`
records the hashes of `study.py` and every input file, git HEAD and the freeze time;
`verify_prereg` refuses a changed input, and refuses a scorer change once an unblinded run is
logged. *On 2026-11-12 two scorers were edited after their freezes, and the record could not
show whether any edit followed an outcome.*

**P17. Power and metric validity before the freeze.** Every pre-registration has a `## Power`
section with the minimum detectable effect (`min_detectable_effect`,
`min_detectable_rate_ratio`) from data already viewed, and states that the primary statistic can
answer the question given the known sign and scale of the outcome. `freeze_prereg` refuses a
text without `## Mechanism` and `## Power`. *A tail gate was frozen with 16 treated events, and
a sizing study compared per-date Sharpe ratios on a book known to lose money, where Sharpe
rewards concentration; neither could answer its question.*

**P18. Develop blind, unblind once, stop at the first failure.** Scorers run on `blind()`
outcomes until they work, then `verify_prereg(..., unblind=True)` once; a second unblinded run
needs a logged reason. Blocks are scored through `staged_scoring`, so a failed trial has no
later-block numbers. *The 2026-11-12 tail scorer printed validation and confirmation rows for
failed trials, and two withdrawn conclusions were drawn from them.*

**P19. The block ledger decides what is clean.** Every viewing of outcomes, by a trial or a
descriptive query, adds a row to `research/ledger/blocks.csv` (`log_block_view`). A block
confirms a hypothesis only if `block_is_clean` finds no row for that outcome and feature family.
Any clean block may confirm, which keeps data scarce enough to use; no block confirms a
hypothesis descended from its own numbers.

**P20. Confirmation is significance plus mechanism.** A confirmed result needs the
date-clustered interval excluding zero, the matched-null percentile at least 95, a t-statistic of
at least 3 (Harvey, Liu and Zhu 2016), its `date_clustered_pvalue` passing Benjamini-Hochberg at
5% within its slate, and an economic or microstructure mechanism accepted before the freeze.
Significance without a mechanism stays exploratory. The LOND alpha (`lond_alpha`) is recorded
beside every trial in `research/ledger/trials.csv` and reported with any confirmation, but it is
advisory, not binding: with no discoveries it falls to about 3e-4 by the tenth trial, which no
sample this size can meet. The first result confirmed under this rule gets a full independent
review before it changes the paper book.

**P21. Separate roles, review per slate.** The designing agent does not grade its own work. The
`quant-reviewer` agent, with fresh context and no outcome access, reviews each slate before the
freeze (`review_pre.md`: power, metric validity, mechanism, block cleanliness, closed list) and
after scoring (`review_post.md`: every claim against the logs). Freezing needs "go" in
`review_pre.md`; only claims `review_post.md` marks supported reach a chat answer or a document,
each labelled confirmatory, exploratory or descriptive. A slate is at most seven trials. Any
trial that passes discovery gets a full independent review before its next block.

## Reporting a result

A findings note (`research/<line>/<study>/findings.md`) leads with hypothesis, scope and success
criteria, then the result table with N, the interval and the basis of every number, the
attrition funnel, the comparison to the matched null, and the verdict against the pre-registered
criterion. Report the result even when it kills the idea; most do. Then update
[`RESEARCH_STATE.md`](RESEARCH_STATE.md) in the same commit.

## Integrity checks before trusting any run

```bash
python -m pytest -q                 # the suite, offline
python scripts/validate_screen.py   # needs the cache: must reproduce N=391, +0.055992
```

The second reproduces the twelve-year book from cached quote marks; if it does not, nothing
built on the same machinery is meaningful.

## References

Bailey, D. H. and Lopez de Prado, M. (2014). The deflated Sharpe ratio. Journal of Portfolio
Management 40(5). Lo, A. W. (2002). The statistics of Sharpe ratios. Financial Analysts Journal
58(4). Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-based improvements for
inference with clustered errors. Review of Economics and Statistics 90(3).
