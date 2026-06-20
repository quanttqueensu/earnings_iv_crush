"""
ib_connection.py
Guarded connection to a TWS / IB Gateway **paper** account.

Two safety rails sit between this code and a broker:

1. a **paper-port guard** - the connection refuses any port listed as a live
   port in ``LiveConfig.ib_live_ports`` (TWS 7496, IB Gateway 4001), so a typo
   can never point the loop at a funded account; and
2. a **kill-switch file** - ``kill_switch_active`` reports whether the sentinel
   file exists, so the orchestrator can stop opening new positions without
   stopping the scheduled task or touching open ones.

``ib_async`` is imported lazily inside the functions so the rest of the package
(and the test suite) imports cleanly when the optional dependency is absent.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import LIVE

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ib_async import IB


class LivePortError(RuntimeError):
    """Raised when a connection is attempted against a known live-account port."""


def kill_switch_active(path: str | Path = LIVE.kill_switch_file) -> bool:
    """Return ``True`` when the kill-switch sentinel file exists.

    The orchestrator checks this before opening any position. Create the file
    (``type nul > outputs\\live\\STOP`` on Windows, ``touch`` on POSIX) to halt
    new entries; delete it to resume. Open positions are never affected.

    Parameters
    ----------
    path : str or Path, optional
        Sentinel path. Defaults to ``LiveConfig.kill_switch_file``.

    Returns
    -------
    bool
        Whether new entries are currently disabled.
    """
    return Path(path).exists()


def _require_ib():
    """Import and return the ``ib_async`` module, with an actionable error."""
    try:
        import ib_async
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "ib_async is not installed. Run `python -m pip install ib_async` "
            "into the project interpreter, then retry."
        ) from exc
    return ib_async


def connect_paper(
    host: str = LIVE.ib_host,
    port: int = LIVE.ib_paper_port,
    client_id: int = LIVE.ib_client_id,
    *,
    live_ports: tuple[int, ...] = LIVE.ib_live_ports,
    timeout: float = 8.0,
) -> IB:
    """Connect to TWS / IB Gateway on a **paper** port and return the ``IB`` handle.

    Refuses to connect to any port in ``live_ports`` (the paper-port guard).
    ``readonly=False`` is set so orders can be transmitted; the caller still
    decides per-order whether to actually transmit.

    Parameters
    ----------
    host : str
        API host. Defaults to ``LiveConfig.ib_host`` (loopback).
    port : int
        Paper socket port. Defaults to ``LiveConfig.ib_paper_port`` (TWS 7497).
    client_id : int
        API client id. Defaults to ``LiveConfig.ib_client_id``.
    live_ports : tuple of int, optional
        Ports treated as live accounts and therefore refused.
    timeout : float, optional
        Connection timeout in seconds. Defaults to ``8.0``.

    Returns
    -------
    ib_async.IB
        A connected client.

    Raises
    ------
    LivePortError
        If ``port`` is a known live-account port.
    """
    if port in live_ports:
        raise LivePortError(
            f"Refusing to connect on port {port}: that is a LIVE-account port "
            f"({live_ports}). Use the paper port {LIVE.ib_paper_port}. No order "
            "will ever be sent to a funded account from this harness."
        )
    ib_async = _require_ib()
    ib = ib_async.IB()
    ib.connect(host, port, clientId=client_id, readonly=False, timeout=timeout)
    return ib


@contextmanager
def paper_session(
    host: str = LIVE.ib_host,
    port: int = LIVE.ib_paper_port,
    client_id: int = LIVE.ib_client_id,
) -> Iterator[IB]:
    """Context manager yielding a connected paper ``IB``, disconnected on exit.

    Examples
    --------
    >>> with paper_session() as ib:  # doctest: +SKIP
    ...     ib.reqCurrentTime()
    """
    ib = connect_paper(host, port, client_id)
    try:
        yield ib
    finally:
        if ib.isConnected():
            ib.disconnect()
