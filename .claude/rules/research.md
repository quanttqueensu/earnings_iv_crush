---
paths:
  - "research/**"
  - "earnings_iv_crush/research/**"
---

# Research code

The full rules are `docs/PROTOCOL.md` (P1 to P15); these are the ones that bite in this folder.

- **Closed studies are frozen.** A module directly under `research/<line>/` produced a recorded
  result. Do not edit its logic; a fix that changes a number is a new study with its own
  pre-registration. New work lives in `research/<line>/<YYYY-MM-DD-slug>/`, copied from
  `research/_template/`.
- **Pre-registrations are hashed.** Never edit `research/*/preregs/*.md`. Amend with a new dated
  file and record its hash.
- **Use the protocol module**: `verify_prereg` first, `date_clustered_ci` for every interval,
  `matched_random_null` for every selector (`earnings_iv_crush/research/protocol.py`).
- **Score selectors on residual value**, not realised P&L (`research/selection/reverse_alpha_lib.py`).
- **Causal**: every threshold at event i uses strictly earlier events (`research/gates.py`).
- **Funnel**: print counts at every filter; test attrition for outcome dependence.
- **Count the trial** in `docs/RESEARCH_STATE.md` in the same commit.
