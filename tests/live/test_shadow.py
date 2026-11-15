"""Shadow book: hedged-exit marks beside real trades, the G1 flag and the term-spread record."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.config import HEDGED, ShadowConfig
from earnings_iv_crush.engine.stats import nyse_sessions
from earnings_iv_crush.live import session, shadow

FEE = HEDGED.fee_per_contract_leg / 100.0


def _trade(**kw) -> pd.Series:
    base = {
        "ticker": "OXY",
        "entry_date": pd.Timestamp("2026-11-09"),
        "exit_date": pd.Timestamp("2026-11-10"),
        "front_expiry": pd.Timestamp("2026-11-13"),
        "strike": 55.0,
        "contracts": 5,
        "spot_entry": 55.0,
        "spot_exit": 55.0,
        "entry_credit": 2.60 * 100 * 5,
        "entry_mid_ps": 2.62,
        "pnl": 0.80 * 100 * 5,
        "assumed_mid_mark_ps": 1.00,
        "iv_term_spread_nearest": np.nan,
        "entry_rel_spread": np.nan,
    }
    base.update(kw)
    return pd.Series(base)


def _path(t1: str, exp: str, closes: list[float], split_at: int | None = None) -> pd.DataFrame:
    idx = nyse_sessions(pd.Timestamp(t1), pd.Timestamp(exp))
    assert len(idx) == len(closes)
    prc = pd.Series(closes, index=idx, dtype=float)
    cf = pd.Series(1.0, index=idx)
    if split_at is not None:
        cf.iloc[split_at:] = 2.0
    return pd.DataFrame({"prc": prc, "ret": prc.pct_change(), "cfacpr": cf})


# ── one trade ────────────────────────────────────────────────────────────────


def test_flat_path_at_the_strike_keeps_the_premium_less_fees_and_hedge_costs() -> None:
    tr = _trade()
    r = shadow.shadow_trade(tr, _path("2026-11-10", "2026-11-13", [55.0] * 4))
    m0 = 0.20 * 55.0 + 2.60
    assert r["status"] == "ok"
    assert r["B_real"] == pytest.approx(0.80 / m0)
    # independent reference: no move, settle at the strike, so only fees and a few bp of hedge
    assert r["H_shadow"] == pytest.approx((2.60 - 2 * FEE) / m0, abs=2e-3)
    assert r["H_shadow"] < (2.60 - 2 * FEE) / m0
    assert r["n_hedge"] == 3


def test_expiry_on_the_exit_session_settles_without_a_hedge() -> None:
    tr = _trade(front_expiry=pd.Timestamp("2026-11-10"))
    r = shadow.shadow_trade(tr, _path("2026-11-10", "2026-11-10", [57.0]))
    m0 = 0.20 * 55.0 + 2.60
    disposal = HEDGED.disposal_bps / 1e4 * 57.0
    assert r["H_shadow"] == pytest.approx((2.60 - 2.0 - 2 * FEE - disposal) / m0)
    assert r["n_hedge"] == 0


def test_a_move_after_the_reaction_close_is_hedged_away() -> None:
    """A steady drift from 55 to 60 after the reaction close: the hedge should recover most of
    what the naked short loses at settlement."""
    tr = _trade()
    r = shadow.shadow_trade(tr, _path("2026-11-10", "2026-11-13", [55.0, 56.5, 58.0, 60.0]))
    naked = (2.60 - 5.0 - 2 * FEE - HEDGED.disposal_bps / 1e4 * 60.0) / (0.20 * 55.0 + 2.60)
    assert r["H_shadow"] > naked


def test_hedged_shadow_nets_the_assigned_share(monkeypatch) -> None:
    """An in-the-money expiry: netting saves the disposal and most of the final unwind, and
    nothing else in the mark moves."""
    path = _path("2026-11-10", "2026-11-13", [55.0, 56.5, 58.0, 60.0])
    netted = shadow.shadow_trade(_trade(), path)
    monkeypatch.setattr(shadow, "HEDGED_NET", HEDGED)
    unwound = shadow.shadow_trade(_trade(), path)
    m0 = 0.20 * 55.0 + 2.60
    gain = netted["H_shadow"] - unwound["H_shadow"]
    disposal = HEDGED.disposal_bps / 1e4 * 60.0 / m0
    full_unwind = 60.0 * ShadowConfig().equity_half_spread_bps / 1e4 / m0
    assert disposal < gain <= disposal + full_unwind + 1e-12
    assert netted["H_mid_shadow"] == pytest.approx(unwound["H_mid_shadow"])


@pytest.mark.parametrize(
    ("path", "status"),
    [
        (None, "pending"),
        (_path("2026-11-10", "2026-11-13", [55.0, 56.0, 57.0, 58.0], split_at=2), "split_in_hold"),
        (_path("2026-11-10", "2026-11-13", [55.0, 56.0, 57.0, 58.0]).iloc[:-1], "missing_close"),
    ],
)
def test_unmarkable_paths_say_why(path: pd.DataFrame | None, status: str) -> None:
    r = shadow.shadow_trade(_trade(), path)
    assert r["status"] == status
    assert np.isnan(r["H_shadow"])
    assert np.isfinite(r["B_real"])


def test_build_does_not_fetch_before_the_expiry_close() -> None:
    calls: list[str] = []

    def fetch(t: str, a: pd.Timestamp, b: pd.Timestamp) -> pd.DataFrame:
        calls.append(t)
        return _path("2026-11-10", "2026-11-13", [55.0] * 4)

    trades = pd.DataFrame([_trade().to_dict()]).assign(announce_date=pd.Timestamp("2026-11-09"))
    book = shadow.build_shadow(trades, fetch, pd.Timestamp("2026-11-12"))
    assert calls == [] and book["status"].tolist() == ["pending"]
    book = shadow.build_shadow(trades, fetch, pd.Timestamp("2026-11-16"))
    assert calls == ["OXY"] and book["status"].tolist() == ["ok"]
    assert list(book.columns) == shadow.COLUMNS


# ── inputs ───────────────────────────────────────────────────────────────────


def test_a_ledger_trade_without_its_position_raises(tmp_path) -> None:
    led = pd.DataFrame([{"ticker": "OXY", "entry_date": "2026-11-09", "pnl": 1.0}])
    pos = pd.DataFrame(
        [{"ticker": "XOM", "entry_date": "2026-11-09", "front_expiry": "2026-11-13"}]
    )
    rec = pd.DataFrame(
        [
            {
                "ticker": "OXY",
                "entry_date": "2026-11-09",
                "assumed_mid_mark_ps": 1.0,
                "nostop_fill_ps": 1.0,
            }
        ]
    )
    paths = {n: str(tmp_path / f"{n}.parquet") for n in ("led", "pos", "rec")}
    led.to_parquet(paths["led"])
    pos.to_parquet(paths["pos"])
    rec.to_parquet(paths["rec"])
    with pytest.raises(ValueError, match="lack a position"):
        shadow.closed_trades(paths["pos"], paths["led"], paths["rec"])


# ── the gate flag ────────────────────────────────────────────────────────────


def test_g1_is_causal_and_warms_up() -> None:
    cfg = ShadowConfig(gate_min_prior=3)
    rng = np.random.default_rng(0)
    d = pd.DataFrame(
        {
            "announce_date": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-04"]
            ),
            "iv_term_spread_nearest": [0.1, 0.2, 0.3, 0.9, 0.0],
            "entry_rel_spread": [0.10, 0.12, 0.14, 0.05, 0.05],
        }
    )
    g = shadow.g1_flags(d, cfg)
    assert g.iloc[:3].isna().all()  # fewer than three strictly earlier trades
    assert g.iloc[3] == 1.0 and g.iloc[4] == 0.0  # same-date trades never see each other
    d.loc[0, "entry_rel_spread"] = np.nan
    assert np.isnan(shadow.g1_flags(d, cfg).iloc[0])
    _ = rng


# ── the term-spread record on the order path ─────────────────────────────────


def _chain(expiry: str, strike: float, iv: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "expiry": pd.Timestamp(expiry),
                "strike": strike,
                "right": r,
                "bid": 1.0,
                "ask": 1.1,
                "iv": iv,
            }
            for r in ("C", "P")
        ]
    )


class _Und:
    contract = type("C", (), {"symbol": "OXY"})()


def test_term_spread_uses_the_nearest_pair_and_reuses_the_front_chain(monkeypatch) -> None:
    asof = pd.Timestamp("2026-11-09")
    exps = [pd.Timestamp(x) for x in ("2026-11-13", "2026-11-20", "2026-12-18")]
    asked: list[pd.Timestamp] = []

    def snap(ib, und, e, strikes):
        asked.append(e)
        return _chain(str(e.date()), 55.0, 0.30)

    monkeypatch.setattr(session.ib_market, "snapshot_strikes", snap)
    front = _chain("2026-11-13", 55.0, 0.55)
    v = session.term_spread_nearest(
        None, _Und(), exps, [54.0, 55.0, 56.0], 55.0, asof, front, pd.Timestamp("2026-11-13")
    )
    assert v == pytest.approx(0.25)
    assert asked == [pd.Timestamp("2026-12-18")]  # back month at least the configured gap out


def test_term_spread_failure_is_nan_and_never_raises(monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("pacing violation")

    monkeypatch.setattr(session.ib_market, "snapshot_strikes", boom)
    exps = [pd.Timestamp(x) for x in ("2026-11-13", "2026-12-18")]
    v = session.term_spread_nearest(
        None,
        _Und(),
        exps,
        [55.0],
        55.0,
        pd.Timestamp("2026-11-09"),
        _chain("2026-11-13", 55.0, 0.5),
        pd.Timestamp("2026-11-13"),
    )
    assert np.isnan(v)


def test_a_mid_under_intrinsic_falls_back_to_the_exit_iv_then_says_why() -> None:
    path = _path("2026-11-10", "2026-11-13", [60.0] * 4)
    tr = _trade(spot_exit=60.0, assumed_mid_mark_ps=4.0, iv_exit=0.40)
    r = shadow.shadow_trade(tr, path)
    assert r["status"] == "ok" and r["hedge_sigma"] == pytest.approx(0.40)
    r = shadow.shadow_trade(_trade(spot_exit=60.0, assumed_mid_mark_ps=4.0, iv_exit=np.nan), path)
    assert r["status"] == "no_hedge_vol"
