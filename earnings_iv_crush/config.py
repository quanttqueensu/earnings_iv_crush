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
    cancel_confirm_s, cancel_confirm_poll_s : float
        Longest wait, and poll interval, for the broker to confirm a cancel before
        the ladder acts on that order: the price-cap re-price after the sweep, and
        the flatten of a legged entry. Defaults to ``30.0`` and ``1.0``.
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
    exit_sweep_at : str
        Time (ET), between the last rung and the cancel, at which every unfilled
        buy-back is re-priced once through the displayed ask. Defaults to
        ``"15:56:30"``.
    exit_sweep_frac, exit_sweep_min : float
        The sweep's allowance above the displayed ask: the larger of this fraction
        of the ask and this many dollars per share. Defaults ``0.20`` and ``0.10``;
        the rationale sits beside the fields.
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
    # How long the ladder keeps re-reading an order the broker is still cancelling
    # (PendingCancel) before acting on it. On the paper account a cancel near the
    # close took from 2 s to over 60 s to confirm (2026-11-13: a price-capped CSCO
    # sweep sat in PendingCancel at +2 s, so its re-price never ran; a part-filled
    # TSN entry was still PendingCancel a minute after its cancel, and the flatten
    # sent beside it was repriced by IB so as not to cross it, and never filled).
    # 30 s keeps the sweep's re-price before 15:57:00 and leaves the flatten at least
    # 18 s before the 15:58:50 cancel; poll each second.
    cancel_confirm_s: float = 30.0
    cancel_confirm_poll_s: float = 1.0

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
    # Closing sweep for buy-backs. The touch rung bids the displayed ask, and on a
    # delayed feed that ask is about fifteen minutes old, so a leg can sit unfilled
    # under the real offer and leave a naked short (the first transmitted exit did).
    # After the last rung every unfilled exit leg, and every flatten of a legged
    # entry, is re-priced once through the displayed ask by the larger of
    # exit_sweep_frac of the ask and exit_sweep_min dollars per share. The broker
    # fills a marketable limit at the real offer, so the allowance bounds the worst
    # price rather than setting it. 20% covers roughly a two-sigma fifteen-minute
    # move in an at-the-money weekly on a post-earnings day (author's estimate, not
    # measured); the 0.10 floor is two coarse ticks, for cheap wings where 20% of
    # the ask is under a tick. No environment override: they bound what is paid.
    exit_sweep_at: str = "15:56:30"
    exit_sweep_frac: float = 0.20
    exit_sweep_min: float = 0.10

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
    net_assignment : bool
        How a hedged hold settles at expiry. ``False`` unwinds the whole stock hedge at the
        settlement close and pays ``disposal_bps`` on the assigned share, the convention frozen
        in every hedged-hold study registered before 2026-11-13, kept so those studies reproduce.
        ``True`` lets physical assignment of the in-the-money leg net against the hedge, so only
        the residual ``h - sign(S - K)`` trades and nothing is disposed of; that is how the
        position actually settles (trial 1,856, adopted 2026-11-13). New work uses
        ``HEDGED_NET``. A naked hold has no hedge to net against and keeps the disposal charge
        under either value.
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
    net_assignment: bool = False


