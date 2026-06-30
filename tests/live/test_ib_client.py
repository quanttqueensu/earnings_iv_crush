"""
test_ib_client.py
Offline tests for the IBKR paper plumbing.

A fake ``IB`` drives every networked path so the suite needs no gateway: the
pure selection helpers, the paper-account safety guard, chain normalisation to
``CHAIN_COLUMNS``, ATM straddle construction and the order guards.
"""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from earnings_iv_crush.data.options import CHAIN_COLUMNS
from live.config import LIVE
from live.ib_client import (
    IBClient,
    NotPaperAccountError,
    StraddleSpec,
    atm_strike,
    select_expiry,
    strikes_in_band,
    to_ib_symbol,
)

EXPIRIES = ["20240119", "20240216", "20240315"]
STRIKES = [90.0, 95.0, 100.0, 105.0, 110.0]


# ── Fake gateway ─────────────────────────────────────────────────────────────


class _StockTick:
    def __init__(self, contract: object, price: float) -> None:
        self.contract = contract
        self._price = price
        self.last = price
        self.close = price
        self.bid = price - 0.01
        self.ask = price + 0.01
        self.modelGreeks = None

    def marketPrice(self) -> float:
        return self._price


class _OptTick:
    def __init__(self, contract: object, bid: float, ask: float, iv: float) -> None:
        self.contract = contract
        self.bid = bid
        self.ask = ask
        self.last = float("nan")
        self.close = float("nan")
        self.modelGreeks = SimpleNamespace(impliedVol=iv)

    def marketPrice(self) -> float:
        return float("nan")


class FakeIB:
    """A minimal stand-in for ``ib_async.IB`` covering the calls IBClient makes."""

    def __init__(
        self,
        accounts: tuple[str, ...] = ("DU111",),
        spot: float = 101.0,
        connect_raises: bool = False,
    ) -> None:
        self._accounts = list(accounts)
        self._spot = spot
        self._connect_raises = connect_raises
        self._connected = False
        self.market_data_type: int | None = None
        self.orders: list[object] = []
        self.ports_tried: list[int] = []

    def connect(self, host, port, clientId, readonly, timeout) -> None:  # noqa: N803
        self.ports_tried.append(port)
        if self._connect_raises:
            raise ConnectionRefusedError(port)
        self._connected = True

    def isConnected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def managedAccounts(self) -> list[str]:
        return self._accounts

    def reqMarketDataType(self, t: int) -> None:
        self.market_data_type = t

    def qualifyContracts(self, *cs: object) -> list[object]:
        for i, c in enumerate(cs):
            if not getattr(c, "conId", 0):
                c.conId = 1000 + i
        return list(cs)

    def reqSecDefOptParams(self, symbol, ftc, sectype, conid):  # noqa: ANN001
        return [
            SimpleNamespace(
                exchange="SMART",
                expirations=EXPIRIES,
                strikes=STRIKES,
                tradingClass=symbol,
                multiplier="100",
            )
        ]

    def reqTickers(self, *cs: object) -> list[object]:
        out: list[object] = []
        for c in cs:
            if getattr(c, "secType", "") == "STK":
                out.append(_StockTick(c, self._spot))
            else:
                out.append(_OptTick(c, bid=2.0, ask=2.4, iv=0.55))
        return out

    def placeOrder(self, contract: object, order: object) -> object:
        trade = SimpleNamespace(contract=contract, order=order)
        self.orders.append(trade)
        return trade

    def positions(self) -> list[object]:
        return []


def _client(ib: FakeIB, **cfg_overrides: object) -> IBClient:
    return IBClient(config=replace(LIVE, **cfg_overrides), ib=ib)


# ── Pure helpers ─────────────────────────────────────────────────────────────


def test_to_ib_symbol_maps_share_class():
    assert to_ib_symbol("BRK-B") == "BRK B"
    assert to_ib_symbol("aapl") == "AAPL"
    assert to_ib_symbol("BRK.B") == "BRK B"


def test_select_expiry_nearest_within_horizon():
    asof = pd.Timestamp("2024-01-02")
    assert select_expiry(EXPIRIES, asof, horizon_days=45) == "20240119"
    # horizon too short: nothing qualifies
    assert select_expiry(EXPIRIES, asof, horizon_days=5) is None
    # as-of past the first expiry rolls to the next
    assert select_expiry(EXPIRIES, pd.Timestamp("2024-01-20"), 45) == "20240216"


def test_atm_and_band_selection():
    assert atm_strike(STRIKES, 101.0) == 100.0
    assert atm_strike([], 100.0) is None
    band = strikes_in_band(STRIKES, 100.0, 0.07)
    assert band == [95.0, 100.0, 105.0]


