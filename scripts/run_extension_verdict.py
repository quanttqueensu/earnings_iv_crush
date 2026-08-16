"""
run_extension_verdict.py
Score the 2013-2018 quote-marked extension on the frozen specification.

The specification is not re-tuned here. The gate stays ``expanding_high_term_mask`` at
q=0.80, costs stay ``MEGACAP_COST``, the outcome stays ``return_on_margin``, and the only
thing that changes is which events are fed in. Re-tuning on a new block would convert an
out-of-sample test into another trial and is the failure this whole exercise exists to
avoid.

Blocks are reported separately before anything is pooled. The 2019-2024 book's P&L is
concentrated in two of its six years, so a pooled headline could hide a block that
contributes nothing, and the pooled number is only meaningful once the reader has seen
the parts.

Two caveats belong beside every number this prints, and are printed with them:

* **Universe survivorship.** The 50 names are today's mega-caps carried backwards. In 2013
  that universe was not knowable, and firms that fell out of the tier are absent by
  construction. The extension is therefore not a clean out-of-sample test; it is the same
  selection applied to more history, and a narrower confidence interval on a biased
  estimate is worth less than it looks.
* **Session asymmetry.** The extension snaps entry and exit onto real trading sessions;
  the 2019-2024 book does not, and silently drops 24 Berkshire events whose Saturday
  announcements put the exit on a non-session. The extension retains that class.

Run: ``python scripts/run_extension_verdict.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.market_validate as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from scripts.validate_skew_oos import expanding_high_term_mask  # noqa: E402

EXTENSION = "data/processed/events_megacap_quotes_2013_2018.parquet"
OUT = Path("outputs/research/extension_verdict.csv")
Q = 0.80


def _sharpe(rom: pd.Series) -> float:
    rom = pd.to_numeric(rom, errors="coerce").dropna()
    if len(rom) < 2 or rom.std(ddof=1) == 0:
        return float("nan")
    return float(rom.mean() / rom.std(ddof=1))


def _clustered_ci(rom: pd.Series, clusters: pd.Series, n_boot: int = 5000) -> tuple[float, float]:
    """Percentile CI on the per-trade Sharpe, resampling whole announcement dates."""
    rng = np.random.default_rng(0)
    keys = pd.Index(clusters.unique())
    groups = {k: rom[clusters == k].to_numpy() for k in keys}
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(keys, size=len(keys), replace=True)
        sample = np.concatenate([groups[k] for k in pick])
        sd = sample.std(ddof=1)
        draws[b] = sample.mean() / sd if sd > 0 else np.nan
    draws = draws[np.isfinite(draws)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _score(label: str, events_path: str) -> dict:
    ev, _ = mv._prepare(events_path, chain_path=dq.cache_path)
    mask = np.asarray(expanding_high_term_mask(ev, Q), dtype=bool)
    led = mv._ledger(ev[mask].reset_index(drop=True), defined_risk=False, costs=mv.MEGACAP_COST)
    rom = pd.to_numeric(led["return_on_margin"], errors="coerce").dropna()
    if len(rom) < 2:
        print(f"\n  {label}: too few marked trades to score (N={len(rom)})")
        return {"block": label, "n": len(rom)}

    n, s = len(rom), _sharpe(rom)
    entry = pd.to_datetime(led.loc[rom.index, "entry_date"])
    lo, hi = _clustered_ci(rom, entry.dt.normalize())
    se = float(np.sqrt((1 + s**2 / 2) / n))
    z = s / se
    span = max((entry.max() - entry.min()).days / 365.25, 1e-9)
    tpy = n / span
    print(f"\n  {label}")
    print(f"    prepared events  {len(ev)}  ({int(mask.sum())} pass the gate)")
    print(f"    N                {n}")
    print(f"    hit rate         {(rom > 0).mean():.1%}")
    print(f"    mean RoM         {rom.mean():+.4f}")
    print(f"    per-trade Sharpe {s:+.6f}  (unannualised)")
    print(
        f"    trades/yr        {tpy:.1f}  -> annualised {s*np.sqrt(tpy):+.3f} (x sqrt({tpy:.1f}))"
    )
    print(f"    z / one-sided p  {z:+.2f} / {1 - sps.norm.cdf(z):.4f}")
    print(f"    clustered 95% CI [{lo:+.4f}, {hi:+.4f}]")
    return {
        "block": label,
        "n": n,
        "hit_rate": float((rom > 0).mean()),
        "mean_rom": float(rom.mean()),
        "per_trade_sharpe": s,
        "trades_per_year": tpy,
        "annualised_sharpe": s * np.sqrt(tpy),
        "z": z,
        "one_sided_p": float(1 - sps.norm.cdf(z)),
        "ci_lo": lo,
        "ci_hi": hi,
    }


def main() -> None:
    print("Frozen spec: expanding pooled term gate q=0.80, quote marks, MEGACAP_COST")
    print("Blocks scored separately; see the module docstring for the two standing caveats.")
    rows = [
        _score("2019-2024 (original)", mv.EVENTS_FULL),
        _score("2013-2018 (extension)", EXTENSION),
    ]
    out = pd.DataFrame([r for r in rows if r.get("n", 0) > 1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nwritten: {OUT.resolve()}")


if __name__ == "__main__":
    main()
