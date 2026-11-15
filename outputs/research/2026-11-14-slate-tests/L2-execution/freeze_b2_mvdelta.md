# Freeze note: B2 minimum-variance delta (trial 2,902)

Written after the 2013-18 fit and discovery read (diagnosis.log entries [10] and [12]) and before
any 2019-24 read. The coefficients in b2_coefficients.json were fitted on 2013-18 chains only and
are frozen with the scorer b2_mvdelta.py and its helper l2lib.py.

Discovery failed the declared pass rule (variance ratio 1.0016 [0.9985, 1.0047]), so the single
2019-24 read is exploratory and cannot make B2 a finding.

block_is_clean (research/ledger/blocks.csv), period 2019-24, outcome hedged_hold, feature family
execution_min_variance_delta: True for base_corrected and hedged_event_hold; the hedged_hold
outcome on 2019-24 has been viewed before by other families.

Reading: variance ratio and paired mean with date-clustered intervals, and the c_hedge and
c_equity_cost split, with `b2_mvdelta.py --block 2019-24`.

Frozen files (sha256):
- b2_mvdelta.py: e7c11656249f82dc7c40868238ee02aefda0b189c02d2d476c84d7ae634a5e63
- b2_coefficients.json: 2ca134f14f8cade0cd2f6e2cee37d3b2ddac584f4ed1f140ee220fc379fabbcc
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63

Self sha256 (sha256 of every byte above this line, LF endings): 560710306dfdbd25c6bc065dc439203697dd51fd9f1d94ece86b971df054eaf8
