"""
reverse_alpha_lib.py
Shared scoring, inference and bookkeeping for the reverse-engineering programme.

The programme asks one question repeatedly: what is the q=0.80 term gate actually
selecting, and is there a continuous economic variable underneath it? Answering that
honestly needs the same scorecard applied to dozens of slices, and a ledger that keeps
every slice including the ones that failed. Both live here so no phase can quietly invent
its own definition of a Sharpe, an interval or a cost.

Commitments
-----------
* **One return basis.** Return on Reg-T margin, per trade, never annualised by a trade
  count. The project's canonical failure was a ``sqrt(252)`` factor on a book that trades
  about thirty times a year; nothing here produces an annualised figure at all.
* **Dates are the cluster.** Forty names reporting into the same tape are not forty
  independent draws. Every interval resamples whole announcement dates.
* **Costs are named, never assumed.** ``frozen`` is the specification that produced the
  settled verdict; ``measured`` is the fills study's attainable unconditional book. Both
  are reported wherever costs could change a conclusion.
* **Failures are kept.** ``ledger_append`` never overwrites, so a hypothesis that died
  stays in the record with the reason.

References
----------
Bailey, D. H. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of
Portfolio Management*, 40(5), 94-107.
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-Based Improvements for
Inference with Clustered Errors. *Review of Economics and Statistics*, 90(3), 414-427.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("outputs/research/reverse_alpha")
LEDGER = OUT / "reverse_search_ledger.csv"

RET = "return_on_margin"
DATE = "announce_date"

N_BOOT = 5000
SEED = 0

#: Measured attainable execution from the 34,672-print fills study, as a fraction of the
#: option mid paid per side. Entry and exit differ because a short straddle is closed by
#: buying back an instrument whose quoted width has widened post-event.
MEASURED_ENTRY_HALF = 0.012714
MEASURED_EXIT_HALF = 0.030182

#: Recorded configurations searched on this book before the reverse-engineering programme
#: began. The DSR is deflated against this plus whatever a phase adds.
TRIALS_PRIOR = 1476

#: Dispersion of trial Sharpes, both recorded readings. The plateau figure is the spread
#: across neighbouring threshold cells; the arms figure is the spread across genuinely
#: different arms crossed with cost assumptions, and is the conservative one.
SR_TRIALS_STD = {"plateau": 0.019345, "arms x cost": 0.127475}


# ── scorecard ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Score:
    """Per-trade scorecard for one slice of the book, on one cost basis."""

    label: str
    n: int
    n_dates: int
    n_names: int
    mean: float
    median: float
    std: float
    sharpe: float
    hit: float
    ci_lo: float
    ci_hi: float
    excludes_zero: bool
    max_dd: float
    worst: float
    top5_share: float
    top_name_share: float
    trades_per_year: float


def _clean(df: pd.DataFrame, ret: str = RET) -> pd.DataFrame:
    d = df.copy()
    d[ret] = pd.to_numeric(d[ret], errors="coerce")
    return d[np.isfinite(d[ret])]


def date_cluster_ci(
    values: np.ndarray,
    dates: np.ndarray,
    stat=lambda v: float(np.mean(v) / np.std(v, ddof=1)) if np.std(v, ddof=1) > 0 else np.nan,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> tuple[float, float]:
    """Percentile interval resampling whole announcement dates with replacement."""
    order = np.argsort(dates)
    v, d = values[order], dates[order]
    _, start = np.unique(d, return_index=True)
    groups = np.split(v, start[1:])
    if len(groups) < 3:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = np.arange(len(groups))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(idx, len(idx), replace=True)
        sample = np.concatenate([groups[i] for i in pick])
        boots[b] = stat(sample)
    boots = boots[np.isfinite(boots)]
    if boots.size < 2:
        return float("nan"), float("nan")
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def score(df: pd.DataFrame, label: str, ret: str = RET, n_boot: int = N_BOOT) -> Score:
    """Full scorecard for one slice. Raises on an empty slice rather than returning NaN.

    An empty selection is an upstream defect, not a null result; letting it through as a
    row of NaNs is how a broken join gets read as "no effect".
    """
    d = _clean(df, ret)
    if len(d) < 3:
        raise ValueError(
            f"{label}: {len(d)} scoreable trades, not a null result but an empty slice"
        )
    v = d[ret].to_numpy(dtype=float)
    dates = pd.to_datetime(d[DATE]).to_numpy()
    sd = float(np.std(v, ddof=1))
    sharpe = float(np.mean(v) / sd) if sd > 0 else float("nan")
    lo, hi = date_cluster_ci(v, dates, n_boot=n_boot)

    equity = np.cumsum(v)
    dd = float(np.min(equity - np.maximum.accumulate(equity)))
    total = float(np.sum(v))
    top5 = float(np.sum(np.sort(v)[-5:]))
    by_name = d.groupby("ticker")[ret].sum()
    top_name = float(by_name.max()) if len(by_name) else float("nan")
    span = pd.to_datetime(d[DATE])
    years = max((span.max() - span.min()).days / 365.25, 1e-9)

    return Score(
        label=label,
        n=len(d),
        n_dates=int(pd.to_datetime(d[DATE]).dt.normalize().nunique()),
        n_names=int(d["ticker"].nunique()),
        mean=float(np.mean(v)),
        median=float(np.median(v)),
        std=sd,
        sharpe=sharpe,
        hit=float(np.mean(v > 0)),
        ci_lo=lo,
        ci_hi=hi,
        excludes_zero=bool(np.isfinite(lo) and np.isfinite(hi) and not (lo <= 0.0 <= hi)),
        max_dd=dd,
        worst=float(np.min(v)),
        top5_share=float(top5 / total) if total != 0 else float("nan"),
        top_name_share=float(top_name / total) if total != 0 else float("nan"),
        trades_per_year=float(len(d) / years),
    )


def score_row(df: pd.DataFrame, label: str, **extra) -> dict:
    """Scorecard as a flat record, with any caller-supplied identifying fields prepended."""
    s = asdict(score(df, label))
    return {**extra, **s}


# ── costs ────────────────────────────────────────────────────────────────────


def rescore_measured(df: pd.DataFrame) -> pd.Series:
    """Return on margin recomputed on the measured attainable execution.

    The panel carries the frozen cost basis. This charges the fills study's measured
    unconditional half-crosses instead, keeping commissions from the frozen stack. The
    trade-conditional arm is deliberately absent: it is 2.35x tighter than the fixed-time
    book because trades cluster where the book is tight, and a 15:59 strategy cannot
    select into those moments.
    """
    credit = pd.to_numeric(df["credit_mkt"], errors="coerce")
    exit_ = pd.to_numeric(df["exit_mkt"], errors="coerce")
    contracts = pd.to_numeric(df["contracts"], errors="coerce")
    margin = pd.to_numeric(df["margin"], errors="coerce")
    gross = pd.to_numeric(df["gross_pnl"], errors="coerce")

    spread = (MEASURED_ENTRY_HALF * credit + MEASURED_EXIT_HALF * exit_) * 100 * contracts
    commission = 0.65 * 4 * contracts  # two legs, opened and closed
    return (gross - spread - commission) / margin


# ── selection ────────────────────────────────────────────────────────────────


def gate(panel: pd.DataFrame, pctl: float, col: str = "term_rank") -> pd.DataFrame:
    """The frozen gate at an arbitrary percentile: keep events at or above the cut."""
    r = pd.to_numeric(panel[col], errors="coerce")
    return panel[np.isfinite(r) & (r >= pctl)]


def jaccard(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Overlap of two selections, as a fraction of their union."""
    ka = set(zip(a["ticker"], a["entry_date"], strict=True))
    kb = set(zip(b["ticker"], b["entry_date"], strict=True))
    union = ka | kb
    return float(len(ka & kb) / len(union)) if union else float("nan")


