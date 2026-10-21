"""
config.py
Central configuration for the Earnings IV-Crush research framework.

All tunable parameters live here as two immutable dataclasses so the assumptions
behind a result are visible in one place rather than scattered across modules:

* ``GlobalConfig``   - account, pricing, cost and data-window settings.
* ``StrategyConfig`` - the filter, sizing, risk and regime parameters that
  define the strategy itself.

The module-level singletons ``GLOBAL`` and ``STRATEGY`` hold the canonical
values; the domain modules re-export the individual fields under their familiar
names (``ACCOUNT_SIZE``, ``IMPLIED_FAIR_RATIO``, ...) so this file is the single
source of truth without changing any public API.

API keys and secrets are a separate concern and live in ``data/config.py``
(loaded from the git-ignored ``.env``); they are deliberately not mixed in here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ── environment overrides ────────────────────────────────────────────────────
# Only the deployment wiring of ``LiveConfig`` reads the environment: a container
# reaches the gateway at a different host and port than a desktop TWS, and the
# cloud book trades a different universe. Research parameters never do, so a
# stray variable cannot change a backtest.


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name}={raw!r} is not a boolean (use true/false).")


SELECTION_RULES = ("unconditional", "term_q80")


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
    earnings_source : str
        Provider for the earnings calendar (announce date + bmo/amc session).
        ``"finnhub"`` (default) is the live free-tier calendar; ``"wrds"`` sources
        the date from Compustat ``fundq.rdq`` and the session from I/B/E/S
        announcement times via the WRDS R2 mirror (``data/wrds_r2.py``).
    spot_source : str
        Provider for equity spot / OHLCV. ``"yfinance"`` (default) or ``"crsp"``
        (CRSP daily stock file on the WRDS mirror, split-factor aware).
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

    # ── Data providers ───────────────────────────────────────────────────────
    earnings_source: str = "finnhub"
    spot_source: str = "yfinance"
    option_source: str = "databento"  # "databento", "databento_quotes", "alpaca"
    # What the bid/ask columns of a chain actually contain. "close" means the
    # adapter wrote the daily closing *trade* on both sides (bid == ask == close),
    # which is what every trade-based provider here does; "quote" means a genuine
    # two-sided market. This is not cosmetic: a book marked on closes and one marked
    # on quotes are different books with different Sharpes, and without this key a
    # cached events file gives no way to tell which one it is. It travels in the
    # provenance stamp so a re-marked cache can never be loaded as a close-marked
    # one, or the reverse.
    mark_basis: str = "close"  # "close" or "quote"
    # Market bundle and chain provider (see data/providers.py). ``market``
    # selects the calendar/spot/chain trio; ``chain_source`` overrides just the
    # chain provider ("alpaca" or "dolthub") or takes the market default when
    # None. The only registered market is "us".
    market: str = "us"
    chain_source: str | None = None


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
        Length of the term-spread trailing window - trading days for the
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
        Host the TWS / IB Gateway API listens on. Defaults to ``"127.0.0.1"``;
        override with ``IB_HOST`` (``ib-gateway`` inside the cloud compose stack).
    ib_paper_port : int
        Socket port for the **paper** account. TWS paper is ``7497``, IB Gateway
        paper is ``4002``, and the dockerised gateway relays paper on ``4004``
        because the gateway itself only accepts loopback connections. Defaults to
        ``7497``; override with ``IB_PORT``.
    ib_live_ports : tuple of int
        Ports that belong to a **live** account (TWS ``7496``, IB Gateway
        ``4001``, dockerised relay ``4003``). The connection guard refuses to
        connect to any of these so the loop can never reach a funded account.
        Not overridable from the environment by design.
    ib_client_id : int
        API client id for this session. Any integer unique among connected API
        clients. Defaults to ``17``.
    ib_market_data_type : int
        IB market-data mode requested once per session: ``1`` live, ``2`` frozen,
        ``3`` delayed, ``4`` delayed-frozen. A paper account with no OPRA/network
        subscription returns NaN on every field under ``1``, which silently skips
        every candidate; ``4`` serves delayed quotes during the session and the
        last delayed snapshot after the close, so the harness accrues a book on an
        unsubscribed account. Defaults to ``4``. Set to ``1`` once real-time
        entitlements are in place - delayed quotes are adequate for the signal but
        not for the fill-quality study. Override with ``IB_MARKET_DATA_TYPE``.
    selection_rule : str
        Which entry rule the forward book applies, one of ``SELECTION_RULES``.
        ``"unconditional"`` trades every eligible universe event; ``"term_q80"``
        applies the term gate at ``term_pctl``. Defaults to ``"unconditional"``:
        the term gate's pre-registered 2025-26 out-of-sample per-trade Sharpe is
        -0.21 with a date-clustered CI excluding zero, so it is kept only for
        comparison, while the unconditional book (+0.043, CI containing zero) is
        the baseline any new selector is measured against. Override with
        ``SELECTION_RULE``.
    universe_path : str
        File whose ``ticker`` column defines the tradable universe (CSV or
        parquet). Defaults to ``data/universe_broad.csv``, the 346 names of the
        2025-26 broad block on which the unconditional baseline was measured. It
        is a plain ticker list, tracked in the repository so a fresh clone trades
        the specified population; the session pass refuses to run without it
        rather than falling back to the whole calendar tape. Override with
        ``UNIVERSE_PATH``.
    kill_switch_file : str
        Path to a sentinel file; when it exists the loop places no new orders
        (existing positions are untouched). Lets you halt entries without killing
        the scheduled task. Defaults to ``"outputs/live/STOP"``.
    open_positions_path, paper_ledger_path : str
        Parquet stores for open paper positions (entry leg, no exit yet) and the
        completed-trade ledger (the backtest's ``LEDGER_COLUMNS`` schema).
    heartbeat_path : str
        Parquet store recording, per entry pass, how many candidates were seen,
        priced and gated. An empty book is the expected state of a healthy harness
        waiting for earnings season and also the state of a harness that has been
        failing on every candidate for weeks; without a per-pass count the two are
        the same string in the report. ``forward_report`` reads this to distinguish
        them and raises an alarm when candidates are seen but none price.
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
        Defaults to ``1`` (enter the session before the report). Ignored when
        ``session_aware_timing`` is set.
    session_aware_timing : bool
        Derive entry and exit from the announcement's reporting session rather
        than a fixed offset. The backtest brackets each print by the closes
        either side of it, a one-session hold: an ``amc`` name is entered on the
        announcement day and exited the next, a ``bmo`` name the reverse. The
        fixed offset applies the ``bmo`` entry and the ``amc`` exit to every
        name, so both cases hold two sessions instead of one, doubling exposure
        to post-print drift and to the day of decay the crush does not pay for.
        Defaults to ``True``, which matches the backtest and the forward-test
        specification; the fixed offset survives only for the legacy ``enter``
        preview. Names whose session is unknown are skipped rather than guessed.
        Override with ``SESSION_AWARE_TIMING``.
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
    exit_cancel_settle_s : float
        Seconds the managed buy-back waits after cancelling its unfilled orders
        before re-reading their status. A fill can reach the exchange ahead of the
        cancel; reading the status straight after sending the cancel books that leg
        as unfilled while the broker has in fact closed it. Defaults to ``2.0``,
        several gateway round trips.
    halt_file : str
        Second switch. When it exists, nothing transmits on any path (entry, exit,
        flatten), and working orders are cancelled at the next rung. ``STOP``
        blocks entries only, so the book can still be flattened; ``HALT`` is for
        incidents in which the ladder itself is suspect. Defaults to
        ``"outputs/live/HALT"``.
    dry_dir : str
        Directory for every store a dry-run pass writes. A dry pass must never
        write to the stores a transmitting exit reads, or it could mark a short
        the broker still holds as closed. Defaults to ``"outputs/live/dry"``.
    order_events_path : str
        Append-only CSV of every order state change (forward-test specification
        section 6), written before the harness acts on the event. CSV rather than
        parquet because a parquet append rewrites the file, which loses the log if
        the process dies mid-write. Defaults to ``"outputs/live/order_events.csv"``.
    intended_path : str
        Append-only CSV of every admitted event and its outcome, filled or not.
        The paired-improvement measure counts unfilled entries at zero, so they
        must be recorded. Defaults to ``"outputs/live/intended_trades.csv"``.
    ladder_rungs : tuple of (str, float)
        Rung schedule, ``(HH:MM:SS ET, fraction of the way from mid to the
        touch)``. The ladder finishes before the 15:59 mark the backtest uses, in
        the tightest part of the option session. Defaults to the specification's
        five rungs from 15:45:00 at mid to 15:55:00 at the touch.
    ladder_cancel_at, ladder_nbbo_at : str
        Times (ET) at which every working order is cancelled, and at which the
        NBBO of every held or intended leg is recorded as the backtest's
        counterfactual basis. Defaults to ``"15:58:00"`` and ``"15:59:00"``.
    ladder_latest_start : str
        Latest time (ET) a pass may begin pricing. A pass that starts after the
        final rung cannot run the ladder and must not improvise one, so it raises
        an alarm and sends nothing. Defaults to ``"15:54:00"``.
    max_names_per_day : int
        Entry cap. The specification's value is 12 (keeps 81.7% of 2025-26
        trades); the default of 3 is the shakedown value, held until 20
        consecutive sessions run with zero reconciliation breaks, so a ladder
        defect touches at most three names. Override with ``MAX_NAMES_PER_DAY``.
    max_contracts_per_leg : int
        Fat-finger guard on the per-leg quantity. Return on margin is scale-free,
        so the cap changes no reported figure except through integer rounding. The
        specification's value is 20; the shakedown default is 5. No environment
        override, because it protects the account.
    """

    ib_host: str = field(default_factory=lambda: _env_str("IB_HOST", "127.0.0.1"))
    ib_paper_port: int = field(default_factory=lambda: _env_int("IB_PORT", 7497))
    ib_live_ports: tuple[int, ...] = (7496, 4001, 4003)
    ib_client_id: int = 17
    ib_market_data_type: int = field(default_factory=lambda: _env_int("IB_MARKET_DATA_TYPE", 4))

    selection_rule: str = field(default_factory=lambda: _env_str("SELECTION_RULE", "unconditional"))

    kill_switch_file: str = "outputs/live/STOP"
    open_positions_path: str = "outputs/live/open_positions.parquet"
    paper_ledger_path: str = "outputs/live/paper_ledger.parquet"
    heartbeat_path: str = "outputs/live/entry_heartbeat.parquet"
    skew_history_path: str = "outputs/live/skew_history.parquet"
    term_panel_path: str = "outputs/live/term_panel_live.parquet"
    skew_seed_path: str = "outputs/research/events_megacap_v2.parquet"
    universe_path: str = field(
        default_factory=lambda: _env_str("UNIVERSE_PATH", "data/universe_broad.csv")
    )

    strike_window: float = 0.20
    horizon_days: int = 90
    entry_offset_days: int = 1
    session_aware_timing: bool = field(
        default_factory=lambda: _env_bool("SESSION_AWARE_TIMING", True)
    )

    skew_keep_frac: float = 0.67
    term_pctl: float = 0.80

    order_type: str = "LMT"
    limit_cross_frac: float = 0.5
    exit_reprice_steps: int = 2
    exit_step_wait_s: float = 10.0
    exit_cancel_settle_s: float = 2.0

    halt_file: str = "outputs/live/HALT"
    dry_dir: str = "outputs/live/dry"
    order_events_path: str = "outputs/live/order_events.csv"
    intended_path: str = "outputs/live/intended_trades.csv"

    ladder_rungs: tuple[tuple[str, float], ...] = (
        ("15:45:00", 0.0),
        ("15:47:30", 0.25),
        ("15:50:00", 0.50),
        ("15:52:30", 0.75),
        ("15:55:00", 1.0),
    )
    ladder_cancel_at: str = "15:58:00"
    ladder_nbbo_at: str = "15:59:00"
    ladder_latest_start: str = "15:54:00"

    max_names_per_day: int = field(default_factory=lambda: _env_int("MAX_NAMES_PER_DAY", 3))
    max_contracts_per_leg: int = 5

    def __post_init__(self) -> None:
        if self.selection_rule not in SELECTION_RULES:
            raise ValueError(
                f"selection_rule={self.selection_rule!r} is not one of {SELECTION_RULES}."
            )
        if self.ib_paper_port in self.ib_live_ports:
            raise ValueError(
                f"ib_paper_port={self.ib_paper_port} is a live-account port {self.ib_live_ports}."
            )


