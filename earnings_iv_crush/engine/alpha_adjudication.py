"""Canonical measurements for separating alpha from risk selection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from .event_study import cluster_bootstrap_ci


def package_relative_spread(widths: Iterable[float], mids: Iterable[float]) -> float:
    """Return total quoted package width divided by total package mid.

    A straddle is a two-leg package. Averaging each leg's relative spread gives
    a near-worthless post-gap leg the same weight as the intrinsic-heavy leg.
    """
    pairs = [
        (float(width), float(mid))
        for width, mid in zip(widths, mids, strict=True)
        if np.isfinite(width) and np.isfinite(mid) and width >= 0 and mid > 0
    ]
    if not pairs:
        return float("nan")
    total_width = sum(width for width, _ in pairs)
    total_mid = sum(mid for _, mid in pairs)
    return float(total_width / total_mid) if total_mid > 0 else float("nan")


def add_return_measures(frame: pd.DataFrame) -> pd.DataFrame:
    """Add explicit premium-return columns without changing the input frame.

    Premium returns require canonical ``entry_credit``, ``exit_value`` and,
    for net returns, ``pnl``. They are not reconstructed from margin returns.
    """
    out = frame.copy()
    if {"entry_credit", "exit_value"}.issubset(out.columns):
        credit = pd.to_numeric(out["entry_credit"], errors="coerce")
        gross = credit - pd.to_numeric(out["exit_value"], errors="coerce")
        valid_credit = credit.where(credit > 0)
        out["gross_return_on_premium"] = gross / valid_credit
        if "pnl" in out.columns:
            out["net_return_on_premium"] = pd.to_numeric(out["pnl"], errors="coerce") / valid_credit
    else:
        if "gross_return_on_premium" not in out.columns:
            out["gross_return_on_premium"] = np.nan
        if "net_return_on_premium" not in out.columns:
            out["net_return_on_premium"] = np.nan
    if "return_on_margin" in out.columns:
        out["return_on_margin"] = pd.to_numeric(out["return_on_margin"], errors="coerce")
    return out


def infer_merge_keys(events: pd.DataFrame, ledger: pd.DataFrame) -> list[str]:
    """Find a stable event identity shared by an event frame and a ledger."""
    for keys in (["event_id"], ["ticker", "entry_date"], ["ticker", "entry_key"]):
        if all(key in events.columns and key in ledger.columns for key in keys):
            return list(keys)
    raise ValueError("events and ledger need one of: event_id; ticker+entry_date; ticker+entry_key")


def stable_event_ids(frame: pd.DataFrame) -> pd.Series:
    """Create deterministic IDs from event identity fields."""
    fields = [
        col
        for col in ("ticker", "announce_date", "entry_date", "entry_key", "event_date")
        if col in frame.columns
    ]
    if not fields:
        return pd.Series([f"row-{i}" for i in range(len(frame))], index=frame.index)

    def make_id(row: pd.Series) -> str:
        raw = "|".join("" if pd.isna(row[col]) else str(row[col]) for col in fields)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    return frame.apply(make_id, axis=1)


def build_canonical_event_ledger(
    events: pd.DataFrame,
    ledger: pd.DataFrame,
    keys: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Join event features to realized trades and add canonical returns."""
    ev = events.copy()
    led = ledger.copy()
    keys = list(keys) if keys is not None else infer_merge_keys(ev, led)
    for key in keys:
        if key.endswith("date") or key in {"entry_date", "announce_date", "event_date"}:
            ev[key] = pd.to_datetime(ev[key], errors="coerce").dt.strftime("%Y-%m-%d")
            led[key] = pd.to_datetime(led[key], errors="coerce").dt.strftime("%Y-%m-%d")
    if ev.duplicated(keys).any():
        raise ValueError(f"events are not unique on merge keys: {keys}")
    if "event_id" not in ev.columns:
        ev["event_id"] = stable_event_ids(ev)
    feature_cols = [col for col in ev.columns if col not in led.columns or col in keys]
    join_cols = list(dict.fromkeys(keys + ["event_id"] + feature_cols))
    out = led.merge(
        ev[join_cols], on=keys, how="left", validate="many_to_one", suffixes=("", "_event")
    )
    if "event_id_event" in out.columns:
        out["event_id"] = out.pop("event_id_event")
    elif "event_id" not in out.columns:
        out["event_id"] = stable_event_ids(out)
    return add_return_measures(out)


def causal_expanding_gate(
    signal: pd.Series,
    dates: pd.Series,
    quantile: float = 0.80,
    min_prior: int = 25,
) -> pd.Series:
    """Apply a strictly-earlier expanding cross-sectional percentile gate."""
    if not 0 < quantile < 1:
        raise ValueError("quantile must be between 0 and 1")
    if min_prior < 1:
        raise ValueError("min_prior must be positive")
    values = pd.to_numeric(signal, errors="coerce")
    day = pd.to_datetime(dates, errors="coerce")
    result = pd.Series(False, index=signal.index, dtype=bool)
    valid = values.notna() & day.notna()
    for idx in signal.index[valid.to_numpy()]:
        prior = values[valid & (day < day.loc[idx])]
        if len(prior) >= min_prior:
            result.loc[idx] = bool(values.loc[idx] >= prior.quantile(quantile))
    return result


