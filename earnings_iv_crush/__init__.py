"""Earnings IV-Crush.

A filtered, cross-sectional short-volatility strategy around scheduled earnings:
sell pre-earnings ATM straddles only on names whose implied event move is rich
versus a regression fair move and whose front-week term structure is steep, then
hold into the post-event implied-volatility collapse.
"""
