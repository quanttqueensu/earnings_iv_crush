"""
test_dl_tabular.py
Tests for lane D2 of the 2026-11-15 deep-learning programme (the tabular mixture-density control
in ``outputs/research/2026-11-15-deep-learning/D2-tabular``). Offline and synthetic. Skipped in an
environment without torch, so the main suite stays green.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import integrate
from scipy.special import logsumexp

LANE = Path(__file__).resolve().parents[2] / "outputs/research/2026-11-15-deep-learning/D2-tabular"
# The lane folder is shared through the R2 bucket, not git, so a fresh clone skips these tests.
if not LANE.exists():
    pytest.skip("lane D2 folder absent", allow_module_level=True)
sys.path.insert(0, str(LANE))

# The lane's numpy side loads first: on Windows, numpy's LAPACK and pyarrow must initialise
# before torch's libraries, or later calls crash.
import d2lib  # noqa: E402

torch = pytest.importorskip("torch")

import d2net  # noqa: E402

MIXTURES = [
    (np.log([1.0]), [0.1], [0.5]),
    (np.log([0.7, 0.3]), [-0.2, 0.6], [0.4, 0.9]),
    (np.log([0.5, 0.3, 0.2]), [-0.5, 0.2, 1.1], [0.3, 0.6, 1.2]),
]


def _arr(m: tuple) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lw, mu, sg = (np.atleast_2d(np.asarray(a, float)) for a in m)
    return lw, mu, sg


def _h_density(h: float, lw: np.ndarray, mu: np.ndarray, sg: np.ndarray, unit: float) -> float:
    hh, uu = np.array([h]), np.array([unit])
    z = d2lib.to_z(hh, uu)
    return float(np.exp(d2lib.log_score_h(d2lib.gm_logpdf(z, lw, mu, sg), hh, uu))[0])


@pytest.mark.parametrize("mix", MIXTURES)
@pytest.mark.parametrize("unit", [2.0, 9.0])
def test_gm_density_integrates_to_one_in_h(mix: tuple, unit: float) -> None:
    lw, mu, sg = _arr(mix)
    f = lambda h: _h_density(h, lw, mu, sg, unit)  # noqa: E731
    tot = integrate.quad(f, -np.inf, np.inf, limit=400)[0]
    assert tot == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("df", [2.5, 5.0, 30.0])
def test_t_density_integrates_to_one_in_h(df: float) -> None:
    unit = 5.0

    def f(h: float) -> float:
        hh, uu = np.array([h]), np.array([unit])
        z = d2lib.to_z(hh, uu)
        lp = d2lib.t_logpdf(z, np.array([0.2]), np.array([0.5]), np.array([df]))
        return float(np.exp(d2lib.log_score_h(lp, hh, uu))[0])

    pieces = [(-np.inf, -1e4), (-1e4, -50.0), (-50.0, 0.0), (0.0, 1e3), (1e3, np.inf)]
    tot = sum(integrate.quad(f, a, b, limit=400)[0] for a, b in pieces)
    assert tot == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize("h", [-40.0, -3.0, -0.2, 0.5, 3.0])
@pytest.mark.parametrize("unit", [1.5, 8.0])
def test_jacobian_matches_finite_difference(h: float, unit: float) -> None:
    eps = 1e-6
    hh, uu = np.array([h - eps, h + eps]), np.array([unit, unit])
    z = d2lib.to_z(hh, uu)
    fd = abs(z[1] - z[0]) / (2 * eps)
    an = np.exp(d2lib.log_jacobian(np.array([h]), np.array([unit])))[0]
    assert an == pytest.approx(fd, rel=1e-6)


@pytest.mark.parametrize("mix", MIXTURES)
def test_quadrature_mean_and_sd_match_adaptive_integration(mix: tuple) -> None:
    unit = 6.0
    lw, mu, sg = _arr(mix)
    s = d2lib.gm_h_summary(lw, mu, sg, np.array([unit]))
    f1 = lambda h: h * _h_density(h, lw, mu, sg, unit)  # noqa: E731
    f2 = lambda h: h * h * _h_density(h, lw, mu, sg, unit)  # noqa: E731
    m = integrate.quad(f1, -np.inf, np.inf, limit=400)[0]
    m2 = integrate.quad(f2, -np.inf, np.inf, limit=400)[0]
    assert s["pred_mean"].iloc[0] == pytest.approx(m, rel=1e-7, abs=1e-9)
    assert s["pred_sd"].iloc[0] == pytest.approx(np.sqrt(m2 - m * m), rel=1e-6)
    p = integrate.quad(lambda h: _h_density(h, lw, mu, sg, unit), 0.0, np.inf)[0]
    assert s["p_pos"].iloc[0] == pytest.approx(p, abs=1e-7)


@pytest.mark.parametrize("mu,sig", [(4.0, 0.3), (6.0, 1.0), (9.0, 1.8)])
def test_quadrature_mean_closed_form_k0_lognormal(mu: float, sig: float) -> None:
    # All mass on z >= 0, where yj_inv(z) = expm1(z) for k = 0: E = exp(mu + sig^2 / 2) - 1.
    unit = 3.0
    s = d2lib.gm_h_summary(np.zeros((1, 1)), np.array([[mu]]), np.array([[sig]]),
                           np.array([unit]))  # fmt: skip
    expect = -unit * (np.exp(mu + sig * sig / 2) - 1)
    assert s["pred_mean"].iloc[0] == pytest.approx(expect, rel=1e-9)


def test_quadrature_mean_closed_form_identity() -> None:
    # k = 1 is the identity: h = -U z, so the mean is -U sum_k w_k mu_k exactly.
    lw, mu, sg = _arr(MIXTURES[2])
    ex, _, _ = d2lib.gm_x_moments(lw, mu, sg, k=1.0)
    assert ex[0] == pytest.approx(float((np.exp(lw) * mu).sum()), abs=1e-12)


def test_ensemble_logpz_is_the_average_density() -> None:
    rng = np.random.default_rng(0)
    fits = [
        {"logw": np.log(np.full((4, 2), 0.5)), "mu": rng.normal(size=(4, 2)),
         "sig": np.exp(rng.normal(size=(4, 2)) * 0.3)}  # fmt: skip
        for _ in range(3)
    ]
    z = rng.normal(size=4)
    got = d2net.ensemble_logpz(fits, z, "gm")
    dens = np.mean([np.exp(d2lib.gm_logpdf(z, f["logw"], f["mu"], f["sig"])) for f in fits], 0)
    assert np.allclose(got, np.log(dens))
    lw, mu, sg = d2net.ensemble_mixture(fits)
    assert np.allclose(logsumexp(lw, axis=1), 0.0)
    assert np.allclose(d2lib.gm_logpdf(z, lw, mu, sg), got)


def test_torch_and_numpy_densities_agree() -> None:
    rng = np.random.default_rng(1)
    z = rng.normal(size=6)
    lw = np.log(np.full((6, 3), 1 / 3))
    mu, sg = rng.normal(size=(6, 3)), np.exp(rng.normal(size=(6, 3)) * 0.2)
    p = {"logw": torch.tensor(lw), "mu": torch.tensor(mu), "sig": torch.tensor(sg)}
    nl = float(d2net.nll(p, torch.tensor(z), "gm"))
    assert nl == pytest.approx(-d2lib.gm_logpdf(z, lw, mu, sg).mean(), rel=1e-10)
    pt = {"mu": torch.tensor(mu[:, 0]), "sig": torch.tensor(sg[:, 0]),
          "df": torch.tensor(np.full(6, 4.0))}  # fmt: skip
    nt = float(d2net.nll(pt, torch.tensor(z), "t"))
    want = -d2lib.t_logpdf(z, mu[:, 0], sg[:, 0], np.full(6, 4.0)).mean()
    assert nt == pytest.approx(want, rel=1e-10)


def test_fold_masks_are_causal() -> None:
    ev = d2lib.synthetic(n=2000, seed=3)
    for f in d2lib.dev_folds() + d2lib.quarterly_folds("2017-01-01", "2018-07-01"):
        m = d2lib.fold_masks(ev, f)
        assert (ev.loc[m["full"], "expiry"] < f.origin).all()
        assert not (m["train"] & m["val"]).any()
        assert (ev.loc[m["val"], "entry_date"] >= f.origin - pd.DateOffset(years=1)).all()
        assert (ev.loc[m["score"], "entry_date"] >= f.score_from).all()


def test_planted_effect_is_recovered() -> None:
    ev = d2lib.synthetic(n=4000, seed=1, effect=0.8)
    out, _ = d2net.run(ev, d2lib.dev_folds()[-1:], d2net.Config(K=2, hidden=(32, 32)), (0,))
    gain = out["d2_log_score"].to_numpy() - ev["l4_model_log_score"].to_numpy()[out["row"]]
    assert np.nanmean(gain) > 0.05
    # The predictive mean tracks the planted location: corr with x1 is negative (h = -U ...).
    x1 = ev["log_half_spread"].to_numpy()[out["row"]]
    assert np.corrcoef(out["pred_mean"], x1)[0, 1] < -0.2


def test_no_effect_gives_no_large_gain() -> None:
    ev = d2lib.synthetic(n=3000, seed=2, effect=0.0)
    out, _ = d2net.run(ev, d2lib.dev_folds()[-1:], d2net.Config(K=1), (0,))
    gain = out["d2_log_score"].to_numpy() - ev["l4_model_log_score"].to_numpy()[out["row"]]
    # The constant benchmark is Gaussian on a mixture outcome, so a K=1 net may not lose much
    # but cannot gain from the features: the gain stays small.
    assert abs(np.nanmean(gain)) < 0.05


def test_tight_per_date_matches_counts_and_takes_smallest() -> None:
    dates = np.array(["a", "a", "a", "b", "b", "c"])
    spread = np.array([0.3, 0.1, 0.2, 0.5, 0.4, 0.9])
    tick = np.array(["x", "y", "z", "x", "y", "z"])
    sel = np.array([True, True, False, True, False, False])
    t = d2lib.tight_per_date(sel, spread, dates, tick)
    assert t.tolist() == [False, True, True, False, True, False]
    with pytest.raises(ValueError):
        d2lib.tight_per_date(sel, np.array([np.nan, 1, 1, 1, 1, 1]), dates, tick)
