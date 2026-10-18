# Document index: which file owns which question

Every markdown file in the repository matches a row here, and `tests/test_docs.py` fails if one
does not. One question has one owner; if you are about to write the same fact into a second file,
link to the owner instead. Live figures are not owned by any document: `python -m
earnings_iv_crush.ops.orient` measures them.

| Path or glob | Role | Owns |
|---|---|---|
| `README.md` | entry | Where a person starts: what the project is, setup, layout, glossary |
| `CLAUDE.md` | rules | The hard rules agents work under; no result figures |
| `CONTRIBUTING.md` | rules | Branches, pull requests, code standard, the order-path rule for contributors |
| `docs/INDEX.md` | manifest | This table |
| `docs/SYSTEM.md` | canonical | What we trade, what the evidence says, how it runs, standing decisions, the bar for new results |
| `docs/RESEARCH_STATE.md` | ledger | The trial count, every closed direction and its number, the never-quote list |
| `docs/ROADMAP.md` | ledger | Every open item, its owner and status |
| `docs/PROTOCOL.md` | rules | The research rules P1 to P15 and how a result is reported |
| `docs/DATA.md` | reference | Sources, licences, costs, the shared bucket and the manifest |
| `docs/ARCHITECTURE.md` | reference | Code layout, the live-path map, valuation, costs, reporting, tests |
| `docs/RUNBOOK.md` | reference | Operating the paper book: setup, the daily pass, switches, alarms |
| `docs/FORWARD_TEST_SPEC.md` | canonical | The paper book's rules, ladder, limits, logs and verdict criteria |
| `docs/REFERENCES.md` | reference | Published work the project builds on or differs from |
| `docs/HISTORY.md` | reference | What the hand-off moved or removed, and how to recover it |
| `docs/decisions/*.md` | ledger | One decision record each |
| `docs/reference/*.md` | reference | Dated documents kept for their detail; each says which sections are superseded |
| `research/README.md` | rules | How a study is run, from the closed-list check to the findings note |
| `research/*/README.md` | reference | One research line: its code, pre-registrations and findings |
| `research/*/preregs/*.md` | record | Frozen pre-registrations, hash-verified; never edited |
| `research/*/findings/*.md` | record | Dated findings, each true as of its date |
| `research/_template/*.md` | template | The card and pre-registration a new study starts from |
| `research/*/*/*.md` | record | A new study's card, pre-registration and findings |
| `scripts/README.md` | reference | The stable entry points and the data builders |
| `deploy/README.md` | reference | The cloud host for the paper book |
| `work-logs/**/*.md` | record | Session logs, one folder per person |
| `.claude/README.md` | desk | The map of the Claude Code configuration |
| `.claude/rules/*.md` | desk | Path-scoped rules |
| `.claude/skills/*/SKILL.md` | desk | One workflow each |
| `.claude/agents/*.md` | desk | One reviewer each |
| `.github/*.md` | desk | The pull request template |
