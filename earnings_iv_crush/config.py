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
        begins ~Feb 2024; the window runs from there to the most recent full
        trading week.
    cache_dir : str
        Directory for cached data frames (git-ignored). Defaults to
        ``"data/processed"``.
    universe : str
        Default backtest universe name (see ``data/universe.py``). One of
        ``"megacap"`` or ``"broad"``. Defaults to ``"megacap"``.
    min_oi : int
        Minimum open interest for a quote to count as tradeable in the
        data-quality filter. Defaults to ``100``.
    min_volume : int
        Minimum daily contract volume for a quote to pass the quality filter.
        Defaults to ``10``.
    max_rel_spread : float
        Maximum relative bid-ask spread accepted by the quality filter. With
        Alpaca's close-as-bid/ask data the spread is synthetic, so this gate
        only binds when a provider supplies real NBBO. Defaults to ``0.10``.
    use_oi_proxy : bool
        Whether the fair-move model may use the current-snapshot open-interest
        proxy. The proxy is not point-in-time, so it defaults to ``False`` and
        should only be enabled for robustness appendices.
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
    end_date: str = "2026-06-05"
    cache_dir: str = "data/processed"

    # ── Universe / data quality ──────────────────────────────────────────────
    universe: str = "megacap"
    min_oi: int = 100
    min_volume: int = 10
    max_rel_spread: float = 0.10
    use_oi_proxy: bool = False


