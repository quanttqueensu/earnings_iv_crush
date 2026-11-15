"""
test_session.py
The daily session pass, offline, on a fake gateway and clock (forward-test spec T4, T5, T9).

Pins: the 2-of-3 calendar rule; ex-dividend and expiry filters; deterministic admission
under the name cap; a transmitted entry is booked from its fills and an unfilled one is
not booked at all; a dry pass writes only to the dry stores and never reads the live
book; HALT stops the pass; STOP blocks entries while exits still run; an exit whose
broker position does not match is not sent; the drivers run the session guard first.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from earnings_iv_crush.config import LIVE
from earnings_iv_crush.live import paper_book
from earnings_iv_crush.live import session as ses
from earnings_iv_crush.live.order_events import (
    check_completeness,
    load_order_events,
    prior_exit_fills,
)
from tests.live.test_ladder import FakeClock, FakeGateway

ROOT = Path(__file__).resolve().parents[2]
DAY = pd.Timestamp("2026-10-19")  # Monday
EXPIRY = pd.Timestamp("2026-10-23")


# ── calendar rule ────────────────────────────────────────────────────────────


def _votes(rows: list[tuple[str, str, str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["source", "ticker", "announce_date", "session"])


@pytest.mark.parametrize(
    "rows, confirmed, session, is_today",
    [
        (
            [("finnhub", "A", "2026-10-19", "amc"), ("nasdaq", "A", "2026-10-19", "amc")],
            True,
            "amc",
            True,
        ),
        (
            [("finnhub", "A", "2026-10-19", "amc"), ("nasdaq", "A", "2026-10-19", "bmo")],
            False,
            None,
            False,
        ),
        (
            [
                ("finnhub", "A", "2026-10-20", "bmo"),
                ("nasdaq", "A", "2026-10-20", "bmo"),
                ("yahoo", "A", "2026-10-19", "amc"),
            ],
            True,
            "bmo",
            True,
        ),
        (
            [("finnhub", "A", "2026-10-20", "dmh"), ("yahoo", "A", "2026-10-20", "bmo")],
            True,
            "bmo",
            True,
        ),
        (
            [("finnhub", "A", "2026-10-19", ""), ("nasdaq", "A", "2026-10-19", float("nan"))],
            False,
            None,
            False,
        ),
        (
            [("finnhub", "A", "2026-10-21", "amc"), ("nasdaq", "A", "2026-10-21", "amc")],
            True,
            "amc",
            False,
        ),  # confirmed, but its entry is Wednesday
    ],
)
def test_two_of_three_calendar_rule(rows, confirmed, session, is_today) -> None:
    out = ses.confirm_events(_votes(rows), DAY).iloc[0]
    assert bool(out["confirmed"]) is confirmed
    assert bool(out["is_today"]) is is_today
    if session:
        assert out["session"] == session
    assert "finnhub=" in out["detail"] or "yahoo=" in out["detail"]


@pytest.mark.parametrize(
    "dates, ok, reason",
    [
        ({"ib": "unreadable", "yahoo": "unreadable"}, False, "exdiv_unknown"),
        ({"ib": None, "yahoo": "unreadable"}, True, ""),
        ({"ib": pd.Timestamp("2026-10-20"), "yahoo": None}, False, "exdiv_in_window"),
        ({"ib": pd.Timestamp("2026-11-20"), "yahoo": pd.Timestamp("2026-08-01")}, True, ""),
    ],
)
def test_exdiv_decision(dates, ok, reason) -> None:
    assert ses.exdiv_decision(dates, DAY, pd.Timestamp("2026-10-20")) == (ok, reason)


def test_admission_order_is_deterministic_and_input_order_free() -> None:
    names = ["MMM", "GM", "HAL", "RTX", "PM"]
    a = ses.admission_order(names, DAY)
    assert a == ses.admission_order(list(reversed(names)), DAY)
    assert sorted(a) == sorted(names)
    assert a != ses.admission_order(names, DAY + pd.Timedelta(days=1))


def test_missing_universe_refuses_to_trade_the_tape(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        ses.load_universe(tmp_path / "nope.csv")


# ── fake market ──────────────────────────────────────────────────────────────


@pytest.fixture
def market(monkeypatch):
    """Patch the IB market and order helpers the session uses with a fake book."""
    state = {"expiries": [EXPIRY, pd.Timestamp("2026-10-30")], "held": {}}

    def qualify_underlying(ib, ticker):
        return SimpleNamespace(
            contract=SimpleNamespace(symbol=ticker, conId=hash(ticker)), spot=100.0
        )

    def option_grid(ib, under):
        return state["expiries"], [90.0, 95.0, 100.0, 105.0, 110.0]

    def snapshot_strikes(ib, under, expiry, strikes):
        return pd.DataFrame(
            [
                {
                    "expiry": expiry,
                    "strike": k,
                    "right": r,
                    "bid": 2.00,
                    "ask": 2.20,
                    "iv": 0.60,
                    "open_interest": float("nan"),
                }
                for k in strikes
                for r in ("C", "P")
            ]
        )

    def qualify_legs(ib, symbol, strike, expiry):
        base = abs(hash((symbol, strike, str(expiry)))) % 10_000 * 10
        return SimpleNamespace(right="C", conId=base + 1), SimpleNamespace(
            right="P", conId=base + 2
        )

    monkeypatch.setattr(ses.ib_market, "qualify_underlying", qualify_underlying)
    monkeypatch.setattr(ses.ib_market, "option_grid", option_grid)
    monkeypatch.setattr(ses.ib_market, "snapshot_strikes", snapshot_strikes)
    monkeypatch.setattr(ses.ib_orders, "qualify_straddle_legs", qualify_legs)
    monkeypatch.setattr(
        ses.ib_orders, "broker_short_qty", lambda ib, c: state["held"].get(c.right, 0)
    )
    state["positions"] = None  # None: derive the seeded ZZZ legs from "held"

    def option_positions(ib):
        if state["positions"] is not None:
            return state["positions"]
        return [
            (_contract("ZZZ", 100.0, EXPIRY, right), qty)
            for right, qty in state["held"].items()
            if qty
        ]

    monkeypatch.setattr(ses.ib_orders, "broker_option_positions", option_positions)
    return state


def _contract(symbol: str, strike: float, expiry: pd.Timestamp, right: str) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        strike=strike,
        lastTradeDateOrContractMonth=pd.Timestamp(expiry).strftime("%Y%m%d"),
        right=right,
        secType="OPT",
        localSymbol=f"{symbol} {pd.Timestamp(expiry):%y%m%d}{right}{int(strike * 1000):08d}",
    )


def _quotes(legs):
    return {leg.key: ses.LegQuote(2.00, 2.20) for leg in legs}


def _config(tmp_path, **kw):
    universe = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DDD", "EEE"]}).to_csv(universe, index=False)
    return dataclasses.replace(
        LIVE,
        universe_path=str(universe),
        halt_file=str(tmp_path / "HALT"),
        kill_switch_file=str(tmp_path / "STOP"),
        **kw,
    )


def _today_votes(names=("AAA", "BBB", "CCC", "DDD", "EEE")) -> pd.DataFrame:
    return _votes([(src, n, "2026-10-19", "amc") for n in names for src in ("finnhub", "nasdaq")])


def _run(tmp_path, gw, *, transmit, config=None, votes=None, exdiv=None):
    config = config or _config(tmp_path)
    stores = ses.Stores.for_mode(transmit, config, root=tmp_path / "live")
    result = ses.run_session(
        DAY,
        transmit=transmit,
        ib=gw,
        clock=FakeClock(),
        quote_fn=_quotes,
        votes=_today_votes() if votes is None else votes,
        config=config,
        exdiv_sources=exdiv or (lambda ib, u, t: {"ib": None, "yahoo": None}),
        stores=stores,
    )
    return result, stores


# ── the pass ─────────────────────────────────────────────────────────────────


def test_dry_pass_admits_the_cap_and_writes_only_dry_stores(tmp_path, market) -> None:
    gw = FakeGateway()
    result, stores = _run(tmp_path, gw, transmit=False)
    assert gw.placed == []
    assert result.funnel["today"] == 5 and result.funnel["admitted"] == 3
    open_dry = paper_book.load_open_positions(stores.open_positions)
    assert len(open_dry) == 3 and not open_dry["transmitted"].astype(bool).any()
    assert "dry" in Path(stores.open_positions).parts
    live_store = ses.Stores.for_mode(True, root=tmp_path / "live").open_positions
    assert not Path(live_store).exists()
    intended = pd.read_csv(stores.intended)
    assert (intended["reason"] == "cap_names").sum() == 2


def test_transmitted_entry_is_booked_from_fills(tmp_path, market) -> None:
    gw = FakeGateway(sell_fill={"C": 2.05, "P": 2.05})  # fills at rung 2 on both legs
    result, stores = _run(tmp_path, gw, transmit=True)
    assert not result.alarms
    book = paper_book.load_open_positions(stores.open_positions)
    assert len(book) == 3
    assert book["entry_fill_ps"].tolist() == pytest.approx([4.10] * 3)
    credit = book["entry_credit"] / (100 * book["contracts"])
    assert credit.tolist() == pytest.approx([4.10] * 3)  # the fill, not the model value
    assert check_completeness(load_order_events(stores.order_events)).empty


def test_unfilled_transmitted_entry_books_nothing(tmp_path, market) -> None:
    gw = FakeGateway()  # nothing ever fills
    result, stores = _run(tmp_path, gw, transmit=True)
    assert paper_book.load_open_positions(stores.open_positions).empty
    intended = pd.read_csv(stores.intended)
    admitted = intended[intended["decision"] == "admit"]
    assert len(admitted) == 3 and set(admitted["outcome"]) == {"unfilled"}


def test_halt_at_start_stops_everything(tmp_path, market) -> None:
    config = _config(tmp_path)
    Path(config.halt_file).write_text("")
    gw = FakeGateway()
    result, _ = _run(tmp_path, gw, transmit=True, config=config)
    assert gw.placed == [] and result.alarms


def _seed_due_position(path: str, ticker: str = "ZZZ") -> None:
    paper_book.record_entry(
        {
            "ticker": ticker,
            "announce_date": pd.Timestamp("2026-10-16"),
            "entry_date": pd.Timestamp("2026-10-16"),
            "exit_date": DAY,
            "front_expiry": EXPIRY,
            "strike": 100.0,
            "contracts": 2,
            "spot_entry": 100.0,
            "iv_entry": 0.80,
            "t_entry": 7 / 365,
            "entry_credit": 4.2 * 100 * 2,
            "margin": 2 * 100 * (0.2 * 100 + 4.2),
            "transmitted": True,
        },
        path=path,
    )


def test_stop_blocks_entries_but_exits_run(tmp_path, market) -> None:
    config = _config(tmp_path)
    Path(config.kill_switch_file).write_text("")
    gw = FakeGateway(buy_fill={"C": 2.15, "P": 2.15})
    market["held"] = {"C": -2, "P": -2}
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    result, stores = _run(tmp_path, gw, transmit=True, config=config)
    assert result.funnel["admitted"] == 0 and result.funnel["exited"] == 1
    assert all(action == "BUY" for _, action, _, _ in gw.placed)
    assert paper_book.load_open_positions(stores.open_positions).empty
    assert len(pd.read_parquet(stores.nostop)) == 1
    assert any("STOP" in a for a in result.alarms)


def test_exit_with_broker_mismatch_is_not_sent(tmp_path, market) -> None:
    gw = FakeGateway()
    market["held"] = {"C": -2, "P": 0}  # put leg missing at the broker
    stores = ses.Stores.for_mode(True, _config(tmp_path), root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    result, stores = _run(tmp_path, gw, transmit=True, votes=_today_votes(()))
    assert not any(action == "BUY" for _, action, _, _ in gw.placed)
    assert any("broker_mismatch" in a for a in result.alarms)
    assert len(paper_book.load_open_positions(stores.open_positions)) == 1


def _legged_exit(tmp_path, market):
    """Session one: the call buys back, the put never fills. Returns the config and stores."""
    config = _config(tmp_path)
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    market["held"] = {"C": -2, "P": -2}
    first, _ = _run(
        tmp_path,
        FakeGateway(buy_fill={"C": 2.15}),
        transmit=True,
        config=config,
        votes=_today_votes(()),
    )
    assert any("exit incomplete" in a for a in first.alarms)
    assert len(paper_book.load_open_positions(stores.open_positions)) == 1
    return config, stores


def test_incomplete_exit_resumes_only_the_open_leg_and_books_the_blend(tmp_path, market) -> None:
    config, stores = _legged_exit(tmp_path, market)
    market["held"] = {"C": 0, "P": -2}  # what the broker holds after session one
    gw = FakeGateway(buy_fill={"P": 2.20})
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(()))
    assert not result.alarms and result.funnel["exited"] == 1
    assert {(right, action) for right, action, _, _ in gw.placed} == {("P", "BUY")}
    assert {t.order.totalQuantity for t in gw._trades.values()} == {2}
    assert paper_book.load_open_positions(stores.open_positions).empty
    assert len(pd.read_parquet(stores.nostop)) == 1
    done = pd.read_csv(stores.intended).iloc[-1]
    assert done["outcome"] == "filled"
    assert done["fill_ps"] == pytest.approx(2.15 + 2.20)  # the call from session one
    assert done["reason"].startswith("resumed_exit") and "C 2@2.15" in done["reason"]
    assert pd.isna(done["nbbo_mid_1559_ps"])
    recon = pd.read_parquet(stores.reconciliation).iloc[-1]
    assert not bool(recon["filled_at_limit"])
    assert check_completeness(load_order_events(stores.order_events)).empty


@pytest.mark.parametrize(
    "held",
    [
        {"C": -2, "P": -2},  # the log says the call was bought, the broker still shows it
        {"C": 0, "P": 0},  # the put was closed outside the harness
        {"C": 0, "P": -1},  # part of the put was closed outside the harness
        {"C": 2, "P": -2},  # long the call
    ],
)
def test_resumed_exit_refuses_a_position_the_log_does_not_explain(tmp_path, market, held) -> None:
    config, stores = _legged_exit(tmp_path, market)
    market["held"] = held
    gw = FakeGateway(buy_fill={"C": 2.20, "P": 2.20})
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(()))
    assert gw.placed == []
    assert any("broker_mismatch" in a and "earlier exit fills" in a for a in result.alarms)
    assert len(paper_book.load_open_positions(stores.open_positions)) == 1


def test_exit_with_nothing_filled_is_an_alarm(tmp_path, market) -> None:
    config = _config(tmp_path)
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    market["held"] = {"C": -2, "P": -2}
    result, _ = _run(tmp_path, FakeGateway(), transmit=True, config=config, votes=_today_votes(()))
    assert any("exit unfilled; position still open" in a for a in result.alarms)
    assert pd.read_csv(stores.intended).iloc[-1]["outcome"] == "unfilled"


def test_stale_ask_exit_is_closed_by_the_sweep(tmp_path, market) -> None:
    # The displayed ask is 2.20 but the real offer is 2.40: every rung to the touch
    # misses, which is how the first transmitted exit was left with a naked put.
    config = _config(tmp_path)
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    market["held"] = {"C": -2, "P": -2}
    gw = FakeGateway(buy_fill={"C": 2.15, "P": 2.40})
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(()))
    assert not result.alarms and result.funnel["exited"] == 1
    assert paper_book.load_open_positions(stores.open_positions).empty
    events = load_order_events(stores.order_events)
    sweeps = events[events["reason"].fillna("").str.startswith("sweep")]
    assert list(sweeps["leg"]) == ["P"] and sweeps["limit_price"].iloc[0] == pytest.approx(2.65)
    assert not bool(pd.read_parquet(stores.reconciliation).iloc[-1]["filled_at_limit"])


def test_position_the_ledger_does_not_know_is_an_alarm(tmp_path, market) -> None:
    market["positions"] = [(_contract("QQQQ", 50.0, EXPIRY, "P"), -3)]
    result, _ = _run(tmp_path, FakeGateway(), transmit=True, votes=_today_votes(()))
    assert any("no open ledger position explains" in a and "-3" in a for a in result.alarms)


def test_one_exit_that_raises_does_not_stop_the_others(tmp_path, market, monkeypatch) -> None:
    config = _config(tmp_path)
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    _seed_due_position(stores.open_positions, ticker="YYY")
    market["held"] = {"C": -2, "P": -2}
    market["positions"] = []
    real = ses.ib_market.qualify_underlying

    def flaky(ib, ticker):
        if ticker == "YYY":
            raise TimeoutError("positions request timed out")
        return real(ib, ticker)

    monkeypatch.setattr(ses.ib_market, "qualify_underlying", flaky)
    gw = FakeGateway(buy_fill={"C": 2.15, "P": 2.15})
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(()))
    assert result.funnel["exited"] == 1
    assert any("YYY exit not placed (error" in a for a in result.alarms)
    assert list(paper_book.load_open_positions(stores.open_positions)["ticker"]) == ["YYY"]


def test_entry_that_raises_is_skipped_and_exits_still_run(tmp_path, market, monkeypatch) -> None:
    config = _config(tmp_path)
    stores = ses.Stores.for_mode(True, config, root=tmp_path / "live")
    _seed_due_position(stores.open_positions)
    market["held"] = {"C": -2, "P": -2}

    def boom(ib, under):
        raise KeyError("grid")

    monkeypatch.setattr(ses.ib_market, "option_grid", boom)
    gw = FakeGateway(buy_fill={"C": 2.15, "P": 2.15})
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(("AAA",)))
    assert result.funnel["exited"] == 1 and result.funnel["admitted"] == 0
    assert "error:KeyError" in set(pd.read_csv(stores.intended)["reason"].dropna())


def test_manual_close_is_recorded_checked_and_booked(tmp_path, market) -> None:
    config, stores = _legged_exit(tmp_path, market)
    args = ("ZZZ", "P", 2, 0.31, "closed by hand in TWS", DAY)
    market["held"] = {"C": 0, "P": -2}  # not closed at the broker yet
    with pytest.raises(ValueError, match="broker holds -2"):
        ses.record_manual_exit_fill(FakeGateway(), *args, config=config, stores=stores)
    assert len(load_order_events(stores.order_events).query("event == 'fill'")) == 1
    market["held"] = {"C": 0, "P": 0}
    with pytest.raises(ValueError, match="reason is required"):
        ses.record_manual_exit_fill(
            FakeGateway(), "ZZZ", "P", 2, 0.31, " ", DAY, config=config, stores=stores
        )
    out = ses.record_manual_exit_fill(FakeGateway(), *args, config=config, stores=stores)
    assert out == "booked"
    assert paper_book.load_open_positions(stores.open_positions).empty
    done = pd.read_csv(stores.intended).iloc[-1]
    assert done["outcome"] == "filled" and done["fill_ps"] == pytest.approx(2.15 + 0.31)
    manual = load_order_events(stores.order_events).iloc[-1]
    assert manual["reason"] == "manual close: closed by hand in TWS"
    assert check_completeness(load_order_events(stores.order_events)).empty


def test_exit_closed_in_the_log_but_never_booked_is_booked_without_an_order(
    tmp_path, market
) -> None:
    config, stores = _legged_exit(tmp_path, market)
    log = ses.OrderEventLog(stores.order_events, DAY, transmit=True)
    log.record(
        "fill",
        ticker="ZZZ",
        position_key=ses.position_key("ZZZ", "2026-10-16", 100.0, EXPIRY),
        leg="P",
        purpose="exit",
        side="BUY",
        fill_qty=2,
        fill_price=2.30,
    )
    market["held"] = {"C": 0, "P": 0}
    gw = FakeGateway()
    result, _ = _run(tmp_path, gw, transmit=True, config=config, votes=_today_votes(()))
    assert gw.placed == [] and not result.alarms and result.funnel["exited"] == 1
    assert paper_book.load_open_positions(stores.open_positions).empty
    assert pd.read_csv(stores.intended).iloc[-1]["fill_ps"] == pytest.approx(2.15 + 2.30)


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def __isub__(self, fn):
        self.handlers.remove(fn)
        return self


def test_competing_live_session_is_named_in_an_alarm(tmp_path, market) -> None:
    gw = FakeGateway()
    gw.errorEvent = _Event()

    def exdiv(ib, under, ticker):
        for fn in list(gw.errorEvent.handlers):
            fn(66, 10197, "No market data during competing live session", None)
        return {"ib": None, "yahoo": None}

    result, _ = _run(tmp_path, gw, transmit=False, exdiv=exdiv)
    assert any("competing live session" in a for a in result.alarms)
    assert gw.errorEvent.handlers == []


def test_unpriced_reasons_say_what_was_missing(tmp_path, market, monkeypatch) -> None:
    calls = {"n": 0}
    real = ses.ib_market.snapshot_strikes

    def one_sided(ib, under, expiry, strikes):
        calls["n"] += 1
        chain = real(ib, under, expiry, strikes)
        chain["bid"] = float("nan")
        return chain

    monkeypatch.setattr(ses.ib_market, "snapshot_strikes", one_sided)
    result, stores = _run(tmp_path, FakeGateway(), transmit=False, votes=_today_votes(("AAA",)))
    assert set(pd.read_csv(stores.intended)["reason"].dropna()) == {"unpriced:one_sided_atm"}
    assert calls["n"] == 2  # the pair is asked for once more before giving up


def test_prior_exit_fills_blends_by_quantity_and_ignores_other_rows() -> None:
    def row(**kw):
        base = {"event": "fill", "purpose": "exit", "position_key": "K", "transmit": True}
        return {**base, **kw}

    events = pd.DataFrame(
        [
            row(leg="C", fill_qty=3, fill_price=2.00),
            row(leg="C", fill_qty=2, fill_price=2.50),
            row(leg="P", fill_qty=5, fill_price=1.00, purpose="entry"),
            row(leg="P", fill_qty=5, fill_price=1.00, transmit=False),
            row(leg="P", fill_qty=5, fill_price=1.00, position_key="other"),
            row(leg="P", fill_qty=None, fill_price=None, event="status"),
        ]
    )
    assert prior_exit_fills(events, "K") == {"C": (5, pytest.approx(2.20))}
    assert prior_exit_fills(events.iloc[0:0], "K") == {}
    holed = pd.DataFrame([row(leg="C", fill_qty=3, fill_price=None)])
    with pytest.raises(ValueError, match="lack a quantity or price"):
        prior_exit_fills(holed, "K")


def test_dry_pass_never_reads_the_live_book(tmp_path, market) -> None:
    live = ses.Stores.for_mode(True, _config(tmp_path), root=tmp_path / "live")
    _seed_due_position(live.open_positions)
    result, _ = _run(tmp_path, FakeGateway(), transmit=False, votes=_today_votes(()))
    assert result.funnel["exits_due"] == 0
    assert len(paper_book.load_open_positions(live.open_positions)) == 1


@pytest.mark.parametrize(
    "expiries, exdiv, reason",
    [
        ([pd.Timestamp("2026-10-20")], None, "expiry_le_exit"),
        (None, {"ib": "unreadable", "yahoo": "unreadable"}, "exdiv_unknown"),
        (None, {"ib": pd.Timestamp("2026-10-20"), "yahoo": None}, "exdiv_in_window"),
    ],
)
def test_entry_filters_skip_with_reason_codes(tmp_path, market, expiries, exdiv, reason) -> None:
    if expiries is not None:
        market["expiries"] = expiries
    exdiv_fn = (lambda ib, u, t: exdiv) if exdiv else None
    result, stores = _run(tmp_path, FakeGateway(), transmit=False, exdiv=exdiv_fn)
    intended = pd.read_csv(stores.intended)
    assert result.funnel["admitted"] == 0
    assert set(intended["reason"].dropna()) == {reason}
    assert any("none admitted" in a for a in result.alarms)  # an emptied day is an alarm


# ── drivers ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("driver", ["scripts/run_paper_daily.ps1", "deploy/run_paper_daily.sh"])
def test_drivers_guard_first_and_run_the_session_pass(driver) -> None:
    text = (ROOT / driver).read_text(encoding="utf-8")
    guard = text.find("session_check")
    run = text.find("scripts.paper_trade_ibkr session")
    assert guard != -1 and run != -1 and guard < run
    assert "paper_trade_ibkr.py enter" not in text and "forward-exit" not in text


def test_schedules_start_at_1520() -> None:
    assert "20 15 * * 1-5" in (ROOT / "deploy" / "crontab").read_text(encoding="utf-8")
