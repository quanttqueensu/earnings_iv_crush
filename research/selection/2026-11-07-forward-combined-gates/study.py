"""
study.py
Premium-and-spread combined gates (G1, G2) scored on residual value over the forward paper book.

Scores the pre-registration in ``prereg.md`` exactly as frozen. The block is the transmitting
paper book, so every run reads whatever trades exist; the verdict is withheld until a gate has
150 selected scored trades.

Usage
-----
    python research/selection/2026-11-07-forward-combined-gates/study.py
    python research/selection/2026-11-07-forward-combined-gates/study.py --live-dir PATH

References
----------
Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2008). Bootstrap-based improvements for
inference with clustered errors. Review of Economics and Statistics 90(3), 414-427.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.gates import MIN_HIST  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    date_clustered_ci,
    matched_random_null,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
AMEND_01 = HERE / "prereg_amendment_01.md"
AMEND_01_RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}-amendment-01.json"
LIVE_DIR = ROOT / "outputs" / "live"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

FIRST_EXIT = pd.Timestamp("2026-11-09")  # first transmitting session of the paper book
MIN_SELECTED_FOR_VERDICT = 150
NULL_PCT_PASS = 95.0
CONTRACT_MULTIPLIER = 100
#: Amendment 01: calendar days from exit to front expiry, bucket edges fixed in the amendment.
TENOR_EDGES = (-1, 1, 4, 9, 100_000)
TENOR_LABELS = ("0-1d", "2-4d", "5-9d", "10d+")


@dataclass(frozen=True)
class Gate:
    """A conjunction of causal quantile conditions: (feature, side, quantile)."""

    name: str
    premium: tuple[str, float]  # feature kept at or above its causal quantile
    spread: tuple[str, float]  # feature kept at or below its causal quantile


GATES = (
    Gate("G1", ("iv_term_spread_nearest", 2 / 3), ("entry_rel_spread", 0.5)),
    Gate("G2", ("implied_move", 0.5), ("entry_rel_spread", 0.5)),
)
FEATURES = ("iv_term_spread_nearest", "implied_move", "entry_rel_spread")


# ── data ─────────────────────────────────────────────────────────────────────


def load_events(live_dir: Path = LIVE_DIR) -> pd.DataFrame:
    """Transmitted forward trades with entry features, exit mid and residual value.

    Raises if a ledger trade has no matching position or reconciliation row: a join that
    silently drops trades would make the funnel depend on whatever broke it.
    """
    led = pd.read_parquet(live_dir / "forward_ledger_nostop.parquet")
    pos = pd.read_parquet(live_dir / "open_positions.parquet")
    rec = pd.read_parquet(live_dir / "forward_reconciliation.parquet")
    keys = ["ticker", "entry_date"]
    for frame in (led, pos, rec):
        frame["entry_date"] = pd.to_datetime(frame["entry_date"]).dt.normalize()
    n0 = len(led)
    if "transmitted" in pos.columns:
        pos = pos[pos["transmitted"].astype(bool)]
    pos = pos[keys + ["announce_date", "front_expiry", *FEATURES]].drop_duplicates(keys)
    rec = rec[keys + ["assumed_mid_mark_ps"]].drop_duplicates(keys)
    d = led.merge(pos, on=keys, how="left", validate="many_to_one", indicator="_pos")
    d = d.merge(rec, on=keys, how="left", validate="many_to_one", indicator="_rec")
    lost = int(((d["_pos"] != "both") | (d["_rec"] != "both")).sum())
    if lost:
        raise ValueError(f"{lost} of {n0} ledger trades lack a position or reconciliation row")
    d = d.drop(columns=["_pos", "_rec"])
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d = d[pd.to_datetime(d["exit_date"]) >= FIRST_EXIT]
    d["residual_value"] = residual_value(d)
    dte = (pd.to_datetime(d["front_expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
    d["tenor"] = pd.cut(dte, list(TENOR_EDGES), labels=list(TENOR_LABELS)).astype(str)
    print(f"funnel: {n0} ledger trades, {len(d)} transmitted with exit on or after {FIRST_EXIT:%F}")
    return d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)


def residual_value(d: pd.DataFrame) -> pd.Series:
    """Option value left at the exit mid net of intrinsic, as a fraction of margin, signed for
    the short seller (negative when the market still prices time value at the exit)."""
    intrinsic = (d["spot_exit"] - d["strike"]).abs()
    scale = CONTRACT_MULTIPLIER * d["contracts"] / d["margin"]
    return -(d["assumed_mid_mark_ps"] - intrinsic) * scale


# ── the frozen rule ──────────────────────────────────────────────────────────


def causal_quantile(values: pd.Series, dates: pd.Series, q: float) -> pd.Series:
    """Quantile ``q`` over finite values with a strictly earlier announcement date.

    NaN where fewer than ``MIN_HIST`` such values exist, so no trade is scored against a
    distribution it helped form.
    """
    v = values.to_numpy(dtype=float)
    t = dates.to_numpy()
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        prior = v[(t < t[i]) & np.isfinite(v)]
        if len(prior) >= MIN_HIST:
            out[i] = np.quantile(prior, q)
    return pd.Series(out, index=values.index)


def cells(events: pd.DataFrame, gate: Gate) -> pd.DataFrame:
    """Per trade: scored flag, premium-high flag, spread-tight flag, selected flag."""
    pf, pq = gate.premium
    sf, sq = gate.spread
    p_thr = causal_quantile(events[pf], events["announce_date"], pq)
    s_thr = causal_quantile(events[sf], events["announce_date"], sq)
    scored = (p_thr.notna() & s_thr.notna() & events[pf].notna() & events[sf].notna()).to_numpy()
    high = (events[pf] >= p_thr).to_numpy()
    tight = (events[sf] <= s_thr).to_numpy()
    return pd.DataFrame(
        {"scored": scored, "high": high, "tight": tight, "selected": scored & high & tight},
        index=events.index,
    )


# ── scoring ──────────────────────────────────────────────────────────────────


def _diff_of_means(block: np.ndarray) -> float:
    """Selected minus unselected mean of column 0, selection flag in column 1."""
    v, f = block[:, 0], block[:, 1] == 1.0
    if f.all() or not f.any():
        return float("nan")
    return float(v[f].mean() - v[~f].mean())


def tenor_matched_null(
    values: np.ndarray, selected: np.ndarray, tenor: np.ndarray, n_draws: int = N_BOOT
) -> float:
    """Percentile of the selected mean among random draws matched on count within each tenor
    bucket (amendment 01), so a gate cannot pass by picking short-dated options."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(tenor == t) for t in np.unique(tenor)]
    counts = [int(selected[g].sum()) for g in groups]
    observed = float(values[selected].mean())
    draws = np.empty(n_draws)
    for b in range(n_draws):
        idx = np.concatenate(
            [rng.choice(g, c, replace=False) for g, c in zip(groups, counts, strict=True) if c]
        )
        draws[b] = values[idx].mean()
    return float(100.0 * (draws < observed).mean())


