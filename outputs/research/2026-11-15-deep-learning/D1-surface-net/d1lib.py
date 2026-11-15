"""
d1lib.py
Lane D1 model code: predictive heads on the Yeo-Johnson loss ratio z, the log density of H_net
with its Jacobian, the predictive mean by deterministic quadrature, the surface networks (an MLP
on the flattened surface and a 1-D convolution over moneyness), fold-level normalisation and the
two-stage fit (early stopping on the last year of the training window, then a refit on the whole
window for the chosen number of epochs).

Target and scale. ``y`` is ``H_net`` in % of m0 per trade, net at the touch, not annualised.
``U`` is the 15:59 premium in % of m0 (``100 s0 / m0``), as L4 builds it. The model works on
``z = yj(-y / U, k)`` with L4's power ``k = 0``; the density of ``y`` is

    log p_y(y) = log p_z(z) + log |dz/dx| - log U,     x = -y / U,

which is ``online_bayes.yj_logderiv`` minus ``log U``, the same expression L4's scorer uses, so
the two log scores are in identical units (nats per % of m0).

Finite mean. ``y = -U yj_inv(z)`` grows like ``exp(z)`` on the loss side, so a Gaussian or
Gaussian-mixture head in ``z`` has a finite mean and a Student-t head does not. The mean is
computed per component by Gauss-Legendre quadrature in the standard normal variable, split at
the branch point ``z = 0``; never by Monte Carlo. Student-t heads are scored on log density only.

Import order. On this machine importing torch before pyarrow segfaults the interpreter, so this
module imports pyarrow first; callers import ``d1lib`` before torch.

Usage
-----
    import d1lib; spec = d1lib.ModelSpec(variant="b", arch="mlp"); see run_fold.

References
----------
Bishop, C. M. (1994). Mixture density networks. Aston University technical report NCRG/94/004.
Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and
estimation. Journal of the American Statistical Association 102(477), 359-378.
Yeo, I.-K. and Johnson, R. A. (2000). A new family of power transformations to improve
normality or symmetry. Biometrika 87(4), 954-959.
"""

from __future__ import annotations

import os

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # deterministic cuBLAS

import sys  # noqa: E402
from dataclasses import asdict, dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402
import pyarrow  # noqa: E402,F401  must precede torch (segfault otherwise)
import pyarrow.parquet  # noqa: E402,F401
from scipy.special import (  # noqa: E402
    gammaln,  # noqa: E402
    logsumexp,
    roots_legendre,
)
from scipy.stats import norm  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
from torch import nn  # noqa: E402

from earnings_iv_crush.config import ONLINE_BAYES_L4_MODEL  # noqa: E402
from earnings_iv_crush.research.online_bayes import yj, yj_inv, yj_logderiv  # noqa: E402

# ── lane configuration ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class D1Config:
    """Declared constants of lane D1 (not searched). ``config.py`` is closed to this lane.

    Attributes
    ----------
    yj_power : float
        Yeo-Johnson power of the loss-ratio transform, L4's (``ONLINE_BAYES_L4_MODEL``), so the
        z space and the Jacobian match the benchmark exactly.
    pct_per_unit : float
        Fraction of m0 to % of m0, L4's (``100``).
    quad_nodes : int
        Gauss-Legendre nodes per piece of the quadrature mean. ``64``: the integrand is smooth on
        each side of the branch point, and the tests show agreement with the closed form to
        1e-10 relative.
    quad_halfwidth : float
        Integration range in standard-normal units around the mass, ``12``: the normal mass
        beyond it is below 1e-32.
    sigma_floor : float
        Floor on every component scale in z, ``1e-3``, so a collapsing component cannot send the
        likelihood to infinity on a duplicated outcome.
    z_clip : float
        Bound on every standardised network input, ``5``, as L4's wide set: one stale quote or
        an extreme spread cannot dominate a fit on a few thousand rows.
    batch_size : int
        Minibatch size, ``512`` events.
    max_epochs, patience, min_epochs : int
        Early-stopping limits: at most ``400`` epochs, stop after ``40`` without improvement in
        the validation negative log-likelihood (epoch 0, the initial network, is a candidate).
        ``min_epochs`` ``0``: a refit may take zero epochs, which for D1b is the Gaussian
        version of L4, so the search can return "the chain adds nothing" honestly.
    val_days : int
        Length of the early-stopping window, the last ``365`` days of the training window (the
        last calendar year for a 1 January origin).
    t_df_init_a, t_df_init_b : float
        Initial degrees of freedom of the Student-t head, ``10`` for D1a and ``30`` (L4's
        ``obs_df``) for D1b, so D1b starts near L4.
    t_df_min : float
        Lower bound of the Student-t degrees of freedom, ``2.05``, keeping a finite variance in z.
    n_search_seeds, n_final_seeds : int
        Seeds per searched configuration (``2``) and in the frozen ensemble (``5``), per the brief.
    """

    yj_power: float = ONLINE_BAYES_L4_MODEL.yj_power
    pct_per_unit: float = ONLINE_BAYES_L4_MODEL.pct_per_unit
    quad_nodes: int = 64
    quad_halfwidth: float = 12.0
    sigma_floor: float = 1e-3
    z_clip: float = 5.0
    batch_size: int = 512
    max_epochs: int = 400
    patience: int = 40
    min_epochs: int = 0
    val_days: int = 365
    t_df_init_a: float = 10.0
    t_df_init_b: float = ONLINE_BAYES_L4_MODEL.obs_df
    t_df_min: float = 2.05
    n_search_seeds: int = 2
    n_final_seeds: int = 5