@dataclass(frozen=True)
class StrategyConfig:
    """
    The filter, sizing, risk and regime parameters that define the strategy.

    Attributes
    ----------
    implied_fair_ratio : float
        Gate 1 threshold. When Gate 1 is active, trade only when the implied
        event move is at least this multiple of the regression fair move.
        Defaults to ``1.20``.
    use_move_gate : bool
        Whether Gate 1 (the implied/fair move filter) is applied. Defaults to
        ``False``: out-of-sample validation showed the move gate does not add
        risk-adjusted return over the term gate alone (it fails its own
        expanding-window test), so the baseline selects on the term structure
        only. Set ``True`` to restore the two-gate book.
    term_spread_pctl : float
        Gate 2. Trade only when the front-minus-back ATM IV term spread is above
        this percentile of its trailing distribution. Defaults to ``0.80`` (the
        interior-stable operating point of the per-trade Sharpe surface).
    trailing_window : int
        Length of the term-spread trailing window — trading days for the
        per-name panel gate, or events for the legacy gate. Defaults to ``30``.
    term_min_periods : int
        Minimum daily observations before the panel term gate will fire.
        Defaults to ``15``.
    asof_offset_days : int
        Business days before the announcement at which the position is entered
        (synthetic path only; the real assembler is session-aware). Defaults to
        ``1``.
    holding_days : int
        Business days the position is held after the announcement (synthetic
        path only). Defaults to ``2``.
    min_exit_dte_days : int
        Minimum trading days of option life that must remain at exit. The real
        assembler picks the nearest post-announcement expiry leaving at least
        this many days so the exit is marked on live time value (the IV crush)
        rather than settling at intrinsic. Defaults to ``2``.
    default_session : str
        Reporting session assumed when the earnings calendar carries no
        ``session``/``hour`` flag: ``"amc"`` (after close), ``"bmo"`` (before
        open) or ``"dmh"`` (during hours, treated as ``bmo``). Defaults to
        ``"amc"`` (the modal session, conservative on time value).
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
    use_move_gate: bool = False
    term_spread_pctl: float = 0.80
    trailing_window: int = 30
    term_min_periods: int = 15

    # ── Trade timing ─────────────────────────────────────────────────────────
    asof_offset_days: int = 1
    holding_days: int = 2
    min_exit_dte_days: int = 2
    default_session: str = "amc"

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


@dataclass(frozen=True)
class LiveConfig:
    """
    Paper-trading / live-execution settings for the Interactive Brokers loop.

    These govern the forward paper-trading harness only (``earnings_iv_crush.live``
    and ``scripts/paper_trade_ibkr.py``); the research backtest never reads them.
    They are kept here so the one place that holds assumptions also holds the
    execution wiring, but no broker credential ever lives in this file - TWS / IB
    Gateway holds the login, and the only secrets are the data-feed keys in
    ``.env`` (see ``data/config.py``).

    Attributes
    ----------
    ib_host : str
        Host the TWS / IB Gateway API listens on. Defaults to ``"127.0.0.1"``.
    ib_paper_port : int
        Socket port for the **paper** account. TWS paper is ``7497`` (IB Gateway
        paper is ``4002``). Defaults to ``7497``.
    ib_live_ports : tuple of int
        Ports that belong to a **live** account (TWS ``7496``, IB Gateway
        ``4001``). The connection guard refuses to connect to any of these so the
        loop can never reach a funded account. Defaults to ``(7496, 4001)``.
    ib_client_id : int
        API client id for this session. Any integer unique among connected API
        clients. Defaults to ``17``.
    kill_switch_file : str
        Path to a sentinel file; when it exists the loop places no new orders
        (existing positions are untouched). Lets you halt entries without killing
        the scheduled task. Defaults to ``"outputs/live/STOP"``.
    open_positions_path, paper_ledger_path : str
        Parquet stores for open paper positions (entry leg, no exit yet) and the
        completed-trade ledger (the backtest's ``LEDGER_COLUMNS`` schema).
    skew_history_path, term_panel_path : str
        Parquet stores for the accumulating per-event skew history (the skew
        gate's expanding cross-section) and the per-name daily term-spread panel
        (the term gate's trailing window).
    skew_seed_path : str
        Cached research events whose ``skew_25d`` seeds the skew gate before the
        live book has enough of its own history. Defaults to the megacap sample.
    strike_window : float
        Half-width of the strike band pulled around spot, as a fraction of spot.
        Defaults to ``0.20``.
    horizon_days : int
        Calendar days past the as-of date to include option expiries when
        snapshotting the chain. Defaults to ``90``.
    entry_offset_days : int
        Business days before the announcement at which the position is entered.
        Defaults to ``1`` (enter the session before the report).
    skew_keep_frac : float
        Keep an event only if its ``skew_25d`` is at or below this quantile of the
        prior skew cross-section (the validated low-skew gate). Defaults to
        ``0.67``.
    term_pctl : float
        Term-gate percentile, mirrored from ``StrategyConfig`` so the live gate
        matches the backtest. Defaults to ``0.80``.
    order_type : str
        ``"LMT"`` (marketable limit, recommended) or ``"MKT"``. Defaults to
        ``"LMT"``.
    limit_cross_frac : float
        For a limit order, the fraction of the bid-ask spread to give up to be
        marketable (0 = sit on the near touch, 1 = cross fully). Defaults to
        ``0.5``.
    exit_reprice_steps : int
        Number of reprice steps the transmitting managed buy-back walks from its
        initial mid-seeking limit toward the touch before crossing fully. ``0``
        posts once and never reprices. Defaults to ``2``.
    exit_step_wait_s : float
        Seconds the managed buy-back rests at each price step waiting for a fill
        before repricing. Defaults to ``10.0``.
    """

    ib_host: str = "127.0.0.1"
    ib_paper_port: int = 7497
    ib_live_ports: tuple[int, ...] = (7496, 4001)
    ib_client_id: int = 17

    kill_switch_file: str = "outputs/live/STOP"
    open_positions_path: str = "outputs/live/open_positions.parquet"
    paper_ledger_path: str = "outputs/live/paper_ledger.parquet"
    skew_history_path: str = "outputs/live/skew_history.parquet"
    term_panel_path: str = "outputs/live/term_panel_live.parquet"
    skew_seed_path: str = "outputs/research/events_megacap_v2.parquet"

    strike_window: float = 0.20
    horizon_days: int = 90
    entry_offset_days: int = 1

    skew_keep_frac: float = 0.67
    term_pctl: float = 0.80

    order_type: str = "LMT"
    limit_cross_frac: float = 0.5
    exit_reprice_steps: int = 2
    exit_step_wait_s: float = 10.0


# Canonical singletons. Domain modules import these and re-export the individual
# fields under their established names, so this file stays the single source of
# truth without altering any public API.
GLOBAL = GlobalConfig()
STRATEGY = StrategyConfig()
LIVE = LiveConfig()