@dataclass(frozen=True)
class HoldCorrectionsConfig:
    """
    Valuation corrections to the hedged hold: early assignment, financing, special dividends.

    Introduced by the 2026-11-14 slate-tests corrections lane. Nothing here changes a default
    of ``hedged_short_straddle``; every correction is opt-in. The broker spreads are declared
    assumptions (recalled from IBKR Pro's published schedule, not verified at source), not fits.

    Attributes
    ----------
    long_spread_bps : float
        Annual spread over the overnight rate charged on a long stock hedge financed on margin,
        bp. ``150``: IBKR Pro's benchmark plus 1.5% on the smallest debit tier, the dearest
        tier, so the long-hedge charge is conservative.
    short_rebate_spread_bps : float
        Annual spread below the overnight rate on the rebate paid on short-sale proceeds, bp.
        ``25``: the broker's stated haircut on short credit for balances that earn a rebate.
    borrow_fee_bps : float
        Annual stock-loan fee on a short hedge, bp. ``25``: general-collateral borrow. Names
        that are hard to borrow cost more; the implied-borrow lane measures that separately.
    cash_credit_spread_bps : float
        Annual spread below the overnight rate on interest paid on the premium held as cash,
        bp. ``50``: IBKR Pro's benchmark less 0.5%. The credit rate is floored at zero.
    day_basis : float
        Day-count denominator for money-market accrual. ``360``: the federal funds rate and
        broker interest on USD balances accrue ACT/360.
    min_recovered_div : float
        Smallest dividend recovered from CRSP total against price return, USD per share.
        ``0.005``: below this the gap is rounding in CRSP's prices (as in the E4 audit).
    special_div_per_contract : float
        OCC adjusts a contract for a non-regular cash dividend of at least this much per
        contract, USD. ``12.50`` (OCC By-Laws, Article VI, Section 11A; recalled).
    contract_multiplier : float
        Shares per standard equity option contract. ``100``.
    special_div_ratio : float
        A dividend counts as non-regular when it exceeds this multiple of the median of the
        name's previous recovered dividends. ``2.0``: regular dividend increases are a few
        percent to a few tens of percent, specials are typically several times the regular.
    occ_large_div_frac : float
        A cash dividend of at least this fraction of the cum-dividend close is adjusted by OCC
        whether or not it is regular. ``0.10`` (recalled).
    """

    long_spread_bps: float = 150.0
    short_rebate_spread_bps: float = 25.0
    borrow_fee_bps: float = 25.0
    cash_credit_spread_bps: float = 50.0
    day_basis: float = 360.0
    min_recovered_div: float = 0.005
    special_div_per_contract: float = 12.50
    contract_multiplier: float = 100.0
    special_div_ratio: float = 2.0
    occ_large_div_frac: float = 0.10


@dataclass(frozen=True)
class ShadowConfig:
    """
    The shadow book: alternatives marked beside every real paper trade, never traded.

    Attributes
    ----------
    equity_half_spread_bps : float
        Per-side half-spread charged on every shadow stock-hedge trade. ``3.0``, the value
        frozen in amendment 01 of the hedged-event-hold study (the 90th percentile of CRSP
        closing half-spreads across its names in 2024 was 2.93 bp).
    gate_min_prior : int
        Prior transmitted trades needed before the G1 flag is computed. ``25``, the
        ``research.gates.MIN_HIST`` warm-up the forward gate study uses.
    gate_term_q, gate_spread_q : float
        G1's cuts as frozen in the forward combined-gates pre-registration: term spread at or
        above its causal two-thirds quantile, entry spread at or below its causal median.
    out_name : str
        File written next to the pass's other stores (dry passes in their own folder).
    """

    equity_half_spread_bps: float = 3.0
    gate_min_prior: int = 25
    gate_term_q: float = 2 / 3
    gate_spread_q: float = 0.5
    out_name: str = "shadow_book.csv"


ONLINE_BAYES_VARIANCE_WEIGHTS = ("none", "premium_share")
ONLINE_BAYES_FEATURE_SETS = ("declared", "wide")
ONLINE_BAYES_TRANSFORMS = ("none", "yj_loss")


