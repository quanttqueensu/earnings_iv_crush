"""Pytest bootstrap: the project root on ``sys.path``, and no test can reach a network or broker.

Lets tests do ``from earnings_iv_crush.data import ...`` regardless of where pytest is invoked.
This file lives at the project root, so pytest imports it before collecting any test, which is
when the network guard below is installed.

The guard refuses every socket connection to a non-loopback address, and every loopback
connection to an Interactive Brokers gateway port (paper or live), because the gateway listens on
localhost and a test that reached it would talk to the paper account. Loopback on any other port
stays open: asyncio builds its self-pipe from a loopback socket pair on Windows. There is
deliberately no switch to turn the guard off; a test that needs a connection takes a fake.
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from earnings_iv_crush.config import LIVE  # noqa: E402
from earnings_iv_crush.ops.orient import PAPER_PORTS  # noqa: E402

# ── network guard ─────────────────────────────────────────────────────────────

# The dockerised gateway relays paper on 4004 (LiveConfig docstring); the other ports come from
# LiveConfig and orient, so a port added there is guarded here too.
_DOCKER_PAPER_RELAY_PORT = 4004
GATEWAY_PORTS = frozenset(
    {*LIVE.ib_live_ports, LIVE.ib_paper_port, *PAPER_PORTS, _DOCKER_PAPER_RELAY_PORT}
)


class NetworkBlockedError(RuntimeError):
    """A test tried to open a connection the guard refuses."""


def _is_loopback(host: Any) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _refuse(address: Any) -> None:
    if not isinstance(address, tuple) or len(address) < 2:
        return  # AF_UNIX and other non-IP families carry no network peer
    host, port = address[0], address[1]
    if not _is_loopback(host):
        raise NetworkBlockedError(f"tests may not connect to {host}:{port}; use a fake")
    if port in GATEWAY_PORTS:
        raise NetworkBlockedError(f"tests may not connect to the IB gateway port {port}")


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


def _connect(self: socket.socket, address: Any) -> None:
    _refuse(address)
    _real_connect(self, address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    _refuse(address)
    return _real_connect_ex(self, address)


def _create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    _refuse(address)
    return _real_create_connection(address, *args, **kwargs)


socket.socket.connect = _connect  # type: ignore[method-assign]
socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
socket.create_connection = _create_connection
