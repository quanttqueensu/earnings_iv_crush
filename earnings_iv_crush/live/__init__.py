"""
earnings_iv_crush.live
Forward paper-trading harness for the filtered earnings IV-crush strategy.

This package places the *same* selection logic the backtest validated against a
live Interactive Brokers **paper** account, so the forward book is directly
comparable to the out-of-sample research. It is deliberately thin and split by
concern:

* ``ib_connection`` - connect to TWS / IB Gateway with a hard paper-port guard
  and a kill-switch file, so the loop can never reach a funded account and can be
  halted without killing the scheduled task;
* ``ib_market`` - qualify the underlying and snapshot an option chain (with model
  implied vol) into the canonical chain schema the feature maths already expects;
* ``ib_orders`` - build and (optionally) transmit the short-straddle legs;
* ``paper_book`` - persist open positions, accumulate the skew / term histories
  the causal gates need, and mark exits into the backtest's ledger schema.

The orchestration lives in ``scripts/paper_trade_ibkr.py``. Nothing here imports
``ib_async`` at module import time except the order/market/connection modules,
which fail with a clear message if the optional dependency is missing.
"""

from __future__ import annotations