@dataclass(frozen=True)
class OnlineBayesConfig:
    """
    The sequential Bayesian model of the hedged hold (``research/online_bayes.py``).

    Introduced by the 2026-11-14 slate-tests lane L4. The four searched fields (``discount``,
    ``coef_prior_scale``, ``name_prior_scale``, ``variance_weight``) hold the values selected on
    2013-18 by mean log predictive score over the declared grids and frozen in
    ``outputs/research/2026-11-14-slate-tests/L4-bayes/freeze_online_bayes.md``; every other
    value is declared, not fitted.

    Attributes
    ----------
    discount : float
        Discount on the coefficient block of the covariance, applied once per update date.
        ``1.0`` is no forgetting; the half-life in update dates is ``ln 0.5 / ln discount``.
    variance_discount : float
        Multiplier on the inverse-gamma ``a`` and ``b`` per update date. ``1.0``: off, not
        searched; the coefficient discount is the declared forgetting mechanism.
    coef_prior_scale : float
        Prior variance of each standardised feature's coefficient, in units of ``sigma^2``.
    intercept_prior_scale : float
        Prior variance of the intercept in units of ``sigma^2``. ``1.0``: weak against the 200
        trades that settle before any prediction is scored.
    name_prior_scale : float
        ``kappa_u = tau^2 / sigma^2``, the name intercepts' prior variance. Zero switches the name
        effect off.
    prior_df : float
        Prior degrees of freedom ``2 a0`` of ``sigma^2``. ``2.0``: the weakest prior with a finite
        predictive scale.
    prior_sigma : float
        Prior guess of the residual standard deviation in the target's units (``b0 = a0
        prior_sigma^2``). ``5.0`` % of m0, an order of magnitude (conjecture); with ``prior_df``
        2 it carries the weight of one trade.
    variance_weight : str
        ``"none"`` (``v_j = 1``) or ``"premium_share"`` (``v_j`` proportional to ``(s0 / m0)^2``
        over its causal expanding mean): the hedged P&L scales with the premium, so its variance
        in % of m0 scales with the premium's share of m0.
    min_settled : int
        Settled trades in the posterior before a prediction is scored or acted on. ``200``.
    min_prior_events : int
        Events with strictly earlier entry dates before features are standardised. ``200``.
    margin_spot_frac : float
        The spot fraction in ``m0 = margin_spot_frac x forward + bid``. ``0.20``, the project's
        margin unit; inverted to recover the 15:59 forward.
    decision_threshold : float
        Trade when the predictive P(y > 0) exceeds this. ``0.5``, declared and not tuned; with a
        symmetric predictive it is a positive predictive mean.
    interval_level : float
        Central predictive interval whose coverage is checked. ``0.90``.
    pit_bins : int
        Bins of the probability-integral-transform histogram. ``10``.
    gauge_level : float
        Credible level of the book gauge's interval. ``0.95``.
    gauge_stop, gauge_promote : float
        Monitor thresholds on the design-effect P(book mean > 0). ``0.05`` and ``0.95``,
        declared; coherent under optional stopping as a posterior, with no frequentist error
        guarantee.
    discount_grid, coef_prior_grid, name_prior_grid, variance_weight_grid : tuple
        The declared search space, scored on 2013-18 only. Updates fall on about 43 dates a year
        on the base panel, so the discount half-lives are about 3.2 years (0.995), 0.8 years
        (0.98) and 0.3 years (0.95).
    pct_per_unit : float
        Multiplier from a fraction of m0 to % of m0. ``100``: ``H_corr``, ``residual_value`` and
        the shadow book's ``H_shadow`` are stored as fractions; the model's target is in %.
    obs_df : float
        Degrees of freedom ``nu`` of a Student-t observation error, written as a scale mixture
        ``e_j | lambda_j ~ N(0, sigma^2 v_j / lambda_j)``, ``lambda_j ~ Gamma(nu / 2, nu / 2)``.
        ``inf`` (the default) is the Gaussian model, unchanged. Added by the L4 iteration round;
        the hedged P&L has gap tails, so a finite ``nu`` is a searched option.
    group_prior_scale : float
        ``kappa_g``, the prior variance of an industry intercept shared by the names in it, in
        ``sigma^2`` units. Zero (the default) switches the level off.
    variance_power : float
        Exponent ``k`` of the premium-share weight, ``v_j = ps_j^k / mean(ps^k)``. ``2.0`` (the
        default) is the original weight; searched in the iteration round.
    feature_set : str
        Which 15:59 feature set ``online_bayes.FEATURE_SETS`` builds. ``"declared"`` (the
        default) is the seven declared features.
    mixture_nodes, mixture_log_lo, mixture_log_hi : int, float, float
        Trapezoid grid in ``log lambda`` on which the Student-t mixture predictive and the
        posterior weight of an observation are integrated. 241 nodes over ``[-14, 4]``: the
        Gamma mass outside it is below 1e-9 for ``nu >= 2``, and the integrand is smooth in
        ``log lambda``, so the rule converges geometrically (checked against adaptive
        quadrature in the tests).
    z_clip : float
        Bound on every causally standardised feature, ``|z| <= z_clip``. ``inf`` (the default)
        leaves the declared features as they were; the wide set's skewed cost and wing fields
        are clipped at 5 so one stale quote cannot dominate a coefficient.
    target_transform, yj_power : str, float
        ``"none"`` (the default) models ``y`` itself. ``"yj_loss"`` models the Yeo-Johnson
        transform, power ``yj_power``, of the loss ratio ``-y / U`` with ``U`` the 15:59 premium
        in % of m0 (``100 s0 / m0``), and scores the density on the original scale through the
        Jacobian. The seller's outcome is bounded above near the premium and has a long loss
        tail, so a symmetric predictive on ``y`` misplaces both tails; on the payout-ratio scale
        the outcome is close to symmetric. ``yj_power`` 1 is the identity on ``-y / U``.
    ev_draws, ev_seed : int
        Common random numbers for the predictive mean of a transformed target (Monte Carlo),
        used only by the expected-value decision rule. 2,000 draws, seed 0.
    """

    discount: float = 1.0
    variance_discount: float = 1.0
    coef_prior_scale: float = 0.01
    intercept_prior_scale: float = 1.0
    name_prior_scale: float = 0.01
    prior_df: float = 2.0
    prior_sigma: float = 5.0
    variance_weight: str = "premium_share"
    min_settled: int = 200
    min_prior_events: int = 200
    margin_spot_frac: float = 0.20
    decision_threshold: float = 0.5
    interval_level: float = 0.90
    pit_bins: int = 10
    gauge_level: float = 0.95
    gauge_stop: float = 0.05
    gauge_promote: float = 0.95
    discount_grid: tuple[float, ...] = (1.0, 0.995, 0.98, 0.95)
    coef_prior_grid: tuple[float, ...] = (0.001, 0.01, 0.1)
    name_prior_grid: tuple[float, ...] = (0.0, 0.003, 0.01, 0.03, 0.1)
    variance_weight_grid: tuple[str, ...] = ONLINE_BAYES_VARIANCE_WEIGHTS
    pct_per_unit: float = 100.0
    obs_df: float = float("inf")
    group_prior_scale: float = 0.0
    variance_power: float = 2.0
    feature_set: str = "declared"
    mixture_nodes: int = 241
    mixture_log_lo: float = -14.0
    mixture_log_hi: float = 4.0
    z_clip: float = float("inf")
    target_transform: str = "none"
    yj_power: float = 1.0
    ev_draws: int = 2000
    ev_seed: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.discount <= 1 or not 0 < self.variance_discount <= 1:
            raise ValueError("discounts lie in (0, 1]")
        if self.target_transform not in ONLINE_BAYES_TRANSFORMS or not 0 <= self.yj_power < 2:
            raise ValueError(f"target_transform in {ONLINE_BAYES_TRANSFORMS}, 0 <= yj_power < 2")
        if not self.z_clip > 0 or self.ev_draws < 1:
            raise ValueError("z_clip > 0 and ev_draws >= 1 required")
        if not self.obs_df > 0 or self.group_prior_scale < 0 or not self.variance_power > 0:
            raise ValueError("obs_df > 0, group_prior_scale >= 0 and variance_power > 0 required")
        if self.feature_set not in ONLINE_BAYES_FEATURE_SETS:
            raise ValueError(f"feature_set is one of {ONLINE_BAYES_FEATURE_SETS}")
        if self.variance_weight not in ONLINE_BAYES_VARIANCE_WEIGHTS:
            raise ValueError(f"variance_weight is one of {ONLINE_BAYES_VARIANCE_WEIGHTS}")
        if min(self.coef_prior_scale, self.intercept_prior_scale) <= 0:
            raise ValueError("coefficient prior scales are positive")
        if self.name_prior_scale < 0 or self.prior_df <= 0 or self.prior_sigma <= 0:
            raise ValueError("name_prior_scale >= 0, prior_df > 0 and prior_sigma > 0 required")


