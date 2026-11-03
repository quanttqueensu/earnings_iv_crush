"""
test_gateway_probe.py
Pins the cloud gateway probe against fake gateways.

The probe gates the unattended daily pass, so each state it must tell apart is
exercised: logged in, listening but logged out (startup sync times out), nothing
listening, a live-account port, and a gateway that reports a funded account.
No test opens a socket or touches a broker.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_PATH = Path(__file__).resolve().parents[2] / "deploy" / "gateway_probe.py"
_spec = importlib.util.spec_from_file_location("gateway_probe", _PATH)
assert _spec is not None and _spec.loader is not None
gateway_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gateway_probe)


class _FakeClient:
    def __init__(self, accounts: list[str]) -> None:
        self._accounts = accounts

    def getAccounts(self) -> list[str]:  # noqa: N802 - mirrors ib_async
        return self._accounts


class _FakeIB:
    def __init__(self, accounts: list[str], connect_error: BaseException | None = None) -> None:
        self.client = _FakeClient(accounts)
        self._error = connect_error
        self.connect_kwargs: dict[str, Any] = {}
        self.disconnected = False

    def connect(self, host: str, port: int, **kwargs: Any) -> None:
        self.connect_kwargs = kwargs
        if self._error is not None:
            raise self._error

    def disconnect(self) -> None:
        self.disconnected = True


def _run(fake: _FakeIB, *, port: int = 4004, listening: bool = True) -> tuple[int, str]:
    return gateway_probe.probe(
        "ib-gateway",
        port,
        ib_factory=lambda: fake,
        socket_open=lambda h, p, t: listening,
    )


def test_logged_in_paper_gateway_passes_read_only():
    fake = _FakeIB(["DU3924858"])
    status, _ = _run(fake)
    assert status == gateway_probe.OK
    assert fake.connect_kwargs["readonly"] is True
    assert fake.connect_kwargs["raiseSyncErrors"] is True
    assert fake.connect_kwargs["clientId"] != gateway_probe.LIVE.ib_client_id
    assert fake.disconnected


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError(["positions request timed out"]),  # logged out: sync times out
        TimeoutError(),  # handshake never completes
        ConnectionResetError(),
    ],
)
def test_listening_but_logged_out(error):
    fake = _FakeIB(["DU3924858"], connect_error=error)
    status, reason = _run(fake)
    assert status == gateway_probe.LOGGED_OUT
    assert "not logged in" in reason
    assert fake.disconnected


def test_no_accounts_is_logged_out():
    assert _run(_FakeIB([]))[0] == gateway_probe.LOGGED_OUT


def test_nothing_listening():
    fake = _FakeIB(["DU3924858"])
    assert _run(fake, listening=False)[0] == gateway_probe.UNREACHABLE
    assert fake.connect_kwargs == {}


@pytest.mark.parametrize("port", [7496, 4001, 4003])
def test_live_ports_refused_before_any_connection(port):
    fake = _FakeIB(["DU3924858"])
    status, _ = _run(fake, port=port, listening=True)
    assert status == gateway_probe.REFUSED
    assert fake.connect_kwargs == {}


@pytest.mark.parametrize("accounts", [["U1234567"], ["DU3924858", "U1234567"]])
def test_funded_account_refused(accounts):
    assert _run(_FakeIB(accounts))[0] == gateway_probe.REFUSED
