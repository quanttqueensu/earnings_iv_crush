"""Strategy-agnostic machinery: option pricing and the backtest engine.

Nothing here knows which book is running. Both the filtered strategy and the
Agent 0 control produce a trade ledger that `backtester` scores identically.
"""