# Canonical singletons. Domain modules import these and re-export the individual
# fields under their established names, so this file stays the single source of
# truth without altering any public API.
@dataclass(frozen=True)
class ExecutionLeversConfig:
    """
    Declared inputs of the execution and cost levers (2026-11-14 slate-tests lane L2).

    Nothing here is fitted and nothing changes an existing default. Fee figures carry their
    status: "verified" was read on the published schedule; "recalled" could not be read at the
    source (Interactive Brokers' site refuses automated clients) and is the project's recollection.

    Attributes
    ----------
    auction_cost_grid_bps : tuple[float, ...]
        Per-side price impact of a market-on-close order relative to the closing print, bp.
        ``(0, 0.5, 1)``: a declared grid, since no auction data exist on disk; the result is read
        as a function of it and through its break-even.
    moc_cutoff_minutes : float
        Minutes before the close at which an MOC order, and so the hedge ratio, must be fixed.
        ``10``: NYSE and Nasdaq accept MOC entries until 15:50 ET (recalled).
    session_minutes, trading_days_per_year : float
        Regular-session length (390 minutes) and the project's 252-day year, used only to scale
        the hold's annual sigma to the cutoff interval.
    tracking_seed : int
        Seed of the simulated pre-cutoff price. ``0``.
    stock_tiered_per_share, stock_tiered_min_order : float
        IBKR Pro Tiered US stock commission at the lowest volume tier, USD 0.0035 per share with a
        USD 0.35 minimum per order (recalled).
    stock_fixed_per_share, stock_fixed_min_order : float
        IBKR Pro Fixed US stock commission, USD 0.005 per share, USD 1.00 minimum (recalled).
    stock_clearing_per_share : float
        Clearing fee passed through on Tiered, USD 0.0002 per share (recalled).
    moc_exchange_fee_per_share : float
        NYSE charge for a non-tier MOC order executed in the closing auction, USD 0.0010 per share
        (verified: NYSE Price List 2026, last updated 2026-11-02).
    stock_take_fee_per_share : float
        Exchange fee for a marketable order removing displayed liquidity, USD 0.0030 per share,
        the Reg NMS access-fee cap of Rule 610(c) (recalled), the dearest case.
    commission_contract_sizes : tuple[int, ...]
        Straddles per event at which per-order minimums are evaluated. ``(1, 5)``: one contract,
        the dearest per share, and the paper book's ``max_contracts_per_leg``.
    option_fixed_per_contract : float
        IBKR Pro Fixed US option commission for a premium of USD 0.10 or more, USD 0.65 per
        contract, exchange and regulatory fees included (recalled).
    option_tiered_per_contract : float
        IBKR Pro Tiered US option commission at the lowest volume tier (up to 10,000 contracts a
        month), USD 0.65 per contract (recalled).
    option_clearing_per_contract : float
        OCC clearing fee passed through on Tiered, USD 0.02 per contract (recalled).
    option_regulatory_per_contract : float
        Options Regulatory Fee and FINRA trading-activity fee passed through on Tiered, about
        USD 0.03 per contract in all (recalled; the ORF rate changes several times a year).
    option_customer_take_fee : float
        Cboe Options (C1) customer fee for an equity option order of under 100 contracts that
        removes liquidity, USD 0.00 (verified: Cboe Exchange Fees Schedule, 2026-11-09).
    option_maker_rebate : float
        Customer rebate for adding liquidity in a penny class on a maker-taker options venue,
        USD 0.25 per contract (recalled), the relevant figure for a resting entry that fills.
    option_maker_taker_take_fee : float
        Customer fee for removing liquidity in a penny class on a maker-taker options venue,
        USD 0.50 per contract (recalled), the dear case for a marketable entry.
    option_min_per_order : float
        IBKR Pro minimum commission per option order, USD 1.00 (recalled); the straddle is one
        combo order, so it binds only below two contracts in all.
    expiry_min_gap_days, expiry_max_gap_days : int
        The later expiry for the per-event expiry choice lies 7 to 60 days after the front,
        the window of the closed later-expiry study (imported, so the two agree).
    depth_sizes : tuple[int, ...]
        Order sizes in contracts per leg for the capacity read. ``(1, 5, 10, 25)``.
    depth_beyond_book_ticks : int
        Size beyond the displayed top of book fills this many price increments worse per leg,
        per multiple of the displayed size (declared, conservative in the absence of depth
        beyond level 0). ``1``.
    entry_window : tuple[str, str]
        First and last entry minute searched by the causal spread-state entry. 15:00 to 15:59.
    stock_max_commission_frac : float
        IBKR Pro cap on the stock commission of one order, as a fraction of its trade value.
        ``0.01`` (recalled); it binds on small orders in low-priced names, below the minimum.
    delta_band_grid : tuple[float, ...]
        No-trade bands in delta units (shares per straddle-share) searched on 2013-18 for the
        commission-aware delta band (B11). ``0`` is the every-close Black-Scholes hedge.
    sec_fee_rate_bound : float
        SEC Section 31 fee on the value of every sale (stock and option), as a fraction. ``27.8e-6``
        (USD 27.80 per million, the fiscal-2024 rate; recalled, and the rate is reset each fiscal
        year, so this is used only to bound the size of the omitted fee, not charged).
    finra_taf_per_share : float
        FINRA trading activity fee per share sold, USD. ``0.000166`` (recalled; bound only).
    """

    auction_cost_grid_bps: tuple[float, ...] = (0.0, 0.5, 1.0)
    moc_cutoff_minutes: float = 10.0
    session_minutes: float = 390.0
    trading_days_per_year: float = 252.0
    tracking_seed: int = 0
    stock_tiered_per_share: float = 0.0035
    stock_tiered_min_order: float = 0.35
    stock_fixed_per_share: float = 0.005
    stock_fixed_min_order: float = 1.00
    stock_clearing_per_share: float = 0.0002
    moc_exchange_fee_per_share: float = 0.0010
    stock_take_fee_per_share: float = 0.0030
    commission_contract_sizes: tuple[int, ...] = (1, 5)
    option_fixed_per_contract: float = 0.65
    option_tiered_per_contract: float = 0.65
    option_clearing_per_contract: float = 0.02
    option_regulatory_per_contract: float = 0.03
    option_customer_take_fee: float = 0.0
    option_maker_rebate: float = 0.25
    option_maker_taker_take_fee: float = 0.50
    option_min_per_order: float = 1.00
    expiry_min_gap_days: int = 7
    expiry_max_gap_days: int = 60
    depth_sizes: tuple[int, ...] = (1, 5, 10, 25)
    depth_beyond_book_ticks: int = 1
    entry_window: tuple[str, str] = ("15:00", "15:59")
    stock_max_commission_frac: float = 0.01
    delta_band_grid: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30)
    sec_fee_rate_bound: float = 27.8e-6
    finra_taf_per_share: float = 0.000166


