"""
study.py
Pre-event signals for earnings tail moves (trials 1,616 to 1,622).

Scores the pre-registration in ``prereg.md`` exactly as frozen: does information outside the
option surface flag events whose reaction exceeds twice the implied move, and does skipping the
flagged events raise the next-day buy-back book's mean return? Discovery 2015-19 gates
validation 2020-24, which gates confirmation 2025-26. Every run is a trial.

Usage
-----
    python research/selection/2026-11-12-tail-event-signals/study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name

EVENTS = ROOT / "outputs/research/2026-11-02-hedged-event-hold/events.parquet"
CONFIRM = ROOT / "outputs/research/2026-11-02-hedged-event-hold/events_confirm_2025_26.parquet"
FEATURES = ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
CHARS = Path.home() / "FIAM_Hackathon_2026/temp/chars_final_with_names.parquet"

# ── frozen parameters (prereg "Specification") ──
TAIL_RATIO = 2.0  # tail: realised move over implied move above this
CHARS_MAX_AGE_D = 62  # characteristics row at most this old at entry
PEER_WINDOW_D = 30  # peer reaction in [d - 30, d - 1]
HIST_N, HIST_MIN = 8, 4  # own history: last 8 events, defined with at least 4
Q_HIGH, Q_LOW = 0.80, 0.20  # cross-sectional quintile cut-offs (standing rule)
BLOCKS = {
    "discovery": ("2015-01-01", "2019-12-31"),
    "validation": ("2020-01-01", "2024-12-31"),
    "confirmation": ("2025-01-01", "2026-12-31"),
}
# Two-group statistics are passed through protocol.date_clustered_ci, which resamples one value
# array; the group is encoded in the value so each replicate keeps whole dates intact.
GROUP_OFFSET = 1000.0  # far above any |B| (fraction of margin)
TRIALS = ["T1_peer_shock", "T2_oscore", "T3_zscore", "T4_off_high", "T5_earn_var", "T6_own_hist"]


# ── data ──


def load_events() -> pd.DataFrame:
    """All scorable events 2013-2026 with ratio, tail flag, outcome B and permno."""
    main = pd.read_parquet(EVENTS)
    conf = pd.read_parquet(CONFIRM)
    n_main, n_conf = len(main), len(conf)
    main = main[main["status"] == "ok"]
    conf = conf[conf["status"] == "ok"]
    ev = pd.concat([main, conf], ignore_index=True)
    feat = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno", "front_fwd"])
    if feat.duplicated(["ticker", "entry_date"]).any():
        raise ValueError("features not unique on ticker, entry_date")
    ev = ev.merge(feat, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    ev["im"] = ev["mid0"] / ev["front_fwd"]
    ev["ratio"] = ev["abs_move"] / ev["im"]
    ok = np.isfinite(ev["ratio"]) & (ev["im"] > 0)
    print(
        f"funnel events: main {n_main} -> ok {len(main)}; confirm {n_conf} -> ok {len(conf)}; "
        f"finite ratio {int(ok.sum())} of {len(ev)}; permno present {ev['permno'].notna().mean():.1%}"
    )
    ev = ev[ok].copy()
    ev["tail"] = ev["ratio"] > TAIL_RATIO
    ev["premium"] = ev["mid0"] / ev["m0"]
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).astype("datetime64[ns]")
    return ev.sort_values("entry_date").reset_index(drop=True)


def load_chars() -> pd.DataFrame:
    """Monthly characteristics with cross-sectional percentiles per month."""
    cols = [
        "permno",
        "eom",
        "gics",
        "o_score",
        "z_score",
        "prc_highprc_252d",
        "earnings_variability",
    ]
    ch = pd.read_parquet(CHARS, columns=cols)
    ch["eom"] = pd.to_datetime(ch["eom"])
    for c in cols[3:]:
        ch[f"{c}_pct"] = ch.groupby("eom")[c].rank(pct=True)
    ch["gics6"] = ch["gics"].map(lambda g: str(int(g))[:6] if pd.notna(g) else None)
    return ch.dropna(subset=["permno"]).sort_values("eom")


def attach_chars(ev: pd.DataFrame, ch: pd.DataFrame) -> pd.DataFrame:
    """Latest characteristics row strictly before entry, at most CHARS_MAX_AGE_D old."""
    left = ev[ev["permno"].notna()].copy()
    left["permno"] = left["permno"].astype("int64")
    left["entry_date"] = left["entry_date"].astype("datetime64[ns]")
    ch = ch.copy()
    ch["permno"] = ch["permno"].astype("int64")
    ch["eom"] = ch["eom"].astype("datetime64[ns]")
    m = pd.merge_asof(
        left.sort_values("entry_date"),
        ch.drop(columns=["gics"]).rename(columns={"eom": "chars_eom"}),
        left_on="entry_date",
        right_on="chars_eom",
        by="permno",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=CHARS_MAX_AGE_D),
    )
    out = ev.merge(
        m[["ticker", "entry_date", "chars_eom", "gics6"] + [c for c in m if c.endswith("_pct")]],
        on=["ticker", "entry_date"],
        how="left",
    )
    print(f"funnel chars: matched {out['chars_eom'].notna().sum()} of {len(out)} events")
    return out


# ── signals ──


def peer_shock(ev: pd.DataFrame, ch: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """T1: a same-industry peer reacted more than 2x implied in the 30 days before entry."""
    # Peer events lacking a chars row (pre-2015) take their permno's earliest industry code.
    first_gics = ch.dropna(subset=["gics6"]).groupby("permno")["gics6"].first()
    ind = ev["gics6"].copy()
    miss = ind.isna() & ev["permno"].notna()
    ind[miss] = ev.loc[miss, "permno"].map(first_gics)
    tickers_by_ind = pd.Series(ev["ticker"].to_numpy()).groupby(ind.to_numpy()).unique()
    treated = np.zeros(len(ev), dtype=bool)
    defined = np.zeros(len(ev), dtype=bool)
    tails = ev[ev["tail"]].assign(ind=ind[ev["tail"]])
    for i, row in ev.iterrows():
        g = row["gics6"]
        if g is None or pd.isna(g):
            continue
        others = [t for t in tickers_by_ind.get(g, []) if t != row["ticker"]]
        if not others:
            continue
        defined[i] = True
        d = row["entry_date"]
        cand = tails[
            (tails["ind"] == g)
            & (tails["ticker"] != row["ticker"])
            & (tails["entry_date"] >= d - pd.Timedelta(days=PEER_WINDOW_D))
            & (tails["entry_date"] <= d - pd.Timedelta(days=1))
            & (tails["exit_date"] < d)
        ]
        treated[i] = len(cand) > 0
    return treated, defined


def own_history(ev: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """T6: a tail among the name's previous eight events with exit strictly before entry."""
    treated = np.zeros(len(ev), dtype=bool)
    defined = np.zeros(len(ev), dtype=bool)
    for _, grp in ev.groupby("ticker"):
        exits = grp["exit_date"].to_numpy()
        tails = grp["tail"].to_numpy()
        for idx, d in zip(grp.index, grp["entry_date"].to_numpy()):
            prior = np.where(exits < d)[0]
            if len(prior) < HIST_MIN:
                continue
            last = prior[-HIST_N:]
            defined[idx] = True
            treated[idx] = bool(tails[last].any())
    return treated, defined


