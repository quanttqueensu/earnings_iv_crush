"""
l2lib.py
Shared helpers for the L2 execution and cost lane: the recorded H_corr inputs, the hedge
sequence they imply, paired date-clustered intervals and block bookkeeping.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    Interval,
    date_clustered_ci,
    log_block_view,
)

HERE = Path(__file__).resolve().parent
BASE_CORR = HERE.parent / "L1-corrections" / "base_corrected.parquet"
PATHS = HERE / "_cache" / "paths.pkl"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
BLOCK_LEDGER = ROOT / "research" / "ledger" / "blocks.csv"
BLOCKS = ("2013-18", "2019-24", "2025-26")


# ── data ─────────────────────────────────────────────────────────────────────


def load_base() -> pd.DataFrame:
    """``base_corrected.parquet`` with typed dates and the reaction date as cluster key."""
    d = pd.read_parquet(BASE_CORR)
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c])
    return d


def load_paths() -> dict[tuple[str, pd.Timestamp], dict]:
    """Recorded ``H_corr`` inputs keyed by (ticker, entry_date); ``kw`` is None if unhedged."""
    with open(PATHS, "rb") as fh:
        res = pickle.load(fh)
    return {
        (r["ticker"], pd.Timestamp(r["entry_date"])): r for r in res if r["h_status"] == "ok"
    }


# ── hedge sequence ───────────────────────────────────────────────────────────


def hedge_sequence(kw: dict, spots: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Shares held at each close and shares traded there, exactly as ``hedged_short_straddle``.

    Parameters
    ----------
    kw : dict
        Recorded inputs of one hedged valuation.
    spots : array, optional
        Spot at which the hedge ratio is computed at each close (default: the close itself).

    Returns
    -------
    h, traded : arrays of length n and n + 1
        ``traded[i]`` for i < n is the rebalance at hedging close i (net of any share delivered
        by an early assignment, as the function charges it); ``traded[n]`` is the residual at
        the settlement close under netting.
    """
    closes = np.asarray(kw["closes"], dtype=float)
    s = closes if spots is None else np.asarray(spots, dtype=float)
    n = closes.size
    k, taus, sig = float(kw["strike"]), kw["taus"], kw["sigmas"]
    ca = kw.get("call_assigned_at")
    pa = kw.get("put_assigned_at")
    if not kw["cfg"].net_assignment:
        raise ValueError("hedge_sequence assumes the netted settlement")
    call_live, put_live = True, True
    h = np.zeros(n)
    traded = np.zeros(n + 1)
    h_prev = 0.0
    for i in range(n):
        delivered = 0.0
        if call_live and ca == i:
            call_live, delivered = False, delivered - 1.0
        if put_live and pa == i:
            put_live, delivered = False, delivered + 1.0
        h[i] = hh._leg_delta(s[i], k, float(taus[i]), float(sig[i]), call_live, put_live)
        traded[i] = abs(h[i] - (h_prev + delivered))
        h_prev = h[i]
    settle = float(kw["settle_close"])
    if call_live and put_live:
        sgn = float(np.sign(settle - k))
    else:
        sgn = float(call_live and settle > k) - float(put_live and settle < k)
    traded[n] = abs(h_prev - sgn)
    return h, traded


# ── intervals ────────────────────────────────────────────────────────────────


def mean_ci(values: np.ndarray | pd.Series, dates: np.ndarray | pd.Series) -> Interval:
    """Mean with its date-clustered 95% interval; raises on an empty input."""
    return date_clustered_ci(np.asarray(values, float), dates, lambda a: float(np.mean(a)))


def ratio_ci(num: np.ndarray, den: np.ndarray, dates: np.ndarray | pd.Series) -> Interval:
    """sum(num) / sum(den) with a date-clustered interval (resampled through an index)."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    idx = np.arange(num.size, dtype=float)

    def stat(ii: np.ndarray) -> float:
        j = ii.astype(int)
        return float(num[j].sum() / den[j].sum())

    return date_clustered_ci(idx, dates, stat)


def var_ratio_ci(new: np.ndarray, old: np.ndarray, dates: np.ndarray | pd.Series) -> Interval:
    """var(new) / var(old) on paired events, date-clustered."""
    new, old = np.asarray(new, float), np.asarray(old, float)
    idx = np.arange(new.size, dtype=float)

    def stat(ii: np.ndarray) -> float:
        j = ii.astype(int)
        return float(np.var(new[j]) / np.var(old[j]))

    return date_clustered_ci(idx, dates, stat)


def iv_dict(iv: Interval, scale: float = 100.0) -> dict[str, Any]:
    """Interval as a json-ready dict, scaled (default fraction to %)."""
    return {
        "point": iv.point * scale,
        "low": iv.low * scale,
        "high": iv.high * scale,
        "n": iv.n,
        "clusters": iv.clusters,
    }


def fmt(iv: Interval, scale: float = 100.0, nd: int = 3) -> str:
    return (
        f"{iv.point * scale:+.{nd}f} [{iv.low * scale:+.{nd}f}, {iv.high * scale:+.{nd}f}] "
        f"(N={iv.n}, {iv.clusters} dates)"
    )


# ── bookkeeping ──────────────────────────────────────────────────────────────


def record_view(period: str, feature_family: str, viewed_by: str, kind: str = "trial") -> None:
    """Append one block view to the lane's ``blocks_viewed.csv``."""
    log_block_view(
        BLOCKS_VIEWED,
        panel="base_corrected",
        period=period,
        outcome_family="hedged_hold",
        feature_family=feature_family,
        viewed_by=viewed_by,
        kind=kind,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=float))
    tmp.replace(path)


def by_block(d: pd.DataFrame, fn: Callable[[pd.DataFrame], dict], blocks: tuple = BLOCKS) -> dict:
    return {b: fn(d[d["block"] == b]) for b in blocks if (d["block"] == b).any()}


# ── freeze notes ─────────────────────────────────────────────────────────────

SELF_HASH_PREFIX = "Self sha256 (sha256 of every byte above this line, LF endings): "


def write_freeze(path: Path, body: str, files: list[Path]) -> str:
    """Write a freeze note listing the sha256 of ``files``, ending with its own hash.

    The self hash covers every byte before its line, so the note can be checked with
    ``verify_freeze``. Refuses to overwrite an existing note.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; a freeze note is written once")
    lines = [body.rstrip("\n"), "", "Frozen files (sha256):"]
    lines += [f"- {Path(f).name}: {sha256(Path(f))}" for f in files]
    text = "\n".join(lines) + "\n\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.write_bytes((text + SELF_HASH_PREFIX + digest + "\n").encode("utf-8"))
    return digest


def verify_freeze(path: Path) -> bool:
    """Whether a freeze note's self hash and every listed file hash still hold."""
    raw = Path(path).read_bytes().decode("utf-8")
    head, _, tail = raw.rpartition(SELF_HASH_PREFIX)
    if hashlib.sha256(head.encode("utf-8")).hexdigest() != tail.strip():
        return False
    for line in head.splitlines():
        if line.startswith("- ") and ": " in line:
            name, h = line[2:].split(": ", 1)
            if sha256(Path(path).parent / name) != h.strip():
                return False
    return True