CFG = D1Config()


@dataclass(frozen=True)
class ModelSpec:
    """One searched configuration.

    ``variant`` ``"a"`` predicts the head from the surface, scalars and features alone;
    ``"b"`` predicts offsets to L4's z location and log scale, initialised at zero. ``head`` is
    ``"gmm"`` (K Gaussian components in z, eligible for the economic rule) or ``"t"`` (a
    Student-t in z, log score only). ``arch`` is ``"mlp"`` or ``"conv"``.
    """

    variant: str = "b"
    arch: str = "mlp"
    head: str = "gmm"
    K: int = 1
    width: int = 64
    depth: int = 2
    conv_ch: int = 16
    dropout: float = 0.1
    weight_decay: float = 1e-3
    lr: float = 1e-3
    use_surface: bool = True

    def __post_init__(self) -> None:
        if self.variant not in ("a", "b") or self.arch not in ("mlp", "conv"):
            raise ValueError("variant in (a, b), arch in (mlp, conv)")
        if self.head not in ("gmm", "t") or not 1 <= self.K <= 3:
            raise ValueError("head in (gmm, t), 1 <= K <= 3")
        if self.variant == "b" and self.K != 1:
            # Zero-initialised offsets make every component identical and keep them so.
            raise ValueError("D1b boosts L4 with a single component")
        if self.head == "t" and self.K != 1:
            raise ValueError("the Student-t head has one component")

    @property
    def eligible(self) -> bool:
        """Whether the predictive mean of H_net is finite (Gaussian or mixture in z)."""
        return self.head == "gmm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── densities, Jacobian and moments (numpy, float64) ─────────────────────────


@dataclass
class Predictive:
    """Per-event predictive in z: mixture weights, locations, scales, and Student-t df.

    Arrays are ``(n, K)``. ``df`` is ``None`` for a Gaussian mixture, else ``(n, K)``.
    """

    w: np.ndarray
    mu: np.ndarray
    sig: np.ndarray
    df: np.ndarray | None = None

    @property
    def eligible(self) -> bool:
        return self.df is None

    def subset(self, idx: np.ndarray) -> Predictive:
        return Predictive(
            self.w[idx], self.mu[idx], self.sig[idx], None if self.df is None else self.df[idx]
        )


def ensemble(preds: list[Predictive]) -> Predictive:
    """Average of densities: the components of every member, weights divided by the count."""
    if not preds:
        raise ValueError("empty ensemble")
    if len({p.eligible for p in preds}) != 1:
        raise ValueError("cannot mix Gaussian and Student-t members")
    m = len(preds)
    w = np.concatenate([p.w / m for p in preds], axis=1)
    mu = np.concatenate([p.mu for p in preds], axis=1)
    sig = np.concatenate([p.sig for p in preds], axis=1)
    df = None if preds[0].df is None else np.concatenate([p.df for p in preds], axis=1)
    return Predictive(w, mu, sig, df)


