"""
protocol.py
The research protocol as code: pre-registration freeze and verify, date-clustered intervals,
and the participation-matched random null.

Every new study follows one sequence (``docs/PROTOCOL.md``): write the pre-registration,
freeze it with :func:`freeze_prereg` before any outcome exists, call :func:`verify_prereg`
at the top of the scorer, report the primary statistic with :func:`date_clustered_ci`, and
read any selector against :func:`matched_random_null`. The freeze also hashes the scorer
and its inputs; scorers are developed on :func:`blind` outcomes and score blocks through
:func:`staged_scoring`; every prereg states a minimum detectable effect
(:func:`min_detectable_effect`); and a confirmation is read against the LOND online-FDR
alpha (:func:`lond_alpha`) with :func:`date_clustered_pvalue`. The defaults here are the project's
inference rules (5,000 draws, seed 0, 95% interval, clusters on the announcement date), so a
new number is on the same basis as every number already in the record.

The bootstrap itself is ``engine.event_study.cluster_bootstrap_ci``; this module fixes its
arguments rather than reimplementing it.

References
----------
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-based improvements for
inference with clustered errors. Review of Economics and Statistics 90(3), 414-427.
Efron, B. and Tibshirani, R. (1993). An Introduction to the Bootstrap. Chapman and Hall.
Javanmard, A. and Montanari, A. (2018). Online rules for control of false discovery rate and
false discovery exceedance. Annals of Statistics 46(2), 526-554.
Kish, L. (1965). Survey Sampling. Wiley.
Klein, J. R. and Roodman, A. (2005). Blind analysis in nuclear and particle physics. Annual
Review of Nuclear and Particle Science 55, 141-163.
Lo, A. W. (2002). The statistics of Sharpe ratios. Financial Analysts Journal 58(4), 36-52.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

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


REQUIRED_SECTIONS = ("## Mechanism", "## Power")  # every new prereg states both
RUN_LOG_SUFFIX = ".runs.jsonl"  # append-only log beside each record: code changes, unblindings


def _file_fingerprint(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return {"path": p.as_posix(), "size": p.stat().st_size, "sha256": sha256_file(p)}


def _git_head(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def freeze_prereg(
    prereg: str | Path,
    record: str | Path,
    *,
    trial_id: str,
    n_trials_declared: int,
    declared_utc: str,
    scorer: str | Path | None = None,
    inputs: Sequence[str | Path] = (),
    required_sections: Sequence[str] = REQUIRED_SECTIONS,
    **fields: Any,
) -> dict[str, Any]:
    """Record the hash of a pre-registration, its scorer and its inputs before any outcome.

    Refuses to overwrite an existing record: a frozen text is changed only through a dated
    amendment with its own hash, never by re-freezing. Freezing the scorer and the input files
    as well as the text means a change to the code or the data after the freeze is detected by
    :func:`verify_prereg`, not only a change to the words.

    Parameters
    ----------
    scorer : path, optional
        The study's ``study.py``. Its hash is recorded and checked on every run.
    inputs : paths
        Every data file the scorer reads; size and SHA-256 are recorded.
    required_sections : sequence of str
        Headings the text must contain. Defaults to Mechanism and Power, so no trial is frozen
        without a stated mechanism and a minimum detectable effect.

    Returns
    -------
    dict
        The record written to ``record``.

    Raises
    ------
    FileExistsError
        If ``record`` exists.
    ValueError
        If a required section is missing.
    """
    rec_path = Path(record)
    if rec_path.exists():
        raise FileExistsError(f"{rec_path} exists; amend with a new file, never re-freeze")
    text = Path(prereg).read_text(encoding="utf-8")
    missing = [h for h in required_sections if h not in text]
    if missing:
        raise ValueError(f"{prereg} lacks required sections {missing}; see research/_template")
    body: dict[str, Any] = {
        "trial_id": trial_id,
        "declared_utc": declared_utc,
        "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prereg_file": Path(prereg).as_posix(),
        "prereg_sha256": sha256_file(prereg),
        "n_trials_declared": int(n_trials_declared),
        "git_head": _git_head(Path(prereg).resolve().parent),
    }
    if scorer is not None:
        body["scorer_file"] = Path(scorer).as_posix()
        body["scorer_sha256"] = sha256_file(scorer)
    if inputs:
        body["inputs"] = [_file_fingerprint(f) for f in inputs]
    body.update(fields)
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return body


def _run_log(record: str | Path) -> Path:
    r = Path(record)
    return r.with_name(r.stem + RUN_LOG_SUFFIX)


def _read_runs(record: str | Path) -> list[dict[str, Any]]:
    log = _run_log(record)
    if not log.exists():
        return []
    lines = log.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _append_run(record: str | Path, event: dict[str, Any]) -> None:
    stamped = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    with _run_log(record).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stamped) + "\n")


def verify_prereg(
    prereg: str | Path,
    record: str | Path,
    *,
    unblind: bool = False,
    rerun_reason: str | None = None,
) -> str:
    """Check a pre-registration, its scorer and inputs against the freeze; call it first.

    The scorer may change before outcomes are seen (a crash fix while developing on blinded
    data); each such change is logged beside the record. Once an unblinded run is logged, any
    change to the scorer raises, and a second unblinded run raises unless ``rerun_reason`` is
    given, which is logged with it. Records frozen before scorer hashing existed are checked on
    the text only.

    Parameters
    ----------
    unblind : bool
        True for the run that computes real outcomes. Logged.
    rerun_reason : str, optional
        Required for any unblinded run after the first, for example a crash part-way through.

    Returns
    -------
    str
        The verified SHA-256 of the text.

    Raises
    ------
    ValueError
        If the text or an input changed, if the scorer changed after an unblinded run, or if a
        second unblinded run has no reason.
    """
    rec = json.loads(Path(record).read_text(encoding="utf-8"))
    got = sha256_file(prereg)
    if got != rec["prereg_sha256"]:
        raise ValueError(
            f"{prereg} does not match its frozen hash in {record} "
            f"({got[:12]} vs {str(rec['prereg_sha256'])[:12]}); the text changed after freezing"
        )
    for fp in rec.get("inputs", []):
        now = sha256_file(fp["path"]) if Path(fp["path"]).exists() else None
        if now != fp["sha256"]:
            raise ValueError(f"input {fp['path']} changed or is missing since the freeze")
    runs = _read_runs(record)
    unblinded = [e for e in runs if e.get("event") == "unblinded_run"]
    if "scorer_file" in rec:
        known = [rec["scorer_sha256"]] + [
            e["scorer_sha256"] for e in runs if e.get("event") == "code_change_pre_unblind"
        ]
        cur = sha256_file(rec["scorer_file"])
        if cur != known[-1]:
            if unblinded:
                raise ValueError(
                    f"{rec['scorer_file']} changed after an unblinded run; a change now needs a "
                    "dated amendment and a new trial"
                )
            _append_run(record, {"event": "code_change_pre_unblind", "scorer_sha256": cur})
            warnings.warn(f"scorer changed before unblinding; logged ({cur[:12]})", stacklevel=2)
    if unblind:
        if unblinded and not rerun_reason:
            raise ValueError(
                f"{record} already has an unblinded run; pass rerun_reason to log why a second "
                "one is needed"
            )
        scorer_sha = sha256_file(rec["scorer_file"]) if "scorer_file" in rec else None
        _append_run(
            record,
            {"event": "unblinded_run", "scorer_sha256": scorer_sha, "rerun_reason": rerun_reason},
        )
    return got


# ── blinding ─────────────────────────────────────────────────────────────────


def blind(
    values: Sequence[float] | np.ndarray | pd.Series,
    dates: Sequence[Any] | np.ndarray | pd.Series,
    *,
    seed: int = SEED,
) -> np.ndarray:
    """Permute outcomes across events within each date, for developing a scorer blind.

    Within-date permutation keeps the outcome distribution and each date's common shock, so
    the scorer meets realistic data, while breaking any link between an event's features and
    its outcome. Develop and debug on this, then unblind once (Klein and Roodman 2005).
    """
    v = np.asarray(values, dtype=float).copy()
    keys = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    rng = np.random.default_rng(seed)
    for k in np.unique(keys):
        idx = np.where(keys == k)[0]
        v[idx] = v[rng.permutation(idx)]
    return v


# ── staged scoring ───────────────────────────────────────────────────────────


def staged_scoring(
    blocks: Sequence[str],
    score: Callable[[str], dict[str, Any]],
    passes: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Score blocks in order and stop at the first failure.

    Later blocks of a failed trial are never computed, so their numbers cannot leak into the
    next idea or be read as a rescue. Returns each scored block's result, the block where it
    stopped (``None`` if all passed) and an overall ``passed`` flag.
    """
    out: dict[str, Any] = {"blocks": {}, "stopped_at": None, "passed": False}
    for b in blocks:
        res = score(b)
        ok = bool(passes(res))
        out["blocks"][b] = {**res, "passes": ok}
        if not ok:
            out["stopped_at"] = b
            return out
    out["passed"] = True
    return out