def pct_flag(ev: pd.DataFrame, col: str, high: bool) -> tuple[np.ndarray, np.ndarray]:
    """Cross-sectional quintile flag on a chars percentile column."""
    v = ev[f"{col}_pct"].to_numpy(float)
    defined = np.isfinite(v)
    treated = defined & ((v >= Q_HIGH) if high else (v <= Q_LOW))
    return treated, defined


# ── statistics ──


def _lift(v: np.ndarray) -> float:
    t, tail = v >= 2, (v % 2) == 1
    if t.all() or not t.any():
        return float("nan")
    base = tail[~t].mean()
    return float(tail[t].mean() / base) if base > 0 else float("nan")


def _gap(v: np.ndarray) -> float:
    t = v > GROUP_OFFSET / 2
    if t.all() or not t.any():
        return float("nan")
    return float((v[t] - GROUP_OFFSET).mean() - v[~t].mean())


def score(blk: pd.DataFrame, treat: np.ndarray, ok: np.ndarray) -> dict[str, object]:
    """Funnel, tail lift, money gap, matched null and right-driver figures for one block."""
    d = blk[ok]
    t = treat[ok]
    res: dict[str, object] = {
        "events": int(len(blk)),
        "defined": int(ok.sum()),
        "treated": int(t.sum()),
        "tails_treated": int(d["tail"][t].sum()),
        "tails_untreated": int(d["tail"][~t].sum()),
    }
    if t.sum() < 5 or (~t).sum() < 5:
        res["note"] = "too few treated or untreated to score"
        return res
    lv = d["tail"].to_numpy(int) + 2 * t.astype(int)
    lift = date_clustered_ci(lv.astype(float), d["entry_date"], _lift)
    hasb = np.isfinite(d["B"].to_numpy(float))
    bv = d["B"].to_numpy(float)[hasb] + GROUP_OFFSET * t[hasb]
    gap = date_clustered_ci(bv, d["entry_date"].to_numpy()[hasb], _gap)
    null = matched_random_null(d["B"].to_numpy(float)[hasb], ~t[hasb], np.mean)
    res.update(
        tail_rate_treated=float(d["tail"][t].mean()),
        tail_rate_untreated=float(d["tail"][~t].mean()),
        lift=[lift.point, lift.low, lift.high],
        gap=[gap.point, gap.low, gap.high],
        n_B=int(hasb.sum()),
        kept_mean_B=float(d["B"][~t].mean()),
        all_mean_B=float(d["B"].mean()),
        null_pct_kept=null.percentile,
        premium=[float(d["premium"][t].mean()), float(d["premium"][~t].mean())],
        implied_move=[float(d["im"][t].mean()), float(d["im"][~t].mean())],
        passes=bool(lift.low > 1 and gap.high < 0),
    )
    return res


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ch = load_chars()
    ev = attach_chars(load_events(), ch)

    flags: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    flags["T1_peer_shock"] = peer_shock(ev, ch)
    flags["T2_oscore"] = pct_flag(ev, "o_score", high=True)
    flags["T3_zscore"] = pct_flag(ev, "z_score", high=False)
    flags["T4_off_high"] = pct_flag(ev, "prc_highprc_252d", high=False)
    flags["T5_earn_var"] = pct_flag(ev, "earnings_variability", high=True)
    flags["T6_own_hist"] = own_history(ev)
    all_def = np.logical_and.reduce([flags[k][1] for k in TRIALS])
    count = np.sum([flags[k][0] for k in TRIALS], axis=0)
    flags["T7_flag_count"] = (all_def & (count >= 2), all_def)

    results: dict[str, dict[str, object]] = {}
    for name, (treat, ok) in flags.items():
        results[name] = {}
        alive = True
        for bname, (lo, hi) in BLOCKS.items():
            m = ((ev["entry_date"] >= lo) & (ev["entry_date"] <= hi)).to_numpy()
            blk = ev[m]
            r = score(blk, treat[m], ok[m])
            r["scored_as_gate"] = alive
            results[name][bname] = r
            fmt: Callable[[list[float]], str] = lambda x: f"{x[0]:+.3f} [{x[1]:+.3f}, {x[2]:+.3f}]"
            line = f"{name:15s} {bname:12s} def {r['defined']:5d} treat {r['treated']:5d}"
            if "lift" in r:
                line += (
                    f" tail {r['tail_rate_treated']:.1%}/{r['tail_rate_untreated']:.1%}"
                    f" L {fmt(r['lift'])} G {fmt(r['gap'])} null {r['null_pct_kept']:.1f}"
                    f" prem {r['premium'][0]:.3f}/{r['premium'][1]:.3f}"
                    f" {'PASS' if r['passes'] else 'fail'}{'' if alive else ' (reported only)'}"
                )
            print(line)
            if bname != "confirmation":
                alive = alive and bool(r.get("passes", False))

    base = {
        b: {
            "events": int(((ev["entry_date"] >= lo) & (ev["entry_date"] <= hi)).sum()),
            "tail_rate": float(
                ev.loc[(ev["entry_date"] >= lo) & (ev["entry_date"] <= hi), "tail"].mean()
            ),
        }
        for b, (lo, hi) in BLOCKS.items()
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"base": base, "trials": results}, indent=2))
    print("base rates:", base)
    print(f"written {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