def _t_logpdf(z: np.ndarray, mu: np.ndarray, sig: np.ndarray, df: np.ndarray) -> np.ndarray:
    r = (z - mu) / sig
    return (
        gammaln((df + 1) / 2)
        - gammaln(df / 2)
        - 0.5 * np.log(df * np.pi)
        - np.log(sig)
        - (df + 1) / 2 * np.log1p(r * r / df)
    )


def logpdf_z(z: np.ndarray, p: Predictive) -> np.ndarray:
    """Log predictive density of z per event."""
    zz = np.asarray(z, float)[:, None]
    if p.df is None:
        comp = norm.logpdf(zz, p.mu, p.sig)
    else:
        comp = _t_logpdf(zz, p.mu, p.sig, p.df)
    with np.errstate(divide="ignore"):
        return logsumexp(comp + np.log(p.w), axis=1)


def cdf_z(z: np.ndarray, p: Predictive) -> np.ndarray:
    """Predictive CDF of z per event (NaN where z is NaN). ``F_y(y) = 1 - F_z(z)``."""
    zz = np.asarray(z, float)[:, None]
    if p.df is None:
        c = norm.cdf((zz - p.mu) / p.sig)
    else:
        from scipy.stats import t as student_t

        c = student_t.cdf((zz - p.mu) / p.sig, p.df)
    return (p.w * c).sum(axis=1)


def to_z(y: np.ndarray, unit: np.ndarray, cfg: D1Config = CFG) -> np.ndarray:
    """``z = yj(-y / U)``, NaN where ``y`` or ``U`` is not usable."""
    y = np.asarray(y, float)
    unit = np.asarray(unit, float)
    ok = np.isfinite(y) & np.isfinite(unit) & (unit > 0)
    out = np.full(y.shape, np.nan)
    out[ok] = yj(-y[ok] / unit[ok], cfg.yj_power)
    return out


def log_jacobian(y: np.ndarray, unit: np.ndarray, cfg: D1Config = CFG) -> np.ndarray:
    """``log |dz / dy|`` at ``y``: ``yj_logderiv(-y / U) - log U``."""
    y = np.asarray(y, float)
    unit = np.asarray(unit, float)
    return yj_logderiv(-y / unit, cfg.yj_power) - np.log(unit)


def logscore_y(y: np.ndarray, unit: np.ndarray, p: Predictive, cfg: D1Config = CFG) -> np.ndarray:
    """Log predictive density of ``y`` (H_net in % of m0) with the Jacobian, per event."""
    return logpdf_z(to_z(y, unit, cfg), p) + log_jacobian(y, unit, cfg)


def _gauss_expect(fn: Any, mu: np.ndarray, sig: np.ndarray, cfg: D1Config = CFG) -> np.ndarray:
    """``E[fn(mu + sig u)]``, ``u`` standard normal, by Gauss-Legendre split at ``z = 0``.

    The two branches of ``yj_inv`` meet at ``z = 0`` with matching first derivatives but
    different higher ones, so each side is integrated separately. On the loss side the
    integrand ``exp(sig u) phi(u)`` has its mass near ``u = sig``, so the upper limit extends to
    ``sig + halfwidth``.
    """
    mu = np.asarray(mu, float)
    sig = np.asarray(sig, float)
    xg, wg = roots_legendre(cfg.quad_nodes)
    hw = cfg.quad_halfwidth
    lo = np.full(mu.shape, -hw)
    hi = np.maximum(hw, sig + hw)
    u0 = np.clip(-mu / sig, lo, hi)
    total = np.zeros(mu.shape)
    for a, b in ((lo, u0), (u0, hi)):
        half = (b - a) / 2
        mid = (b + a) / 2
        u = mid[..., None] + half[..., None] * xg
        with np.errstate(over="ignore", invalid="ignore"):
            f = fn(mu[..., None] + sig[..., None] * u) * norm.pdf(u)
        total += half * (f * wg).sum(axis=-1)
    return total