def _within_tenor_diff(block: np.ndarray) -> float:
    """Selected-count-weighted mean of within-bucket differences; columns value, flag, bucket."""
    v, f, t = block[:, 0], block[:, 1] == 1.0, block[:, 2]
    num = den = 0.0
    for u in np.unique(t):
        m = t == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (v[f & m].mean() - v[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def score_gate(events: pd.DataFrame, gate: Gate) -> dict:
    """Every pre-registered statistic for one gate, and its verdict or the reason withheld."""
    c = cells(events, gate)
    s = events[c["scored"]].assign(sel=c.loc[c["scored"], "selected"])
    out: dict = {
        "gate": gate.name,
        "n_trades": len(events),
        "n_unscored": int((~c["scored"]).sum()),
        "n_selected": int(s["sel"].sum()),
        "n_unselected": int((~s["sel"]).sum()),
    }
    bins = []
    for high in (True, False):
        for tight in (True, False):
            m = c["scored"] & (c["high"] == high) & (c["tight"] == tight)
            cell_rv = events.loc[m, "residual_value"]
            bins.append(
                {
                    "premium": "high" if high else "low",
                    "spread": "tight" if tight else "wide",
                    "n": int(m.sum()),
                    "mean_rv": float(cell_rv.mean()) if len(cell_rv) else float("nan"),
                }
            )
    out["bins"] = bins
    if out["n_selected"] < 2 or out["n_unselected"] < 2:
        out["verdict"] = "WITHHELD: too few scored trades to compute anything"
        return out
    rv = s["residual_value"].to_numpy(dtype=float)
    rom = s["return_on_margin"].to_numpy(dtype=float)
    sel = s["sel"].to_numpy(dtype=bool)
    codes = pd.Categorical(s["tenor"], categories=list(TENOR_LABELS)).codes.astype(float)
    out["null"] = matched_random_null(rv, sel, stat=np.mean)  # original, kept for reference
    out["null_pct_tenor_rv"] = tenor_matched_null(rv, sel, codes)
    out["null_pct_tenor_rom"] = tenor_matched_null(rom, sel, codes)
    trio = np.column_stack([rv, sel.astype(float), codes])
    keys = s["announce_date"].dt.normalize().to_numpy()
    out["diff"] = _within_tenor_diff(trio)
    out["diff_ci"] = cluster_bootstrap_ci(trio, keys, _within_tenor_diff, n_boot=N_BOOT, seed=SEED)
    chosen = s[sel]
    out["sel_rom_mean"] = date_clustered_ci(
        chosen["return_on_margin"], chosen["announce_date"], np.mean
    )
    out["sel_rom_sharpe"] = date_clustered_ci(chosen["return_on_margin"], chosen["announce_date"])
    if out["n_selected"] < MIN_SELECTED_FOR_VERDICT:
        out["verdict"] = (
            f"WITHHELD: {out['n_selected']} of {MIN_SELECTED_FOR_VERDICT} selected scored trades"
        )
    else:
        passed = (  # amendment 01 verdict rule
            out["null_pct_tenor_rv"] >= NULL_PCT_PASS
            and out["diff_ci"][0] > 0
            and out["null_pct_tenor_rom"] >= NULL_PCT_PASS
            and out["sel_rom_mean"].point > 0
        )
        out["verdict"] = "PASS" if passed else "FAIL"
    return out


def report(r: dict) -> str:
    """Plain-text report of one gate, every bin included."""
    lines = [
        f"{r['gate']}: {r['verdict']}",
        f"  trades {r['n_trades']}, unscored {r['n_unscored']}, selected {r['n_selected']}, "
        f"unselected {r['n_unselected']}",
        "  bins (mean residual value per trade, fraction of margin, at the exit mid):",
    ]
    for b in r["bins"]:
        lines.append(
            f"    premium {b['premium']:<4} spread {b['spread']:<5} N={b['n']:<4} "
            f"{b['mean_rv']:+.4f}"
        )
    if "null" in r:
        lo, hi = r["diff_ci"]
        lines += [
            f"  within-tenor selected minus unselected residual value {r['diff']:+.4f} "
            f"[{lo:+.4f}, {hi:+.4f}]",
            f"  tenor-matched null percentile: residual value {r['null_pct_tenor_rv']:.1f}, "
            f"net return on margin {r['null_pct_tenor_rom']:.1f} (pass needs >= {NULL_PCT_PASS})",
            f"  unmatched null (reference only): {r['null']}",
            f"  selected net return on margin, mean per trade: {r['sel_rom_mean']}",
            f"  selected net return on margin, per-trade Sharpe: {r['sel_rom_sharpe']}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live-dir", type=Path, default=LIVE_DIR, help="transmitting book stores")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    print(f"amendment 01 verified, sha256 {verify_prereg(AMEND_01, AMEND_01_RECORD)[:12]}")
    if not (args.live_dir / "forward_ledger_nostop.parquet").exists():
        print(f"No forward ledger under {args.live_dir}: nothing to score yet.")
        return
    events = load_events(args.live_dir)
    print("Basis: per trade; market data type 4 (delayed) unless the book says otherwise.")
    for gate in GATES:
        print()
        print(report(score_gate(events, gate)))


if __name__ == "__main__":
    main()
