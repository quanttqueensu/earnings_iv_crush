---
name: new-study
description: Start a new research study the project's way, from the graveyard check to a frozen pre-registration and a scorer skeleton. Use when someone wants to test a new idea.
argument-hint: [line] [short slug] [the idea]
---

# New study

1. Run `/graveyard` on the idea. Stop if it is closed.
2. Pick the line (`frozen_selector`, `execution`, `timing`, `selection`, `off_earnings`,
   `other_markets`) and a slug; create `research/<line>/<YYYY-MM-DD-slug>/` from
   `research/_template/`.
3. Fill the card `README.md`: the sentence, why it matters, the closest prior work and the nearest
   closed study.
4. Run `/prereg` with the analyst and freeze it.
5. Fill `study.py`: load the declared block, implement the frozen rule as a mask, score through
   the package (`engine.pnl.build_trade`, `research.protocol`), print the funnel. No parameter is a
   literal in the body; each is a named constant at the top with its derivation.
6. Add or claim the row in `docs/ROADMAP.md`.
7. Run it once. The analyst writes `findings.md`, opening with the `**Verdict:**` and
   `**Reproduce:**` lines (`research/README.md` step 7); you may draft the Reproduce commands, never
   the verdict.
8. Add the row to `research/catalogue.csv`, run `python -m earnings_iv_crush.ops.catalogue`, and
   update `docs/RESEARCH_STATE.md`, all in the same pull request.