def predictive_moments(
    p: Predictive, unit: np.ndarray, cfg: D1Config = CFG
) -> dict[str, np.ndarray]:
    """Mean and sd of ``y = -U yj_inv(z)`` by quadrature, and ``P(y > 0) = P(z < 0)``.

    For a Student-t head the mean and sd are NaN (infinite in y space) and only ``p_pos`` is
    returned finite.
    """
    unit = np.asarray(unit, float)
    k = cfg.yj_power
    if p.df is None:
        p_pos = (p.w * norm.cdf(-p.mu / p.sig)).sum(axis=1)
        m1 = _gauss_expect(lambda z: yj_inv(z.ravel(), k).reshape(z.shape), p.mu, p.sig, cfg)
        m2 = _gauss_expect(lambda z: yj_inv(z.ravel(), k).reshape(z.shape) ** 2, p.mu, p.sig, cfg)
        ex = (p.w * m1).sum(axis=1)
        ex2 = (p.w * m2).sum(axis=1)
        mean = -unit * ex
        sd = unit * np.sqrt(np.maximum(ex2 - ex * ex, 0.0))
    else:
        from scipy.stats import t as student_t

        p_pos = (p.w * student_t.cdf(-p.mu / p.sig, p.df)).sum(axis=1)
        mean = np.full(unit.shape, np.nan)
        sd = np.full(unit.shape, np.nan)
    return {"mean": mean, "sd": sd, "p_pos": p_pos}


def lognormal_branch_mean(mu: np.ndarray, sig: np.ndarray) -> np.ndarray:
    """Closed form of ``E[(exp(z) - 1) 1{z >= 0}]`` for ``z ~ N(mu, sig^2)`` (the k = 0 loss
    branch), used to check the quadrature."""
    a = mu / sig
    return np.exp(mu + sig * sig / 2) * norm.cdf(a + sig) - norm.cdf(a)


# ── inputs and normalisation ─────────────────────────────────────────────────


@dataclass
class Inputs:
    """Network inputs aligned on events.

    surf : (n, C, E, G) float, NaN where not quoted; ``mask_ch`` indexes the validity channel.
    scal : (n, S) scalars, raw. feats : (n, F) L4's causally standardised features.
    l4_loc, l4_scale : L4's prior predictive location and scale in z (NaN where L4 has none).
    z : the target in z (NaN where unknown).
    """

    surf: np.ndarray
    mask_ch: int
    scal: np.ndarray
    feats: np.ndarray
    l4_loc: np.ndarray
    l4_scale: np.ndarray
    z: np.ndarray
    channel_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def n(self) -> int:
        return int(self.z.shape[0])


@dataclass
class Normaliser:
    """Means and sds fit on training rows only; masked surface points are zeroed after it."""

    s_mu: np.ndarray
    s_sd: np.ndarray
    sc_log: np.ndarray
    sc_mu: np.ndarray
    sc_sd: np.ndarray
    f_mu: np.ndarray
    f_sd: np.ndarray

    @staticmethod
    def fit(inp: Inputs, rows: np.ndarray) -> Normaliser:
        s = inp.surf[rows]
        valid = s[:, inp.mask_ch : inp.mask_ch + 1] > 0.5
        sv = np.where(valid & np.isfinite(s), s, np.nan)
        with np.errstate(invalid="ignore"), _quiet_nan():
            s_mu = np.nanmean(sv, axis=0)
            s_sd = np.nanstd(sv, axis=0)
        s_mu = np.where(np.isfinite(s_mu), s_mu, 0.0)
        s_sd = np.where(np.isfinite(s_sd) & (s_sd > 0), s_sd, 1.0)
        sc = inp.scal[rows]
        sc_log = np.array(
            [bool(np.all(sc[np.isfinite(sc[:, j]), j] > 0)) for j in range(sc.shape[1])]
        )
        sct = _sc_transform(sc, sc_log)
        with _quiet_nan():
            sc_mu = np.nan_to_num(np.nanmean(sct, axis=0), nan=0.0)
            sc_sd = np.nanstd(sct, axis=0)
        sc_sd = np.where(np.isfinite(sc_sd) & (sc_sd > 0), sc_sd, 1.0)
        f = inp.feats[rows]
        with _quiet_nan():
            f_mu = np.nan_to_num(np.nanmean(f, axis=0), nan=0.0)
            f_sd = np.nanstd(f, axis=0)
        f_sd = np.where(np.isfinite(f_sd) & (f_sd > 0), f_sd, 1.0)
        return Normaliser(s_mu, s_sd, sc_log, sc_mu, sc_sd, f_mu, f_sd)

    def apply(
        self, inp: Inputs, rows: np.ndarray, cfg: D1Config = CFG, occlude: tuple[int, ...] = ()
    ) -> tuple[np.ndarray, np.ndarray]:
        """Normalised surface ``(n, C, E, G)`` and flat side inputs ``(n, S + F)``.

        ``occlude`` lists channels set to zero (their training mean) after normalisation.
        """
        s = inp.surf[rows]
        valid = s[:, inp.mask_ch : inp.mask_ch + 1] > 0.5
        sn = (s - self.s_mu) / self.s_sd
        sn = np.where(valid & np.isfinite(sn), np.clip(sn, -cfg.z_clip, cfg.z_clip), 0.0)
        sn[:, inp.mask_ch] = valid[:, 0].astype(float)
        for c in occlude:
            sn[:, c] = 0.0
        sc = (_sc_transform(inp.scal[rows], self.sc_log) - self.sc_mu) / self.sc_sd
        f = (inp.feats[rows] - self.f_mu) / self.f_sd
        side = np.concatenate([sc, f], axis=1)
        side = np.where(np.isfinite(side), np.clip(side, -cfg.z_clip, cfg.z_clip), 0.0)
        return sn.astype(np.float32), side.astype(np.float32)


