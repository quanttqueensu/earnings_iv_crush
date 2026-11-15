"""
gateway_probe.py
Check that the paper gateway is logged in to IBKR, not merely listening.

IB Gateway keeps its API port open after it loses its broker session (for example
when a nightly reconnect is refused and IBC leaves the error dialog up). A bare
socket check then passes, the session pass connects, every startup request times
out, and the pass hangs. This probe connects read-only with its own client id,
asks for positions only, and treats an unanswered request as logged out.

It never sends, modifies or cancels an order, refuses every live-account port,
and fails if any account the gateway reports is not a paper (DU) account.

Exit status: 0 logged in, 1 port unreachable, 2 listening but not logged in,
3 refused (live port or non-paper account).

Usage
-----
    python deploy/gateway_probe.py                 # IB_HOST / IB_PORT from the environment
    python deploy/gateway_probe.py --host ib-gateway --port 4004
"""

from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Callable, Sequence
from typing import Any

from earnings_iv_crush.config import LIVE

# ── constants ──

OK, UNREACHABLE, LOGGED_OUT, REFUSED = 0, 1, 2, 3

# Distinct from the session pass (ib_client_id) and the research scripts (+1, +2),
# so a probe can never collide with a pass that is already connected.
PROBE_CLIENT_ID = LIVE.ib_client_id + 3

# A logged-in paper gateway answers the positions request in well under a second;
# 20 s leaves room for a slow swap-bound 1 GB host without letting a dead session
# pass for long.
PROBE_TIMEOUT_S = 20.0
SOCKET_TIMEOUT_S = 5.0

# Paper account ids at IBKR start with "DU"; anything else is a funded account.
PAPER_ACCOUNT_PREFIX = "DU"


# ── probe ──


def _default_ib_factory() -> Any:
    from ib_async import IB

    return IB()


def _socket_open(host: str, port: int, timeout: float) -> bool:
    try:
        socket.create_connection((host, port), timeout).close()
    except OSError:
        return False
    return True


def probe(
    host: str,
    port: int,
    *,
    client_id: int = PROBE_CLIENT_ID,
    timeout: float = PROBE_TIMEOUT_S,
    live_ports: tuple[int, ...] = LIVE.ib_live_ports,
    ib_factory: Callable[[], Any] = _default_ib_factory,
    socket_open: Callable[[str, int, float], bool] = _socket_open,
) -> tuple[int, str]:
    """Classify the gateway at ``host:port``.

    Parameters
    ----------
    host, port : str, int
        API endpoint of the paper gateway.
    client_id : int, optional
        API client id for the probe connection.
    timeout : float, optional
        Seconds allowed for the handshake and the positions request.
    live_ports : tuple of int, optional
        Ports that belong to a live account; the probe refuses them.
    ib_factory : callable, optional
        Returns an ``ib_async.IB``-like object. Injected by tests.
    socket_open : callable, optional
        Bare TCP reachability check. Injected by tests.

    Returns
    -------
    tuple of (int, str)
        Exit status (``OK``, ``UNREACHABLE``, ``LOGGED_OUT`` or ``REFUSED``) and a
        one-line reason.
    """
    if port in live_ports:
        return REFUSED, f"port {port} is a live-account port {live_ports}; not probing"
    if not socket_open(host, port, SOCKET_TIMEOUT_S):
        return UNREACHABLE, f"nothing listening on {host}:{port}"

    from ib_async import StartupFetch

    ib = ib_factory()
    try:
        # raiseSyncErrors turns the silent "positions request timed out" of a
        # logged-out gateway into an exception.
        ib.connect(
            host,
            port,
            clientId=client_id,
            readonly=True,
            timeout=timeout,
            raiseSyncErrors=True,
            fetchFields=StartupFetch.POSITIONS,
        )
        accounts = list(ib.client.getAccounts())
    except Exception as exc:  # any failure after the socket opened means no usable session
        return LOGGED_OUT, f"{host}:{port} is listening but not logged in ({exc!r})"
    finally:
        ib.disconnect()

    if not accounts:
        return LOGGED_OUT, f"{host}:{port} reported no accounts"
    funded = [a for a in accounts if not a.startswith(PAPER_ACCOUNT_PREFIX)]
    if funded:
        return REFUSED, f"non-paper account(s) on {host}:{port}: {len(funded)} of {len(accounts)}"
    return OK, f"logged in, {len(accounts)} paper account(s)"


# ── cli ──


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default=LIVE.ib_host)
    ap.add_argument("--port", type=int, default=LIVE.ib_paper_port)
    args = ap.parse_args(argv)
    status, reason = probe(args.host, args.port)
    print(f"gateway probe: {reason}")
    return status


if __name__ == "__main__":
    sys.exit(main())
