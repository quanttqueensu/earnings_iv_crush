"""Offline tests for the P1 skew signal against synthetic Black-76 chains."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.greeks import bs_price
from research.selection import research_p1_skew_reaction as p1

T = 7 / 365


def _chain(fwd: float, vol_of_k, half_spread: float = 0.01) -> pd.DataFrame:
    rows = []
    for k in np.arange(fwd * 0.70, fwd * 1.30, fwd * 0.01):
        k = round(float(k), 2)
        for right in ("C", "P"):
            mid = float(bs_price(fwd, k, T, 0.0, vol_of_k(k), right))
            if mid < 0.02:
                continue
            rows.append(
                {
                    "strike": k,
                    "right": right,
                    "expiry": pd.Timestamp("2025-05-02"),
                    "bid_px_00": mid - half_spread,
                    "ask_px_00": mid + half_spread,
                }
            )
    return pd.DataFrame(rows)


def _legs(ch: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    u = p1.usable(ch)
    return (
        u[u["right"] == "C"].groupby("strike")["mid"].last(),
        u[u["right"] == "P"].groupby("strike")["mid"].last(),
    )


@pytest.mark.parametrize("fwd, vol", [(100.0, 0.40), (55.3, 0.90), (412.0, 0.25)])
def test_flat_smile_gives_zero_skew_and_recovers_forward(fwd: float, vol: float) -> None:
    calls, puts = _legs(_chain(fwd, lambda k: vol))
    f_hat = p1.parity_forward(calls, puts)
    assert f_hat == pytest.approx(fwd, rel=1e-3)
    atm = p1.atm_call_iv(p1._ivs(calls, f_hat, T, "C"), f_hat)
    p25 = p1.put25_iv(p1._ivs(puts, f_hat, T, "P"), f_hat, T)
    assert atm == pytest.approx(vol, abs=5e-3)
    assert p25 - atm == pytest.approx(0.0, abs=5e-3)


@pytest.mark.parametrize("slope", [0.5, 1.0, 2.0])
def test_put_skew_sign_and_size(slope: float) -> None:
    fwd, base = 100.0, 0.40

    def smile(k: float) -> float:
        return base + slope * max(0.0, (fwd - k) / fwd)

    calls, puts = _legs(_chain(fwd, smile))
    f_hat = p1.parity_forward(calls, puts)
    put_iv = p1._ivs(puts, f_hat, T, "P")
    p25 = p1.put25_iv(put_iv, f_hat, T)
    atm = p1.atm_call_iv(p1._ivs(calls, f_hat, T, "C"), f_hat)
    # Independent reference: solve N(-d1) = 0.25 on the true smile by bisection.
    lo, hi = fwd * 0.70, fwd
    for _ in range(80):
        mid = (lo + hi) / 2
        if p1.put_abs_delta(fwd, mid, T, smile(mid)) > 0.25:
            hi = mid
        else:
            lo = mid
    assert p25 - atm > 0
    assert p25 == pytest.approx(smile(lo), abs=0.01)


def test_put25_does_not_extrapolate() -> None:
    put_iv = pd.Series({99.0: 0.4, 98.0: 0.4})  # both near the money, deltas above 0.25
    assert np.isnan(p1.put25_iv(put_iv, 100.0, T))


def test_usable_drops_wide_and_crossed_quotes() -> None:
    ch = pd.DataFrame({"bid_px_00": [1.0, 0.1, 0.0, 2.0], "ask_px_00": [1.1, 1.0, 0.5, 1.9]})
    assert list(p1.usable(ch).index) == [0]


@pytest.mark.parametrize(
    "counts, expected_groups",
    [
        ({"2025-01": 60, "2025-02": 20, "2025-03": 40}, 2),
        ({"2025-01": 10, "2025-02": 10, "2025-03": 10}, 1),
        ({"2025-01": 50, "2025-02": 50, "2025-03": 5}, 2),
    ],
)
def test_month_buckets_merge_to_minimum(counts: dict[str, int], expected_groups: int) -> None:
    dates = pd.Series([pd.Timestamp(f"{m}-15") for m, c in counts.items() for _ in range(c)])
    b = p1.month_buckets(dates)
    assert b.nunique() == expected_groups
    sizes = b.value_counts()
    assert (sizes >= 50).all() or len(sizes) == 1


def test_deciles_are_balanced_and_ordered() -> None:
    rng = np.random.default_rng(0)
    d = pd.DataFrame({"ticker": [f"T{i}" for i in range(200)], "skew": rng.normal(size=200)})
    dec = p1.assign_deciles(d, None)
    assert np.bincount(dec)[1:].tolist() == [20] * 10
    assert d.loc[dec == 1, "skew"].max() < d.loc[dec == 10, "skew"].min()