class _quiet_nan:
    def __enter__(self) -> None:
        import warnings

        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", category=RuntimeWarning)

    def __exit__(self, *a: Any) -> None:
        self._w.__exit__(*a)


def _sc_transform(sc: np.ndarray, use_log: np.ndarray) -> np.ndarray:
    out = sc.astype(float).copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out[:, use_log] = np.log(out[:, use_log])
    out[~np.isfinite(out)] = np.nan
    return out


# ── networks ─────────────────────────────────────────────────────────────────


class SurfaceNet(nn.Module):
    """Trunk over the surface and side inputs, and a head with ``K`` components in z."""

    def __init__(
        self,
        spec: ModelSpec,
        n_ch: int,
        n_exp: int,
        n_grid: int,
        n_side: int,
        z_mu: float,
        z_sd: float,
        cfg: D1Config = CFG,
    ) -> None:
        super().__init__()
        self.spec = spec
        self.cfg = cfg
        act = nn.GELU
        if spec.use_surface and spec.arch == "conv":
            c = spec.conv_ch
            self.conv: nn.Module | None = nn.Sequential(
                nn.Conv1d(n_ch * n_exp, c, 3, padding=1),
                act(),
                nn.Conv1d(c, c, 3, padding=1),
                act(),
            )
            d_surf = c * n_grid
        elif spec.use_surface:
            self.conv = None
            d_surf = n_ch * n_exp * n_grid
        else:
            self.conv = None
            d_surf = 0
        layers: list[nn.Module] = []
        d = d_surf + n_side
        for _ in range(spec.depth):
            layers += [nn.Linear(d, spec.width), act(), nn.Dropout(spec.dropout)]
            d = spec.width
        self.trunk = nn.Sequential(*layers)
        K = spec.K
        n_out = 3 * K if spec.head == "gmm" else 2
        self.out = nn.Linear(d, n_out)
        if spec.variant == "b":
            nn.init.zeros_(self.out.weight)
            nn.init.zeros_(self.out.bias)
            df0 = cfg.t_df_init_b
        else:
            nn.init.normal_(self.out.weight, std=1e-2)
            with torch.no_grad():
                b = torch.zeros(n_out)
                if spec.head == "gmm":
                    spread = torch.linspace(-0.5, 0.5, K) if K > 1 else torch.zeros(1)
                    b[K : 2 * K] = z_mu + spread * z_sd
                    b[2 * K :] = float(np.log(np.expm1(z_sd)))
                else:
                    b[0] = z_mu
                    b[1] = float(np.log(np.expm1(z_sd)))
                self.out.bias.copy_(b)
            df0 = cfg.t_df_init_a
        self.raw_df = nn.Parameter(torch.tensor(float(np.log(np.expm1(df0 - cfg.t_df_min)))))

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(
        self, surf: torch.Tensor, side: torch.Tensor, l4_loc: torch.Tensor, l4_ls: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor | None]:
        """Log weights, locations and scales ``(n, K)``, and the Student-t df (or None)."""
        n = surf.shape[0]
        parts = [side]
        if self.spec.use_surface:
            if self.conv is not None:
                s = surf.reshape(n, surf.shape[1] * surf.shape[2], surf.shape[3])
                parts.insert(0, self.conv(s).reshape(n, -1))
            else:
                parts.insert(0, surf.reshape(n, -1))
        h = self.trunk(torch.cat(parts, dim=1))
        o = self.out(h)
        K = self.spec.K
        floor = self.cfg.sigma_floor
        if self.spec.head == "gmm":
            logit, mu, raw = o[:, :K], o[:, K : 2 * K], o[:, 2 * K :]
        else:
            logit, mu, raw = torch.zeros_like(o[:, :1]), o[:, :1], o[:, 1:2]
        if self.spec.variant == "b":
            mu = l4_loc[:, None] + mu
            sig = torch.exp(l4_ls[:, None] + raw) + floor
        else:
            sig = nn.functional.softplus(raw) + floor
        logw = torch.log_softmax(logit, dim=1)
        df = None
        if self.spec.head == "t":
            df = (nn.functional.softplus(self.raw_df) + self.cfg.t_df_min).expand(n, 1)
        return logw, mu, sig, df


