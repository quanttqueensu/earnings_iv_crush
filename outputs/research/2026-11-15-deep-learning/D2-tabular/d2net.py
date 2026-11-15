"""
d2net.py
Lane D2 (tabular control), torch side: a mixture-density MLP on L4's seven 15:59 features plus
L4's causal name effect, with a Gaussian-mixture head (K = 1 to 3) or a Student-t head in the
standardised transformed outcome, its training with early stopping and refit, and the fold
runner that turns a fit into per-event mixture parameters in z space.

The head and Jacobian code is D2's own; D1's folder held no tested heads when this was written.

Usage
-----
    import d2lib, d2net
    ev = d2lib.synthetic(); pars = d2net.fit_fold(ev, d2lib.dev_folds()[0], d2net.Config(), 0)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import d2lib  # noqa: F401  (imports pyarrow before torch)
import numpy as np
import pandas as pd
import torch
from torch import nn

SIG_FLOOR = 1e-3  # floor on a component sd in standardised z units, so no spike collapses
DF_FLOOR = 2.0  # Student-t df > 2 keeps the variance finite in z (the H mean stays infinite)
BATCH = 256
MAX_EPOCHS = 600
PATIENCE = 40
N_THREADS = 2


@dataclass(frozen=True)
class Config:
    """One searched configuration."""

    head: str = "gm"  # "gm" (Gaussian mixture) or "t" (Student-t, log score only)
    K: int = 1
    hidden: tuple[int, ...] = (16,)
    weight_decay: float = 1e-4
    dropout: float = 0.0
    lr: float = 1e-3
    scale_net: bool = True  # False: one free scale per component (a homoscedastic control)
    drop_inputs: tuple[str, ...] = ()  # inputs left out (a control)
    name: str = field(default="", compare=False)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hidden"] = list(self.hidden)
        d["drop_inputs"] = list(self.drop_inputs)
        return d


class MDN(nn.Module):
    """MLP body and a mixture head; outputs parameters in standardised z units."""

    def __init__(self, n_in: int, cfg: Config) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        d = n_in
        for h in cfg.hidden:
            layers += [nn.Linear(d, h), nn.SiLU(), nn.Dropout(cfg.dropout)]
            d = h
        self.body = nn.Sequential(*layers)
        self.cfg = cfg
        n_out = 3 * cfg.K if cfg.head == "gm" else 3
        self.out = nn.Linear(d, n_out)
        with torch.no_grad():
            self.out.weight.mul_(0.01)
            self.out.bias.zero_()
            inv_sp1 = math.log(math.e - 1.0)  # softplus^-1(1): unit sd at start
            if cfg.head == "gm":
                K = cfg.K
                self.out.bias[K : 2 * K] = torch.linspace(-0.5, 0.5, K) if K > 1 else 0.0
                self.out.bias[2 * K :] = inv_sp1
            else:
                self.out.bias[1] = inv_sp1
                self.out.bias[2] = math.log(math.expm1(8.0))  # df starts near 10
        if not cfg.scale_net:
            if cfg.head != "gm":
                raise ValueError("the constant-scale control is defined for the mixture head")
            # Creating a parameter draws no random numbers, so other weights are unchanged.
            self.free_sig = nn.Parameter(torch.full((cfg.K,), inv_sp1))

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        o = self.out(self.body(x))
        sp = nn.functional.softplus
        if self.cfg.head == "gm":
            K = self.cfg.K
            return {
                "logw": torch.log_softmax(o[:, :K], dim=1),
                "mu": o[:, K : 2 * K],
                "sig": (
                    sp(o[:, 2 * K :])
                    if self.cfg.scale_net
                    else sp(self.free_sig).expand(o.shape[0], K)
                )
                + SIG_FLOOR,
            }
        return {
            "mu": o[:, 0],
            "sig": sp(o[:, 1]) + SIG_FLOOR,
            "df": sp(o[:, 2]) + DF_FLOOR,
        }


def nll(p: dict[str, torch.Tensor], z: torch.Tensor, head: str) -> torch.Tensor:
    """Mean negative log density of standardised z."""
    if head == "gm":
        zc = z[:, None]
        lp = (
            p["logw"]
            - 0.5 * math.log(2 * math.pi)
            - torch.log(p["sig"])
            - 0.5 * ((zc - p["mu"]) / p["sig"]) ** 2
        )
        return -torch.logsumexp(lp, dim=1).mean()
    u = (z - p["mu"]) / p["sig"]
    df = p["df"]
    lp = (
        torch.lgamma((df + 1) / 2)
        - torch.lgamma(df / 2)
        - 0.5 * torch.log(df * math.pi)
        - torch.log(p["sig"])
        - (df + 1) / 2 * torch.log1p(u * u / df)
    )
    return -lp.mean()


def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_num_threads(N_THREADS)


def _epochs(
    model: MDN,
    opt: torch.optim.Optimizer,
    X: torch.Tensor,
    z: torch.Tensor,
    gen: torch.Generator,
) -> None:
    model.train()
    n = X.shape[0]
    perm = torch.randperm(n, generator=gen)
    for lo in range(0, n, BATCH):
        idx = perm[lo : lo + BATCH]
        opt.zero_grad()
        loss = nll(model(X[idx]), z[idx], model.cfg.head)
        loss.backward()
        opt.step()


def train(
    Xtr: np.ndarray,
    ztr: np.ndarray,
    cfg: Config,
    seed: int,
    Xva: np.ndarray | None = None,
    zva: np.ndarray | None = None,
    epochs: int | None = None,
) -> tuple[MDN, int, float]:
    """Fit on (Xtr, ztr). With validation data, stop at the best validation epoch (patience
    ``PATIENCE``) and return that state; with ``epochs``, run exactly that many.

    Returns the model, the epoch count used and the best validation NLL (NaN without one).
    """
    seed_all(seed)
    gen = torch.Generator().manual_seed(seed)
    model = MDN(Xtr.shape[1], cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    Xt = torch.as_tensor(Xtr, dtype=torch.float32)
    zt = torch.as_tensor(ztr, dtype=torch.float32)
    if epochs is not None:
        for _ in range(epochs):
            _epochs(model, opt, Xt, zt, gen)
        return model, epochs, float("nan")
    assert Xva is not None and zva is not None
    Xv = torch.as_tensor(Xva, dtype=torch.float32)
    zv = torch.as_tensor(zva, dtype=torch.float32)
    best, best_ep, best_state, wait = float("inf"), 0, None, 0
    for ep in range(1, MAX_EPOCHS + 1):
        _epochs(model, opt, Xt, zt, gen)
        model.eval()
        with torch.no_grad():
            v = float(nll(model(Xv), zv, cfg.head))
        if v < best - 1e-6:
            best, best_ep, wait = v, ep, 0
            best_state = {k: t.clone() for k, t in model.state_dict().items()}
        else:
            wait += 1
            if wait >= PATIENCE:
                break
    assert best_state is not None
    model.load_state_dict(best_state)
    return model, best_ep, best


def _standardiser(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m = a.mean(axis=0)
    s = a.std(axis=0, ddof=1)
    s = np.where(s > 0, s, 1.0)  # a constant training column carries no information
    return m, s


def fit_fold(
    ev: pd.DataFrame, fold: d2lib.Fold, cfg: Config, seed: int, refit: bool = True
) -> dict[str, Any]:
    """Fit one seed on one fold and predict its score rows.

    Inputs and the transformed outcome are standardised with training-window means and sds
    (the early-stopping fit uses the window minus its last year; the refit uses the full
    window, each with its own standardiser). Returns the score rows' index and the mixture
    parameters in unstandardised z units.
    """
    m = d2lib.fold_masks(ev, fold)
    cols = [c for c in d2lib.FEATURES if c not in cfg.drop_inputs]
    if len(cols) + len(cfg.drop_inputs) != len(d2lib.FEATURES):
        raise ValueError(f"unknown inputs to drop: {cfg.drop_inputs}")
    X = ev[cols].to_numpy(float)
    z = d2lib.to_z(ev["h"].to_numpy(float), ev["U"].to_numpy(float))

    def prep(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
        mx, sx = _standardiser(X[rows])
        mz, sz = float(z[rows].mean()), float(z[rows].std(ddof=1))
        return mx, sx, mz, sz

    mx, sx, mz, sz = prep(m["train"])
    model, ep, vbest = train(
        (X[m["train"]] - mx) / sx,
        (z[m["train"]] - mz) / sz,
        cfg,
        seed,
        (X[m["val"]] - mx) / sx,
        (z[m["val"]] - mz) / sz,
    )
    if refit:
        mx, sx, mz, sz = prep(m["full"])
        model, _, _ = train((X[m["full"]] - mx) / sx, (z[m["full"]] - mz) / sz, cfg, seed,
                            epochs=ep)  # fmt: skip
    model.eval()
    Xs = (X[m["score"]] - mx) / sx
    with torch.no_grad():
        p = model(torch.as_tensor(Xs, dtype=torch.float32))
    occ: dict[str, dict[str, np.ndarray]] = {}
    if cfg.head == "gm":
        # Occlusion: each input group set to its training mean (zero after standardisation)
        # at prediction time, same fitted network; a mechanism read, not a refit.
        for g, members in d2lib.OCCLUSION.items():
            j = [cols.index(c) for c in members if c in cols]
            if not j:
                continue
            Xo = Xs.copy()
            Xo[:, j] = 0.0
            with torch.no_grad():
                po = model(torch.as_tensor(Xo, dtype=torch.float32))
            occ[g] = {
                "logw": po["logw"].numpy().astype(float),
                "mu": mz + sz * po["mu"].numpy().astype(float),
                "sig": sz * po["sig"].numpy().astype(float),
            }
    out: dict[str, Any] = {
        "occ": occ,
        "index": np.flatnonzero(m["score"]),
        "epochs": ep,
        "val_nll": vbest,
        "n_train": int(m["train"].sum()),
        "n_val": int(m["val"].sum()),
        "n_full": int(m["full"].sum()),
    }
    if cfg.head == "gm":
        out["logw"] = p["logw"].numpy().astype(float)
        out["mu"] = mz + sz * p["mu"].numpy().astype(float)
        out["sig"] = sz * p["sig"].numpy().astype(float)
    else:
        out["mu"] = mz + sz * p["mu"].numpy().astype(float)
        out["sig"] = sz * p["sig"].numpy().astype(float)
        out["df"] = p["df"].numpy().astype(float)
    return out


def ensemble_logpz(fits: list[dict[str, Any]], z: np.ndarray, head: str) -> np.ndarray:
    """Log density of z under the equal-weight average of the seeds' predictive densities."""
    parts = []
    for f in fits:
        if head == "gm":
            parts.append(d2lib.gm_logpdf(z, f["logw"], f["mu"], f["sig"]))
        else:
            parts.append(d2lib.t_logpdf(z, f["mu"], f["sig"], f["df"]))
    return np.logaddexp.reduce(np.vstack(parts), axis=0) - np.log(len(fits))


