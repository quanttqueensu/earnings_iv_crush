"""
test_chain_surface.py
Offline tests of ``earnings_iv_crush/research/chain_surface.py`` on synthetic chains only.

The vectorised Black-76 inverter is checked against planted vols and against the independent
scalar root-finder ``hedged_hold.option_iv`` (zero rate); a flat smile must interpolate exactly;
quotes stamped after 15:59 ET must not reach the snapshot; missing strikes must clear the mask;
a one-sided quote must give no mid IV; and put-call parity must recover a planted forward.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.config import CHAIN_SURFACE
from earnings_iv_crush.research import chain_surface as cs
from earnings_iv_crush.research.hedged_hold import option_iv

ENTRY = pd.Timestamp("2024-07-24")
FRONT = pd.Timestamp("2024-08-02")
NEXT = pd.Timestamp("2024-08-16")
CHAN = {c: i for i, c in enumerate(cs.CHANNELS)}


# ── synthetic chain ──────────────────────────────────────────────────────────


def _symbol(expiry: pd.Timestamp, right: str, strike: float) -> str:
    return f"SYN   {expiry:%y%m%d}{right}{int(round(strike * 1000)):08d}"


def _chain(
    fwd: dict[pd.Timestamp, float],
    vol: float,
    strikes: np.ndarray,
    rate: float = 0.0,
    half_spread: float = 0.01,
    stamp: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Two-sided quotes at Black-76 prices plus and minus ``half_spread`` (relative)."""
    ts = stamp if stamp is not None else cs.snapshot_cutoff(ENTRY)
    rows = []
    for exp, f in fwd.items():
        tau = cs.year_fraction(ENTRY, exp)
        disc = np.exp(-rate * tau)
        for k in strikes:
            for r in "CP":
                p = float(cs.black76(f, k, tau, vol, disc, r == "C"))
                rows.append(
                    {
                        "ts_recv": ts,
                        "symbol": _symbol(exp, r, k),
                        "bid_px_00": p * (1 - half_spread),
                        "ask_px_00": p * (1 + half_spread),
                        "bid_sz_00": 10,
                        "ask_sz_00": 20,
                    }
                )
    return pd.DataFrame(rows).set_index("ts_recv")


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("tau", [0.01, 0.1, 1.0])
@pytest.mark.parametrize("vol", [0.1, 0.4, 1.5])
@pytest.mark.parametrize("lnk", [-0.3, 0.0, 0.3])
def test_inverter_recovers_planted_iv(is_call: bool, tau: float, vol: float, lnk: float) -> None:
    f = 100.0
    k = f * np.exp(lnk * vol * np.sqrt(tau) / 0.3)  # within about one sd, so vega is material
    for disc in (1.0, 0.97):
        p = cs.black76(f, k, tau, vol, disc, is_call)
        iv = float(cs.implied_vol(p, f, k, tau, disc, is_call))
        assert iv == pytest.approx(vol, abs=1e-9)
    ref = option_iv(
        float(cs.black76(f, k, tau, vol, 1.0, is_call)), f, k, tau, "C" if is_call else "P"
    )
    assert float(
        cs.implied_vol(cs.black76(f, k, tau, vol, 1.0, is_call), f, k, tau, 1.0, is_call)
    ) == pytest.approx(ref, abs=1e-7)


def test_inverter_grid_against_option_iv() -> None:
    rng = np.random.default_rng(0)
    n = 300
    f = rng.uniform(20, 300, n)
    tau = rng.uniform(0.005, 1.0, n)
    vol = rng.uniform(0.05, 2.0, n)
    k = f * np.exp(rng.uniform(-1.0, 1.0, n) * vol * np.sqrt(tau))
    c = rng.random(n) < 0.5
    p = cs.black76(f, k, tau, vol, 1.0, c)
    iv = cs.implied_vol(p, f, k, tau, 1.0, c)
    ref = np.array([option_iv(p[j], f[j], k[j], tau[j], "C" if c[j] else "P") for j in range(n)])
    assert np.nanmax(np.abs(iv - vol)) < 1e-8
    assert np.nanmax(np.abs(iv - ref)) < 1e-6
    assert not np.isnan(iv).any()


def test_inverter_rejects_unbracketed_prices() -> None:
    f, k, tau = 100.0, 100.0, 0.1
    assert np.isnan(cs.implied_vol(0.0, f, k, tau, 1.0, True))
    assert np.isnan(cs.implied_vol(f * 1.01, f, k, tau, 1.0, True))  # above the forward
    assert np.isnan(cs.implied_vol(np.nan, f, k, tau, 1.0, True))


