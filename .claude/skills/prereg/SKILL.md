---
name: prereg
description: Write and freeze a pre-registration before any outcome of a new study is computed. Use when starting a study, before the first data request or scoring run.
argument-hint: [study slug]
---

# Pre-registration

Write it before any outcome exists. A pre-registration written afterwards is a rationalisation.

1. Copy `research/_template/` to `research/<line>/<YYYY-MM-DD-slug>/` if not done.
2. Fill `prereg.md` with the analyst: hypothesis and mechanism; data, universe and blocks (and
   which blocks have had outcomes viewed before); the exact rule with each parameter's derivation;
   the primary statistic and its basis; date-clustered inference and the matched null; the
   success criterion; the kill criterion; trials declared. Model: any file in
   `research/*/preregs/`, for example `research/selection/preregs/p1_skew_reaction_prereg.md`.
3. Fill `## Mechanism` (economic or microstructure, stated before data) and `## Power` (the
   minimum detectable effect from `protocol.min_detectable_effect` or
   `min_detectable_rate_ratio`, using data already viewed, and a line saying why the primary
   statistic can answer the question given the outcome's known sign and scale). Check every
   declared block with `protocol.block_is_clean`.
4. Check the kill criterion cannot be reread as a pass, and that no parameter was chosen by
   looking at the declared blocks.
5. Write `study.py` from the template and debug it on blinded outcomes only (`--blind`, the
   default).
6. Review per slate (at most seven trials): run the `quant-reviewer` agent in pre-freeze mode on
   the slate's prereg and scorer, with no outcome access. It writes `review_pre.md` ending in
   `go` or `no-go` per trial. The team lead has delegated approval to this review; do not freeze
   a `no-go` trial.
7. Freeze with the scorer and every input:
   ```bash
   python -c "from earnings_iv_crush.research.protocol import freeze_prereg as f; f('research/<line>/<slug>/prereg.md', 'outputs/research/prereg_<slug>.json', trial_id='<ids>', n_trials_declared=<n>, declared_utc='<YYYY-MM-DD>', scorer='research/<line>/<slug>/study.py', inputs=[<every input path>])"
   ```
8. Add the trial rows to `research/ledger/trials.csv` (LOND index and alpha) and
   `docs/RESEARCH_STATE.md` section 1.
9. Run `study.py --unblind` once. Log the blocks it viewed with `protocol.log_block_view`.
10. Run `quant-reviewer` in post-score mode on the findings; it writes `review_post.md`. Only the
   claims it marks supported go to the team lead, each labelled confirmatory, exploratory or
   descriptive.

After freezing, the text is never edited. A change is `prereg_amendment_01.md` with its own hash
recorded, written before the outcome it would affect.