def temporal_quantile_rule(
    signal: pd.Series,
    dates: pd.Series,
    fit_end: str | pd.Timestamp,
    quantile: float = 0.75,
    lower_is_true: bool = True,
) -> tuple[pd.Series, float]:
    """Fit one quantile on the training window and apply it to later dates.

    This is the fixed interface for the conditional exit experiment: the
    threshold is estimated from dates on or before ``fit_end`` and the boolean
    rule is only true on dates strictly after it. No test observation can alter
    the threshold.
    """
    if not 0 < quantile < 1:
        raise ValueError("quantile must be between 0 and 1")
    values = pd.to_numeric(signal, errors="coerce")
    day = pd.to_datetime(dates, errors="coerce")
    cutoff = pd.Timestamp(fit_end)
    train = values[(day <= cutoff) & values.notna()]
    if train.empty:
        raise ValueError("fit window contains no finite signal observations")
    threshold = float(train.quantile(quantile))
    later = day > cutoff
    if lower_is_true:
        rule = later & values.notna() & (values <= threshold)
    else:
        rule = later & values.notna() & (values >= threshold)
    return rule.astype(bool), threshold


def book_metrics(
    frame: pd.DataFrame,
    outcome_col: str,
    date_col: str = "announce_date",
    cluster_col: str = "announce_date",
    n_boot: int = 2000,
) -> dict[str, float | int | str]:
    """Return a denominator-specific scorecard with clustered Sharpe CI."""
    for col in (outcome_col, date_col, cluster_col):
        if col not in frame.columns:
            raise ValueError(f"missing column: {col}")
    # date_col and cluster_col are equal by default; selecting the list verbatim
    # would duplicate that column and turn later lookups into DataFrames.
    data = frame[list(dict.fromkeys([outcome_col, date_col, cluster_col]))].copy()
    data[outcome_col] = pd.to_numeric(data[outcome_col], errors="coerce")
    data = data.dropna(subset=list(dict.fromkeys([outcome_col, date_col, cluster_col])))
    values = data[outcome_col].to_numpy(dtype=float)
    if len(values) == 0:
        return {"outcome": outcome_col, "n": 0}
    sd = float(np.std(values, ddof=1)) if len(values) > 1 else float("nan")
    sr = float(np.mean(values) / sd) if sd > 0 else float("nan")
    dates = pd.to_datetime(data[date_col])
    ppy = float(len(data) * 365.25 / max((dates.max() - dates.min()).days, 1))

    def annualised_sharpe(x: np.ndarray) -> float:
        x_sd = np.std(x, ddof=1)
        return float(np.mean(x) / x_sd * np.sqrt(ppy)) if x_sd > 0 else 0.0

    lo, hi = cluster_bootstrap_ci(
        values,
        data[cluster_col].astype(str).to_numpy(),
        annualised_sharpe,
        n_boot=n_boot,
        seed=0,
    )
    return {
        "outcome": outcome_col,
        "n": int(len(values)),
        "mean": float(np.mean(values)),
        "hit_rate": float(np.mean(values > 0)),
        "per_trade_sharpe": sr,
        "annualised_sharpe": float(sr * np.sqrt(ppy)) if np.isfinite(sr) else float("nan"),
        "periods_per_year": ppy,
        "clustered_ci_low": lo,
        "clustered_ci_high": hi,
    }


def permutation_gate_test(
    outcome: pd.Series,
    gate: pd.Series,
    n_permutations: int = 5000,
    seed: int = 0,
) -> dict[str, float | int]:
    """Test whether a fixed gate lifts mean outcome over its complement."""
    if n_permutations < 1:
        raise ValueError("n_permutations must be positive")
    y = pd.to_numeric(outcome, errors="coerce")
    g = pd.Series(gate, index=outcome.index, dtype=bool)
    valid = y.notna()
    yv = y[valid].to_numpy(dtype=float)
    gv = g[valid].to_numpy(dtype=bool)
    n_gate = int(gv.sum())
    if n_gate == 0 or n_gate == len(gv):
        return {
            "n": int(len(yv)),
            "n_gate": n_gate,
            "observed_lift": float("nan"),
            "p_value": float("nan"),
        }
    observed = float(yv[gv].mean() - yv[~gv].mean())
    rng = np.random.default_rng(seed)
    simulated = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        shuffled = np.zeros(len(gv), dtype=bool)
        shuffled[rng.choice(len(gv), size=n_gate, replace=False)] = True
        simulated[i] = yv[shuffled].mean() - yv[~shuffled].mean()
    return {
        "n": int(len(yv)),
        "n_gate": n_gate,
        "observed_lift": observed,
        "p_value": (1.0 + float(np.sum(simulated >= observed))) / (n_permutations + 1.0),
        "null_mean": float(simulated.mean()),
        "null_sd": float(simulated.std(ddof=1)),
        "n_permutations": int(n_permutations),
    }


def file_sha256(path: str | Path) -> str:
    """Return a content hash suitable for a research manifest."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: str | Path, manifest: dict) -> None:
    """Write stable, human-readable JSON metadata for a result run."""
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
