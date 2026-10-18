"""
protocol.py
The research protocol as code: pre-registration freeze and verify, date-clustered intervals,
and the participation-matched random null.

Every new study follows one sequence (``docs/PROTOCOL.md``): write the pre-registration,
freeze it with :func:`freeze_prereg` before any outcome exists, call :func:`verify_prereg`
at the top of the scorer, report the primary statistic with :func:`date_clustered_ci`, and
read any selector against :func:`matched_random_null`. The defaults here are the project's
inference rules (5,000 draws, seed 0, 95% interval, clusters on the announcement date), so a
new number is on the same basis as every number already in the record.

The bootstrap itself is ``engine.event_study.cluster_bootstrap_ci``; this module fixes its
arguments rather than reimplementing it.

References
----------
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-based improvements for
inference with clustered errors. Review of Economics and Statistics 90(3), 414-427.
Efron, B. and Tibshirani, R. (1993). An Introduction to the Bootstrap. Chapman and Hall.
Lo, A. W. (2002). The statistics of Sharpe ratios. Financial Analysts Journal 58(4), 36-52.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..engine.event_study import cluster_bootstrap_ci

# ── inference defaults ───────────────────────────────────────────────────────

N_BOOT = 5000  # every interval in the record uses 5,000 cluster draws
SEED = 0  # and seed 0, so a rerun reproduces it exactly
CI = 0.95


def per_trade_sharpe(returns: Sequence[float] | np.ndarray | pd.Series) -> float:
    """Mean over sample standard deviation (ddof=1) of per-trade returns.

    The project's primary statistic. It is not annualised; an annual figure, where one is
    needed, multiplies by the square root of the book's own trades per year and says so
    (Lo 2002), never by the daily square root of 252.
    """
    x = np.asarray(returns, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 else float("nan")


@dataclass(frozen=True)
class Interval:
    """A point estimate with its date-clustered interval and the sample behind it."""

    point: float
    low: float
    high: float
    n: int
    clusters: int

    @property
    def excludes_zero(self) -> bool:
        return bool(self.low > 0 or self.high < 0)

    def __str__(self) -> str:
        return (
            f"{self.point:+.4f} [{self.low:+.4f}, {self.high:+.4f}] "
            f"(N={self.n}, {self.clusters} date clusters)"
        )


def date_clustered_ci(
    values: Sequence[float] | np.ndarray | pd.Series,
    dates: Sequence[Any] | np.ndarray | pd.Series,
    stat: Callable[[np.ndarray], float] = per_trade_sharpe,
    *,
    n_boot: int = N_BOOT,
    seed: int = SEED,
    ci: float = CI,
) -> Interval:
    """Point estimate and percentile interval, resampling whole announcement dates.

    Many events report on the same date and share that night's market move, so they are
    not independent draws; resampling dates keeps that dependence in every replicate.

    Raises
    ------
    ValueError
        If the inputs differ in length or nothing finite remains.
    """
    v = np.asarray(values, dtype=float)
    keys = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    if v.shape[0] != keys.shape[0]:
        raise ValueError(f"values ({v.shape[0]}) and dates ({keys.shape[0]}) differ in length")
    ok = np.isfinite(v)
    if not ok.any():
        raise ValueError("no finite values to score")
    v, keys = v[ok], keys[ok]
    low, high = cluster_bootstrap_ci(v, keys, stat, n_boot=n_boot, ci=ci, seed=seed)
    return Interval(
        point=float(stat(v)), low=low, high=high, n=int(v.size), clusters=len(np.unique(keys))
    )


# ── participation-matched random null ────────────────────────────────────────


@dataclass(frozen=True)
class NullComparison:
    """A selector's statistic against the same statistic on random selections."""

    observed: float
    null: np.ndarray
    n_selected: int

    @property
    def percentile(self) -> float:
        """Share of random draws strictly below the observed statistic, in percent."""
        finite = self.null[np.isfinite(self.null)]
        return float(100.0 * (finite < self.observed).mean()) if finite.size else float("nan")

    def __str__(self) -> str:
        return (
            f"observed {self.observed:+.4f} vs matched null median "
            f"{np.nanmedian(self.null):+.4f}; percentile {self.percentile:.1f} "
            f"(N={self.n_selected}, {self.null.size} draws)"
        )


def matched_random_null(
    population: Sequence[float] | np.ndarray | pd.Series,
    selected: Sequence[bool] | np.ndarray | pd.Series,
    stat: Callable[[np.ndarray], float] = per_trade_sharpe,
    *,
    n_draws: int = N_BOOT,
    seed: int = SEED,
) -> NullComparison:
    """Compare a selection to random selections of the same size from the same pool.

    Holding the count and the pool fixed isolates the rule: a selector that cannot beat
    picking the same number of events at random has not shown selection skill, whatever its
    level. ``population`` is every eligible event's outcome and ``selected`` the rule's
    boolean mask over it.

    Raises
    ------
    ValueError
        If the mask is the wrong length or selects nothing or everything.
    """
    pop = np.asarray(population, dtype=float)
    mask = np.asarray(selected, dtype=bool)
    if pop.shape != mask.shape:
        raise ValueError("population and selection mask differ in shape")
    k = int(mask.sum())
    if k == 0 or k == pop.size:
        raise ValueError(f"selection takes {k} of {pop.size} events; nothing to compare")
    rng = np.random.default_rng(seed)
    draws = np.array(
        [stat(pop[rng.choice(pop.size, size=k, replace=False)]) for _ in range(n_draws)]
    )
    return NullComparison(observed=float(stat(pop[mask])), null=draws, n_selected=k)


# ── pre-registration ─────────────────────────────────────────────────────────


def sha256_file(path: str | Path) -> str:
    """SHA-256 of a file's exact bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze_prereg(
    prereg: str | Path,
    record: str | Path,
    *,
    trial_id: str,
    n_trials_declared: int,
    declared_utc: str,
    **fields: Any,
) -> dict[str, Any]:
    """Record the hash of a pre-registration before any outcome is computed.

    Refuses to overwrite an existing record: a frozen text is changed only through a dated
    amendment with its own hash, never by re-freezing.

    Returns
    -------
    dict
        The record written to ``record``.
    """
    rec_path = Path(record)
    if rec_path.exists():
        raise FileExistsError(f"{rec_path} exists; amend with a new file, never re-freeze")
    body = {
        "trial_id": trial_id,
        "declared_utc": declared_utc,
        "prereg_file": Path(prereg).as_posix(),
        "prereg_sha256": sha256_file(prereg),
        "n_trials_declared": int(n_trials_declared),
        **fields,
    }
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return body


def verify_prereg(prereg: str | Path, record: str | Path) -> str:
    """Check a pre-registration against its frozen hash; call it first in every scorer.

    Returns
    -------
    str
        The verified SHA-256.

    Raises
    ------
    ValueError
        If the text no longer matches the hash recorded when it was frozen.
    """
    rec = json.loads(Path(record).read_text(encoding="utf-8"))
    got = sha256_file(prereg)
    if got != rec["prereg_sha256"]:
        raise ValueError(
            f"{prereg} does not match its frozen hash in {record} "
            f"({got[:12]} vs {str(rec['prereg_sha256'])[:12]}); the text changed after freezing"
        )
    return got