GLOBAL = GlobalConfig()
STRATEGY = StrategyConfig()
LIVE = LiveConfig()
HEDGED = HedgedHoldConfig()
# The settlement convention signed off on 2026-11-13; HEDGED stays as frozen for closed studies.
HEDGED_NET = HedgedHoldConfig(net_assignment=True)
HOLD_CORRECTIONS = HoldCorrectionsConfig()
SHADOW = ShadowConfig()
ONLINE_BAYES = OnlineBayesConfig()
# Lane L4 iteration round 1 champions, each the best of its class by 2015-18 rolling-origin mean
# log predictive score (outputs/research/2026-11-14-slate-tests/L4-bayes/search_log.csv, 800
# rows) and frozen in that folder's freeze_online_bayes.md. ONLINE_BAYES keeps the stage-1
# defaults. H_corr: a Student-t (nu 30) model of the Yeo-Johnson (power 0) loss ratio -H/U on the
# seven declared features; the baseline is the same likelihood with only the intercept and name.
ONLINE_BAYES_L4_MODEL = OnlineBayesConfig(
    discount=1.0,
    variance_discount=0.99,
    coef_prior_scale=0.03,
    name_prior_scale=0.01,
    variance_weight="none",
    obs_df=30.0,
    target_transform="yj_loss",
    yj_power=0.0,
)
ONLINE_BAYES_L4_BASELINE = OnlineBayesConfig(
    discount=1.0,
    variance_discount=0.99,
    coef_prior_scale=0.01,
    name_prior_scale=0.03,
    variance_weight="none",
    obs_df=30.0,
    target_transform="yj_loss",
    yj_power=0.0,
)
# residual_value (secondary target): Student-t (nu 4) on the wide set, SIC-division level.
ONLINE_BAYES_L4_RV_MODEL = OnlineBayesConfig(
    discount=0.98,
    variance_discount=0.99,
    coef_prior_scale=0.1,
    name_prior_scale=0.03,
    group_prior_scale=0.03,
    variance_weight="premium_share",
    obs_df=4.0,
    feature_set="wide",
    z_clip=5.0,
)
ONLINE_BAYES_L4_RV_BASELINE = OnlineBayesConfig(
    discount=0.98,
    variance_discount=0.99,
    coef_prior_scale=0.01,
    name_prior_scale=0.1,
    variance_weight="premium_share",
    obs_df=6.0,
)
EXECUTION_LEVERS = ExecutionLeversConfig()


