"""
config.py
Central configuration for the Earnings IV-Crush research framework.

All tunable parameters live here as two immutable dataclasses so the assumptions
behind a result are visible in one place rather than scattered across modules:

* ``GlobalConfig``   — account, pricing, cost and data-window settings.
* ``StrategyConfig`` — the filter, sizing, risk and regime parameters that
  define the strategy itself.

The module-level singletons ``GLOBAL`` and ``STRATEGY`` hold the canonical
values; the domain modules re-export the individual fields under their familiar
names (``ACCOUNT_SIZE``, ``IMPLIED_FAIR_RATIO``, ...) so this file is the single
source of truth without changing any public API.

API keys and secrets are a separate concern and live in ``data/config.py``
(loaded from the git-ignored ``.env``); they are deliberately not mixed in here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalConfig:
    """
    Account, pricing, cost and data-window settings.

    Attributes
    ----------
    account_size : float
        Reg-T account notional in USD. Drives position sizing. Defaults to
        ``250_000``.
    risk_free_rate : float
        Continuously compounded annual risk-free rate used in Black-Scholes
        pricing and IV inversion. Defaults to ``0.0`` (rates are a second-order
        effect on the short-dated straddles this strategy trades).
    contract_multiplier : int
        Shares per option contract. Defaults to ``100``.
    fills_per_straddle : int
        Commissionable fills per round-trip straddle (two legs, open and close).
        Defaults to ``4``.
    cost_per_contract : float
        Commission per contract per fill in USD (Khan & Khan 2024). Defaults to
        ``0.65`` (IBKR Pro).
    trading_days_per_year : int
        Business-day convention for annualising volatility and Sharpe ratios.
        Defaults to ``252``.
    back_month_min_gap_days : int
        Minimum gap between the front and back expiries when measuring the term
        structure. Defaults to ``21`` (~one month).
    start_date, end_date : str
        Default backtest window (``YYYY-MM-DD``). Alpaca's free option history
        begins ~Feb 2024, so the default window is calendar-2024.
    cache_dir : str
        Directory for cached data frames (git-ignored). Defaults to
        ``"data/processed"``.
    """

    # ── Account ──────────────────────────────────────────────────────────────
    account_size: float = 250_000

    # ── Pricing model ────────────────────────────────────────────────────────
    risk_free_rate: float = 0.0
    contract_multiplier: int = 100

    # ── Transaction costs ────────────────────────────────────────────────────
    fills_per_straddle: int = 4
    cost_per_contract: float = 0.65

    # ── Conventions ──────────────────────────────────────────────────────────
    trading_days_per_year: int = 252
    back_month_min_gap_days: int = 21

    # ── Data window / cache ──────────────────────────────────────────────────
    start_date: str = "2024-02-01"
    end_date: str = "2024-12-31"
    cache_dir: str = "data/processed"


@dataclass(frozen=True)
class StrategyConfig:
    """
    The filter, sizing, risk and regime parameters that define the strategy.

    Attributes
    ----------
    implied_fair_ratio : float
        Gate 1. Trade only when the implied event move is at least this multiple
        of the regression fair move. Defaults to ``1.20``.
    term_spread_pctl : float
        Gate 2. Trade only when the front-minus-back ATM IV term spread is above
        this percentile of its trailing distribution. Defaults to ``0.75``.
    trailing_window : int
        Length of the term-spread trailing window — trading days for the
        per-name panel gate, or events for the legacy gate. Defaults to ``30``.
    term_min_periods : int
        Minimum daily observations before the panel term gate will fire.
        Defaults to ``15``.
    asof_offset_days : int
        Business days before the announcement at which the position is entered.
        Defaults to ``1``.
    holding_days : int
        Business days the position is held after the announcement. Defaults to
        ``2``.
    risk_frac_per_trade : float
        Worst-case capital at risk per position as a fraction of NAV. Defaults
        to ``0.01`` (1 %).
    premium_stop_multiple : float
        Stop the naked straddle when its value reaches this multiple of the
        entry credit. Defaults to ``3.0``.
    drawdown_circuit_breaker : float
        Portfolio drawdown that halts new entries. Defaults to ``0.15`` (15 %).
    max_per_ticker : int
        Maximum concurrent positions per underlying. Defaults to ``1``.
    max_per_sector : int
        Maximum positions opened per sector per day. Defaults to ``3``.
    vix_defensive_threshold : float
        VIX level above which the regime selector switches to the defined-risk
        iron fly. Defaults to ``25.0``.
    calendar_min_term_spread : float
        Minimum term-structure premium for the calendar variant. Defaults to
        ``0.10``.
    calendar_dominance : float
        Term-structure dominance multiple required to favour the calendar.
        Defaults to ``1.0``.
    """

    # ── Entry filters ────────────────────────────────────────────────────────
    implied_fair_ratio: float = 1.20
    term_spread_pctl: float = 0.75
    trailing_window: int = 30
    term_min_periods: int = 15

    # ── Trade timing ─────────────────────────────────────────────────────────
    asof_offset_days: int = 1
    holding_days: int = 2

    # ── Risk and sizing ──────────────────────────────────────────────────────
    risk_frac_per_trade: float = 0.01
    premium_stop_multiple: float = 3.0
    drawdown_circuit_breaker: float = 0.15
    max_per_ticker: int = 1
    max_per_sector: int = 3

    # ── Regime selector ──────────────────────────────────────────────────────
    vix_defensive_threshold: float = 25.0
    calendar_min_term_spread: float = 0.10
    calendar_dominance: float = 1.0


# Canonical singletons. Domain modules import these and re-export the individual
# fields under their established names, so this file stays the single source of
# truth without altering any public API.
GLOBAL = GlobalConfig()
STRATEGY = StrategyConfig()
