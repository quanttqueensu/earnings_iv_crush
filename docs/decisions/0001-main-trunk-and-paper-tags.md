# 0001. Main is the trunk; each version the paper book runs is tagged
*Date: 2026-10-18 · Status: Accepted*

**Context:** Several people now change the same repository, and one of its entry points sends
orders to a paper account every session. Research changes must not reach the order path by
accident, and any forward result has to name the exact code that produced it.

**Decision:** `main` is protected. Changes arrive by pull request with green CI, and the team lead
is code owner for `earnings_iv_crush/live/`, `earnings_iv_crush/config.py`,
`earnings_iv_crush/frozen.py`, the drivers and every pre-registration. The commit the paper book
runs from is tagged `paper-YYYY-MM-DD` before the first session on it. Research happens on
short-lived branches.

**Consequences:** A forward trade joins to its code through the tag in force on its entry date.
An experiment branch cannot change what the paper account trades.
