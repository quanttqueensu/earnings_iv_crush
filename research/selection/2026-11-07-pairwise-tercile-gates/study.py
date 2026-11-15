"""
study.py
Pairwise tercile gates on seven 15:59 entry features, scored on residual value in three blocks.

Scores the pre-registration in ``prereg.md`` exactly as frozen. ``--build`` reads the reaction-
session exit chains once and caches the exit marks; the default run scores from that cache.

Usage
-----
    python research/selection/2026-11-07-pairwise-tercile-gates/study.py --build
    python research/selection/2026-11-07-pairwise-tercile-gates/study.py

References
----------
Bakshi, G. and Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk
premium. Review of Financial Studies 16(2), 527-566.
Bakshi, G., Kapadia, N. and Madan, D. (2003). Stock return characteristics, skew laws, and the
differential pricing of individual equity options. Review of Financial Studies 16(1), 101-143.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option pricing of earnings
announcement risks. Review of Financial Studies 32(2), 646-687.
Goyal, A. and Saretto, A. (2009). Cross-section of option returns and volatility. Journal of
Financial Economics 94(2), 310-326.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
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
OUT = ROOT / "outputs" / "research" / HERE.name
ZOO = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
HH_STUDY = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

N_BINS = 3
MIN_PRIOR = 200
NULL_PCT_PASS = 95.0
BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
#: feature -> favourable bin (0 = bottom tercile, 2 = top tercile)
FAVOURABLE = {
    "implied_over_hist": 2,
    "iv_term_spread": 2,
    "variance_risk_premium": 2,
    "entry_half_spread": 0,
    "name_prior_ratio": 0,
    "bkm_kurt": 2,
    "hist_move_dispersion": 0,
}
PAIRS = list(itertools.combinations(FAVOURABLE, 2))


# ── exit marks (built once) ──────────────────────────────────────────────────


def _hh_module():
    """The closed hedged-hold study, imported (never edited) for its exit readers."""
    spec = importlib.util.spec_from_file_location("hh_study", HH_STUDY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hh_study"] = mod
    spec.loader.exec_module(mod)
    return mod


def leg_mark(bid: float, ask: float) -> float:
    """Mid when two-sided, half the ask when the bid is zero, undefined otherwise."""
    if not (np.isfinite(ask) and ask > 0):
        return float("nan")
    if np.isfinite(bid) and bid > 0:
        return (bid + ask) / 2.0
    return ask / 2.0


def residual_value(mark_c: float, mark_p: float, fwd: float, strike: float, m0: float) -> float:
    """Option value left at the exit net of intrinsic, as a fraction of m0, signed for the seller."""
    return -(mark_c + mark_p - abs(fwd - strike)) / m0


def _marks_one(args: tuple) -> dict:
    ticker, entry_date, exit_date, strike, expiry, m0 = args
    hh = _hh_module() if "hh_study" not in sys.modules else sys.modules["hh_study"]
    day, exp = pd.Timestamp(exit_date), pd.Timestamp(expiry)
    out = {"ticker": ticker, "entry_date": entry_date}
    q = hh.exit_quotes(ticker, day, strike, exp)
    if q["status"] != "ok":
        return {**out, "mark_status": q["status"]}
    mc, mp = leg_mark(q["bid_C"], q["ask_C"]), leg_mark(q["bid_P"], q["ask_P"])
    if not (np.isfinite(mc) and np.isfinite(mp)):
        return {**out, "mark_status": "zero_ask"}
    fwd, fsrc = hh.exit_fwd(ticker, day, exp), "parity_chain"
    if not np.isfinite(fwd):
        fwd, fsrc = strike + mc - mp, "parity_own_strike"
    one_sided = int(q["bid_C"] <= 0) + int(q["bid_P"] <= 0)
    return {
        **out,
        "mark_status": "ok",
        "fwd_src": fsrc,
        "one_sided_legs": one_sided,
        "mark_c": mc,
        "mark_p": mp,
        "fwd_exit": fwd,
        "residual_value": residual_value(mc, mp, fwd, strike, m0),
    }


def load_base() -> pd.DataFrame:
    """Broad events with features, hedged-hold entry fields and outcomes; funnel printed."""
    z = pd.read_parquet(ZOO)
    z = z[z["block"] != "megacap"].copy()
    hh = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ],
        ignore_index=True,
    )
    hh = hh[hh["status"] == "ok"]
    for f in (z, hh):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    keep = ["ticker", "entry_date", "strike", "expiry", "m0", "s0", "mid0", "B", "H"]
    d = z.merge(hh[keep], on=["ticker", "entry_date"], how="inner", validate="one_to_one")
    d["entry_half_spread"] = (d["mid0"] - d["s0"]) / d["mid0"]
    d["year"] = pd.to_datetime(d["announce_date"]).dt.year
    print(f"funnel: {len(z)} broad zoo events, {len(hh)} hedged-hold ok, {len(d)} joined")
    return d


def build() -> None:
    """Read every exit chain once and cache the marks."""
    d = load_base()
    jobs = list(
        d[["ticker", "entry_date", "exit_date", "strike", "expiry", "m0"]].itertuples(
            index=False, name=None
        )
    )
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_marks_one, jobs, chunksize=50))
    marks = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    marks.to_parquet(OUT / "exit_marks.parquet", index=False)
    print(marks["mark_status"].value_counts().to_string())
    print(marks.get("fwd_src", pd.Series(dtype=str)).value_counts().to_string())


# ── scoring ──────────────────────────────────────────────────────────────────


def _diff_of_means(block: np.ndarray) -> float:
    v, f = block[:, 0], block[:, 1] == 1.0
    if f.all() or not f.any():
        return float("nan")
    return float(v[f].mean() - v[~f].mean())


def attrition(d: pd.DataFrame) -> pd.DataFrame:
    """Per block: dropped count and whether drops lean to large moves relative to implied."""
    rows = []
    ratio = d["realised_move"].abs() / d["implied_move"]
    for name, (y0, y1) in BLOCKS.items():
        b = d[d["year"].between(y0, y1)]
        r = ratio.loc[b.index]
        dropped = b["residual_value"].isna()
        pair = np.column_stack([r.to_numpy(float), dropped.to_numpy(float)])
        ok = np.isfinite(pair[:, 0])
        keys = pd.to_datetime(b["announce_date"]).dt.normalize().to_numpy()[ok]
        ci = cluster_bootstrap_ci(pair[ok], keys, _diff_of_means, n_boot=N_BOOT, seed=SEED)
        rows.append(
            {
                "block": name,
                "n": len(b),
                "dropped": int(dropped.sum()),
                "ratio_dropped_minus_kept": _diff_of_means(pair[ok]),
                "ci_low": ci[0],
                "ci_high": ci[1],
            }
        )
    return pd.DataFrame(rows)


def score(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every pair in every block; returns the scorecard and the full 3x3 bin table."""
    bins = {
        f: causal_bins(d[f].to_numpy(float), d["announce_date"], N_BINS, MIN_PRIOR)
        for f in FAVOURABLE
    }
    has_rv = d["residual_value"].notna().to_numpy()
    rows, cells = [], []
    for a, b in PAIRS:
        ba, bb = bins[a], bins[b]
        scored_all = (ba >= 0) & (bb >= 0) & has_rv
        sel_all = scored_all & (ba == FAVOURABLE[a]) & (bb == FAVOURABLE[b])
        rec: dict = {"pair": f"{a} x {b}"}
        for name, (y0, y1) in BLOCKS.items():
            inb = d["year"].between(y0, y1).to_numpy()
            sc, sel = scored_all & inb, sel_all & inb
            for i in range(N_BINS):
                for j in range(N_BINS):
                    m = sc & (ba == i) & (bb == j)
                    cells.append(
                        {
                            "pair": rec["pair"],
                            "block": name,
                            "bin_a": i,
                            "bin_b": j,
                            "n": int(m.sum()),
                            "mean_rv": (
                                float(d.loc[m, "residual_value"].mean()) if m.any() else np.nan
                            ),
                        }
                    )
            rv = d.loc[sc, "residual_value"].to_numpy(float)
            mask = sel[sc]
            rec[f"{name}_n_scored"], rec[f"{name}_n_sel"] = int(sc.sum()), int(mask.sum())
            if mask.sum() < 2 or (~mask).sum() < 2:
                rec[f"{name}_null_pct"] = np.nan
                rec[f"{name}_diff"] = rec[f"{name}_lo"] = rec[f"{name}_hi"] = np.nan
                continue
            rec[f"{name}_null_pct"] = matched_random_null(rv, mask, stat=np.mean).percentile
            pair = np.column_stack([rv, mask.astype(float)])
            keys = pd.to_datetime(d.loc[sc, "announce_date"]).dt.normalize().to_numpy()
            rec[f"{name}_diff"] = _diff_of_means(pair)
            lo, hi = cluster_bootstrap_ci(pair, keys, _diff_of_means, n_boot=N_BOOT, seed=SEED)
            rec[f"{name}_lo"], rec[f"{name}_hi"] = lo, hi
        skill = all(rec[f"{n}_null_pct"] >= NULL_PCT_PASS for n in BLOCKS) and all(
            rec[f"{n}_lo"] > 0 for n in ("validation", "confirmation")
        )
        rec["verdict"] = "SELECTION SKILL" if skill else "FAIL"
        if skill:
            conf = sel_all & d["year"].between(*BLOCKS["confirmation"]).to_numpy()
            h = d.loc[conf]
            ci = date_clustered_ci(h["H"], h["announce_date"], np.mean)
            rec["conf_H_mean"], rec["conf_H_lo"] = ci.point, ci.low
            rec["verdict"] = "TRADABLE" if ci.low > 0 else "SELECTION SKILL"
        rows.append(rec)
    return pd.DataFrame(rows), pd.DataFrame(cells)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="read exit chains and cache the marks")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    if args.build:
        build()
        return
    d = load_base()
    marks = pd.read_parquet(OUT / "exit_marks.parquet")
    marks["entry_date"] = pd.to_datetime(marks["entry_date"]).dt.normalize()
    d = d.merge(marks, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d = d.reset_index(drop=True)
    print(d["mark_status"].value_counts(dropna=False).to_string())
    att = attrition(d)
    print("\nattrition (|realised| / implied, dropped minus kept, date-clustered 95%):")
    print(att.to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
    card, cells = score(d)
    OUT.mkdir(parents=True, exist_ok=True)
    card.to_csv(OUT / "scorecard.csv", index=False)
    cells.to_csv(OUT / "bins.csv", index=False)
    att.to_csv(OUT / "attrition.csv", index=False)
    cols = ["pair"] + [f"{n}_{s}" for n in BLOCKS for s in ("n_sel", "null_pct", "diff")]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print("\nUnit: residual value per trade, fraction of m0, at the exit mid, gross of costs.")
        print(card[cols + ["verdict"]].to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(f"\nverdicts: {card['verdict'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