@dataclass(frozen=True)
class HedgedHoldConfig:
    """
    Parameters of the delta-hedged hold-to-expiry studies and their HAR selector.

    Every value is fixed by the 2026-10-20 pre-registrations
    (``research/timing/2026-10-20-hedged-hold/prereg.md`` and siblings); none was swept.

    Attributes
    ----------
    pre_event_dte : tuple[int, int]
        Calendar days to expiry for the pre-event sale. ``(20, 45)``: long enough that a single
        half-spread is spread over several weeks of diffusive premium, short enough to stay in
        the liquid monthly expiries.
    post_event_dte : tuple[int, int]
        The same window for the post-event sale. ``(14, 45)``, matching the unhedged post-event
        study so the hedge is the only difference.
    split_min_gap_days : int
        Minimum days between the two expiries of the jump split when the sold expiry is the
        front one. ``14``: below this the variance difference is dominated by quote noise.
    jump_split_min_gap_days : int
        The same gap for the next-session jump-richness book. ``7``: the weekly after the front.
    fee_per_contract_leg : float
        Option commission per contract per leg, USD. ``0.65``, the book's broker rate.
    disposal_bps : float
        Cost of disposing of delivered stock at settlement, bp of spot. ``5``.
    equity_cost_floor_bps : float
        Floor on the per-side equity half-spread, bp. ``1``: CRSP closing quotes on megacaps can
        be a cent wide, which understates impact.
    hedge_margin_frac : float
        Reg-T margin on the stock hedge. ``0.5``.
    har_lags : tuple[int, int, int]
        HAR-RV regressor windows in trading days (Corsi 2009). ``(1, 5, 22)``.
    har_min_rows : int
        Minimum complete regression rows before a HAR forecast is issued. ``500``, about two
        years.
    tercile_min_prior : int
        Minimum strictly earlier events before a causal tercile is assigned. ``200``.
    decile_min_prior : int
        The same for the equity decile sorts. ``300``.
    jump_hist_windows : tuple[int, int, int]
        Prior announcements averaged in the HAR-style jump forecast. ``(1, 4, 8)``.
    jump_hist_min : int
        Minimum prior announcements for a jump forecast. ``4``.
    equity_hold_days : int
        Holding period of the post-event equity signals, trading days. ``20``.
    put_delta_target : float
        Delta of the skew leg. ``-0.25``.
    slope_min_gap_days : int
        Days beyond the sold expiry for the far leg of the post-event term slope. ``21``.
    """

    pre_event_dte: tuple[int, int] = (20, 45)
    post_event_dte: tuple[int, int] = (14, 45)
    split_min_gap_days: int = 14
    jump_split_min_gap_days: int = 7
    fee_per_contract_leg: float = 0.65
    disposal_bps: float = 5.0
    equity_cost_floor_bps: float = 1.0
    hedge_margin_frac: float = 0.5
    har_lags: tuple[int, int, int] = (1, 5, 22)
    har_min_rows: int = 500
    tercile_min_prior: int = 200
    decile_min_prior: int = 300
    jump_hist_windows: tuple[int, int, int] = (1, 4, 8)
    jump_hist_min: int = 4
    equity_hold_days: int = 20
    put_delta_target: float = -0.25
    slope_min_gap_days: int = 21


# Canonical singletons. Domain modules import these and re-export the individual
# fields under their established names, so this file stays the single source of
# truth without altering any public API.
GLOBAL = GlobalConfig()
STRATEGY = StrategyConfig()
LIVE = LiveConfig()
HEDGED = HedgedHoldConfig()
