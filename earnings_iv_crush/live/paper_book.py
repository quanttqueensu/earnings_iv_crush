"""
paper_book.py
Persistence and the causal gate histories for the live paper book.

The backtest's gates are causal: the skew gate keeps an event only if its
``skew_25d`` sits at or below a quantile of *prior* events' skew, and the term
gate compares an event's ``iv_term_spread`` to that name's *trailing* daily
distribution. A forward loop has to build those histories as it goes, so this
module owns three small parquet stores under ``outputs/live``:

* a **skew history** - one row per booked/seen event, seeded from cached research
  events so the gate is sensible from day one and then extended live;
* a **term panel** - one ``(ticker, date, iv_term_spread)`` row per run, the
  trailing distribution the existing ``passes_term_filter_panel`` consumes; and
* an **open-positions** store plus the completed-trade **ledger** in the
  backtest's ``LEDGER_COLUMNS`` schema, so the paper book is read with the same
  tooling as the research ledger.

Pure pandas only; no broker or network calls live here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..config import LIVE
from ..engine.costs import CostModel
from ..engine.pnl import LEDGER_COLUMNS, build_trade
from ..strategy.filters import passes_term_filter_panel

OPEN_COLUMNS = [
    "ticker",
    "announce_date",
    "entry_date",
    "exit_date",
    "front_expiry",
    "strike",
    "contracts",
    "spot_entry",
    "iv_entry",
    "t_entry",
    "entry_credit",
    "margin",
    "skew_25d",
    "iv_term_spread",
    "status",
]


# ── small parquet helpers ────────────────────────────────────────────────────


def _read(path: str | Path, columns: list[str]) -> pd.DataFrame:
    """Read a parquet store, or an empty correctly-typed frame when absent."""
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_parquet(p)


def _append(path: str | Path, row: dict, columns: list[str]) -> pd.DataFrame:
    """Append one row to a parquet store, creating it (and its dir) if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = _read(p, columns)
    out = pd.concat([df, pd.DataFrame([row], columns=columns)], ignore_index=True)
    out.to_parquet(p, index=False)
    return out


# ── skew gate history ────────────────────────────────────────────────────────


def load_skew_history(
    history_path: str | Path = LIVE.skew_history_path,
    seed_path: str | Path = LIVE.skew_seed_path,
) -> np.ndarray:
    """Prior ``skew_25d`` values: cached seed plus any accumulated live events.

    Seeding from the research events means the low-skew quantile is meaningful
    before the live book has its own history; once live events accumulate they
    extend the same distribution.

    Returns
    -------
    np.ndarray
        Finite prior skews (may be empty if neither store resolves).
    """
    skews: list[float] = []
    seed = Path(seed_path)
    if seed.exists():
        s = pd.read_parquet(seed, columns=["skew_25d"])["skew_25d"]
        skews.extend(pd.to_numeric(s, errors="coerce").dropna().tolist())
    hist = _read(history_path, ["ticker", "announce_date", "skew_25d"])
    if not hist.empty:
        skews.extend(pd.to_numeric(hist["skew_25d"], errors="coerce").dropna().tolist())
    return np.asarray(skews, dtype=float)


def passes_skew_gate(
    skew_value: float,
    prior_skews: np.ndarray,
    keep_frac: float = LIVE.skew_keep_frac,
    min_history: int = 40,
) -> bool:
    """Causal low-skew gate: keep when ``skew_value`` <= the ``keep_frac`` quantile.

    Mirrors ``scripts/validate_skew_oos.expanding_low_skew_mask`` but for a single
    live event against the accumulated prior cross-section. Rejects when the
    history is too thin (< ``min_history``) or the value is missing.

    Parameters
    ----------
    skew_value : float
        The candidate event's ``skew_25d``.
    prior_skews : np.ndarray
        Prior skews from :func:`load_skew_history`.
    keep_frac : float, optional
        Quantile to keep at or below. Defaults to ``LiveConfig.skew_keep_frac``.
    min_history : int, optional
        Minimum prior observations before the gate will fire. Defaults to ``40``.

    Returns
    -------
    bool
        Whether the event passes the low-skew gate.
    """
    if keep_frac >= 1.0:
        return True
    finite = prior_skews[np.isfinite(prior_skews)]
    if finite.size < min_history or not np.isfinite(skew_value):
        return False
    return bool(skew_value <= np.quantile(finite, keep_frac))


def record_skew_observation(
    ticker: str,
    announce_date: pd.Timestamp,
    skew_25d: float,
    history_path: str | Path = LIVE.skew_history_path,
) -> None:
    """Append one event's skew to the live history (called once per candidate)."""
    _append(
        history_path,
        {
            "ticker": ticker,
            "announce_date": pd.Timestamp(announce_date),
            "skew_25d": float(skew_25d),
        },
        ["ticker", "announce_date", "skew_25d"],
    )