# ── Connection + safety ──────────────────────────────────────────────────────


def test_connect_returns_paper_account_and_sets_data_type():
    ib = FakeIB(accounts=("DU111",))
    client = _client(ib)
    assert client.connect() == "DU111"
    assert ib.market_data_type == LIVE.market_data_type
    assert ib.ports_tried == [LIVE.paper_ports[0]]


def test_connect_refuses_live_account_when_not_allowed():
    ib = FakeIB(accounts=("U999",))
    client = _client(ib)
    with pytest.raises(NotPaperAccountError):
        client.connect()
    assert not ib.isConnected()


def test_connect_allows_live_account_when_opted_in():
    ib = FakeIB(accounts=("U999",))
    client = _client(ib, allow_live=True)
    assert client.connect() == "U999"


def test_connect_raises_when_no_port_open():
    ib = FakeIB(connect_raises=True)
    client = _client(ib)
    with pytest.raises(ConnectionError):
        client.connect()
    # both paper ports attempted
    assert ib.ports_tried == list(LIVE.paper_ports)


# ── Market data ──────────────────────────────────────────────────────────────


def test_spot_prefers_market_price():
    client = _client(FakeIB(spot=123.45))
    client.connect()
    assert client.spot("AAPL") == pytest.approx(123.45)


def test_fetch_chain_schema_and_content():
    ib = FakeIB(spot=101.0)
    client = _client(ib)
    client.connect()
    chain = client.fetch_chain("AAPL", asof=pd.Timestamp("2024-01-02"), strike_window=0.07)
    assert list(chain.columns) == CHAIN_COLUMNS
    # 3 strikes in the 7% band x call+put
    assert len(chain) == 6
    assert set(chain["right"]) == {"C", "P"}
    assert (chain["iv"] == 0.55).all()
    assert chain["open_interest"].isna().all()
    assert chain["expiry"].iloc[0] == pd.Timestamp("2024-01-19")


def test_fetch_chain_empty_when_no_expiry_in_horizon():
    client = _client(FakeIB())
    client.connect()
    chain = client.fetch_chain("AAPL", asof=pd.Timestamp("2024-01-02"), horizon_days=3)
    assert chain.empty
    assert list(chain.columns) == CHAIN_COLUMNS


# ── Execution ────────────────────────────────────────────────────────────────


def test_straddle_contracts_picks_atm():
    ib = FakeIB(spot=101.0)
    client = _client(ib)
    client.connect()
    spec = client.straddle_contracts("AAPL", asof=pd.Timestamp("2024-01-02"))
    assert isinstance(spec, StraddleSpec)
    assert spec.strike == 100.0
    assert spec.expiry == "20240119"
    assert spec.call.right == "C" and spec.put.right == "P"


def test_place_short_straddle_blocked_in_read_only():
    ib = FakeIB()
    client = _client(ib)  # read_only defaults True
    client.connect()
    spec = client.straddle_contracts("AAPL", asof=pd.Timestamp("2024-01-02"))
    with pytest.raises(PermissionError):
        client.place_short_straddle(spec, contracts=1)
    assert ib.orders == []


def test_place_short_straddle_routes_two_legs():
    ib = FakeIB()
    client = _client(ib, read_only=False)
    client.connect()
    spec = client.straddle_contracts("AAPL", asof=pd.Timestamp("2024-01-02"))
    trades = client.place_short_straddle(spec, contracts=2)
    assert len(trades) == 2
    assert [t.order.action for t in trades] == ["SELL", "SELL"]
    assert all(t.order.totalQuantity == 2 for t in trades)


def test_order_size_cap_enforced():
    client = _client(FakeIB(), read_only=False)
    client.connect()
    spec = client.straddle_contracts("AAPL", asof=pd.Timestamp("2024-01-02"))
    with pytest.raises(ValueError):
        client.place_short_straddle(spec, contracts=LIVE.max_contracts + 1)


def test_close_buys_back_both_legs():
    ib = FakeIB()
    client = _client(ib, read_only=False)
    client.connect()
    spec = client.straddle_contracts("AAPL", asof=pd.Timestamp("2024-01-02"))
    closes = client.close_short_straddle(spec, contracts=1)
    assert [t.order.action for t in closes] == ["BUY", "BUY"]


def test_iv_nan_safe_row():
    # a tick with no greeks should still map, with NaN iv
    tick = SimpleNamespace(
        contract=SimpleNamespace(lastTradeDateOrContractMonth="20240119", strike=100.0, right="C"),
        bid=float("nan"),
        ask=2.0,
        modelGreeks=None,
    )
    row = IBClient._tick_to_row(tick)
    assert math.isnan(row["iv"])
    assert math.isnan(row["bid"])
    assert row["ask"] == 2.0
