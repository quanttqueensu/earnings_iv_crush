"""
session.py
The daily paper-book pass: confirm the calendar, plan exits and entries, run one ladder, book fills.

This is the forward-test specification's daily rule (sections 2 to 7) in one place:

1. **Calendar.** A name is a candidate only when at least two of three independent
   sources (Finnhub, Nasdaq, Yahoo) agree on its announcement date and session, and
   that bracket puts the entry on today's session. Fewer than two is skipped with
   reason ``calendar_unconfirmed``; an unknown session is never guessed.
2. **Exits.** Every open position due today is closed on the stored strike and
   expiry. A transmitting exit first checks the broker holds the short legs.
3. **Entries.** Candidates are admitted in ascending SHA-256 of ``ticker|entry_date``,
   an order that depends on nothing about the trade, up to ``max_names_per_day``. Each
   is priced on the first expiry strictly after the exit date, skipped if an
   ex-dividend date falls inside the hold or cannot be read, and sized with the
   backtest's ``size_contracts`` capped at ``max_contracts_per_leg``.
4. **Ladder.** Every entry and exit leg runs through one ``ladder.run_ladder``.
5. **Booking.** A transmitted entry is booked from its fills, never from the model
   price; a dry pass books its intent at the 15:59 mid into the dry stores only, so a
   dry run can never mark a broker-held short as closed.

Every admitted event and every due exit gets a row in the intended-trades log, filled
or not, because the paired-improvement measure counts unfilled entries at zero. Every
alarm is printed with the ``ALARM:`` prefix the drivers look for, and the pass returns
the alarm count so the driver can exit non-zero.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from ..config import GLOBAL, LIVE, LiveConfig
from ..data.features import atm_iv, nearest_strike
from ..engine.greeks import implied_vol
from ..engine.pnl import ACCOUNT_SIZE, _straddle_value, regt_straddle_margin, size_contracts
from . import ib_market, ib_orders, paper_book
from .forward_test import FORWARD, StraddleQuote
from .ib_connection import kill_switch_active
from .ladder import (
    Clock,
    GroupOutcome,
    IBClock,
    LadderLeg,
    LadderSchedule,
    LadderTooLate,
    LegQuote,
    run_ladder,
)
from .order_events import OrderEventLog, load_order_events, position_key, prior_exit_fills

R = GLOBAL.risk_free_rate
MULT = GLOBAL.contract_multiplier
SESSIONS = ("bmo", "amc")
# Strikes snapshotted around spot per name: enough for the ATM pair after a gap in the
# listed grid, small enough to stay far inside IB's market-data line limit.
STRIKES_AROUND_SPOT = 8


# ── stores ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stores:
    """Every path one pass reads or writes. Dry passes get their own copies."""

    open_positions: str
    nostop: str
    stop: str
    reconciliation: str
    heartbeat: str
    intended: str
    order_events: str

    @classmethod
    def for_mode(
        cls, transmit: bool, config: LiveConfig = LIVE, root: str | Path | None = None
    ) -> Stores:
        """The stores for a transmitting or a dry pass.

        ``root`` relocates every store (tests use a temporary directory); a dry pass
        always lives one level down, in its own ``dry`` folder.
        """
        if root is not None:
            base = Path(root)
            names = cls.for_mode(True, config)
            live_root = cls(**{k: str(base / Path(v).name) for k, v in names.__dict__.items()})
            if transmit:
                return live_root
            return cls(**{k: str(base / "dry" / Path(v).name) for k, v in names.__dict__.items()})
        live = cls(
            open_positions=config.open_positions_path,
            nostop=FORWARD.nostop_ledger_path,
            stop=FORWARD.stop_ledger_path,
            reconciliation=FORWARD.reconciliation_path,
            heartbeat=config.heartbeat_path,
            intended=config.intended_path,
            order_events=config.order_events_path,
        )
        if transmit:
            return live
        dry = Path(config.dry_dir)
        return cls(**{k: str(dry / Path(v).name) for k, v in live.__dict__.items()})


INTENDED_COLUMNS = [
    "run_id",
    "session_date",
    "ticker",
    "purpose",
    "announce_date",
    "session",
    "entry_date",
    "exit_date",
    "position_key",
    "strike",
    "expiry",
    "contracts",
    "decision",
    "reason",
    "outcome",
    "fill_ps",
    "nbbo_mid_1559_ps",
    "transmit",
    "calendar_detail",
]


def _append_intended(path: str, row: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists() or p.stat().st_size == 0
    with p.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(INTENDED_COLUMNS)
        w.writerow(["" if row.get(c) is None else row.get(c) for c in INTENDED_COLUMNS])


# ── universe and calendar confirmation ───────────────────────────────────────


def load_universe(path: str | Path) -> set[str]:
    """Tickers of the tradable universe; raises when the file is missing or empty.

    The calendar is the whole US tape, so trading without the universe would put
    micro-caps into a book specified and costed on 346 liquid names.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Universe file {p} not found; the session pass will not trade the whole tape."
        )
    frame = pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p, columns=["ticker"])
    tickers = set(frame["ticker"].dropna().astype(str))
    if not tickers:
        raise ValueError(f"Universe file {p} lists no tickers.")
    return tickers