def nll_z(
    z: torch.Tensor,
    logw: torch.Tensor,
    mu: torch.Tensor,
    sig: torch.Tensor,
    df: torch.Tensor | None,
) -> torch.Tensor:
    """Mean negative log density of z. The Jacobian is constant per event, so this is the
    H_net-space objective up to a constant."""
    zz = z[:, None]
    r = (zz - mu) / sig
    if df is None:
        comp = -0.5 * r * r - torch.log(sig) - 0.5 * float(np.log(2 * np.pi))
    else:
        comp = (
            torch.lgamma((df + 1) / 2)
            - torch.lgamma(df / 2)
            - 0.5 * torch.log(df * np.pi)
            - torch.log(sig)
            - (df + 1) / 2 * torch.log1p(r * r / df)
        )
    return -torch.logsumexp(comp + logw, dim=1).mean()


# ── fitting ──────────────────────────────────────────────────────────────────


def set_seed(seed: int) -> None:
    import random

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False


def _tensors(
    inp: Inputs, rows: np.ndarray, nrm: Normaliser, device: str, occlude: tuple[int, ...] = ()
) -> tuple[torch.Tensor, ...]:
    sn, side = nrm.apply(inp, rows, occlude=occlude)
    loc = np.nan_to_num(inp.l4_loc[rows], nan=0.0)
    ls = np.log(np.where(np.isfinite(inp.l4_scale[rows]), inp.l4_scale[rows], 1.0))
    z = np.nan_to_num(inp.z[rows], nan=0.0)
    return tuple(
        torch.as_tensor(a, dtype=torch.float32, device=device) for a in (sn, side, loc, ls, z)
    )


def _train(
    spec: ModelSpec,
    inp: Inputs,
    rows: np.ndarray,
    val_rows: np.ndarray | None,
    epochs: int,
    seed: int,
    device: str,
    cfg: D1Config = CFG,
) -> tuple[SurfaceNet, Normaliser, int, list[float]]:
    """Train on ``rows``; with ``val_rows``, early-stop on their NLL and return the best state."""
    set_seed(seed)
    nrm = Normaliser.fit(inp, rows)
    zt = inp.z[rows]
    C, E, G = inp.surf.shape[1:]
    side_dim = inp.scal.shape[1] + inp.feats.shape[1]
    net = SurfaceNet(spec, C, E, G, side_dim, float(np.mean(zt)), float(np.std(zt)), cfg)
    net.to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=spec.lr, weight_decay=spec.weight_decay)
    S, X, L, LS, Z = _tensors(inp, rows, nrm, device)
    if val_rows is not None and val_rows.size:
        Sv, Xv, Lv, LSv, Zv = _tensors(inp, val_rows, nrm, device)
    n = rows.size
    gen = torch.Generator(device="cpu").manual_seed(seed)
    best, best_ep, best_state, since = np.inf, 0, None, 0
    curve: list[float] = []
    has_val = val_rows is not None and val_rows.size > 0
    if has_val:
        # Epoch 0 is a candidate: for D1b it is the Gaussian version of L4.
        net.eval()
        with torch.no_grad():
            best = float(nll_z(Zv, *net(Sv, Xv, Lv, LSv)))
        curve.append(best)
        best_state = {k: t.detach().clone() for k, t in net.state_dict().items()}
    for ep in range(1, epochs + 1):
        net.train()
        perm = torch.randperm(n, generator=gen).to(device)
        for i in range(0, n, cfg.batch_size):
            b = perm[i : i + cfg.batch_size]
            loss = nll_z(Z[b], *net(S[b], X[b], L[b], LS[b]))
            opt.zero_grad()
            loss.backward()
            opt.step()
        if not has_val:
            continue
        net.eval()
        with torch.no_grad():
            v = float(nll_z(Zv, *net(Sv, Xv, Lv, LSv)))
        curve.append(v)
        if v < best - 1e-6:
            best, best_ep, since = v, ep, 0
            best_state = {k: t.detach().clone() for k, t in net.state_dict().items()}
        else:
            since += 1
            if since >= cfg.patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    return net, nrm, (best_ep if val_rows is not None else epochs), curve