def ensemble_mixture(fits: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The seeds' Gaussian mixtures stacked into one mixture with weights divided by S."""
    S = len(fits)
    logw = np.hstack([f["logw"] for f in fits]) - np.log(S)
    mu = np.hstack([f["mu"] for f in fits])
    sig = np.hstack([f["sig"] for f in fits])
    return logw, mu, sig


def run(
    ev: pd.DataFrame, folds: list[d2lib.Fold], cfg: Config, seeds: tuple[int, ...]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Every fold, every seed: per-event ensemble log score of h, per-seed scores, and for a
    Gaussian-mixture head the quadrature mean, sd and P(h > 0). Rows without an outcome are
    predicted but carry a NaN score."""
    rows: list[pd.DataFrame] = []
    info: list[dict[str, Any]] = []
    h = ev["h"].to_numpy(float)
    U = ev["U"].to_numpy(float)
    for f in folds:
        fits = [fit_fold(ev, f, cfg, s) for s in seeds]
        idx = fits[0]["index"]
        hz = d2lib.to_z(np.where(np.isfinite(h[idx]), h[idx], 0.0), U[idx])
        jac = d2lib.log_jacobian(np.where(np.isfinite(h[idx]), h[idx], 0.0), U[idx])
        has = np.isfinite(h[idx])
        out = pd.DataFrame({"row": idx, "fold": f.label})
        out["d2_log_score"] = np.where(has, ensemble_logpz(fits, hz, cfg.head) + jac, np.nan)
        for s, ft in zip(seeds, fits, strict=True):
            out[f"seed{s}_log_score"] = np.where(
                has, ensemble_logpz([ft], hz, cfg.head) + jac, np.nan
            )
        if cfg.head == "gm":
            lw, mu, sg = ensemble_mixture(fits)
            summ = d2lib.gm_h_summary(lw, mu, sg, U[idx])
            for c in summ.columns:
                out[c] = summ[c].to_numpy()
            for s, ft in zip(seeds, fits, strict=True):
                out[f"seed{s}_pred_mean"] = d2lib.gm_h_summary(
                    ft["logw"], ft["mu"], ft["sig"], U[idx]
                )["pred_mean"].to_numpy()
            for g in fits[0]["occ"]:
                of = [ft["occ"][g] for ft in fits]
                out[f"occ_{g}_log_score"] = np.where(
                    has, ensemble_logpz(of, hz, cfg.head) + jac, np.nan
                )
            out["mix_logw"] = list(lw)
            out["mix_mu"] = list(mu)
            out["mix_sig"] = list(sg)
        else:
            out["t_mu"] = np.mean([ft["mu"] for ft in fits], axis=0)
            out["t_df"] = np.mean([ft["df"] for ft in fits], axis=0)
        rows.append(out)
        info.append(
            {
                "fold": f.label,
                "epochs": [ft["epochs"] for ft in fits],
                "val_nll": [round(ft["val_nll"], 5) for ft in fits],
                "n_train": fits[0]["n_train"],
                "n_val": fits[0]["n_val"],
                "n_full": fits[0]["n_full"],
                "n_score": int(idx.size),
            }
        )
    return pd.concat(rows, ignore_index=True), info