def _norm_session(value: Any) -> str | None:
    """``bmo``/``amc``; ``dmh`` shares the ``bmo`` bracket; anything else is unknown."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    key = str(value).strip().lower()
    if key == "dmh":
        return "bmo"
    return key if key in SESSIONS else None


def confirm_events(votes: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Apply the 2-of-3 rule to calendar votes and bracket each confirmed event.

    Parameters
    ----------
    votes : pandas.DataFrame
        One row per (source, ticker) with ``source``, ``ticker``, ``announce_date``
        and ``session``.
    asof : pandas.Timestamp
        Today's exchange date.

    Returns
    -------
    pandas.DataFrame
        One row per ticker: ``ticker``, ``announce_date``, ``session``, ``n_agree``,
        ``confirmed``, ``entry_date``, ``exit_date``, ``is_today`` and ``detail``
        (each source's answer, so disagreements are visible in the log).
    """
    from ..data.earnings import trade_dates_for_session

    cols = [
        "ticker",
        "announce_date",
        "session",
        "n_agree",
        "confirmed",
        "entry_date",
        "exit_date",
        "is_today",
        "detail",
    ]
    if votes.empty:
        return pd.DataFrame(columns=cols)
    v = votes.copy()
    v["announce_date"] = pd.to_datetime(v["announce_date"]).dt.normalize()
    v["session_n"] = v["session"].map(_norm_session)
    rows = []
    for ticker, g in v.groupby("ticker", sort=True):
        detail = "; ".join(
            f"{s}={pd.Timestamp(d).date()} {sess or 'unknown'}"
            for s, d, sess in zip(g["source"], g["announce_date"], g["session_n"], strict=True)
        )
        known = g[g["session_n"].notna()]
        counts = known.groupby(["announce_date", "session_n"])["source"].nunique()
        best = counts[counts >= 2]
        row: dict[str, Any] = {"ticker": ticker, "detail": detail, "confirmed": False}
        if len(best) == 1:
            pair, n = next(iter(best.items()))
            day, sess = pd.Timestamp(pair[0]), str(pair[1])  # type: ignore[index]
            bracket = trade_dates_for_session(day, sess)
            if bracket is not None:
                row.update(
                    announce_date=day,
                    session=sess,
                    n_agree=int(n),
                    confirmed=True,
                    entry_date=bracket[0],
                    exit_date=bracket[1],
                )
        if not row["confirmed"]:
            row["n_agree"] = int(counts.max()) if len(counts) else 0
        row["is_today"] = bool(row["confirmed"] and row["entry_date"] == asof.normalize())
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


VoteFn = Callable[[pd.Timestamp, set[str]], pd.DataFrame]


