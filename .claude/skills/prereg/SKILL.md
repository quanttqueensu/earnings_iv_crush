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
3. Check the kill criterion cannot be reread as a pass, and that no parameter was chosen by
   looking at the declared blocks.
4. Show the analyst the final text. When they approve, freeze it:
   ```bash
   python -c "from earnings_iv_crush.research.protocol import freeze_prereg as f; f('research/<line>/<slug>/prereg.md', 'outputs/research/prereg_<slug>.json', trial_id='<slug>', n_trials_declared=<n>, declared_utc='<YYYY-MM-DD>')"
   ```
5. Add the trial to `docs/RESEARCH_STATE.md` section 1 and commit the text, the record and the
   count together.

After freezing, the text is never edited. A change is `prereg_amendment_01.md` with its own hash
recorded, written before the outcome it would affect.