def predict(
    net: SurfaceNet,
    nrm: Normaliser,
    inp: Inputs,
    rows: np.ndarray,
    device: str,
    occlude: tuple[int, ...] = (),
) -> Predictive:
    """The network's predictive in z on ``rows``, as float64 arrays."""
    net.eval()
    S, X, L, LS, _ = _tensors(inp, rows, nrm, device, occlude)
    with torch.no_grad():
        logw, mu, sig, df = net(S, X, L, LS)
    to = lambda t: t.detach().cpu().double().numpy()  # noqa: E731
    return Predictive(np.exp(to(logw)), to(mu), to(sig), None if df is None else to(df))


@dataclass
class FitResult:
    nets: list[SurfaceNet]
    nrms: list[Normaliser]
    best_epochs: list[int]
    val_nll: list[float]


def fit_two_stage(
    spec: ModelSpec,
    inp: Inputs,
    train_rows: np.ndarray,
    val_rows: np.ndarray,
    seeds: list[int],
    device: str,
    cfg: D1Config = CFG,
) -> FitResult:
    """Stage 1: fit on the window less its last year and early-stop on that year. Stage 2:
    refit on the whole window for the chosen number of epochs, same seed."""
    if train_rows.size == 0 or val_rows.size == 0:
        raise ValueError(f"empty fold: train {train_rows.size}, validation {val_rows.size}")
    inner = np.setdiff1d(train_rows, val_rows)
    if inner.size == 0:
        raise ValueError("no training rows outside the validation year")
    nets, nrms, eps, vals = [], [], [], []
    for s in seeds:
        _, _, ep, curve = _train(spec, inp, inner, val_rows, cfg.max_epochs, s, device, cfg)
        ep = max(ep, cfg.min_epochs)
        net, nrm, _, _ = _train(spec, inp, train_rows, None, ep, s, device, cfg)
        nets.append(net)
        nrms.append(nrm)
        eps.append(ep)
        vals.append(float(min(curve)) if curve else float("nan"))
    return FitResult(nets, nrms, eps, vals)


def predict_ensemble(
    fr: FitResult, inp: Inputs, rows: np.ndarray, device: str, occlude: tuple[int, ...] = ()
) -> Predictive:
    return ensemble(
        [predict(n, r, inp, rows, device, occlude) for n, r in zip(fr.nets, fr.nrms, strict=True)]
    )


def score_rows(
    pred: Predictive, y: np.ndarray, unit: np.ndarray, cfg: D1Config = CFG
) -> dict[str, np.ndarray]:
    """Per-event log score in y space, PIT, moments, and the declared decision.

    The decision is ``mean > 0`` and is False wherever the mean is not finite (a Student-t
    head), so such a head can never trade.
    """
    mom = predictive_moments(pred, unit, cfg)
    ls = logscore_y(y, unit, pred, cfg)
    pit = 1.0 - cdf_z(to_z(y, unit, cfg), pred)
    decide = np.where(np.isfinite(mom["mean"]), mom["mean"] > 0, False)
    return {"log_score": ls, "pit": pit, **mom, "decide": decide}