def gather_votes(
    asof: pd.Timestamp,
    universe: set[str],
    *,
    finnhub: Callable[[str, str], pd.DataFrame] | None = None,
    nasdaq: Callable[[str], pd.DataFrame] | None = None,
    yahoo: Callable[[list[str], str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Collect each source's (date, session) for universe names that could enter today.

    An entry today means an announcement today after the close or on the next session
    before the open, so only those two dates are read. A source that fails contributes
    no votes and is reported, never silently treated as agreement.
    """
    from ..data import earnings as cal

    finnhub = finnhub or cal.fetch_earnings_calendar
    nasdaq = nasdaq or cal.fetch_nasdaq_calendar
    yahoo = yahoo or cal.fetch_earnings_dates
    days = [asof.normalize(), (asof + BDay(1)).normalize()]
    lo, hi = str(days[0].date()), str(days[1].date())
    frames: list[pd.DataFrame] = []

    try:
        fh = finnhub(lo, hi)
        if not fh.empty:
            fh = fh.rename(columns={"hour": "session"})
            fh["source"] = "finnhub"
            frames.append(fh[["source", "ticker", "announce_date", "session"]])
    except Exception as exc:  # noqa: BLE001 - a dead source is reported and outvoted
        print(f"  warning: Finnhub calendar unavailable ({type(exc).__name__}: {exc}).")
    for day in days:
        try:
            nq = nasdaq(str(day.date()))
            nq["source"] = "nasdaq"
            frames.append(nq[["source", "ticker", "announce_date", "session"]])
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: Nasdaq calendar unavailable for {day.date()} ({exc}).")
    seen = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if seen.empty:
        return pd.DataFrame(columns=["source", "ticker", "announce_date", "session"])
    seen["announce_date"] = pd.to_datetime(seen["announce_date"]).dt.normalize()
    seen = seen[seen["ticker"].isin(universe) & seen["announce_date"].isin(days)]
    names = sorted(seen["ticker"].unique())
    if names:
        try:
            yh = yahoo(names, lo, hi)
            yh["source"] = "yahoo"
            seen = pd.concat([seen, yh[["source", "ticker", "announce_date", "session"]]])
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: Yahoo earnings dates unavailable ({exc}).")
    return seen.reset_index(drop=True)


# ── ex-dividend ──────────────────────────────────────────────────────────────


def exdiv_decision(
    dates: dict[str, Any], entry: pd.Timestamp, exit_: pd.Timestamp
) -> tuple[bool, str]:
    """Whether a hold from ``entry`` to ``exit_`` is clear of an ex-dividend date.

    ``dates`` maps each source to a ``Timestamp``, ``None`` (the source reports no
    upcoming dividend) or ``"unreadable"``. Any readable date inside the hold blocks
    the trade, because a short call in the money before an ex-date can be assigned
    early. If no source could be read the answer is unknown and the trade is skipped.
    """
    readable = {s: d for s, d in dates.items() if not (isinstance(d, str) and d == "unreadable")}
    if not readable:
        return False, "exdiv_unknown"
    for d in readable.values():
        if d is not None and entry.normalize() <= pd.Timestamp(d).normalize() <= exit_.normalize():
            return False, "exdiv_in_window"
    return True, ""


def _yahoo_exdiv(ticker: str) -> Any:
    """Ex-dividend date from Yahoo's calendar, ``None`` when it lists none."""
    try:
        import yfinance as yf

        cal = yf.Ticker(ticker).calendar or {}
    except Exception:  # noqa: BLE001 - reported to the caller as unreadable
        return "unreadable"
    d = cal.get("Ex-Dividend Date") if isinstance(cal, dict) else None
    return pd.Timestamp(d) if d else None


# ── plans ────────────────────────────────────────────────────────────────────


def admission_order(tickers: list[str], entry_date: pd.Timestamp) -> list[str]:
    """Deterministic admission order, independent of any signal or outcome."""
    day = str(pd.Timestamp(entry_date).date())
    return sorted(tickers, key=lambda t: hashlib.sha256(f"{t}|{day}".encode()).hexdigest())


@dataclass
class EntryPlan:
    ticker: str
    announce_date: pd.Timestamp
    session: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    expiry: pd.Timestamp
    strike: float
    spot: float
    iv: float
    t_entry: float
    contracts: int
    call: Any
    put: Any
    implied_move: float
    calendar_detail: str = ""
    # Record-only entry features for the forward gate study; never used to select.
    iv_term_spread_nearest: float = float("nan")
    entry_rel_spread: float = float("nan")

    @property
    def key(self) -> str:
        return position_key(self.ticker, self.entry_date, self.strike, self.expiry)


@dataclass
class ExitPlan:
    position: pd.Series
    call: Any
    put: Any
    spot: float
    iv_exit: float
    t_exit: float
    extra: dict[str, Any] = field(default_factory=dict)
    # Contracts and average price already bought back per leg by an earlier session's
    # incomplete exit (``order_events.prior_exit_fills``); empty for a first attempt.
    prior: dict[str, tuple[int, float]] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return _position_key(self.position)

    def remaining(self, right: str) -> int:
        """Contracts still to buy back on one leg."""
        return int(self.position["contracts"]) - self.prior.get(right, (0, 0.0))[0]


def _position_key(p: pd.Series) -> str:
    return str(
        p.get("position_key")
        or position_key(p["ticker"], p["entry_date"], float(p["strike"]), p["front_expiry"])
    )


def _leg_mid(chain: pd.DataFrame, expiry: pd.Timestamp, strike: float, right: str) -> float:
    rows = chain[
        (pd.to_datetime(chain["expiry"]) == expiry)
        & np.isclose(chain["strike"].astype(float), strike)
        & (chain["right"] == right)
    ]
    if rows.empty:
        return float("nan")
    bid, ask = float(rows["bid"].iloc[0]), float(rows["ask"].iloc[0])
    if not (np.isfinite(bid) and np.isfinite(ask) and ask >= bid > 0):
        return float("nan")
    return 0.5 * (bid + ask)


def _leg_quote(chain: pd.DataFrame, expiry: pd.Timestamp, strike: float) -> StraddleQuote | None:
    """Two-sided bid and ask of both legs at one strike, or None."""
    legs = {}
    for right in ("C", "P"):
        rows = chain[
            (pd.to_datetime(chain["expiry"]) == expiry)
            & np.isclose(chain["strike"].astype(float), strike)
            & (chain["right"] == right)
        ]
        if rows.empty:
            return None
        bid, ask = float(rows["bid"].iloc[0]), float(rows["ask"].iloc[0])
        if not (np.isfinite(bid) and np.isfinite(ask) and ask >= bid > 0):
            return None
        legs[right] = (bid, ask)
    return StraddleQuote(legs["C"][0], legs["C"][1], legs["P"][0], legs["P"][1])


def _atm_iv_at(chain: pd.DataFrame, expiry: pd.Timestamp, spot: float, asof: pd.Timestamp) -> float:
    """ATM implied volatility of one expiry: the feed's, else solved from the leg mids."""
    strike = float(nearest_strike(chain, expiry, spot))
    if not np.isfinite(strike):
        return float("nan")
    iv = float(atm_iv(chain, expiry, strike))
    if np.isfinite(iv):
        return iv
    t = max((expiry - asof).days, 1) / 365.0
    ivs = [
        implied_vol(_leg_mid(chain, expiry, strike, r), spot, strike, t, R, r) for r in ("C", "P")
    ]
    finite = [x for x in ivs if x is not None and np.isfinite(x)]
    return float(np.mean(finite)) if finite else float("nan")


def term_spread_nearest(
    ib: Any,
    underlying: Any,
    expiries: list[pd.Timestamp],
    strikes: list[float],
    spot: float,
    asof: pd.Timestamp,
    front_chain: pd.DataFrame,
    front_expiry: pd.Timestamp,
) -> float:
    """Front-minus-back ATM IV on the nearest expiries as of the entry day.

    The panel definition (``data.features.nearest_expiries`` with ``asof``): front is the
    first expiry after the entry date, back the first at least
    ``GLOBAL.back_month_min_gap_days`` beyond it, else the latest listed. Record-only:
    any failure returns NaN and never skips the trade.
    """
    try:
        after = sorted(e for e in expiries if e > asof.normalize())
        if len(after) < 2:
            return float("nan")
        n_front = after[0]
        gap = pd.Timedelta(days=GLOBAL.back_month_min_gap_days)
        n_back = next((e for e in after[1:] if e >= n_front + gap), after[-1])
        near = sorted(sorted(strikes, key=lambda k: abs(k - spot))[:2])
        ivs = []
        for e in (n_front, n_back):
            ch = (
                front_chain
                if e == front_expiry
                else ib_market.snapshot_strikes(ib, underlying, e, near)
            )
            ivs.append(_atm_iv_at(ch, e, spot, asof) if not ch.empty else float("nan"))
        return float(ivs[0] - ivs[1])
    except Exception as exc:  # noqa: BLE001 - a feature request must never block a trade
        print(f"  term spread unavailable for {getattr(underlying, 'contract', '?')}: {exc!r}")
        return float("nan")


def plan_entry(
    ib: Any,
    cand: pd.Series,
    asof: pd.Timestamp,
    config: LiveConfig = LIVE,
    exdiv_sources: Callable[[Any, Any, str], dict[str, Any]] | None = None,
) -> EntryPlan | str:
    """Price one confirmed candidate, or return the reason it is skipped."""
    ticker = str(cand["ticker"])
    exit_date = pd.Timestamp(cand["exit_date"])
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        expiries, strikes = ib_market.option_grid(ib, underlying)
    except (ValueError, RuntimeError) as exc:
        print(f"  {ticker}: no underlying or option grid ({exc}).")
        return "unpriced:underlying"
    later = [e for e in expiries if e > exit_date]
    if not later:
        return "expiry_le_exit"
    expiry = later[0]
    spot = float(underlying.spot)
    near = sorted(sorted(strikes, key=lambda k: abs(k - spot))[:STRIKES_AROUND_SPOT])
    chain = ib_market.snapshot_strikes(ib, underlying, expiry, near)
    if chain.empty:
        return "unpriced:no_chain"
    strike = float(nearest_strike(chain, expiry, spot))
    if not np.isfinite(strike):
        return "unpriced:no_atm_strike"
    call_mid, put_mid = (_leg_mid(chain, expiry, strike, r) for r in ("C", "P"))
    if not (np.isfinite(call_mid) and np.isfinite(put_mid)):
        # A snapshot can return before a slow delayed tick lands, so the pair is asked
        # for once more on its own before the name is given up. A book that is still
        # one-sided stays unpriced: a one-sided quote never becomes a mid.
        again = ib_market.snapshot_strikes(ib, underlying, expiry, [strike])
        if not again.empty:
            chain = again
            call_mid, put_mid = (_leg_mid(chain, expiry, strike, r) for r in ("C", "P"))
    if not (np.isfinite(call_mid) and np.isfinite(put_mid)):
        print(f"  {ticker}: no two-sided quote on the {strike:g} pair exp {expiry.date()}.")
        return "unpriced:one_sided_atm"
    t_entry = max((expiry - asof).days, 1) / 365.0
    iv = float(atm_iv(chain, expiry, strike))
    if not np.isfinite(iv):
        ivs = [
            implied_vol(call_mid, spot, strike, t_entry, R, "C"),
            implied_vol(put_mid, spot, strike, t_entry, R, "P"),
        ]
        iv = float(np.nanmean([x for x in ivs if x is not None]))
    if not np.isfinite(iv):
        return "unpriced:no_iv"

    sources = (exdiv_sources or _exdiv_sources)(ib, underlying, ticker)
    ok, reason = exdiv_decision(sources, asof, exit_date)
    if not ok:
        return reason

    credit_ps = _straddle_value(spot, strike, t_entry, R, iv)
    contracts = min(
        int(size_contracts(ACCOUNT_SIZE, spot, strike, credit_ps)), config.max_contracts_per_leg
    )
    if contracts <= 0:
        return "sized_zero"
    try:
        call, put = ib_orders.qualify_straddle_legs(ib, underlying.contract.symbol, strike, expiry)
    except ValueError:
        return "unpriced:legs_unqualified"
    entry_quote = _leg_quote(chain, expiry, strike)
    return EntryPlan(
        ticker=ticker,
        announce_date=pd.Timestamp(cand["announce_date"]),
        session=str(cand["session"]),
        entry_date=asof.normalize(),
        exit_date=exit_date,
        expiry=expiry,
        strike=strike,
        spot=spot,
        iv=iv,
        t_entry=t_entry,
        contracts=contracts,
        call=call,
        put=put,
        implied_move=(call_mid + put_mid) / spot,
        calendar_detail=str(cand.get("detail", "")),
        iv_term_spread_nearest=term_spread_nearest(
            ib, underlying, list(expiries), list(strikes), spot, asof, chain, expiry
        ),
        entry_rel_spread=entry_quote.relative_spread if entry_quote else float("nan"),
    )


def _exdiv_sources(ib: Any, underlying: Any, ticker: str) -> dict[str, Any]:
    try:
        ib_date = ib_market.next_ex_dividend(ib, underlying)
    except Exception:  # noqa: BLE001 - an unreadable tick is "unknown", never "none"
        ib_date = "unreadable"
    return {"ib": ib_date, "yahoo": _yahoo_exdiv(ticker)}


def plan_exit(
    ib: Any,
    pos: pd.Series,
    asof: pd.Timestamp,
    *,
    transmit: bool,
    order_events_path: str | Path | None = None,
) -> ExitPlan | str:
    """Qualify the stored contracts of one due position, or return why it cannot exit.

    A transmitting exit is sent only when the broker's position is explained. A leg no
    earlier exit touched must still be short the full ledger quantity. A leg an earlier
    incomplete exit partly or wholly bought back (its fills are in the order-event log
    at ``order_events_path``) must be short exactly the remainder, and only that
    remainder is worked. Anything else, including a leg closed outside the harness and
    not yet recorded with :func:`record_manual_exit_fill`, is a ``broker_mismatch`` and
    nothing is sent. When the log already accounts for both legs in full the plan has no
    legs left to work, and the pass books it without sending an order.
    """
    ticker = str(pos["ticker"])
    strike = float(pos["strike"])
    expiry = pd.Timestamp(pos["front_expiry"])
    try:
        underlying = ib_market.qualify_underlying(ib, ticker)
        call, put = ib_orders.qualify_straddle_legs(ib, underlying.contract.symbol, strike, expiry)
    except (ValueError, RuntimeError) as exc:
        return f"unqualified: {exc}"
    prior: dict[str, tuple[int, float]] = {}
    if transmit:
        need = int(pos["contracts"])
        if order_events_path is not None:
            try:
                prior = prior_exit_fills(load_order_events(order_events_path), _position_key(pos))
            except ValueError as exc:
                return f"prior_fills_unreadable: {exc}"
        held = {c.right: ib_orders.broker_short_qty(ib, c) for c in (call, put)}
        for right in ("C", "P"):
            done = prior.get(right, (0, 0.0))[0]
            left = need - done
            # An untouched leg keeps the original test (short at least the ledger
            # quantity); a resumed leg must reconcile to the contract.
            explained = held[right] == -left if done else held[right] <= -need
            if left < 0 or not explained:
                bought = {r: q for r, (q, _) in prior.items()}
                return (
                    f"broker_mismatch: broker holds {held}, ledger expects -{need} per leg, "
                    f"earlier exit fills bought {bought or 'nothing'}"
                )
    chain = ib_market.snapshot_strikes(ib, underlying, expiry, [strike])
    iv_exit = float(atm_iv(chain, expiry, strike)) if not chain.empty else float("nan")
    return ExitPlan(
        position=pos,
        call=call,
        put=put,
        spot=float(underlying.spot),
        iv_exit=iv_exit,
        t_exit=max((expiry - asof).days, 0) / 365.0,
        prior=prior,
    )


def _legs_for_entry(plan: EntryPlan) -> list[LadderLeg]:
    return [
        LadderLeg(
            group=f"{plan.key}:entry",
            ticker=plan.ticker,
            position_key=plan.key,
            purpose="entry",
            side="SELL",
            right=right,
            contract=contract,
            quantity=plan.contracts,
            strike=plan.strike,
            expiry=plan.expiry,
        )
        for right, contract in (("C", plan.call), ("P", plan.put))
    ]


def _legs_for_exit(plan: ExitPlan) -> list[LadderLeg]:
    pos = plan.position
    return [
        LadderLeg(
            group=f"{plan.key}:exit",
            ticker=str(pos["ticker"]),
            position_key=plan.key,
            purpose="exit",
            side="BUY",
            right=right,
            contract=contract,
            quantity=plan.remaining(right),
            strike=float(pos["strike"]),
            expiry=pd.Timestamp(pos["front_expiry"]),
        )
        for right, contract in (("C", plan.call), ("P", plan.put))
        if plan.remaining(right) > 0
    ]


# ── booking ──────────────────────────────────────────────────────────────────


def _mid_1559(outcome: GroupOutcome) -> float:
    mids = []
    for q in outcome.nbbo_1559.values():
        if q is None or not q.usable_for("SELL"):
            return float("nan")
        mids.append(0.5 * (q.bid + q.ask))
    return float(sum(mids))


def _book_entry(plan: EntryPlan, outcome: GroupOutcome, stores: Stores, transmit: bool) -> str:
    """Write the open position from fills (transmit) or the 15:59 mid (dry).

    A transmitted entry that did not fill in full books nothing. A dry entry never
    fills, so its intent is booked at the 15:59 mid into the dry store, which lets the
    next day's dry exit exercise the whole path without touching the live book.
    """
    if transmit:
        if outcome.status != "filled":
            return outcome.status
        credit_ps = outcome.fill_ps
    else:
        credit_ps = _mid_1559(outcome)
    if not np.isfinite(credit_ps) or credit_ps <= 0:
        return "booking_error" if transmit else "unquoted"
    paper_book.record_entry(
        {
            "ticker": plan.ticker,
            "announce_date": plan.announce_date,
            "entry_date": plan.entry_date,
            "exit_date": plan.exit_date,
            "front_expiry": plan.expiry,
            "strike": plan.strike,
            "contracts": int(plan.contracts),
            "spot_entry": plan.spot,
            "iv_entry": plan.iv,
            "t_entry": plan.t_entry,
            "entry_credit": float(credit_ps * MULT * plan.contracts),
            "margin": float(
                regt_straddle_margin(plan.spot, plan.strike, credit_ps, plan.contracts)
            ),
            "selection_rule": "unconditional",
            "implied_move": plan.implied_move,
            "iv_term_spread_nearest": plan.iv_term_spread_nearest,
            "entry_rel_spread": plan.entry_rel_spread,
            "entry_mid_ps": _mid_1559(outcome),
            "entry_fill_ps": float(credit_ps),
            "transmitted": bool(transmit),
            "position_key": plan.key,
        },
        path=stores.open_positions,
    )
    return "filled" if transmit else "dry_booked_at_mid"


def _exit_fill_ps(plan: ExitPlan, outcome: GroupOutcome) -> float:
    """Per-share straddle buy-back price over every session that worked the exit.

    A first-attempt exit is the ladder's own figure. A resumed exit blends each leg's
    earlier fills with this session's by quantity, so the booked price is what was
    actually paid for the whole straddle, not for the legs that happened to trade today.
    """
    if not plan.prior or outcome.status != "filled":
        return outcome.fill_ps
    need = int(plan.position["contracts"])
    today = {leg.right: leg for leg in outcome.legs}
    total = 0.0
    for right in ("C", "P"):
        qty, px = plan.prior.get(right, (0, 0.0))
        paid = qty * px
        leg = today.get(right)
        if leg is not None:
            paid += leg.filled_qty * leg.avg_fill
            qty += leg.filled_qty
        if qty != need:
            raise RuntimeError(
                f"{plan.key} leg {right}: fills cover {qty} of {need} contracts; not booking"
            )
        total += paid / need
    return float(total)


def _exit_resume_note(plan: ExitPlan) -> str:
    """Intended-trades reason text recording what an earlier session already closed."""
    if not plan.prior:
        return ""
    parts = [f"{r} {q}@{px:.4g}" for r, (q, px) in sorted(plan.prior.items())]
    return "resumed_exit: earlier fills " + ", ".join(parts)


def _book_exit(
    plan: ExitPlan, outcome: GroupOutcome, stores: Stores, transmit: bool, asof: pd.Timestamp
) -> str:
    if transmit and outcome.status != "filled":
        return outcome.status
    fill_ps = _exit_fill_ps(plan, outcome)
    quotes: dict[str, LegQuote | None] = {
        leg.right: (outcome.nbbo_1559.get(leg.right) or leg.last_quote) for leg in outcome.legs
    }
    for right, (_, px) in plan.prior.items():
        # A leg closed in an earlier session has no quote today; its own fill stands
        # in on both sides, so it adds nothing to the measured spread or slippage.
        quotes.setdefault(right, LegQuote(px, px))
    c, p = quotes.get("C"), quotes.get("P")
    if c is None or p is None:
        if not transmit:
            return "unquoted"
        fills = {leg.right: leg.avg_fill for leg in outcome.legs}
        c = c or LegQuote(fills["C"], fills["C"])
        p = p or LegQuote(fills["P"], fills["P"])
    quote = StraddleQuote(call_bid=c.bid, call_ask=c.ask, put_bid=p.bid, put_ask=p.ask)
    max_rung = max(((leg.rung or 0) for leg in outcome.legs), default=0)
    paper_book.forward_exit_from_quote(
        plan.position,
        quote,
        spot_exit=plan.spot,
        iv_exit=plan.iv_exit,
        exit_date=asof,
        t_exit=plan.t_exit,
        # An exit that needed a second session did not fill at a mid-seeking rung.
        filled_at_limit=not plan.prior and max_rung < len(LIVE.ladder_rungs) - 1,
        transmitted_fill_ps=fill_ps if transmit else None,
        nostop_path=stores.nostop,
        stop_path=stores.stop,
        reconciliation_path=stores.reconciliation,
        open_path=stores.open_positions,
    )
    return "filled" if transmit else "dry_booked_at_mid"


# ── the pass ─────────────────────────────────────────────────────────────────


@dataclass
class SessionResult:
    run_id: str
    funnel: dict[str, int]
    alarms: list[str]
    outcomes: list[GroupOutcome]


def _alarm(alarms: list[str], text: str) -> None:
    alarms.append(text)
    print(f"  ALARM: {text}")


# IB error 10197, "No market data during competing live session": the paper login
# shares its market data with the live login of the same user, and loses it while
# that user is signed in elsewhere. Quotes then come back empty for the whole pass.
COMPETING_SESSION_ERROR = 10197


def _leg_ident(symbol: Any, strike: Any, expiry: Any, right: Any) -> tuple[str, float, str, str]:
    """Contract identity that needs no gateway round trip and survives expiry."""
    return (
        str(symbol).replace("-", " ").upper(),
        round(float(strike), 4),
        pd.Timestamp(str(expiry)).strftime("%Y%m%d"),
        str(right).upper()[:1],
    )


def _orphan_positions(ib: Any, book: pd.DataFrame) -> list[str]:
    """Option positions at the broker that no open ledger position accounts for."""
    known = {
        _leg_ident(pos["ticker"], pos["strike"], pos["front_expiry"], right)
        for _, pos in book.iterrows()
        for right in ("C", "P")
    }
    out = []
    for contract, qty in ib_orders.broker_option_positions(ib):
        ident = _leg_ident(
            contract.symbol, contract.strike, contract.lastTradeDateOrContractMonth, contract.right
        )
        if ident not in known:
            name = getattr(contract, "localSymbol", "") or " ".join(map(str, ident))
            out.append(f"broker holds {qty:+d} {name}, which no open ledger position explains")
    return out


def _closed_outcome(plan: ExitPlan) -> GroupOutcome:
    """Outcome of an exit whose legs were all bought back before this pass."""
    return GroupOutcome(
        group=f"{plan.key}:exit",
        purpose="exit",
        status="filled",
        fill_ps=float("nan"),
        legs=(),
        nbbo_1559={},
    )


def run_session(
    asof: pd.Timestamp,
    *,
    transmit: bool,
    ib: Any = None,
    clock: Clock | None = None,
    quote_fn: Callable[[list[LadderLeg]], dict[str, LegQuote | None]] | None = None,
    votes: pd.DataFrame | None = None,
    config: LiveConfig = LIVE,
    exdiv_sources: Callable[[Any, Any, str], dict[str, Any]] | None = None,
    stores: Stores | None = None,
) -> SessionResult:
    """Run one session of the paper book end to end.

    Parameters
    ----------
    asof : pandas.Timestamp
        Exchange date of the session.
    transmit : bool
        Whether orders are sent to the paper account. The driver passes this only
        when ``_private/TRANSMIT_OK`` exists.
    ib : ib_async.IB, optional
        A connected client; one is opened (and closed) when omitted.
    clock, quote_fn : optional
        Injected for tests; default to the wall clock and live leg quotes.
    votes : pandas.DataFrame, optional
        Calendar votes (``source, ticker, announce_date, session``); gathered from
        the three sources when omitted. A manual run passes its own.
    config : LiveConfig, optional
        Settings; defaults to ``LIVE``.

    Returns
    -------
    SessionResult
        Run id, the funnel counts, every alarm raised, and each group's outcome.
    """
    asof = pd.Timestamp(asof).normalize()
    stores = stores or Stores.for_mode(transmit, config)
    alarms: list[str] = []
    funnel = dict.fromkeys(
        ("seen", "confirmed", "today", "admitted", "priced", "entered", "exits_due", "exited"), 0
    )

    def halted() -> bool:
        return Path(config.halt_file).exists()

    log = OrderEventLog(
        stores.order_events, asof, transmit=transmit, market_data_type=config.ib_market_data_type
    )
    print(
        f"Session {asof.date()} run {log.run_id[:8]}: "
        f"{'TRANSMIT to PAPER' if transmit else 'DRY RUN (nothing sent)'}; "
        f"cap {config.max_names_per_day} names, {config.max_contracts_per_leg} contracts/leg."
    )
    if halted():
        _alarm(alarms, f"HALT present ({config.halt_file}); nothing runs on any path.")
        log.record("halt", reason="HALT present at start")
        return SessionResult(log.run_id, funnel, alarms, [])

    universe = load_universe(config.universe_path)
    if votes is None:
        votes = gather_votes(asof, universe)
    confirmed = confirm_events(votes, asof)
    funnel["seen"] = int(confirmed["ticker"].nunique())
    funnel["confirmed"] = int(confirmed["confirmed"].sum())
    today = confirmed[confirmed["is_today"]]
    funnel["today"] = len(today)
    for _, row in confirmed[~confirmed["confirmed"]].iterrows():
        _append_intended(
            stores.intended,
            {
                "run_id": log.run_id,
                "session_date": asof.date(),
                "ticker": row["ticker"],
                "purpose": "entry",
                "decision": "skip",
                "reason": "calendar_unconfirmed",
                "transmit": transmit,
                "calendar_detail": row["detail"],
            },
        )

    own_ib = ib is None
    if own_ib:
        from .ib_connection import connect_paper

        ib = connect_paper()
    error_codes: set[int] = set()

    def _on_error(_req_id: int, code: int, *_rest: Any) -> None:
        error_codes.add(int(code))

    error_event = getattr(ib, "errorEvent", None)
    if error_event is not None:
        error_event += _on_error
    try:
        clock = clock or IBClock(ib)
        quote_fn = quote_fn or (lambda legs: ib_market.quote_legs(ib, legs))

        # Exits first: they are planned even when STOP blocks entries.
        book = paper_book.load_open_positions(stores.open_positions)
        if transmit:
            try:
                for text in _orphan_positions(ib, book):
                    _alarm(alarms, text)
            except Exception as exc:  # noqa: BLE001 - reported; the pass still exits what it can
                _alarm(alarms, f"broker positions unreadable for the ledger check ({exc!r}).")
        due = (
            book[pd.to_datetime(book["exit_date"]).dt.normalize() <= asof]
            if not book.empty
            else book
        )
        funnel["exits_due"] = len(due)
        exit_plans: list[ExitPlan] = []
        for _, pos in due.iterrows():
            # One position's fault (a positions request that times out, a contract
            # that will not qualify) must not stop the others from exiting.
            try:
                plan = plan_exit(
                    ib, pos, asof, transmit=transmit, order_events_path=stores.order_events
                )
            except Exception as exc:  # noqa: BLE001
                plan = f"error: {exc!r}"
            if isinstance(plan, str):
                _alarm(alarms, f"{pos['ticker']} exit not placed ({plan}); position left open.")
                continue
            if not _legs_for_exit(plan):
                # Every contract was bought back earlier (an exit that completed but
                # was never booked, or legs closed by hand and recorded): nothing to
                # send, so book it now from the fills in the log.
                done = _closed_outcome(plan)
                try:
                    status = _book_exit(plan, done, stores, transmit, asof)
                except Exception as exc:  # noqa: BLE001
                    _alarm(alarms, f"{pos['ticker']} exit booking failed ({exc!r}).")
                    continue
                funnel["exited"] += status == "filled"
                _append_intended(
                    stores.intended, _intended_row(log.run_id, asof, plan, done, status, transmit)
                )
                print(f"    exit  {pos['ticker']}: booked from earlier fills, no order sent")
                continue
            exit_plans.append(plan)

        entry_plans: list[EntryPlan] = []
        if kill_switch_active(config.kill_switch_file):
            _alarm(alarms, f"STOP present ({config.kill_switch_file}); no entries today.")
        else:
            by_ticker = {str(r["ticker"]): r for _, r in today.iterrows()}
            for ticker in admission_order(list(by_ticker), asof):
                cand = by_ticker[ticker]
                if len(entry_plans) >= config.max_names_per_day:
                    decision, reason, plan_e = "skip", "cap_names", None
                else:
                    # An entry that cannot be priced is skipped with its reason; it must
                    # never take the day's exits down with it.
                    try:
                        res = plan_entry(ib, cand, asof, config, exdiv_sources)
                    except Exception as exc:  # noqa: BLE001
                        res = f"error:{type(exc).__name__}"
                        print(f"  warning: {ticker} entry planning raised {exc!r}; skipped.")
                    plan_e = res if isinstance(res, EntryPlan) else None
                    decision = "admit" if plan_e else "skip"
                    reason = "" if plan_e else str(res)
                if plan_e is not None:
                    entry_plans.append(plan_e)
                    continue
                _append_intended(
                    stores.intended,
                    {
                        "run_id": log.run_id,
                        "session_date": asof.date(),
                        "ticker": ticker,
                        "purpose": "entry",
                        "announce_date": pd.Timestamp(cand["announce_date"]).date(),
                        "session": cand["session"],
                        "entry_date": asof.date(),
                        "exit_date": pd.Timestamp(cand["exit_date"]).date(),
                        "decision": decision,
                        "reason": reason,
                        "transmit": transmit,
                        "calendar_detail": cand["detail"],
                    },
                )
        funnel["admitted"] = len(entry_plans)
        funnel["priced"] = len(entry_plans)
        if funnel["today"] and not entry_plans and not kill_switch_active(config.kill_switch_file):
            _alarm(alarms, f"{funnel['today']} candidates today and none admitted; read the log.")

        legs = [leg for p in exit_plans for leg in _legs_for_exit(p)] + [
            leg for p in entry_plans for leg in _legs_for_entry(p)
        ]
        _print_funnel(funnel, entry_plans, exit_plans)
        if not legs:
            paper_book.record_heartbeat(asof, funnel["today"], 0, 0, 0, path=stores.heartbeat)
            return SessionResult(log.run_id, funnel, alarms, [])

        try:
            outcomes = run_ladder(
                ib,
                legs,
                quote_fn=quote_fn,
                clock=clock,
                schedule=LadderSchedule.for_session(asof, config),
                log=log,
                transmit=transmit,
                halted=halted,
                sweep_frac=config.exit_sweep_frac,
                sweep_min=config.exit_sweep_min,
            )
        except LadderTooLate as exc:
            _alarm(alarms, str(exc))
            for p in exit_plans:
                _alarm(alarms, f"{p.position['ticker']} exit not placed; position left open.")
            return SessionResult(log.run_id, funnel, alarms, [])
        if transmit:
            try:
                for text in ib_orders.cancel_resting_orders(ib):
                    _alarm(alarms, f"order still working after the ladder, now cancelled: {text}")
            except Exception as exc:  # noqa: BLE001
                _alarm(alarms, f"could not confirm that no order is left working ({exc!r}).")
    finally:
        if error_event is not None:
            error_event -= _on_error
        if COMPETING_SESSION_ERROR in error_codes:
            _alarm(
                alarms,
                "market data was cut by a competing live session (IB error 10197): quotes "
                "were missing for part of this pass. Stay signed out of live IBKR "
                "(TWS, web and mobile) from 15:15 to 16:00 ET.",
            )
        if own_ib and ib is not None and ib.isConnected():
            ib.disconnect()

    booked = ("filled", "dry_booked_at_mid")
    by_group = {o.group: o for o in outcomes}
    for p in exit_plans:
        o = by_group[f"{p.key}:exit"]
        ticker = p.position["ticker"]
        # A booking fault on one position is reported and the rest are still booked:
        # the fills are safe in the order log either way.
        try:
            status = _book_exit(p, o, stores, transmit, asof)
        except Exception as exc:  # noqa: BLE001
            status = "booking_error"
            _alarm(alarms, f"{ticker} exit booking failed ({exc!r}); fills are in the order log.")
        if o.alarm:
            _alarm(alarms, f"{ticker} exit {o.status}; working orders cancelled.")
        elif status not in booked and status != "booking_error":
            # An exit with nothing filled used to pass in silence, leaving the
            # straddle open a day past its rule with a green run.
            _alarm(alarms, f"{ticker} exit {status}; position still open.")
        funnel["exited"] += status in booked
        _append_intended(stores.intended, _intended_row(log.run_id, asof, p, o, status, transmit))
    for e in entry_plans:
        o = by_group[f"{e.key}:entry"]
        try:
            status = _book_entry(e, o, stores, transmit)
        except Exception as exc:  # noqa: BLE001
            status = "booking_failed"
            _alarm(
                alarms,
                f"{e.ticker} entry booking failed ({exc!r}); the broker may hold the straddle.",
            )
        if o.alarm:
            _alarm(alarms, f"{e.ticker} entry {o.status}: a naked leg may be held at the broker.")
        elif status == "booking_error" and o.status == "filled":
            _alarm(alarms, f"{e.ticker} entry filled at the broker but was not booked.")
        funnel["entered"] += status in booked
        _append_intended(stores.intended, _intended_row(log.run_id, asof, e, o, status, transmit))

    paper_book.record_heartbeat(
        asof,
        funnel["today"],
        funnel["priced"],
        funnel["admitted"],
        funnel["entered"],
        path=stores.heartbeat,
    )
    print(
        f"  done: {funnel['entered']} entered of {funnel['admitted']} admitted; "
        f"{funnel['exited']} exited of {funnel['exits_due']} due; {len(alarms)} alarm(s)."
    )
    return SessionResult(log.run_id, funnel, alarms, outcomes)


# ── recording a close made outside the harness ───────────────────────────────


def record_manual_exit_fill(
    ib: Any,
    ticker: str,
    right: str,
    qty: int,
    price: float,
    reason: str,
    asof: pd.Timestamp,
    *,
    config: LiveConfig = LIVE,
    stores: Stores | None = None,
) -> str:
    """Record contracts of an open position bought back by hand, and book it if complete.

    When the operator closes a leg in TWS (or it expires), the broker and the ledger
    disagree and every later pass refuses the position as a ``broker_mismatch``. This
    is the correction: one dated ``fill`` row in the order-event log carrying the
    operator's price and reason, written only after the broker's position is seen to
    equal what the ledger would hold once the fill is counted. Nothing is sent to the
    broker. When the log then accounts for both legs in full the exit is booked at the
    blended price straight away; otherwise the next pass works the remainder.

    Parameters
    ----------
    ib : ib_async.IB
        A connected paper client, used read-only (positions, and the spot for the
        ledger row).
    ticker, right : str
        The open position and the leg, ``"C"`` or ``"P"``.
    qty : int
        Contracts closed by hand on that leg.
    price : float
        Average price paid per share; ``0`` for a leg that expired worthless.
    reason : str
        Why it was closed outside the harness. Required: it is the audit trail.
    asof : pandas.Timestamp
        Exchange date of the close.

    Returns
    -------
    str
        ``"booked"`` when the exit is now complete and in the ledgers, else
        ``"recorded"``.

    Raises
    ------
    ValueError
        If the position is not open exactly once, the inputs are unusable, or the
        broker's position does not match the ledger after the fill. Nothing is
        written in any of these cases.
    """
    asof = pd.Timestamp(asof).normalize()
    stores = stores or Stores.for_mode(True, config)
    right = str(right).upper()[:1]
    if right not in ("C", "P"):
        raise ValueError(f"leg must be C or P, got {right!r}")
    if not str(reason).strip():
        raise ValueError("a reason is required: it is the only record of why")
    if int(qty) <= 0 or not np.isfinite(price) or float(price) < 0:
        raise ValueError(f"need a positive quantity and a non-negative price, got {qty}, {price}")
    book = paper_book.load_open_positions(stores.open_positions)
    rows = book[book["ticker"] == ticker] if not book.empty else book
    if len(rows) != 1:
        raise ValueError(f"{ticker}: expected exactly one open position, found {len(rows)}")
    pos = rows.iloc[0]
    key = _position_key(pos)
    need = int(pos["contracts"])
    prior = prior_exit_fills(load_order_events(stores.order_events), key)
    done = prior.get(right, (0, 0.0))[0]
    if done + int(qty) > need:
        raise ValueError(
            f"{key} leg {right}: {done} already bought back, {qty} more exceeds {need}"
        )
    ident = _leg_ident(ticker, pos["strike"], pos["front_expiry"], right)
    held = sum(
        q
        for c, q in ib_orders.broker_option_positions(ib)
        if _leg_ident(c.symbol, c.strike, c.lastTradeDateOrContractMonth, c.right) == ident
    )
    expect = -(need - done - int(qty))
    if held != expect:
        raise ValueError(
            f"{key} leg {right}: broker holds {held}, but the ledger would hold {expect} "
            "after this fill; nothing recorded"
        )
    log = OrderEventLog(
        stores.order_events, asof, transmit=True, market_data_type=config.ib_market_data_type
    )
    log.record(
        "fill",
        ticker=ticker,
        position_key=key,
        leg=right,
        strike=float(pos["strike"]),
        expiry=str(pd.Timestamp(pos["front_expiry"]).date()),
        purpose="exit",
        side="BUY",
        order_qty=int(qty),
        fill_qty=int(qty),
        fill_price=float(price),
        cum_filled=int(qty),
        avg_fill_price=float(price),
        status="Filled",
        reason=f"manual close: {str(reason).strip()}",
    )
    prior = prior_exit_fills(load_order_events(stores.order_events), key)
    if any(prior.get(r, (0, 0.0))[0] != need for r in ("C", "P")):
        return "recorded"
    try:
        spot = float(ib_market.qualify_underlying(ib, ticker).spot)
    except (ValueError, RuntimeError):
        spot = float("nan")
    expiry = pd.Timestamp(pos["front_expiry"])
    plan = ExitPlan(
        position=pos,
        call=None,
        put=None,
        spot=spot,
        iv_exit=float("nan"),
        t_exit=max((expiry - asof).days, 0) / 365.0,
        prior=prior,
    )
    done_outcome = _closed_outcome(plan)
    status = _book_exit(plan, done_outcome, stores, True, asof)
    _append_intended(
        stores.intended, _intended_row(log.run_id, asof, plan, done_outcome, status, True)
    )
    return "booked"


def _intended_row(
    run_id: str, asof: pd.Timestamp, plan: Any, o: GroupOutcome, status: str, transmit: bool
) -> dict[str, Any]:
    if isinstance(plan, EntryPlan):
        base = {
            "ticker": plan.ticker,
            "purpose": "entry",
            "announce_date": plan.announce_date.date(),
            "session": plan.session,
            "entry_date": plan.entry_date.date(),
            "exit_date": plan.exit_date.date(),
            "strike": plan.strike,
            "expiry": plan.expiry.date(),
            "contracts": plan.contracts,
            "calendar_detail": plan.calendar_detail,
        }
    else:
        pos = plan.position
        base = {
            "ticker": pos["ticker"],
            "purpose": "exit",
            "entry_date": pd.Timestamp(pos["entry_date"]).date(),
            "exit_date": asof.date(),
            "strike": float(pos["strike"]),
            "expiry": pd.Timestamp(pos["front_expiry"]).date(),
            "contracts": int(pos["contracts"]),
        }
    resumed = isinstance(plan, ExitPlan) and bool(plan.prior)
    return {
        **base,
        "run_id": run_id,
        "session_date": asof.date(),
        "position_key": plan.key,
        "decision": "admit",
        "reason": _exit_resume_note(plan) if resumed else "",
        "outcome": status,
        "fill_ps": _exit_fill_ps(plan, o) if resumed else o.fill_ps,
        # Today's ladder quoted only the legs still open, so their mid is not a
        # straddle mid and is left empty rather than passed off as one.
        "nbbo_mid_1559_ps": float("nan") if resumed else _mid_1559(o),
        "transmit": transmit,
    }


def _print_funnel(funnel: dict[str, int], entries: list[EntryPlan], exits: list[ExitPlan]) -> None:
    print(
        "  funnel: "
        + ", ".join(f"{k} {v}" for k, v in funnel.items() if k not in ("entered", "exited"))
    )
    for p in exits:
        pos = p.position
        print(
            f"    exit  {pos['ticker']}: {int(pos['contracts'])}x {float(pos['strike']):g} "
            f"exp {pd.Timestamp(pos['front_expiry']).date()}"
        )
        if p.prior:
            left = {r: p.remaining(r) for r in ("C", "P") if p.remaining(r) > 0}
            print(f"          resuming an incomplete exit: buying {left}; {_exit_resume_note(p)}")
    for e in entries:
        print(
            f"    entry {e.ticker}: {e.contracts}x {e.strike:g} exp {e.expiry.date()} "
            f"({e.session} {e.announce_date.date()}, exit {e.exit_date.date()}, "
            f"iv {e.iv:.2f}, implied move {e.implied_move:.1%})"
        )
