"""
test_live_selection_rule.py
Offline tests for the forward book's deployment wiring: the environment overrides
on ``LiveConfig``, the live-port guard under those overrides, the selection-rule
dispatch in ``paper_trade_ibkr``, and the entry-time features in the open book.

The guard tests matter most. The cloud stack points the harness at a container
relay port through ``IB_PORT``, so an override must never be able to reach a
funded account: a live port is refused both when the config is built and when a
connection is attempted.
"""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_iv_crush.config import SELECTION_RULES, LiveConfig
from earnings_iv_crush.live import paper_book
from earnings_iv_crush.live.ib_connection import LivePortError, connect_paper
from scripts import paper_trade_ibkr

_ENV = (
    "IB_HOST",
    "IB_PORT",
    "IB_MARKET_DATA_TYPE",
    "SELECTION_RULE",
    "UNIVERSE_PATH",
    "SESSION_AWARE_TIMING",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _signal(spread_nearest: float = 0.05) -> paper_trade_ibkr.EntrySignal:
    return paper_trade_ibkr.EntrySignal(
        front_expiry=pd.Timestamp("2026-10-09"),
        strike=100.0,
        t_entry=3 / 365,
        front_atm_iv=0.60,
        iv_term_spread=0.20,
        iv_term_spread_nearest=spread_nearest,
        skew_25d=0.02,
        implied_move=0.06,
    )


# ── config overrides ─────────────────────────────────────────────────────────


def test_defaults_without_environment():
    cfg = LiveConfig()
    assert cfg.ib_host == "127.0.0.1"
    assert cfg.ib_paper_port == 7497
    assert cfg.selection_rule == "unconditional"
    assert cfg.session_aware_timing is True
    assert cfg.universe_path == "data/universe_broad.csv"
    assert (cfg.max_names_per_day, cfg.max_contracts_per_leg) == (3, 5)


def test_tracked_universe_is_the_broad_block():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "universe_broad.csv"
    tickers = pd.read_csv(path)["ticker"]
    assert tickers.is_unique and len(tickers) == 346


def test_container_overrides(monkeypatch):
    monkeypatch.setenv("IB_HOST", "ib-gateway")
    monkeypatch.setenv("IB_PORT", "4004")
    monkeypatch.setenv("IB_MARKET_DATA_TYPE", "1")
    monkeypatch.setenv("SELECTION_RULE", "term_q80")
    monkeypatch.setenv("UNIVERSE_PATH", "outputs/research/events_broad_oos_2025.parquet")
    monkeypatch.setenv("SESSION_AWARE_TIMING", "true")
    cfg = LiveConfig()
    assert (cfg.ib_host, cfg.ib_paper_port, cfg.ib_market_data_type) == ("ib-gateway", 4004, 1)
    assert cfg.selection_rule == "term_q80"
    assert cfg.universe_path.endswith("events_broad_oos_2025.parquet")
    assert cfg.session_aware_timing is True


@pytest.mark.parametrize("port", [7496, 4001, 4003])
def test_live_port_override_refused_at_config(monkeypatch, port):
    monkeypatch.setenv("IB_PORT", str(port))
    with pytest.raises(ValueError, match="live-account port"):
        LiveConfig()


@pytest.mark.parametrize("port", [7496, 4001, 4003])
def test_live_port_refused_at_connect(port):
    # The guard fires before ib_async is imported, so this needs no gateway.
    with pytest.raises(LivePortError):
        connect_paper(port=port)


def test_unknown_rule_refused(monkeypatch):
    monkeypatch.setenv("SELECTION_RULE", "term_q90")
    with pytest.raises(ValueError, match="selection_rule"):
        LiveConfig()


def test_malformed_boolean_refused(monkeypatch):
    monkeypatch.setenv("SESSION_AWARE_TIMING", "maybe")
    with pytest.raises(ValueError, match="boolean"):
        LiveConfig()


# ── rule dispatch ────────────────────────────────────────────────────────────


def test_unconditional_never_consults_the_gate(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("term gate consulted under the unconditional rule")

    monkeypatch.setattr(paper_book, "passes_term_gate", _boom)
    traded, reason = paper_trade_ibkr.passes_rule(
        "unconditional", "TEST", pd.Timestamp("2026-10-08"), _signal(), prior_skews=None
    )
    assert traded and reason == "unconditional"


@pytest.mark.parametrize("gate", [True, False])
def test_term_rule_gates_on_nearest_spread(monkeypatch, gate):
    seen: list[float] = []

    def _gate(_ticker, _day, spread):
        seen.append(spread)
        return gate

    monkeypatch.setattr(paper_book, "passes_term_gate", _gate)
    traded, _ = paper_trade_ibkr.passes_rule(
        "term_q80", "TEST", pd.Timestamp("2026-10-08"), _signal(0.0731), prior_skews=None
    )
    assert traded is gate
    assert seen == [0.0731]


def test_unknown_rule_raises_in_dispatch():
    with pytest.raises(ValueError, match="unknown selection rule"):
        paper_trade_ibkr.passes_rule(
            "random", "TEST", pd.Timestamp("2026-10-08"), _signal(), prior_skews=None
        )


@pytest.mark.parametrize("rule", SELECTION_RULES)
def test_cli_accepts_each_rule(rule):
    args = paper_trade_ibkr.build_parser().parse_args(["enter", "--rule", rule])
    assert args.rule == rule


def test_cli_rule_defaults_to_config():
    args = paper_trade_ibkr.build_parser().parse_args(["enter"])
    assert args.rule is None


# ── open-book features ───────────────────────────────────────────────────────


def test_entry_features_persist(tmp_path):
    path = tmp_path / "open.parquet"
    paper_book.record_entry(
        {
            "ticker": "TEST",
            "strike": 100.0,
            "contracts": 2,
            "selection_rule": "unconditional",
            "iv_term_spread_nearest": 0.05,
            "implied_move": 0.06,
            "entry_mid_ps": 7.10,
            "entry_rel_spread": 0.031,
        },
        path=path,
    )
    book = paper_book.load_open_positions(path)
    row = book.iloc[0]
    assert row["selection_rule"] == "unconditional"
    assert row["entry_rel_spread"] == pytest.approx(0.031)
    assert row["implied_move"] == pytest.approx(0.06)
    assert row["status"] == "open"