def test_straddle_iv_matches_planted() -> None:
    f, k, tau, vol = 50.0, 51.0, 0.05, 0.6
    p = cs.black76(f, k, tau, vol, 1.0, True) + cs.black76(f, k, tau, vol, 1.0, False)
    assert float(cs.straddle_implied_vol(p, f, k, tau, 1.0)) == pytest.approx(vol, abs=1e-9)


def test_flat_smile_interpolates_exactly() -> None:
    vol, f = 0.5, 100.0
    strikes = np.arange(60.0, 150.0, 1.0)
    raw = _chain({FRONT: f, NEXT: f}, vol, strikes)
    s = cs.event_surface(raw, ENTRY, FRONT, f, 0.0, 30.0)
    assert s.status["front_found"] and s.status["next_found"]
    assert s.scalars["sigma_atm_front"] == pytest.approx(vol, abs=1e-9)
    assert s.scalars["sigma_atm_next"] == pytest.approx(vol, abs=1e-9)
    for e in range(2):
        assert (s.grid[CHAN["mask"], e] == 1).all()
        for ch in ("call_iv_rel", "put_iv_rel"):
            np.testing.assert_allclose(s.grid[CHAN[ch], e], 1.0, atol=1e-8)
        for ch in ("call_rel_spread", "put_rel_spread"):
            np.testing.assert_allclose(s.grid[CHAN[ch], e], 0.02, atol=1e-12)
        np.testing.assert_allclose(s.grid[CHAN["call_log1p_bid_size"], e], np.log1p(10.0))
        np.testing.assert_allclose(s.grid[CHAN["put_log1p_ask_size"], e], np.log1p(20.0))
    assert s.scalars["fill"] == 1.0


def test_interp_masked_no_extrapolation_and_gap() -> None:
    g = np.array([-2.0, -1.0, 0.0, 0.5, 1.0, 2.0])
    xq = np.array([-1.0, 0.0, 1.5])
    v = np.array([1.0, 2.0, 5.0])
    out = cs.interp_masked(xq, v, g, max_gap=1.0)
    assert np.isnan(out[0]) and np.isnan(out[5])  # outside the quoted range
    assert out[1] == 1.0 and out[2] == 2.0  # on quoted points
    assert np.isnan(out[3]) and np.isnan(out[4])  # inside a bracket of width 1.5
    out2 = cs.interp_masked(xq, v, g, max_gap=2.0)
    assert out2[3] == pytest.approx(3.0) and out2[4] == pytest.approx(4.0)


def test_quotes_after_snapshot_are_excluded() -> None:
    vol, f = 0.5, 100.0
    strikes = np.arange(60.0, 150.0, 1.0)
    good = _chain({FRONT: f, NEXT: f}, vol, strikes)
    late = _chain(
        {FRONT: f, NEXT: f}, 2.0, strikes, stamp=cs.snapshot_cutoff(ENTRY) + pd.Timedelta(seconds=1)
    )
    raw = pd.concat([good, late])
    snap = cs.snapshot(raw, ENTRY)
    assert snap.n_after_cutoff == len(late)
    assert len(snap.chain) == len(good)
    s = cs.event_surface(raw, ENTRY, FRONT, f, 0.0, 30.0)
    assert s.scalars["sigma_atm_front"] == pytest.approx(vol, abs=1e-9)
    # An earlier quote of the same contract is superseded by the 15:59 one.
    early = _chain(
        {FRONT: f, NEXT: f}, 2.0, strikes, stamp=cs.snapshot_cutoff(ENTRY) - pd.Timedelta(minutes=1)
    )
    snap2 = cs.snapshot(pd.concat([good, early]), ENTRY)
    assert snap2.n_superseded == len(early)
    s2 = cs.event_surface(pd.concat([early, good]), ENTRY, FRONT, f, 0.0, 30.0)
    assert s2.scalars["sigma_atm_front"] == pytest.approx(vol, abs=1e-9)


def test_snapshot_cutoff_is_eastern_time() -> None:
    assert cs.snapshot_cutoff("2024-07-24") == pd.Timestamp("2024-07-24 19:59", tz="UTC")
    assert cs.snapshot_cutoff("2024-01-24") == pd.Timestamp("2024-01-24 20:59", tz="UTC")
    # 15:59 to 16:00 the same day is one minute
    assert cs.year_fraction("2024-07-24", "2024-07-24") == pytest.approx(1 / 1440 / 365)


