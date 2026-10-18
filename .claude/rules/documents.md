---
paths:
  - "docs/**"
  - "README.md"
  - "CONTRIBUTING.md"
  - "research/**/findings/**"
  - "research/**/README.md"
---

# Documents

- **One owner per question.** `docs/INDEX.md` says which file owns what; link to the owner
  rather than restating it. A new markdown file gets an INDEX row (`tests/test_docs.py` checks).
- **Every number checkable**: N, the interval, the basis (per trade or per year, net or gross,
  per side or round trip) and the source file beside it. Never from memory.
- **Never quote** a figure in `docs/RESEARCH_STATE.md` section 4.
- **Supersede in the same change.** When a result replaces another, mark or remove the old one in
  the same commit.
- British spelling, commas or full stops instead of em dashes, finished prose, no filler.
- Findings are the analyst's own words; an agent drafts structure and gathers evidence only.
