"""
research_name_persistence.py
Test whether persistent name-level straddle richness is a tradeable selection
overlay on the short earnings-straddle book, using only cached event tables.

Motivation. The frozen-spec verdict is a closed negative: the unconditional book
does not replicate out of sample. This asks a narrower question the term gate never
did. Working in move space, the short ATM straddle's return on premium is

    ret = 1 - |realised_move| / implied_move

so ret > 0 when the stock moved less than the option implied. The efficient-markets
null is that no pre-event variable predicts ret. This script tests one variable: a
name's own prior expanding-mean ret (causal, leave-current-out), i.e. whether names
whose straddles were historically rich stay rich.

Three things are reported, each a way the effect could be fake:

  overlay      per-trade Sharpe and drawdown of the book restricted to the top-quantile
               prior-rich names, versus the unconditional book, full sample and OOS
               (priors from 2019+, traded 2022+). Inference by NAME-block bootstrap,
               since events cluster into a few dozen repeated name-bets.
  mechanism    partial IC of prior_mean vs ret after residualising both on the name's
               observable ex-ante vol (trailing_rv, implied_move, iv_entry). If it
               survives, the effect is incremental to volatility, not the low-vol tilt.
  cross-era    the same prior->ret rank IC on the independent broad 2024 and 2025 tables.

All returns are net of the project break-even round-trip cost (11.6% of premium).
Output: outputs/research/name_persistence.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

EVENTS = Path("outputs/research/events_megacap_databento.parquet")
BROAD = {
    "broad_2024": Path("outputs/research/events_broad_full.parquet"),
    "broad_2025": Path("outputs/research/events_broad_oos_2025.parquet"),
}
OUT = Path("outputs/research/name_persistence.csv")

COST = 0.116  # break-even round-trip as a fraction of premium
MIN_PRIORS = 3  # a name needs this many past events before its signal is used
TOP_Q = 0.70  # overlay trades the top 30% of names by prior richness
WINSOR = (0.01, 0.99)  # tame single blow-ups in the mean/Sharpe (worst raw reported apart)
N_BOOT = 5000
SEED = 0


def _load(path: Path, min_im: float = 0.02) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"event table missing: {path.resolve()}")
    d = pd.read_parquet(path)
    need = {"ticker", "announce_date", "implied_move", "realised_move"}
    missing = need - set(d.columns)
    if missing:
        raise KeyError(f"{path.name} lacks required columns: {sorted(missing)}")
    d = d[
        (d["implied_move"] >= min_im) & d["implied_move"].notna() & d["realised_move"].notna()
    ].copy()
    if len(d) < 100:
        raise ValueError(
            f"{path.name}: only {len(d)} usable events after filtering; refusing to proceed"
        )
    d["adate"] = pd.to_datetime(d["announce_date"])
    d = d.sort_values("adate").reset_index(drop=True)
    d["ret_raw"] = 1.0 - d["realised_move"].abs() / d["implied_move"]
    lo, hi = d["ret_raw"].quantile(list(WINSOR))
    d["ret"] = d["ret_raw"].clip(lo, hi)
    d["year"] = d["adate"].dt.year
    return d


def _add_prior(d: pd.DataFrame) -> pd.DataFrame:
    """Causal expanding mean of a name's own past ret (leave-current-out)."""
    d = d.copy()
    d["prior_mean"] = np.nan
    d["prior_n"] = 0
    for _, g in d.groupby("ticker"):
        idx = g.index
        csum = g["ret"].cumsum().shift(1)
        cnt = pd.Series(np.arange(len(g)), index=idx)
        d.loc[idx, "prior_mean"] = (csum / cnt.replace(0, np.nan)).to_numpy()
        d.loc[idx, "prior_n"] = cnt.to_numpy()
    return d