def test_missing_strikes_set_the_mask() -> None:
    vol, f = 0.5, 100.0
    strikes = np.arange(60.0, 150.0, 1.0)
    tau = cs.year_fraction(ENTRY, FRONT)
    sd = vol * np.sqrt(tau)
    # Drop every front strike above 1 sd: points x > 1 have no quote to interpolate from.
    raw = _chain({FRONT: f, NEXT: f}, vol, strikes).reset_index()
    body = raw["symbol"].str.replace(" ", "").str[-15:]
    k = body.str[7:].astype(float) / 1000.0
    is_front = body.str[:6] == f"{FRONT:%y%m%d}"
    raw = raw[~(is_front & (np.log(k / f) > sd))]
    s = cs.event_surface(raw.set_index("ts_recv"), ENTRY, FRONT, f, 0.0, 30.0)
    g = cs.grid_points()
    m = s.grid[CHAN["mask"], 0]
    assert (m[g > 1.0 + 1e-9] == 0).all()
    assert (m[g <= 0.5] == 1).all()
    assert np.isnan(s.grid[CHAN["call_iv_rel"], 0][g > 1.0 + 1e-9]).all()
    assert (s.grid[CHAN["mask"], 1] == 1).all()  # the next expiry is untouched
    # A missing expiry masks its whole row.
    s2 = cs.event_surface(_chain({FRONT: f}, vol, strikes), ENTRY, FRONT, f, 0.0, 30.0)
    assert not s2.status["next_found"] and (s2.grid[CHAN["mask"], 1] == 0).all()
    assert s2.scalars["fill"] == pytest.approx(0.5)


def test_one_sided_quote_gives_no_mid_iv() -> None:
    vol, f = 0.5, 100.0
    strikes = np.arange(60.0, 150.0, 1.0)
    raw = _chain({FRONT: f, NEXT: f}, vol, strikes).reset_index()
    tgt = raw["symbol"] == _symbol(FRONT, "C", 101.0)
    raw.loc[tgt, "bid_px_00"] = 0.0
    tgt2 = raw["symbol"] == _symbol(FRONT, "P", 99.0)
    raw.loc[tgt2, "ask_px_00"] = np.nan
    s = cs.event_surface(raw.set_index("ts_recv"), ENTRY, FRONT, f, 0.0, 30.0)
    st = s.expiries["front"].strikes.set_index(["right", "strike"])
    assert np.isnan(st.loc[("C", 101.0), "iv_mid"]) and not st.loc[("C", 101.0), "in_grid"]
    assert np.isfinite(st.loc[("C", 101.0), "iv_ask"])  # the ask side keeps its own IV
    assert np.isnan(st.loc[("C", 101.0), "iv_bid"])
    assert np.isnan(st.loc[("P", 99.0), "iv_mid"]) and np.isfinite(st.loc[("P", 99.0), "iv_bid"])
    # The ATM strike skips a one-sided leg: with 100 two-sided the straddle is still struck there.
    assert s.scalars["atm_strike_front"] == 100.0


@pytest.mark.parametrize("rate", [0.0, 0.05])
@pytest.mark.parametrize("planted", [97.3, 100.0, 104.6])
def test_parity_recovers_planted_forward(rate: float, planted: float) -> None:
    vol = 0.4
    strikes = np.arange(60.0, 150.0, 2.5)
    raw = _chain({FRONT: 100.0, NEXT: planted}, vol, strikes, rate=rate)
    dff_pct = 100.0 * np.expm1(rate)  # rate_from_dff inverts this exactly
    s = cs.event_surface(raw, ENTRY, FRONT, 100.0, dff_pct, 30.0)
    assert s.scalars["rate"] == pytest.approx(rate, abs=1e-12)
    assert s.scalars["next_fwd"] == pytest.approx(planted, abs=1e-9)
    assert s.scalars["n_parity_next"] == CHAIN_SURFACE.parity_strikes
    assert s.scalars["sigma_atm_next"] == pytest.approx(vol, abs=1e-8)


def test_parity_needs_enough_pairs() -> None:
    raw = _chain({FRONT: 100.0, NEXT: 100.0}, 0.4, np.array([99.0, 100.0]))
    s = cs.event_surface(raw, ENTRY, FRONT, 100.0, 0.0, 30.0)
    assert np.isnan(s.scalars["next_fwd"]) and not s.status["next_found"]


def test_missing_columns_raise() -> None:
    raw = _chain({FRONT: 100.0}, 0.4, np.array([100.0])).drop(columns="bid_sz_00")
    with pytest.raises(ValueError, match="lacks columns"):
        cs.snapshot(raw, ENTRY)
