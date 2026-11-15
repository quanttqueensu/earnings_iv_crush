"""
study.py
Analyst disagreement (IBES dispersion over the forward) as a selector for the hedged event hold.

Scores the pre-registration in ``prereg.md`` exactly as frozen: discovery first, and the later
blocks only if discovery passes.

Usage
-----
    python research/selection/2026-11-07-analyst-disagreement-hedged-hold/study.py

References
----------
de Silva, T., So, E. C. and Smith, K. (2025). Losing is optional: retail option trading and
expected announcement volatility. Review of Finance.
Diether, K. B., Malloy, C. J. and Scherbina, A. (2002). Differences of opinion and the cross
section of stock returns. Journal of Finance 57(5), 2113-2141.
"""

from __future__ import annotations

import argparse
import glob
import sys
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
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
WRDS = ROOT / "data" / "processed" / "wrds" / "raw"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

MARGIN_SPOT_FRAC = 0.20  # m0 = 0.20 x F0 + s0, so F0 = (m0 - s0) / 0.20
MAX_STALE_DAYS = 40
MIN_NUMEST = 3
MIN_PRIOR = 200
NULL_PCT_PASS = 95.0
TENOR_EDGES = [-1, 1, 4, 9, 100_000]
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
BLOCKS = {
    "discovery": ("2013-01-01", "2018-12-31"),
    "validation": ("2019-01-01", "2024-12-31"),
    "confirmation": ("2025-01-01", "2026-01-15"),
}


# ── data ─────────────────────────────────────────────────────────────────────