# ── power ────────────────────────────────────────────────────────────────────


def min_detectable_effect(
    n_treated: int,
    n_control: int,
    sd: float,
    *,
    design_effect: float = 1.0,
    alpha: float = 0.05,
    power: float = 0.80,
) -> float:
    """Smallest difference in means a two-sided test detects with the given power.

    ``MDE = (z_{1-alpha/2} + z_power) * sd * sqrt((1/n_t + 1/n_c) * design_effect)``. The
    design effect inflates the variance for clustering; with mean cluster size ``m`` and
    intra-date correlation ``rho`` it is ``1 + (m - 1) rho`` (Kish 1965). Take ``sd`` from data
    viewed before, never from the declared blocks.
    """
    if n_treated < 1 or n_control < 1:
        raise ValueError("both groups need at least one event")
    z = float(norm.ppf(1 - alpha / 2) + norm.ppf(power))
    return z * sd * float(np.sqrt((1 / n_treated + 1 / n_control) * design_effect))


def min_detectable_rate_ratio(
    base_rate: float,
    n_treated: int,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> float:
    """Smallest treated-over-base rate ratio detectable for a binary outcome (normal approx).

    Solves ``p1 - p0 = z * sqrt(p0 (1 - p0) / n_treated)`` with the control rate taken as
    known, which flatters power, so a trial failing this check is certainly underpowered.
    """
    if not 0 < base_rate < 1 or n_treated < 1:
        raise ValueError("base_rate in (0, 1) and n_treated >= 1 required")
    z = float(norm.ppf(1 - alpha / 2) + norm.ppf(power))
    p1 = base_rate + z * float(np.sqrt(base_rate * (1 - base_rate) / n_treated))
    return p1 / base_rate


# ── significance ─────────────────────────────────────────────────────────────


def date_clustered_pvalue(
    values: Sequence[float] | np.ndarray | pd.Series,
    dates: Sequence[Any] | np.ndarray | pd.Series,
    stat: Callable[[np.ndarray], float] = per_trade_sharpe,
    *,
    null: float = 0.0,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> float:
    """Two-sided percentile-bootstrap p-value for ``stat`` against ``null``, resampling dates.

    Twice the smaller tail share of the date-clustered bootstrap distribution on either side of
    ``null``: the inversion of the interval :func:`date_clustered_ci` reports, with the same
    draw sequence and seed. Floored at ``1 / n_boot``.
    """
    v = np.asarray(values, dtype=float)
    keys = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    ok = np.isfinite(v)
    v, keys = v[ok], keys[ok]
    if v.size == 0:
        raise ValueError("no finite values to score")
    uniq = np.unique(keys)
    idx_by = {k: np.where(keys == k)[0] for k in uniq}
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        drawn = rng.choice(uniq, size=len(uniq), replace=True)
        boot[b] = stat(v[np.concatenate([idx_by[k] for k in drawn])])
    boot = boot[np.isfinite(boot)]
    p = 2 * min(float((boot <= null).mean()), float((boot >= null).mean()))
    return float(min(1.0, max(p, 1.0 / n_boot)))


def lond_alpha(trial_index: int, discoveries_before: int, *, target: float = 0.05) -> float:
    """Alpha for the next trial under LOND online false-discovery-rate control.

    ``alpha_i = target * gamma_i * (D_{i-1} + 1)`` with ``gamma_i = 6 / (pi^2 i^2)``, so the
    ``gamma`` sum to one and, with no discoveries, the alphas sum to at most ``target``
    (Javanmard and Montanari 2018). ``trial_index`` counts from 1 within the ledger.
    """
    if trial_index < 1 or discoveries_before < 0:
        raise ValueError("trial_index >= 1 and discoveries_before >= 0 required")
    gamma = 6.0 / (np.pi**2 * trial_index**2)
    return float(target * gamma * (discoveries_before + 1))


# ── block ledger ─────────────────────────────────────────────────────────────

BLOCK_LEDGER_COLUMNS = (
    "utc",
    "panel",
    "period",
    "outcome_family",
    "feature_family",
    "viewed_by",
    "kind",
)
"""Columns of ``research/ledger/blocks.csv``: one row each time outcomes on a block are viewed.

``kind`` is ``trial`` or ``descriptive``. A block is clean for a hypothesis when no row shares
its panel, period, outcome family and feature family; ``*`` in a row matches every family.
"""


def log_block_view(
    ledger: str | Path,
    *,
    panel: str,
    period: str,
    outcome_family: str,
    feature_family: str,
    viewed_by: str,
    kind: str = "trial",
) -> None:
    """Append one viewing of a block to the ledger, creating the file with a header."""
    if kind not in ("trial", "descriptive"):
        raise ValueError("kind is 'trial' or 'descriptive'")
    path = Path(ledger)
    row = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": panel,
        "period": period,
        "outcome_family": outcome_family,
        "feature_family": feature_family,
        "viewed_by": viewed_by,
        "kind": kind,
    }
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row], columns=list(BLOCK_LEDGER_COLUMNS)).to_csv(
        path, mode="a", header=new, index=False
    )


def block_is_clean(
    ledger: str | Path, *, panel: str, period: str, outcome_family: str, feature_family: str
) -> tuple[bool, pd.DataFrame]:
    """Whether a block is unviewed for this outcome and feature family; returns the clashes."""
    path = Path(ledger)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; the block ledger must exist before any trial")
    led = pd.read_csv(path, dtype=str)

    def _match(col: str, val: str) -> pd.Series:
        return (led[col] == val) | (led[col] == "*")

    hit = (
        (led["panel"] == panel)
        & (led["period"] == period)
        & _match("outcome_family", outcome_family)
        & _match("feature_family", feature_family)
    )
    return (not bool(hit.any())), led[hit]