def _per_trade_sharpe(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 and len(x) > 1 else 0.0


def _max_dd_monthly(df: pd.DataFrame) -> float:
    mo = df.groupby(df["adate"].dt.to_period("M"))["net"].mean()
    eq = (1.0 + mo).cumprod()
    return float(((eq / eq.cummax()) - 1.0).min())


def _name_block_ci(df: pd.DataFrame, rng: np.random.Generator) -> tuple[float, float]:
    """Resample whole names (not events) so the CI respects name clustering."""
    groups = [g["net"].to_numpy() for _, g in df.groupby("ticker")]
    k = len(groups)
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, k, size=k)
        sample = np.concatenate([groups[i] for i in pick])
        boots.append(sample.mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


def _book_row(df: pd.DataFrame, label: str, rng: np.random.Generator) -> dict:
    x = df["net"].to_numpy()
    lo, hi = _name_block_ci(df, rng)
    return {
        "book": label,
        "n_events": len(df),
        "n_names": df["ticker"].nunique(),
        "net_mean": float(x.mean()),
        "hit": float((x > 0).mean()),
        "per_trade_sharpe": _per_trade_sharpe(x),
        "max_dd_monthly": _max_dd_monthly(df),
        "worst_trade_raw": float(df["ret_raw"].min()),
        "name_block_ci_lo": lo,
        "name_block_ci_hi": hi,
    }


def _residualise(y: np.ndarray, controls: np.ndarray) -> np.ndarray:
    x = np.column_stack([np.ones(len(y)), controls])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return y - x @ beta


def _partial_ic(d: pd.DataFrame) -> tuple[float, float, int]:
    """IC of prior_mean vs ret after removing the linear part of both due to vol."""
    cols = ["trailing_rv", "implied_move", "iv_entry"]
    have = [c for c in cols if c in d.columns]
    s = d.dropna(subset=["prior_mean", "ret"] + have)
    ctrl = s[have].to_numpy()
    ry = _residualise(s["ret"].to_numpy(), ctrl)
    rp = _residualise(s["prior_mean"].to_numpy(), ctrl)
    rho, p = stats.spearmanr(rp, ry)
    return float(rho), float(p), len(s)


def main() -> None:
    rng = np.random.default_rng(SEED)
    d = _add_prior(_load(EVENTS))
    sig = d[d["prior_n"] >= MIN_PRIORS].dropna(subset=["prior_mean"]).copy()
    sig["net"] = sig["ret"] - COST

    rows: list[dict] = []
    for era, sub in [("full_2019_2024", sig), ("oos_2022_2024", sig[sig["year"] >= 2022])]:
        thr = sub["prior_mean"].quantile(TOP_Q)
        rows.append({**_book_row(sub, f"unconditional | {era}", rng), "era": era})
        rows.append(
            {**_book_row(sub[sub["prior_mean"] >= thr], f"rich_overlay | {era}", rng), "era": era}
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)

    rho, p, n = _partial_ic(sig)

    print("=== name-persistence overlay on the short-straddle book (net of 11.6% cost) ===")
    print(df.drop(columns="era").to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    print(
        "\nMECHANISM (incremental to vol): partial IC of prior_mean vs ret, "
        f"residualised on trailing_rv+implied_move+iv_entry = {rho:+.4f} (p={p:.4f}, N={n})"
    )
    print("  positive and significant => genuine residual name richness, not the low-vol tilt.")

    print("\nCROSS-ERA (independent universes): prior_mean -> ret rank IC")
    for name, path in BROAD.items():
        try:
            b = _add_prior(_load(path))
            yr = b["year"].max()
            bb = b[(b["prior_n"] >= max(2, MIN_PRIORS - 1)) & (b["year"] == yr)].dropna(
                subset=["prior_mean"]
            )
            if len(bb) < 60:
                print(f"  {name}: {len(bb)} events in {yr}, too few to judge")
                continue
            ic = stats.spearmanr(bb["prior_mean"], bb["ret"])
            print(
                f"  {name} ({yr}, {bb['ticker'].nunique()} names, N={len(bb)}): IC={ic.statistic:+.4f} p={ic.pvalue:.4f}"
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"  {name}: skipped ({exc})")

    ok = bool(
        df.loc[df["book"].str.startswith("rich_overlay | oos"), "name_block_ci_lo"].iloc[0] > 0
    )
    print(f"\nOOS rich-overlay mean clears zero on the name-block CI: {ok}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