# ── term gate panel ──────────────────────────────────────────────────────────


def record_term_observation(
    ticker: str,
    date: pd.Timestamp,
    iv_term_spread: float,
    panel_path: str | Path = LIVE.term_panel_path,
) -> None:
    """Append today's ``iv_term_spread`` for ``ticker`` to the trailing panel.

    Run daily, this accumulates the per-name distribution the term gate reads.
    Until a name has ``StrategyConfig.term_min_periods`` observations the gate
    rejects it (handled inside ``passes_term_filter_panel``).
    """
    _append(
        panel_path,
        {"ticker": ticker, "date": pd.Timestamp(date), "iv_term_spread": float(iv_term_spread)},
        ["ticker", "date", "iv_term_spread"],
    )


def passes_term_gate(
    ticker: str,
    announce_date: pd.Timestamp,
    iv_term_spread: float,
    panel_path: str | Path = LIVE.term_panel_path,
    pctl: float = LIVE.term_pctl,
) -> bool:
    """Evaluate the trailing-day term gate for one live event.

    Thin wrapper over ``filters.passes_term_filter_panel`` so the live gate is
    byte-for-byte the backtest gate. Returns ``False`` when the panel lacks
    enough trailing history for the name.
    """
    panel = _read(panel_path, ["ticker", "date", "iv_term_spread"])
    if panel.empty:
        return False
    event = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "announce_date": pd.Timestamp(announce_date),
                "iv_term_spread": iv_term_spread,
            }
        ]
    )
    return bool(passes_term_filter_panel(event, panel, pctl=pctl).iloc[0])


# ── open positions and the completed-trade ledger ────────────────────────────


def record_entry(row: dict, path: str | Path = LIVE.open_positions_path) -> None:
    """Persist one opened position (entry leg only; exit marked later)."""
    full = {c: row.get(c) for c in OPEN_COLUMNS}
    full["status"] = full.get("status") or "open"
    _append(path, full, OPEN_COLUMNS)


def load_open_positions(path: str | Path = LIVE.open_positions_path) -> pd.DataFrame:
    """Return the open-positions store (``status == 'open'`` rows)."""
    df = _read(path, OPEN_COLUMNS)
    return df[df["status"] == "open"].reset_index(drop=True) if not df.empty else df


def mark_exit(
    position: pd.Series,
    spot_exit: float,
    iv_exit: float,
    exit_date: pd.Timestamp,
    t_exit: float,
    *,
    costs: CostModel | None = None,
    r: float = 0.0,
    ledger_path: str | Path = LIVE.paper_ledger_path,
    open_path: str | Path = LIVE.open_positions_path,
) -> dict:
    """Close one position into the ledger schema and flip its open-store status.

    Reuses ``pnl.build_trade`` so the completed paper trade is priced exactly
    like a backtest trade (entry credit at ``iv_entry``, bought back at
    ``iv_exit`` and ``spot_exit``). The new ledger row is appended to the paper
    ledger and the position's ``status`` is set to ``closed``.

    Parameters
    ----------
    position : pd.Series
        A row from :func:`load_open_positions`.
    spot_exit, iv_exit : float
        Post-event underlying price and front ATM implied vol (the crush).
    exit_date : pd.Timestamp
        The realised exit date.
    t_exit : float
        Time-to-expiry of the front leg at exit, in years.
    costs : CostModel, optional
        Full cost stack; ``None`` uses commission-only (matching the headline
        backtest ledger).
    r : float, optional
        Risk-free rate. Defaults to ``0.0``.

    Returns
    -------
    dict
        The completed ledger row.
    """
    trade = build_trade(
        ticker=position["ticker"],
        entry_date=position["entry_date"],
        exit_date=pd.Timestamp(exit_date),
        spot_entry=float(position["spot_entry"]),
        strike=float(position["strike"]),
        t_entry=float(position["t_entry"]),
        t_exit=float(t_exit),
        iv_entry=float(position["iv_entry"]),
        iv_exit=float(iv_exit),
        spot_exit=float(spot_exit),
        contracts=int(position["contracts"]),
        r=r,
        costs=costs,
    )
    columns = LEDGER_COLUMNS + (
        ["exchange_fee", "spread_cost", "slippage_cost", "total_cost"] if costs is not None else []
    )
    _append(ledger_path, trade, columns)
    _close_position(position, open_path)
    return trade


def _close_position(position: pd.Series, open_path: str | Path) -> None:
    """Flip the matching open-store row to ``status == 'closed'``."""
    p = Path(open_path)
    df = _read(p, OPEN_COLUMNS)
    if df.empty:
        return
    match = (df["ticker"] == position["ticker"]) & (
        pd.to_datetime(df["entry_date"]) == pd.Timestamp(position["entry_date"])
    )
    df.loc[match, "status"] = "closed"
    df.to_parquet(p, index=False)