def yearly(df: pd.DataFrame, ret: str = RET) -> pd.DataFrame:
    """Mean return and count by announcement year."""
    d = _clean(df, ret)
    y = pd.to_datetime(d[DATE]).dt.year
    g = d.groupby(y)[ret]
    return pd.DataFrame(
        {"year": g.mean().index, "mean": g.mean().to_numpy(), "n": g.size().to_numpy()}
    )


# ── monotonicity ─────────────────────────────────────────────────────────────


def quantile_sort(
    df: pd.DataFrame, signal: str, k: int, ret: str = RET, by_period: str | None = "Q"
) -> pd.DataFrame:
    """Sort into ``k`` bins on ``signal`` and score each, optionally within calendar period.

    Binning within announcement quarter removes the drift in the signal's own level over
    time, so a bin is a cross-sectional statement rather than a slow regime indicator.
    """
    d = _clean(df, ret).dropna(subset=[signal])
    if d.empty:
        return pd.DataFrame()
    if by_period:
        period = pd.to_datetime(d[DATE]).dt.to_period(by_period)
        d = d.assign(
            bin=d.groupby(period)[signal].transform(
                lambda s: (
                    pd.qcut(s, k, labels=False, duplicates="drop")
                    if s.notna().sum() >= 4 * k
                    else np.nan
                )
            )
        )
    else:
        d = d.assign(bin=pd.qcut(d[signal], k, labels=False, duplicates="drop"))
    d = d.dropna(subset=["bin"])
    rows = []
    for b, g in d.groupby("bin"):
        if len(g) < 3:
            continue
        rows.append(
            {
                "bin": int(b),
                **{
                    key: val
                    for key, val in asdict(score(g, f"{signal}_bin{int(b)}")).items()
                    if key != "label"
                },
                "signal_mean": float(pd.to_numeric(g[signal], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows)


def spearman(df: pd.DataFrame, signal: str, ret: str = RET) -> tuple[float, int]:
    """Rank correlation between a signal and the per-trade return."""
    d = _clean(df, ret).dropna(subset=[signal])
    if len(d) < 10:
        return float("nan"), len(d)
    x = pd.to_numeric(d[signal], errors="coerce")
    return float(x.corr(d[ret], method="spearman")), len(d)


def monotone_frac(tbl: pd.DataFrame, col: str = "mean") -> float:
    """Fraction of adjacent bin steps that move upward. 1.0 is strictly increasing."""
    if tbl.empty or len(tbl) < 2:
        return float("nan")
    m = tbl.sort_values("bin")[col].to_numpy(dtype=float)
    return float(np.mean(np.diff(m) > 0))


# ── ledger ───────────────────────────────────────────────────────────────────

LEDGER_FIELDS = [
    "hypothesis_id",
    "timestamp",
    "hypothesis",
    "mechanism",
    "variables",
    "sample",
    "parameters",
    "conceived",
    "result",
    "inference",
    "verdict",
    "reason",
    "next",
]


def ledger_append(**row) -> None:
    """Append one hypothesis outcome. Never overwrites; failures stay in the record."""
    OUT.mkdir(parents=True, exist_ok=True)
    row.setdefault("timestamp", datetime.now(UTC).isoformat(timespec="seconds"))
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LEDGER_FIELDS})


def write(frame: pd.DataFrame, name: str) -> Path:
    """Write one deliverable and report where it went."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    frame.to_csv(path, index=False)
    print(f"  wrote {path}  ({len(frame)} rows)")
    return path


def show(tbl: pd.DataFrame, cols: list[str] | None = None) -> None:
    """Print a scorecard table with a consistent float format."""
    if tbl.empty:
        print("  (empty)")
        return
    use = [c for c in (cols or tbl.columns) if c in tbl.columns]
    print(
        tbl[use].to_string(
            index=False,
            float_format=lambda v: f"{v:+.4f}",
        )
    )


# ── executable fills ─────────────────────────────────────────────────────────


def attach_quotes(panel: pd.DataFrame) -> pd.DataFrame:
    """Merge the real two-sided quotes onto the panel, keyed on ticker and entry date."""
    from research.selection.reverse_alpha_quotes import load_quotes

    q = load_quotes()
    keys = ["ticker", "entry_date", "block"]
    cols = [c for c in q.columns if c not in panel.columns or c in keys]
    return panel.merge(q[cols].drop_duplicates(keys), on=keys, how="left")


def rom_executable(df: pd.DataFrame) -> pd.Series:
    """Return on margin taking liquidity on both sides: sell the bid, buy the ask.

    Contract count and margin stay as the frozen book sized them, off the entry mid. Only
    the fill prices move. Re-sizing off the bid would change the book's composition as well
    as its fills and make the execution effect unreadable against everything else.
    """
    bid = pd.to_numeric(df["entry_bid"], errors="coerce")
    ask = pd.to_numeric(df["exit_ask"], errors="coerce")
    contracts = pd.to_numeric(df["contracts"], errors="coerce")
    margin = pd.to_numeric(df["margin"], errors="coerce")
    commission = 0.65 * 4 * contracts
    return ((bid - ask) * 100 * contracts - commission) / margin


def quoted_width(df: pd.DataFrame, when: str) -> pd.Series:
    """Full quoted spread as a fraction of the mid, at ``entry`` or ``exit``."""
    b = pd.to_numeric(df[f"{when}_bid"], errors="coerce")
    a = pd.to_numeric(df[f"{when}_ask"], errors="coerce")
    mid = (a + b) / 2
    return pd.Series(np.where(mid > 0, (a - b) / mid, np.nan), index=df.index)


# ── residualisation ──────────────────────────────────────────────────────────


def residualise(df: pd.DataFrame, signal: str, controls: list[str]) -> pd.Series:
    """Signal orthogonalised against controls by OLS, returned aligned to ``df``.

    Used to ask whether a candidate variable survives once a suspected proxy is removed.
    Reported alongside the stratified version rather than instead of it: if the two
    disagree the signal is specification fragile, and choosing the kinder one is exactly
    the failure this programme exists to avoid.
    """
    use = [c for c in controls if c in df.columns]
    d = df[[signal, *use]].apply(pd.to_numeric, errors="coerce")
    ok = np.isfinite(d.to_numpy()).all(axis=1)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if ok.sum() < len(use) + 10:
        return out
    x = np.column_stack([np.ones(int(ok.sum())), d.loc[ok, use].to_numpy(dtype=float)])
    y = d.loc[ok, signal].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    out.loc[ok] = y - x @ beta
    return out


def demean_within(df: pd.DataFrame, signal: str, key: str) -> pd.Series:
    """Signal demeaned within groups of ``key``: the stratified counterpart to OLS control.

    A within-name sort answers "is this event rich for this name" without assuming the
    relationship is linear in the control, which cross-sectional residualisation does.
    """
    s = pd.to_numeric(df[signal], errors="coerce")
    return s - s.groupby(df[key]).transform("mean")