@dataclass(frozen=True)
class ChainSurfaceConfig:
    """The 15:59 option-surface tensor of ``research/chain_surface.py`` (deep-learning lane D0).

    Attributes
    ----------
    exchange_tz : str
        Time zone of the snapshot and expiry clocks, ``America/New_York``.
    snapshot_time : str
        Entry snapshot, ``15:59``: the clock of ``research/chains.py::SNAPSHOT``, which pulled the
        cached backfill chains as the 15:59:00 ET one-minute consolidated BBO. A row stamped
        after it on the entry date is excluded.
    expiry_time : str
        Expiry clock for time to expiry, ``16:00`` ET, the close of the last trading session.
    days_per_year : float
        ACT/365 day count, the project convention.
    grid_lo, grid_hi : float
        Ends of the standardised-moneyness grid ``x = ln(K/F) / (sigma_atm sqrt(tau))``,
        ``-2`` and ``+2``: two ATM standard deviations each side, where implied moves differing
        about tenfold across names still land on quoted strikes.
    grid_points : int
        Grid size, ``9``: a step of 0.5 ATM standard deviations.
    iv_lo, iv_hi : float
        Bracket of the implied-vol inversion in decimals, ``1e-4`` and ``5.0``, the bracket of
        ``hedged_hold.option_iv``, so both inverters return NaN on the same prices.
    iv_iterations : int
        Bisection steps of the vectorised inverter, ``60``: the bracket width over 2^60 is below
        1e-17 in vol, under double-precision rounding.
    parity_strikes : int
        Strikes nearest the front forward whose put-call parity forwards are pooled (median) for
        the next expiry's forward, ``5``.
    parity_min_strikes : int
        Fewest two-sided call-put pairs among those for the next expiry's forward to count as
        found, ``3``: a median of fewer is one quote's noise.
    max_gap_x : float
        Widest bracket, in grid units of x, across which a channel is interpolated, ``1.0`` (two
        grid steps). A wider hole between quoted strikes leaves the point masked rather than
        bridged by a straight line.
    sparse_fill : float
        Grid fill below which a surface counts as sparse in the attrition test, ``0.5``.
    recon_iv_tol : float
        Reconciliation tolerance of the front ATM straddle IV against the lane E panel's
        ``front_iv``, ``0.005`` (half a vol point): the surface discounts at DFF and times to the
        minute where the panel used a zero rate and whole days, about 0.1% of the vol on a
        one-month front.
    recon_spread_tol : float
        Reconciliation tolerance of the front ATM straddle half-spread against the panel's
        ``half_spread``, ``1e-9``: both are the same quote arithmetic.
    """

    exchange_tz: str = "America/New_York"
    snapshot_time: str = "15:59"
    expiry_time: str = "16:00"
    days_per_year: float = 365.0
    grid_lo: float = -2.0
    grid_hi: float = 2.0
    grid_points: int = 9
    iv_lo: float = 1e-4
    iv_hi: float = 5.0
    iv_iterations: int = 60
    parity_strikes: int = 5
    parity_min_strikes: int = 3
    max_gap_x: float = 1.0
    sparse_fill: float = 0.5
    recon_iv_tol: float = 0.005
    recon_spread_tol: float = 1e-9


