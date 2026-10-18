---
name: log-work
description: Log a work session by gathering the evidence (commits, files, study runs) since the last entry and adding the analyst's own short update to work-logs/<handle>/YYYY-MM.md. Use at the end of a session or when asked to log work.
---

# Log work

Claude gathers the evidence; the analyst writes the update.

1. **Who.** Handle from `git config ivcrush.handle`; if unset, ask for the GitHub handle and save it
   with `git config ivcrush.handle <handle>`. Email from `git config user.email`.
2. **Since when.** The newest entry in `work-logs/<handle>/YYYY-MM.md` ends with
   `Evidence through: <sha> . <date>`. Use `<sha>..HEAD` if it is an ancestor, else `--since=<date>`,
   else the last seven days.
3. **Evidence**, excluding `work-logs/`: commits by that email with links
   (`https://github.com/quanttqueensu/earnings_iv_crush/commit/<sha>`), files touched grouped as
   studies, pre-registrations, findings, code, tests and docs; uncommitted paths from
   `git status --porcelain`; new folders under `outputs/research/` marked local.
4. **Ask exactly one question**: "In two to four sentences, in your own words: what did you work
   on, what did you learn, and what is next or blocking you?" Paste the answer verbatim. If asked
   to write it, decline: the update is theirs.
5. **Write** the entry at the top of this month's file:
   ```markdown
   ## YYYY-MM-DD HH:MM . <topic>
   **Update (by <first name>):** <their words>

   **Evidence**
   - Commits: ...
   - Files: ...

   <sub>Evidence through: <sha> . YYYY-MM-DD</sub>
   ```
6. Show it and ask "Commit this log?" If yes, stage only that file and commit as
   `Work log: <handle> YYYY-MM-DD`, with no attribution lines. Never push.
