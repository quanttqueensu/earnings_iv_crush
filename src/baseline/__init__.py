"""The Agent 0 control: an unfiltered short-straddle book.

Kept separate from `strategy` on purpose. Agent 0 is not part of the edge; it
is the benchmark the filtered strategy must beat by >= 0.5 Sharpe.
"""
