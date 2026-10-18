# The desk: how this repository is configured for Claude Code

`CLAUDE.md` at the root is the always-on context: the hard rules for the order path, research,
data, code and git. Everything here is the machinery around it.

```
.claude/
  settings.json   shared permissions and hooks (personal overrides go in settings.local.json)
  hooks/          advisory scripts; none blocks
  rules/          path-scoped context that loads when matching files are opened
  skills/         workflows you or Claude invoke as /name
  agents/         specialist reviewers (subagents)
```

Start every session with `/orient`, or `python -m earnings_iv_crush.ops.orient`. The SessionStart
hook runs it for you.

## Permissions

`settings.json` denies reading or editing `.env` and anything that would create the transmit
marker. It asks before editing a pre-registration, a hash record, the order path, `config.py`,
`frozen.py` or the live stores; before any transmitting run, metered builder, bucket upload, push,
hard reset, clean, rebase or install. It allows the test suite, the linters, `orient`, `sync
verify`, the demo, `validate_screen` and a dry-run session. Put personal additions in
`.claude/settings.local.json`, which is git-ignored.

## Hooks

| Hook | Event | What it does |
|---|---|---|
| `session_context.py` | SessionStart | Runs `orient` and adds the report and the three most important reminders to the session. |
| `post_edit_check.py` | PostToolUse (Edit, Write) | Never blocks. Flags, on the text just added, the defect classes this project has shipped: a square root of 252, `fillna`, a swallowed exception, `sys.path` in the package, Alpaca data in research code, code touching the transmit marker; and warns when a frozen pre-registration, a closed study or the order path is edited. |

Hooks call `python`, so start Claude Code from a shell with the project's environment active.

## Rules

| File | Loads when you open |
|---|---|
| `research.md` | `research/**`, `earnings_iv_crush/research/**` |
| `live-trading.md` | `earnings_iv_crush/live/**`, the paper-book script and drivers, `deploy/**`, `outputs/live/**` |
| `data.md` | `earnings_iv_crush/data/**`, `scripts/build/**`, `data/**` |
| `documents.md` | `docs/**`, the README, contributing guide, findings and line READMEs |

## Skills

| Skill | Use it for |
|---|---|
| `/orient` | Measured state and what needs attention |
| `/graveyard` | Has this idea been tested? Read before proposing anything |
| `/new-study` | Start a study: card, pre-registration, scorer skeleton |
| `/prereg` | Write and freeze a pre-registration |
| `/repro` | Reproduce a recorded number before quoting it |
| `/book-status` | The paper book's state and today's plan, read-only |
| `/log-work` | End-of-session work log in your own words |

## Agents

| Agent | Seat |
|---|---|
| `quant-reviewer` | Look-ahead, basis, inference, attrition and valuation errors in a result |
| `beta-detector` | Adversarial: tries to show an edge is an artefact, a known premium or luck |
| `execution-trader` | Reviews order-path changes and interprets fills |

## Maintaining this

- A convention an agent gets wrong twice goes into `CLAUDE.md`, or a `rules/` file if it is
  path-specific.
- A prompt typed a third time becomes a skill.
- Something that must happen every time becomes a hook, with a test in `tests/test_claude_hooks.py`.
- Numbers never go in these files; they come from `orient` or a findings file.
