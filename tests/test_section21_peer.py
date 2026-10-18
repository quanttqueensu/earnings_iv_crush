"""
test_section21_peer.py
Offline checks of the building blocks of ``research/selection/research_section21_peer.py``.

Covers the priced announcement jump against an independent two-expiry variance split, season
assignment at every window edge, peer eligibility (cluster, season, self, exit timing), the
causal expanding quantile rule against a brute-force reference, and the r = 0 straddle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from research.selection.research_section21_peer import (
    bs_straddle,
    causal_quantile_rule,
    eligible_peer_mask,
    priced_jump_var,
    season_start,
)

# ── priced jump ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sigma", [0.15, 0.30, 0.60])
@pytest.mark.parametrize("jump", [0.0, 0.02, 0.08])
@pytest.mark.parametrize("t_f", [2 / 365, 7 / 365, 30 / 365])
def test_jump_recovers_planted_variance(sigma: float, jump: float, t_f: float) -> None:
    """Total variance = sigma^2 t + J^2 in both expiries; the formula must return J^2."""
    t_b = t_f + 21 / 365
    f = np.sqrt((sigma**2 * t_f + jump**2) / t_f)
    b = np.sqrt((sigma**2 * t_b + jump**2) / t_b)
    assert priced_jump_var(f, b, t_f, t_b) == pytest.approx(jump**2, abs=1e-12)


@pytest.mark.parametrize(("f", "b"), [(0.2, 0.3), (0.25, 0.25)])
def test_jump_floors_at_zero(f: float, b: float) -> None:
    assert priced_jump_var(f, b, 7 / 365, 28 / 365) == 0.0


def test_jump_undefined_without_later_back_expiry() -> None:
    assert np.isnan(priced_jump_var(0.4, 0.2, 0.05, 0.05))


# ── seasons ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("day", "start"),
    [
        ("2020-01-09", "2019-10-10"),
        ("2020-01-10", "2020-01-10"),
        ("2020-04-09", "2020-01-10"),
        ("2020-04-10", "2020-04-10"),
        ("2020-07-09", "2020-04-10"),
        ("2020-07-10", "2020-07-10"),
        ("2020-10-09", "2020-07-10"),
        ("2020-10-10", "2020-10-10"),
        ("2020-12-31", "2020-10-10"),
        ("2021-01-01", "2020-10-10"),
    ],
)
def test_season_edges(day: str, start: str) -> None:
    assert season_start(pd.Timestamp(day)) == pd.Timestamp(start)


# ── peer eligibility ─────────────────────────────────────────────────────────


def _peers() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tk = np.array(["AAA", "BBB", "CCC", "DDD", "BBB", "AAA"])
    se = np.array(["2020-01-10"] * 4 + ["2019-10-10", "2020-01-10"], dtype="datetime64[ns]")
    ex = np.array(
        ["2020-01-20", "2020-01-25", "2020-01-30", "2020-01-20", "2019-11-01", "2020-01-20"],
        dtype="datetime64[ns]",
    )
    return tk, se, ex


@pytest.mark.parametrize(
    ("entry", "mates", "expected"),
    [
        # AAA is self; BBB exits on the entry day (eligible); CCC after; DDD outside the
        # cluster; the second BBB row is last season.
        ("2020-01-25", {"AAA", "BBB", "CCC"}, [False, True, False, False, False, False]),
        ("2020-01-24", {"AAA", "BBB", "CCC"}, [False, False, False, False, False, False]),
        ("2020-02-15", {"AAA", "BBB", "CCC", "DDD"}, [False, True, True, True, False, False]),
        ("2020-02-15", {"AAA"}, [False] * 6),
    ],
)
def test_peer_eligibility(entry: str, mates: set[str], expected: list[bool]) -> None:
    tk, se, ex = _peers()
    m = eligible_peer_mask(
        tk, se, ex, "AAA", pd.Timestamp("2020-01-10"), pd.Timestamp(entry), mates
    )
    assert m.tolist() == expected


# ── causal quantile ──────────────────────────────────────────────────────────


def _reference_rule(v: np.ndarray, d: np.ndarray, q: float, min_hist: int) -> np.ndarray:
    out = []
    for i in range(len(v)):
        prior = [v[j] for j in range(len(v)) if d[j] < d[i] and not np.isnan(v[j])]
        out.append(
            bool(not np.isnan(v[i]) and len(prior) >= min_hist and v[i] >= np.quantile(prior, q))
        )
    return np.array(out)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("q", [0.5, 0.8])
@pytest.mark.parametrize("min_hist", [5, 25])
def test_causal_rule_matches_reference(seed: int, q: float, min_hist: int) -> None:
    rng = np.random.default_rng(seed)
    n = 120
    v = rng.normal(size=n)
    v[rng.choice(n, 6, replace=False)] = np.nan
    d = np.sort(rng.integers(0, 60, size=n))  # ties: same-day events never see each other
    got = causal_quantile_rule(v, d, q, min_hist)
    assert np.array_equal(got, _reference_rule(v, d, q, min_hist))
    assert not got[:min_hist].any()


def test_causal_rule_ignores_future_values() -> None:
    rng = np.random.default_rng(3)
    v = rng.normal(size=80)
    d = np.arange(80)
    base = causal_quantile_rule(v, d)
    v2 = v.copy()
    v2[60:] = 1e6
    assert np.array_equal(base[:60], causal_quantile_rule(v2, d)[:60])


# ── straddle ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("s", [80.0, 100.0, 125.0])
@pytest.mark.parametrize("t", [1 / 365, 0.1])
@pytest.mark.parametrize("sigma", [0.2, 0.5])
def test_straddle_matches_closed_form(s: float, t: float, sigma: float) -> None:
    k = 100.0
    v = sigma * np.sqrt(t)
    d1 = np.log(s / k) / v + v / 2
    call = s * norm.cdf(d1) - k * norm.cdf(d1 - v)
    put = k * norm.cdf(v - d1) - s * norm.cdf(-d1)
    assert bs_straddle(s, k, t, sigma) == pytest.approx(call + put, rel=1e-10)


def test_straddle_edges() -> None:
    assert bs_straddle(105.0, 100.0, 0.0, 0.3) == pytest.approx(5.0)
    assert np.isnan(bs_straddle(105.0, 100.0, 0.1, np.nan))
