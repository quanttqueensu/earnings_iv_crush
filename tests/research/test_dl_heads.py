"""
test_dl_heads.py
Offline synthetic checks of lane D1's predictive heads and surface network
(``outputs/research/2026-11-15-deep-learning/D1-surface-net/d1lib.py``): densities of H_net
integrate to one, the Jacobian matches a finite difference, the quadrature mean matches the
closed form, D1b starts at the Gaussian version of L4, and a planted surface effect is
recovered. Needs torch, so it skips in the main environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# pyarrow must be imported before torch on this machine (the reverse order segfaults).
pytest.importorskip("pyarrow")
pytest.importorskip("torch")

LANE = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "research"
    / "2026-11-15-deep-learning"
    / "D1-surface-net"
)
if not LANE.exists():
    pytest.skip("lane D1 folder absent", allow_module_level=True)
sys.path.insert(0, str(LANE))

import d1lib  # noqa: E402
import torch  # noqa: E402
from scipy import integrate  # noqa: E402
from scipy.stats import norm  # noqa: E402

CFG = d1lib.CFG


def _one(w: list[float], mu: list[float], sig: list[float], df: list[float] | None = None):
    a = lambda v: np.asarray([v], float)  # noqa: E731
    return d1lib.Predictive(a(w), a(mu), a(sig), None if df is None else a(df))


# ── densities and Jacobian ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pred",
    [
        _one([1.0], [0.0], [0.4]),
        _one([1.0], [-0.3], [0.8]),
        _one([0.3, 0.5, 0.2], [-0.4, 0.1, 0.9], [0.2, 0.5, 0.3]),
        _one([1.0], [0.1], [0.5], [4.0]),
        _one([1.0], [-0.2], [0.3], [30.0]),
    ],
)
@pytest.mark.parametrize("unit", [2.5, 9.0])
def test_density_of_h_integrates_to_one(pred: d1lib.Predictive, unit: float) -> None:
    def f(y: float) -> float:
        return float(np.exp(d1lib.logscore_y(np.array([y]), np.array([unit]), pred))[0])

    # The k = 0 loss side is exponential in z, so H reaches far below zero; integrate in pieces.
    pieces = [(-np.inf, -50 * unit), (-50 * unit, 0.0), (0.0, 50 * unit), (50 * unit, np.inf)]
    tot = sum(integrate.quad(f, a, b, limit=400)[0] for a, b in pieces)
    assert tot == pytest.approx(1.0, abs=2e-6)


@pytest.mark.parametrize("y", [-40.0, -5.0, -0.3, 0.0, 0.2, 1.5, 4.0])
@pytest.mark.parametrize("unit", [1.0, 3.7])
def test_jacobian_matches_finite_difference(y: float, unit: float) -> None:
    h = 1e-6
    zp = d1lib.to_z(np.array([y + h]), np.array([unit]))[0]
    zm = d1lib.to_z(np.array([y - h]), np.array([unit]))[0]
    fd = np.log(abs((zp - zm) / (2 * h)))
    an = d1lib.log_jacobian(np.array([y]), np.array([unit]))[0]
    assert an == pytest.approx(fd, abs=1e-6)


# ── quadrature mean ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("mu", [-1.0, -0.2, 0.0, 0.3, 1.0])
@pytest.mark.parametrize("sig", [0.05, 0.3, 0.9, 1.6])
def test_quadrature_mean_matches_closed_form(mu: float, sig: float) -> None:
    # k = 0: E[x] = E[(e^z - 1) 1{z >= 0}] (closed form) + E[(1 - sqrt(1 - 2z)) 1{z < 0}].
    gain = integrate.quad(
        lambda z: (1 - np.sqrt(1 - 2 * z)) * norm.pdf(z, mu, sig), -np.inf, 0.0, epsabs=1e-13
    )[0]
    ex = float(d1lib.lognormal_branch_mean(np.array([mu]), np.array([sig]))[0]) + gain
    unit = 4.0
    got = d1lib.predictive_moments(_one([1.0], [mu], [sig]), np.array([unit]))["mean"][0]
    assert got == pytest.approx(-unit * ex, rel=1e-9, abs=1e-12)


def test_quadrature_mean_pure_closed_form_on_the_loss_branch() -> None:
    # All mass on z > 0 (P(z < 0) about 1e-23): the mean is the lognormal closed form alone.
    mu, sig, unit = 3.0, 0.3, 2.0
    ex = float(np.exp(mu + sig * sig / 2) - 1)
    got = d1lib.predictive_moments(_one([1.0], [mu], [sig]), np.array([unit]))["mean"][0]
    assert got == pytest.approx(-unit * ex, rel=1e-10)


def test_mixture_moments_are_weighted_and_t_mean_is_undefined() -> None:
    a = d1lib.predictive_moments(_one([1.0], [-0.3], [0.4]), np.array([2.0]))
    b = d1lib.predictive_moments(_one([1.0], [0.5], [0.2]), np.array([2.0]))
    m = d1lib.predictive_moments(_one([0.25, 0.75], [-0.3, 0.5], [0.4, 0.2]), np.array([2.0]))
    assert m["mean"][0] == pytest.approx(0.25 * a["mean"][0] + 0.75 * b["mean"][0], rel=1e-12)
    assert m["p_pos"][0] == pytest.approx(0.25 * a["p_pos"][0] + 0.75 * b["p_pos"][0])
    t = d1lib.predictive_moments(_one([1.0], [0.0], [0.3], [30.0]), np.array([2.0]))
    assert np.isnan(t["mean"][0]) and 0 < t["p_pos"][0] < 1
    s = d1lib.score_rows(_one([1.0], [-2.0], [0.1], [30.0]), np.array([1.0]), np.array([2.0]))
    assert not s["decide"][0]  # a Student-t head never trades


def test_ensemble_density_is_the_average() -> None:
    p1, p2 = _one([1.0], [0.0], [0.3]), _one([0.5, 0.5], [0.2, -0.5], [0.4, 0.2])
    e = d1lib.ensemble([p1, p2])
    z = np.array([0.13])
    want = np.log(0.5 * np.exp(d1lib.logpdf_z(z, p1)) + 0.5 * np.exp(d1lib.logpdf_z(z, p2)))
    assert d1lib.logpdf_z(z, e)[0] == pytest.approx(want[0])


# ── networks on synthetic surfaces ───────────────────────────────────────────


def _synthetic(n: int, effect: float, seed: int = 0) -> tuple[d1lib.Inputs, np.ndarray]:
    rng = np.random.default_rng(seed)
    C, E, G = 4, 2, 9
    surf = rng.normal(size=(n, C, E, G))
    surf[:, 3] = 1.0  # validity mask
    hole = rng.random((n, G)) < 0.1
    surf[:, 3, 1][hole] = 0.0
    surf[:, 0, 1][hole] = np.nan
    planted = surf[:, 0, 0, 4]
    z = -0.2 + effect * planted + 0.3 * rng.normal(size=n)
    inp = d1lib.Inputs(
        surf=surf,
        mask_ch=3,
        scal=np.exp(rng.normal(size=(n, 3))),
        feats=rng.normal(size=(n, 7)),
        l4_loc=np.full(n, -0.2),
        l4_scale=np.full(n, float(np.sqrt(effect**2 + 0.09))),
        z=z,
    )
    return inp, planted


@pytest.fixture(scope="module")
def device() -> str:
    return "cpu"


def test_d1b_starts_at_gaussian_l4(device: str) -> None:
    inp, _ = _synthetic(300, 0.5)
    rows = np.arange(300)
    spec = d1lib.ModelSpec(variant="b", arch="conv", width=16, depth=1, conv_ch=4)
    net, nrm, _, _ = d1lib._train(spec, inp, rows, None, 0, 0, device)
    p = d1lib.predict(net, nrm, inp, rows, device)
    assert np.allclose(p.mu[:, 0], inp.l4_loc, atol=1e-6)
    assert np.allclose(p.sig[:, 0], inp.l4_scale + CFG.sigma_floor, rtol=1e-5)


def test_masked_points_are_zero_after_normalisation() -> None:
    inp, _ = _synthetic(200, 0.5)
    rows = np.arange(200)
    nrm = d1lib.Normaliser.fit(inp, rows[:150])
    sn, side = nrm.apply(inp, rows)
    hole = inp.surf[:, 3, 1] < 0.5
    assert np.all(sn[:, 0, 1][hole] == 0.0) and np.isfinite(sn).all() and np.isfinite(side).all()
    assert set(np.unique(sn[:, 3])) <= {0.0, 1.0}


@pytest.mark.parametrize("arch", ["mlp", "conv"])
def test_planted_surface_effect_is_recovered(arch: str, device: str) -> None:
    torch.set_num_threads(2)
    n = 2400
    inp, planted = _synthetic(n, 0.5, seed=1)
    tr, va, te = np.arange(0, 1600), np.arange(1200, 1600), np.arange(1600, n)
    spec = d1lib.ModelSpec(variant="a", arch=arch, width=32, depth=2, conv_ch=8, lr=3e-3)
    fr = d1lib.fit_two_stage(spec, inp, tr, va, [0], device)
    p = d1lib.predict_ensemble(fr, inp, te, device)
    assert np.corrcoef(p.mu[:, 0], planted[te])[0, 1] > 0.9
    # Against the no-surface model the log score in z gains about log(sqrt(0.34 / 0.09)) = 0.66.
    off = d1lib.ModelSpec(variant="a", arch=arch, width=32, depth=2, lr=3e-3, use_surface=False)
    p0 = d1lib.predict_ensemble(d1lib.fit_two_stage(off, inp, tr, va, [0], device), inp, te, device)
    gain = float(np.mean(d1lib.logpdf_z(inp.z[te], p) - d1lib.logpdf_z(inp.z[te], p0)))
    assert gain > 0.4
