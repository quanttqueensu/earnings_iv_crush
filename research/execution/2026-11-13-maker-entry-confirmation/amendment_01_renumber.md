# Amendment 01: trial numbers 1,629 and 1,630 become 1,779 and 1,780

Amends `prereg.md` (SHA-256 aeee3fcc8235...) without editing it. Record:
`outputs/research/prereg_2026-11-13-maker-entry-confirmation-amendment-01.json`. Scorer:
`research/execution/2026-11-13-maker-entry-confirmation/study.py`. Written after the freeze
(2026-11-13T17:02:06Z) and before any outcome: no unblinded run is logged against the record, and
no results file exists.

## Why

`docs/RESEARCH_STATE.md` gave 1,629 as the next free trial number. Two pieces of work took it on
the same day. This study froze trials 1,629 and 1,630. A five-lane exploratory search
(`outputs/research/2026-11-13-alpha-hunt/`) had already scored 117 variants under numbers
allocated in blocks across 1,629 to 1,778: 1,629 to 1,657 except 1,655, plus 1,644b; 1,659 to
1,681; 1,689 to 1,708; 1,719 to 1,740; and 1,749 to 1,771. Each lane's `trials.csv` is the record.
The numbers must be unique for the trial count and the deflated Sharpe to be checkable.

## Change

Trial A is renumbered 1,629 to 1,779, and trial B 1,630 to 1,780. The span 1,629 to 1,778 is
treated as used by the search; the numbers in it that were never scored are not counted.

The scorer's label constant changes from `TRIALS = {"A": 1629, "B": 1630}` to
`TRIALS = {"A": 1779, "B": 1780}`. That constant only labels the printed verdicts and the block
views written to the ledger. It does not touch the event set, the fill rules, the statistics or
the criterion. The change is made before unblinding, and `verify_prereg` logs it as a
pre-unblind code change.

Everything else in `prereg.md` and `review_pre.md` stands as frozen: hypotheses, mechanism,
block, specification, power, criterion, and LOND indices 1 and 2 under the P16 to P21 regime.

## Trial accounting

No new trial: the same two tests under new numbers. Count after this study: 1,780, of which
1,629 to 1,778 are the search's span. The 117 scored variants of the search still need rows in
`docs/RESEARCH_STATE.md`. `research/ledger/trials.csv` is append-only, so the two rows frozen
under 1,629 and 1,630 stay. Two rows under this record carry the new numbers, and each names the
number it replaces.