CHAIN_SURFACE = ChainSurfaceConfig()


@dataclass(frozen=True)
class CatalogueConfig:
    """The results catalogue: ``research/catalogue.csv`` rendered as ``docs/RESULTS.md``.

    Attributes
    ----------
    csv_path, page_path : str
        Repository-relative paths of the catalogue and of the page rendered from it.
    kinds : tuple of str
        How a result was produced: ``preregistered`` (a frozen pre-registration was scored),
        ``exploratory`` (a programme run under the exploratory regime, or ad hoc), ``audit`` (a
        data or defect investigation, not a strategy test) and ``reference`` (a dossier or a
        compilation of verdicts).
    statuses : tuple of str
        Where a result stands, in the order the page lists them: ``adopted`` (the paper book uses
        it), ``open`` (started, no verdict recorded), ``closed`` (tested and rejected),
        ``superseded`` (replaced; the row names its successor) and ``reference``.
    headline_max_chars : int
        Longest headline, ``200``: about two lines of a rendered table, enough for one claim with
        its N, interval and basis, short enough that the page stays a scan.
    header_required_from : str
        First catalogue date, ``2026-11-16``, from which a findings note must open with the
        ``**Verdict:**`` and ``**Reproduce:**`` lines within ``header_lines`` lines. Earlier notes
        are records and are not edited to fit.
    header_lines : int
        How far into a note the two lines may sit, ``40``: room for a title and a provenance
        paragraph above them, close enough that a reader meets the verdict first.
    """

    csv_path: str = "research/catalogue.csv"
    page_path: str = "docs/RESULTS.md"
    kinds: tuple[str, ...] = ("preregistered", "exploratory", "audit", "reference")
    statuses: tuple[str, ...] = ("adopted", "open", "closed", "superseded", "reference")
    headline_max_chars: int = 200
    header_required_from: str = "2026-11-16"
    header_lines: int = 40


CATALOGUE = CatalogueConfig()
