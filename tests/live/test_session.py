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
from earnings_iv_crush.live.order_events import check_completeness, load_order_events
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
    return state


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


def _seed_due_position(path: str) -> None:
    paper_book.record_entry(
        {
            "ticker": "ZZZ",
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
