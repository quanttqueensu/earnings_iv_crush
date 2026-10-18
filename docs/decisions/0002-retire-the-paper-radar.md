# 0002. The paper radar is retired; the IBKR paper book is the forward record
*Date: 2026-10-18 · Status: Accepted*

**Context:** The radar was a GitHub Actions recorder that booked hypothetical trades from free
yfinance chains after the close. By 2026-09-11 it held 18 trades on 7 exit dates, and from about
2026-09-22 its UTC run date booked 12 exits on the evening before the announcement reaction. Its
fixes were never deployed. It measured nothing about execution, which is where every test since
has failed.

**Decision:** Retire it. Its workflow, scripts, seed file and tests are removed; the last commit
of its ledger on the private recorder repository is tagged `radar-final`. The forward record is
the IBKR paper book, which trades real order lifecycles through the ladder in
`docs/FORWARD_TEST_SPEC.md`.

**Consequences:** No free-data forward mark exists any more. The paper book needs a gateway and,
for P&L evidence, real-time quotes (`docs/ROADMAP.md` B9).
