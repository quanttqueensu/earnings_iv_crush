---
name: book-status
description: Report the paper book's state and today's plan without placing any order. Use when asked how the paper book is doing, what it will trade today, or whether the last pass was clean.
---

# Paper book status

Read-only. Nothing in this skill connects with transmit or places an order.

1. `python -m earnings_iv_crush.ops.orient` for switches, gateway, open positions and lifecycle
   completeness.
2. Read the tail of `outputs/live/order_events.csv` and `outputs/live/intended_trades.csv` for the
   last pass: admitted events, outcomes, any alarm rows, any lifecycle without a terminal status.
3. For today's plan, a dry run is allowed only when the team lead asks:
   `python -m scripts.paper_trade_ibkr session --dry-run` (it waits for the ladder times; say so).
4. Report: positions open and due, last pass outcome, alarms and what `docs/RUNBOOK.md` section 5
   says to do about each, and whether the operational go counter (20 clean sessions) has advanced.

Never report a P&L figure from the book before the operational go, and never one built on delayed
market data as evidence.