def load_events() -> pd.DataFrame:
    """Hedged-hold events with announcement date, permno, forward, implied move and tenor."""
    hh = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ],
        ignore_index=True,
    )
    hh = hh[hh["status"] == "ok"].copy()
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "announce_date", "permno"])
    for x in (hh, f):
        x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = hh.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    latest = (
        f.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    )
    d["permno"] = d["permno"].fillna(d["ticker"].map(latest))
    d["announce_date"] = pd.to_datetime(d["announce_date"])
    d["F0"] = (d["m0"] - d["s0"]) / MARGIN_SPOT_FRAC
    d["implied_move"] = d["mid0"] / d["F0"]
    dte = (pd.to_datetime(d["expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
    d["tenor"] = pd.cut(dte, TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    d["y"] = d["H"] * d["m0"] / d["mid0"]
    print(
        f"funnel: {len(hh)} hedged-hold ok, {int(d['announce_date'].notna().sum())} dated, "
        f"{int(d['permno'].notna().sum())} with permno"
    )
    return d.sort_values("announce_date").reset_index(drop=True)


def attach_dispersion(d: pd.DataFrame) -> pd.DataFrame:
    """D = IBES stdev / F0 at the latest statpers strictly before entry, causal only."""
    s = pd.read_parquet(
        glob.glob(str(WRDS / "tr_ibes.statsum_epsus.*.parquet"))[0],
        columns=["ticker", "statpers", "fpedats", "numest", "stdev"],
    )
    link = pd.read_parquet(glob.glob(str(WRDS / "wrdsapps_link_crsp_ibes.ibcrsphist.*.parquet"))[0])
    for c in ("statpers", "fpedats"):
        s[c] = pd.to_datetime(s[c])
    for c in ("sdate", "edate"):
        link[c] = pd.to_datetime(link[c])
    s = s[s["numest"] >= MIN_NUMEST].rename(columns={"ticker": "ibes"})
    link = link.rename(columns={"ticker": "ibes"}).dropna(subset=["permno"])
    by_ibes = {k: g for k, g in s.groupby("ibes")}
    by_permno = {int(float(str(k))): g for k, g in link.groupby("permno")}
    permnos = d["permno"].to_numpy(float)
    entries = pd.to_datetime(d["entry_date"]).tolist()
    announces = pd.to_datetime(d["announce_date"]).tolist()
    fwds = d["F0"].to_numpy(float)
    out = np.full(len(d), np.nan)
    found = 0
    stale = pd.Timedelta(days=MAX_STALE_DAYS)
    for i in range(len(d)):
        pn, t_in, t_ann = permnos[i], entries[i], announces[i]
        if not np.isfinite(pn) or int(pn) not in by_permno:
            continue
        lk = by_permno[int(pn)]
        lk = lk[(lk["sdate"] <= t_in) & (lk["edate"] >= t_in)]
        if lk.empty:
            continue
        g = by_ibes.get(lk.sort_values("score")["ibes"].iloc[0])
        if g is None:
            continue
        g = g[(g["statpers"] < t_in) & (g["statpers"] >= t_in - stale) & (g["fpedats"] < t_ann)]
        if g.empty:
            continue
        g = g[g["statpers"] == g["statpers"].max()]
        row = g.sort_values("fpedats").iloc[-1]
        found += 1
        out[i] = float(row["stdev"]) / float(fwds[i])
    d = d.assign(D=out)
    print(f"funnel: IBES row found {found}, D finite {int(np.isfinite(out).sum())}")
    return d


def assign(d: pd.DataFrame) -> pd.DataFrame:
    """Causal implied-move tercile, causal D decile within tercile, treated flag."""
    d = d.copy()
    d["im_bin"] = causal_bins(d["implied_move"].to_numpy(float), d["announce_date"], 3, MIN_PRIOR)
    d["d_bin"] = -1
    for t in range(3):
        idx = d.index[d["im_bin"] == t]
        sub = d.loc[idx]
        d.loc[idx, "d_bin"] = causal_bins(
            sub["D"].to_numpy(float), sub["announce_date"], 10, MIN_PRIOR
        )
    d["scored"] = (d["im_bin"] >= 0) & (d["d_bin"] >= 0)
    d["treated"] = d["scored"] & (d["d_bin"] == 9)
    print(
        f"funnel: tercile assigned {int((d['im_bin'] >= 0).sum())}, scored {int(d['scored'].sum())}"
    )
    return d


# ── statistics ───────────────────────────────────────────────────────────────


def _cell_codes(b: pd.DataFrame) -> np.ndarray:
    return (b["im_bin"].astype(int) * 10 + pd.Categorical(b["tenor"], TENOR_LABELS).codes).to_numpy(
        float
    )


def _delta(block: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell differences; columns y, treated, cell."""
    y, f, c = block[:, 0], block[:, 1] == 1.0, block[:, 2]
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def cell_matched_null(h: np.ndarray, treated: np.ndarray, cells: np.ndarray) -> float:
    """Percentile of the treated per-trade Sharpe among draws matched on count within cell."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(cells == u) for u in np.unique(cells)]
    counts = [int(treated[g].sum()) for g in groups]
    obs = per_trade_sharpe(h[treated])
    draws = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate(
            [rng.choice(g, k, replace=False) for g, k in zip(groups, counts, strict=True) if k]
        )
        draws[b] = per_trade_sharpe(h[idx])
    return float(100.0 * (draws < obs).mean())


def score_block(d: pd.DataFrame, name: str) -> dict:
    lo, hi = (pd.Timestamp(x) for x in BLOCKS[name])
    b = d[d["scored"] & d["announce_date"].between(lo, hi)]
    cells = _cell_codes(b)
    trio = np.column_stack([b["y"].to_numpy(float), b["treated"].to_numpy(float), cells])
    keys = b["announce_date"].dt.normalize().to_numpy()
    res: dict = {
        "block": name,
        "n_scored": len(b),
        "n_treated": int(b["treated"].sum()),
        "delta": _delta(trio),
    }
    res["delta_ci"] = cluster_bootstrap_ci(trio, keys, _delta, n_boot=N_BOOT, seed=SEED)
    tr = b["treated"].to_numpy(bool)
    res["null_pct"] = cell_matched_null(b["H"].to_numpy(float), tr, cells)
    res["treated_H"] = date_clustered_ci(b.loc[tr, "H"], b.loc[tr, "announce_date"], np.mean)
    res["treated_sharpe"] = date_clustered_ci(b.loc[tr, "H"], b.loc[tr, "announce_date"])
    res["all_H_mean"] = float(b["H"].mean())
    res["pass"] = bool(res["delta_ci"][0] > 0 and res["null_pct"] >= NULL_PCT_PASS)
    return res


def show(r: dict) -> None:
    lo, hi = r["delta_ci"]
    print(f"\n{r['block']}: scored {r['n_scored']}, treated {r['n_treated']}")
    print(f"  Delta (H per unit premium, within cell) {r['delta']:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    print(f"  cell-matched null percentile, per-trade Sharpe of H: {r['null_pct']:.1f}")
    print(f"  treated H per trade on m0, mean: {r['treated_H']}")
    print(
        f"  treated H per-trade Sharpe: {r['treated_sharpe']}  (all scored mean {r['all_H_mean']:+.4f})"
    )


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = assign(attach_dispersion(load_events()))
    OUT.mkdir(parents=True, exist_ok=True)
    d.drop(
        columns=[c for c in d.columns if d[c].dtype == object and c not in ("ticker", "tenor")]
    ).to_parquet(OUT / "events.parquet", index=False)
    disc = score_block(d, "discovery")
    show(disc)
    if not disc["pass"]:
        print("\nVERDICT: FAIL at discovery; validation and confirmation not scored (prereg).")
        return
    val = score_block(d, "validation")
    show(val)
    if not val["pass"]:
        print("\nVERDICT: FAIL at validation.")
        return
    conf = score_block(d, "confirmation")
    show(conf)
    ok = conf["delta"] > 0 and conf["treated_H"].point > 0
    print(f"\nVERDICT: {'PASS' if ok else 'FAIL at confirmation'}")


if __name__ == "__main__":
    main()
