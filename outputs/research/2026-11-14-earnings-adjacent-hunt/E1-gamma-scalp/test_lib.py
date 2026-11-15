"""
test_lib.py
Offline checks of the lane E1 scalp on synthetic sessions: IV inversion round-trips, a fairly
priced straddle on a noiseless path scalps to about zero at the mid, and the 30-second lag
removes the spurious gain that i.i.d. noise in the parity forward creates.

Usage:
    python -m pytest outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/test_lib.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib  # noqa: E402

SIG_HOUR = 0.004  # per-hour log-sd of the synthetic stock
T_SEC = 2 * 86400.0  # two calendar days to expiry


def _synthetic(n: int, noise: float, seed: int = 0) -> lib.Session:
    """Straddle quoted at the 'fair' calendar vol for the path's own hourly variance."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / lib.N_GRID
    r = rng.normal(0.0, SIG_HOUR * np.sqrt(dt), size=(n, lib.N_GRID))
    s = 100.0 * np.exp(np.cumsum(r, axis=1))
    k = np.full(n, 100.0)
    # implied vol in calendar years such that the quoted decay over the hour equals the hour's
    # variance: sigma^2 / YEAR_SEC * 3600 = SIG_HOUR^2
    sig = np.sqrt(SIG_HOUR**2 * lib.YEAR_SEC / 3600.0)
    tau = (T_SEC - np.arange(lib.N_GRID) * lib.STEP) / lib.YEAR_SEC
    f_obs = s + rng.normal(0.0, noise, size=s.shape)
    call = np.empty_like(s)
    put = np.empty_like(s)
    for j in range(lib.N_GRID):
        st = lib.straddle_px(s[:, j], k, np.full(n, tau[j]), np.full(n, sig))
        call[:, j] = 0.5 * (st + (s[:, j] - k))
        put[:, j] = 0.5 * (st - (s[:, j] - k))
    shift = 0.5 * (f_obs - s)  # put the forward noise into the option mids, half in each leg
    c_mid, p_mid = call + shift, put - shift
    hs = 0.0005
    return lib.Session(cb=c_mid - hs, ca=c_mid + hs, pb=p_mid - hs, pa=p_mid + hs, strike=k,
                       t_sec=np.full(n, T_SEC))


def test_iv_round_trip() -> None:
    f = np.array([95.0, 100.0, 108.0])
    k = np.full(3, 100.0)
    t = np.full(3, 3 / 365)
    sig = np.array([0.3, 0.6, 1.2])
    px = lib.straddle_px(f, k, t, sig)
    assert np.allclose(lib.straddle_iv(px, f, k, t), sig, atol=1e-6)


def test_fair_noiseless_scalp_is_near_zero() -> None:
    s = _synthetic(4000, noise=0.0)
    out = lib.scalp(s, clock_sec=60, lag_sec=0)
    rel = out["gross_mid"] / out["mid0"]
    assert abs(rel.mean()) < 3 * rel.std() / np.sqrt(len(rel)) + 2e-4


@pytest.mark.parametrize("lag", [0, 30])
def test_noise_bias_and_lag_guard(lag: int) -> None:
    s = _synthetic(4000, noise=0.03, seed=1)
    out = lib.scalp(s, clock_sec=60, lag_sec=lag)
    rel = (out["gross_mid"] / out["mid0"]).to_numpy()
    se = rel.std() / np.sqrt(len(rel))
    if lag == 0:
        assert rel.mean() > 3 * se  # the bias the guard exists for
    else:
        assert abs(rel.mean()) < 3 * se + 2e-4
