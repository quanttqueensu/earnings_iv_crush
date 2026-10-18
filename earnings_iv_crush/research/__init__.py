"""
earnings_iv_crush.research
Shared research infrastructure used across study lines.

* ``market_marks`` - scores straddles on their actual two-leg market marks (the frozen
  specification's marking and ledger path);
* ``gates`` - the causal, expanding term and skew masks;
* ``chains`` - quote-marked OPRA chain fetch, parse and straddle marking;
* ``protocol`` - pre-registration verification, the date-clustered bootstrap and the
  participation-matched random null, for new studies.

Closed studies live under ``research/`` at the repository root and import from here.
"""

from __future__ import annotations
