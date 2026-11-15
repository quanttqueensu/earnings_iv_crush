"""
test_netguard.py
The test-suite network guard in ``conftest.py`` is installed and refuses what it should.

No test may reach a network or a broker. The guard refuses non-loopback connections and loopback
connections to any Interactive Brokers gateway port; these tests prove it is active in this
session, that the gateway ports it guards include the configured paper and live ports, and that
ordinary loopback (which asyncio needs) still works. No connection here leaves the machine: each
refused call raises before the real ``connect`` runs.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

import conftest
from earnings_iv_crush.config import LIVE

# TEST-NET-1 (RFC 5737): reserved for documentation, never routed.
_UNROUTABLE = "192.0.2.1"


def test_guard_is_installed() -> None:
    assert socket.socket.connect is conftest._connect
    assert socket.create_connection is conftest._create_connection


def test_gateway_ports_include_configured_paper_and_live_ports() -> None:
    assert LIVE.ib_paper_port in conftest.GATEWAY_PORTS
    assert set(LIVE.ib_live_ports) <= conftest.GATEWAY_PORTS


def test_external_connection_is_refused() -> None:
    with pytest.raises(conftest.NetworkBlockedError, match="may not connect"):
        socket.create_connection((_UNROUTABLE, 443), timeout=0.1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(conftest.NetworkBlockedError):
            s.connect((_UNROUTABLE, 80))
        with pytest.raises(conftest.NetworkBlockedError):
            s.connect_ex((_UNROUTABLE, 80))


@pytest.mark.parametrize("port", sorted(conftest.GATEWAY_PORTS))
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_gateway_ports_are_refused(host: str, port: int) -> None:
    with pytest.raises(conftest.NetworkBlockedError, match="gateway port"):
        socket.create_connection((host, port), timeout=0.1)


def test_ordinary_loopback_still_works() -> None:
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"ok")
        assert b.recv(2) == b"ok"
    asyncio.run(asyncio.sleep(0))
