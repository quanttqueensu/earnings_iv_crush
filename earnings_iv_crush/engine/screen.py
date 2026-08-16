"""
screen.py
One scoring contract for every pivot candidate, event-indexed or calendar-indexed.

Why this module exists
----------------------
The IV-crush verdict turned on two reporting failures that a shared contract
prevents. The first was basis: a per-trade Sharpe annualised by ``sqrt(252)`` on a
book trading 34 times a year inflated the headline roughly threefold. The second
was selection: the number of configurations actually searched was reconstructed
after the fact rather than declared before, so the Deflated Sharpe Ratio could not
be trusted until it was rebuilt.

Candidates arriving from the pivot programme differ in cadence. A cross-sectional
option sort rebalances monthly on a calendar; an event book fires irregularly on
announcement dates. Scoring them through one function means the cadence is read
from the data in both cases and the basis is carried on the result rather than
inferred by a reader.

Design commitments
------------------
- **The basis is a field, not a convention.** :class:`ScreenResult` carries
  ``sharpe_basis`` and ``periods_per_year`` explicitly. There is no code path that
  produces an annualised figure without recording the factor that produced it.
- **Degenerate input raises.** An empty selection, a zero-variance return series or
  a gate that admits nothing is a defect, not a NaN to be propagated. Silent
  emptiness is what lets a broken join look like a null result.
- **Gross before net.** :func:`gross_gate` answers whether a signal exists at all
  before any cost model is applied. The cross-market work established that this
  ordering is what separates "no signal" from "signal inside the spread".

References
----------
Bailey, D. H. and López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal
of Portfolio Management*, 40(5), 94-107.
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-Based
Improvements for Inference with Clustered Errors. *Review of Economics and
Statistics*, 90(3), 414-427.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from .event_study import cluster_bootstrap_ci
from .stats import (
    deflated_sharpe_ratio,
    infer_periods_per_year,
    probabilistic_sharpe_ratio,
)

# ── types ────────────────────────────────────────────────────────────────────

SharpeBasis = Literal["per-trade", "annualised"]
Cadence = Literal["event", "calendar"]

_MIN_OBS = 2

#: Relative tolerance below which a return series counts as constant.
_VARIANCE_TOL = 1e-12


class DegenerateScreenError(ValueError):
    """Raised when a candidate produces no scoreable sample.

    Distinct from a null result. A null result is a scored sample whose interval
    contains zero; this is the absence of a sample, which almost always means a
    join, gate or filter is broken upstream.
    """


# ── result record ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScreenResult:
    """Scorecard for one candidate on one specification.

    Attributes
    ----------
    label : str
        Candidate identifier, matching the pre-registered trial ledger entry.
    cadence : {"event", "calendar"}
        Whether the signal fires on irregular events or a regular calendar.
    n : int
        Number of scored observations.
    n_clusters : int
        Number of distinct cluster keys, the effective sample size for inference.
    mean, std : float
        Per-observation return moments.
    hit_rate : float
        Fraction of observations strictly greater than zero.
    sharpe : float
        Sharpe on the basis named by ``sharpe_basis``.
    sharpe_basis : {"per-trade", "annualised"}
        The basis of ``sharpe``. Always populated.
    periods_per_year : float
        Annualisation factor implied by the data's own cadence. Reported even when
        ``sharpe_basis`` is ``"per-trade"``, so a reader can convert and see the
        factor that would be used.
    ci_low, ci_high : float
        Cluster-bootstrap interval for the Sharpe on ``sharpe_basis``.
    psr : float
        Probabilistic Sharpe Ratio against zero.
    dsr : float
        Deflated Sharpe Ratio against ``n_trials``.
    n_trials : int
        Configurations declared in the trial ledger when this was scored.
    gross : bool
        Whether the scored returns are gross of costs.
    """

    label: str
    cadence: Cadence
    n: int
    n_clusters: int
    mean: float
    std: float
    hit_rate: float
    sharpe: float
    sharpe_basis: SharpeBasis
    periods_per_year: float
    ci_low: float
    ci_high: float
    psr: float
    dsr: float
    n_trials: int
    gross: bool
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def interval_contains_zero(self) -> bool:
        """Whether the confidence interval straddles zero."""
        return bool(self.ci_low <= 0.0 <= self.ci_high)

    def to_row(self) -> dict[str, object]:
        """Flatten to a single record suitable for a results table."""
        row = asdict(self)
        row.pop("notes")
        row["interval_contains_zero"] = self.interval_contains_zero
        return row

    def summary(self) -> str:
        """One-line human summary with the basis always stated."""
        verdict = "contains zero" if self.interval_contains_zero else "excludes zero"
        return (
            f"{self.label}: N={self.n} ({self.n_clusters} clusters), "
            f"Sharpe {self.sharpe:+.4f} [{self.sharpe_basis}], "
            f"95% CI [{self.ci_low:+.4f}, {self.ci_high:+.4f}] {verdict}, "
            f"PSR {self.psr:.4f}, DSR {self.dsr:.4f} vs {self.n_trials} trials"
        )


# ── scoring ──────────────────────────────────────────────────────────────────


def _clean(returns: pd.Series | np.ndarray) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(returns), errors="coerce").to_numpy(dtype=float)
    return arr[np.isfinite(arr)]


def _per_trade_sharpe(values: np.ndarray) -> float:
    if values.size < _MIN_OBS:
        return float("nan")
    sd = float(np.std(values, ddof=1))
    return float(np.mean(values) / sd) if sd > 0 else float("nan")


def score_signal(
    returns: pd.Series | np.ndarray,
    dates: pd.Series | np.ndarray,
    label: str,
    *,
    cadence: Cadence,
    cluster_keys: pd.Series | np.ndarray | None = None,
    basis: SharpeBasis = "per-trade",
    n_trials: int = 1,
    sr_trials_std: float = 0.0,
    gross: bool = True,
    n_boot: int = 5000,
    seed: int = 0,
    notes: dict[str, str] | None = None,
) -> ScreenResult:
    """Score one candidate's return series on the shared contract.

    Parameters
    ----------
    returns : array-like
        Per-observation returns. For ``cadence="event"`` these are per-trade; for
        ``cadence="calendar"`` they are per-period.
    dates : array-like
        Observation dates, same length as ``returns``. Used to infer the
        annualisation factor from the data's own cadence.
    label : str
        Candidate identifier; should match a pre-registered trial ledger entry.
    cadence : {"event", "calendar"}
        Signal cadence. Recorded on the result and used to pick the default
        cluster key when none is supplied.
    cluster_keys : array-like, optional
        Cluster each observation belongs to. Defaults to ``dates``, which is the
        right choice for an event book (dozens of names report the same day) and
        harmless for a calendar book (one observation per cluster).
    basis : {"per-trade", "annualised"}
        Basis for the reported Sharpe. ``"per-trade"`` is the unambiguous unit and
        the default. ``"annualised"`` multiplies by ``sqrt(periods_per_year)``
        where the factor comes from :func:`stats.infer_periods_per_year`.
    n_trials : int
        Configurations declared before this was run, feeding the DSR.
    sr_trials_std : float
        Per-period standard deviation of trial Sharpes, feeding the DSR.
    gross : bool
        Whether ``returns`` are gross of costs.
    n_boot : int
        Cluster-bootstrap replicates.
    seed : int
        RNG seed.
    notes : dict, optional
        Free-form provenance recorded alongside the result.

    Returns
    -------
    ScreenResult
        The scorecard, with the Sharpe basis and annualisation factor recorded.

    Raises
    ------
    DegenerateScreenError
        If fewer than two finite returns survive, or the return series has zero
        variance. Both indicate an upstream defect rather than a null result.
    """
    ret = pd.Series(returns).reset_index(drop=True)
    dts = pd.Series(dates).reset_index(drop=True)
    if len(ret) != len(dts):
        raise DegenerateScreenError(
            f"{label}: returns ({len(ret)}) and dates ({len(dts)}) differ in length"
        )

    finite = pd.to_numeric(ret, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(finite)
    if int(mask.sum()) < _MIN_OBS:
        raise DegenerateScreenError(
            f"{label}: only {int(mask.sum())} finite returns of {len(ret)} rows. "
            "This is an empty selection, not a null result: check the gate, join "
            "and date alignment upstream."
        )

    values = finite[mask]
    kept_dates = dts[mask].reset_index(drop=True)
    keys = (
        pd.Series(cluster_keys).reset_index(drop=True)[mask]
        if cluster_keys is not None
        else kept_dates
    )

    sd = float(np.std(values, ddof=1))
    # A constant series does not give sd exactly 0: summing identical floats leaves
    # the mean off by an ULP, so the residual sd lands around 1e-18. Compare against
    # the data's own scale rather than against zero.
    scale_ref = max(abs(float(np.mean(values))), float(np.max(np.abs(values))), 1.0)
    if not np.isfinite(sd) or sd <= _VARIANCE_TOL * scale_ref:
        raise DegenerateScreenError(
            f"{label}: return series has zero or non-finite variance over N={values.size} "
            f"(sd={sd:.3e}). A constant return series is an upstream defect, not a null result."
        )

    ppy = float(infer_periods_per_year(pd.Index(pd.to_datetime(kept_dates))))
    scale = float(np.sqrt(ppy)) if basis == "annualised" else 1.0

    def stat(sample: np.ndarray) -> float:
        return _per_trade_sharpe(sample) * scale

    lo, hi = cluster_bootstrap_ci(values, keys.to_numpy(), stat, n_boot=n_boot, seed=seed)

    series = pd.Series(values)
    return ScreenResult(
        label=label,
        cadence=cadence,
        n=int(values.size),
        n_clusters=int(pd.Series(keys).nunique()),
        mean=float(np.mean(values)),
        std=sd,
        hit_rate=float(np.mean(values > 0.0)),
        sharpe=stat(values),
        sharpe_basis=basis,
        periods_per_year=ppy,
        ci_low=lo,
        ci_high=hi,
        psr=probabilistic_sharpe_ratio(series),
        dsr=deflated_sharpe_ratio(series, n_trials=n_trials, sr_trials_std=sr_trials_std),
        n_trials=int(n_trials),
        gross=bool(gross),
        notes=dict(notes or {}),
    )


# ── gross-first gate ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateOutcome:
    """Verdict of the gross-first gate, with the funnel that produced it."""

    label: str
    passed: bool
    reason: str
    funnel: dict[str, int]

    def report(self) -> str:
        """Printable funnel, so an empty result is never silent."""
        lines = [f"{self.label}: {'PASS' if self.passed else 'FAIL'} - {self.reason}"]
        lines.extend(f"    {stage:<28} {count:>8,}" for stage, count in self.funnel.items())
        return "\n".join(lines)


def gross_gate(
    returns: pd.Series | np.ndarray,
    label: str,
    *,
    funnel: dict[str, int] | None = None,
    min_n: int = 30,
    require_positive_mean: bool = True,
) -> GateOutcome:
    """Ask whether a gross signal exists before any cost model is applied.

    A candidate whose gross mean is negative cannot be rescued by a better
    execution assumption, which is the distinction the cross-market work
    established between "no signal at all" and "signal inside the spread".

    Parameters
    ----------
    returns : array-like
        Gross per-observation returns.
    label : str
        Candidate identifier.
    funnel : dict, optional
        Row counts by pipeline stage, printed with the verdict so an empty
        selection is always attributable.
    min_n : int
        Minimum observations to render any verdict at all.
    require_positive_mean : bool
        Whether a non-positive gross mean fails the gate. Set ``False`` for
        long-short candidates scored on a spread that may legitimately be signed
        either way before the legs are ordered.

    Returns
    -------
    GateOutcome
        Verdict plus the funnel.
    """
    values = _clean(returns)
    stages = dict(funnel or {})
    stages["scoreable returns"] = int(values.size)

    if values.size < min_n:
        return GateOutcome(label, False, f"N={values.size} below minimum {min_n}", stages)
    mean = float(np.mean(values))
    if require_positive_mean and mean <= 0.0:
        return GateOutcome(
            label,
            False,
            f"gross mean {mean:+.6f} is not positive; no cost model can rescue it",
            stages,
        )
    return GateOutcome(label, True, f"gross mean {mean:+.6f} over N={values.size}", stages)


# ── table assembly ───────────────────────────────────────────────────────────


def results_table(results: list[ScreenResult]) -> pd.DataFrame:
    """Assemble scored candidates into one table, most significant first."""
    if not results:
        return pd.DataFrame()
    frame = pd.DataFrame([r.to_row() for r in results])
    return frame.sort_values("dsr", ascending=False).reset_index(drop=True)
