"""
order_events.py
Append-only record of every order state change in the paper book.

The forward-test specification (section 6) makes this log the primary record: the
ledgers are derived from it and must reconcile to it. Two properties matter more
than convenience:

* a row is written **before** the harness acts on the event it describes, so a
  crash leaves evidence of what was about to happen rather than a silent gap; and
* the file is appended one line at a time (CSV), never rewritten, so a process
  that dies mid-write loses at most the line in flight.

:func:`check_completeness` applies the specification's lifecycle rule: every order
that was submitted has a terminal row, and the terminal cumulative fill equals the
sum of the fills recorded against it.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import LIVE

ORDER_EVENT_COLUMNS = [
    "event_id",
    "run_id",
    "ts_utc",
    "ts_broker",
    "session_date",
    "ticker",
    "position_key",
    "leg",
    "con_id",
    "strike",
    "expiry",
    "purpose",
    "side",
    "order_id",
    "perm_id",
    "rung",
    "cross_frac",
    "event",
    "status",
    "order_qty",
    "limit_price",
    "fill_qty",
    "fill_price",
    "cum_filled",
    "avg_fill_price",
    "remaining",
    "commission",
    "nbbo_bid",
    "nbbo_ask",
    "nbbo_bid_size",
    "nbbo_ask_size",
    "nbbo_ts_utc",
    "market_data_type",
    "underlying_bid",
    "underlying_ask",
    "reason",
    "transmit",
]

EVENTS = (
    "submit",
    "modify",
    "status",
    "fill",
    "cancel_req",
    "cancel_ack",
    "reject",
    "hold_stale_quote",
    "skip_bad_book",
    "nbbo_1559",
    "halt",
    "alarm",
)

TERMINAL_STATUSES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})


def position_key(ticker: str, entry_date: Any, strike: float, expiry: Any) -> str:
    """``ticker|entry_date|strike|expiry``: joins an entry lifecycle to its exit."""
    return (
        f"{ticker}|{pd.Timestamp(entry_date).date()}|{float(strike):g}|"
        f"{pd.Timestamp(expiry).date()}"
    )


class OrderEventLog:
    """Writer for one pass's order events.

    Parameters
    ----------
    path : str or Path
        The CSV store. Created with a header when absent.
    session_date : pandas.Timestamp
        Exchange date of the pass.
    transmit : bool
        Whether this pass transmits. Dry-run rows are intents, flagged ``False``.
    market_data_type : int
        IB market-data mode in force (1 real time, 3 delayed, 4 delayed-frozen).
        Only type-1 rows count toward the P&L verdict (specification section 11).
    run_id : str, optional
        Pass identifier; a fresh UUID4 when omitted.
    """

    def __init__(
        self,
        path: str | Path,
        session_date: pd.Timestamp,
        *,
        transmit: bool,
        market_data_type: int = LIVE.ib_market_data_type,
        run_id: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.session_date = pd.Timestamp(session_date).normalize()
        self.transmit = bool(transmit)
        self.market_data_type = int(market_data_type)
        self.run_id = run_id or str(uuid.uuid4())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(ORDER_EVENT_COLUMNS)

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        """Append one event row and return it.

        Unknown field names raise, so a typo cannot silently drop a column.

        Raises
        ------
        ValueError
            If ``event`` is not a known event type or a field is not in the schema.
        """
        if event not in EVENTS:
            raise ValueError(f"Unknown order event {event!r}; expected one of {EVENTS}.")
        unknown = set(fields) - set(ORDER_EVENT_COLUMNS)
        if unknown:
            raise ValueError(f"Fields not in the order-event schema: {sorted(unknown)}.")
        row: dict[str, Any] = {c: None for c in ORDER_EVENT_COLUMNS}
        row.update(
            event_id=str(uuid.uuid4()),
            run_id=self.run_id,
            ts_utc=pd.Timestamp.now(tz="UTC").isoformat(),
            session_date=str(self.session_date.date()),
            market_data_type=self.market_data_type,
            transmit=self.transmit,
        )
        row.update(fields)
        row["event"] = event
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([_cell(row[c]) for c in ORDER_EVENT_COLUMNS])
            fh.flush()
        return row


def _cell(value: Any) -> Any:
    """CSV cell for one value: empty for missing, ISO text for timestamps."""
    if value is None:
        return ""
    if isinstance(value, float) and not np.isfinite(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def load_order_events(path: str | Path = LIVE.order_events_path) -> pd.DataFrame:
    """Read the order-event log, empty-framed with the schema when absent."""
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=ORDER_EVENT_COLUMNS)
    return pd.read_csv(p, dtype={"order_id": "Int64", "perm_id": "Int64"})


def check_completeness(events: pd.DataFrame) -> pd.DataFrame:
    """Lifecycles that break the specification's completeness rule.

    An order lifecycle (one ``order_id`` within a ``run_id``) is complete when it
    has a ``submit`` row and a row whose ``status`` is terminal, and the
    ``cum_filled`` on the last terminal row equals the sum of ``fill_qty`` over its
    ``fill`` rows. Dry-run intents carry no order id and are not lifecycles.

    Parameters
    ----------
    events : pandas.DataFrame
        Rows in the :data:`ORDER_EVENT_COLUMNS` schema.

    Returns
    -------
    pandas.DataFrame
        One row per incomplete lifecycle: ``run_id``, ``order_id``, ``problem``.
        Empty when every lifecycle is complete.
    """
    problems: list[dict[str, Any]] = []
    placed = events[events["order_id"].notna()]
    for (run_id, order_id), rows in placed.groupby(["run_id", "order_id"], sort=False):
        evs = set(rows["event"])
        if "submit" not in evs:
            problems.append({"run_id": run_id, "order_id": order_id, "problem": "no_submit"})
            continue
        terminal = rows[rows["status"].isin(TERMINAL_STATUSES)]
        if terminal.empty:
            problems.append({"run_id": run_id, "order_id": order_id, "problem": "no_terminal"})
            continue
        fills = pd.to_numeric(rows.loc[rows["event"] == "fill", "fill_qty"], errors="coerce")
        cum = pd.to_numeric(terminal["cum_filled"], errors="coerce").iloc[-1]
        if not np.isclose(float(fills.fillna(0).sum()), float(0 if pd.isna(cum) else cum)):
            problems.append(
                {"run_id": run_id, "order_id": order_id, "problem": "fill_sum_mismatch"}
            )
    return pd.DataFrame(problems, columns=["run_id", "order_id", "problem"])


def completeness_share(events: pd.DataFrame) -> float:
    """Share of order lifecycles that are complete (NaN when there are none)."""
    placed = events[events["order_id"].notna()]
    n = placed.groupby(["run_id", "order_id"]).ngroups
    if n == 0:
        return float("nan")
    return 1.0 - len(check_completeness(events)) / n


def iter_alarm_rows(events: pd.DataFrame, run_id: str) -> Iterable[str]:
    """Reason text of every alarm row a pass wrote, for the end-of-pass summary."""
    rows = events[(events["run_id"] == run_id) & (events["event"] == "alarm")]
    return [str(r) for r in rows["reason"].fillna("")]
