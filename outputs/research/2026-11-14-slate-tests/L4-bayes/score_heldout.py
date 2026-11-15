"""
score_heldout.py
Lane L4 held-out scorer for the iteration round's frozen champion: runs the frozen model and its
frozen baseline once over 2013-26 (walk-forward: each outcome enters the posterior on the first
entry date after its expiry) and scores 2019-24 and 2025-26.

It refuses to run unless ``freeze_online_bayes.md`` verifies: the note's own SHA-256, this
file's, the model module's, ``l4lib``'s, ``l4iter``'s, the corrected panel's and
``search_log.csv``'s, and the frozen configurations against ``earnings_iv_crush/config.py``. A
second run needs ``--rerun-reason`` and is recorded in ``heldout_runs.jsonl``.

Primary (trials 3,013 and 3,014 for H_corr; 3,018 and 3,019 for residual_value): mean per-event
log predictive score, model minus baseline, date-clustered 95%. Secondary: calibration (PIT,
90% coverage), the selected book under the two declared rules against a date-stratified random
null and ``matched_random_null`` (3,015 and 3,016 for P(H > 0) > 0.5; 3,020 and 3,021 for the
expected-value rule), and the book gauge.

Basis: outcomes per trade, net at the touch, in % of m0; log scores in nats per event.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/score_heldout.py
    python outputs/research/2026-11-14-slate-tests/L4-bayes/score_heldout.py --rerun-reason "..."
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    date_clustered_ci,
    log_block_view,
    matched_random_null,
    per_trade_sharpe,
)

FREEZE = HERE / "freeze_online_bayes.md"
LOCK = HERE / "heldout_runs.jsonl"
OUT = HERE / "heldout_results.json"
TRIALS = HERE / "trials.csv"
HELDOUT = ("2019-24", "2025-26")
BLOCKS = ("2013-18", "2015-18", "2019-24", "2025-26")
TRIAL_IDS = {
    ("H_corr", "2019-24"): 3013,
    ("H_corr", "2025-26"): 3014,
    ("book_p", "2019-24"): 3015,
    ("book_p", "2025-26"): 3016,
    ("residual_value", "2019-24"): 3018,
    ("residual_value", "2025-26"): 3019,
    ("book_ev", "2019-24"): 3020,
    ("book_ev", "2025-26"): 3021,
}
TRIAL_FIELDS = ["trial_id", "idea", "rule", "block", "N", "statistic", "interval", "verdict"]
FROZEN = {
    "H_corr": ("ONLINE_BAYES_L4_MODEL", "ONLINE_BAYES_L4_BASELINE"),
    "residual_value": ("ONLINE_BAYES_L4_RV_MODEL", "ONLINE_BAYES_L4_RV_BASELINE"),
}
RULES = {"book_p": ("decide", "P(H_corr > 0) > 0.5"), "book_ev": ("decide_ev", "E[H_corr] > 0")}
NULL_PASS_PCT = 95.0  # declared selection-skill pass: date-stratified null percentile


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── freeze verification ──────────────────────────────────────────────────────


def verify_freeze() -> dict[str, Any]:
    """Check every hash and the frozen configurations; return the note's frozen JSON block."""
    raw = FREEZE.read_bytes()
    cut = raw.rfind(b"\nself_sha256: ")
    if cut < 0:
        raise ValueError("freeze note has no self_sha256 line")
    body, tail = raw[: cut + 1], raw[cut + 1 :].decode().strip()
    if hashlib.sha256(body).hexdigest() != tail.split(": ", 1)[1]:
        raise ValueError("freeze note changed after it was hashed")
    text = body.decode("utf-8")

    def field(name: str) -> str:
        m = re.search(rf"^{name}: ([0-9a-f]{{64}})$", text, re.M)
        if not m:
            raise ValueError(f"freeze note lacks {name}")
        return m.group(1)

    checks = {
        "scorer_sha256": Path(__file__).resolve(),
        "module_sha256": Path(ob.__file__).resolve(),
        "l4lib_sha256": HERE / "l4lib.py",
        "l4iter_sha256": HERE / "l4iter.py",
        "base_sha256": l4lib.BASE,
        "search_log_sha256": HERE / "search_log.csv",
    }
    for name, path in checks.items():
        if _sha(path) != field(name):
            raise ValueError(f"{path.name} does not match {name} in the freeze note")
    m = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not m:
        raise ValueError("freeze note lacks the frozen JSON block")
    frozen: dict[str, Any] = json.loads(m.group(1))
    for tname, (mname, bname) in FROZEN.items():
        for inst, key in ((mname, "model"), (bname, "baseline")):
            have = ob.describe_config(getattr(C, inst))
            want = {
                k: v for k, v in frozen[tname][key].items() if k not in ("group_level", "score")
            }
            if json.dumps(have, sort_keys=True) != json.dumps(want, sort_keys=True):
                raise ValueError(f"config.{inst} {have} differs from frozen {want}")
    return frozen


def _guard(rerun_reason: str | None) -> None:
    runs = LOCK.read_text(encoding="utf-8").splitlines() if LOCK.exists() else []
    if runs and not rerun_reason:
        raise PermissionError("held-out already read once; pass --rerun-reason")
    with LOCK.open("a", encoding="utf-8") as fh:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fh.write(json.dumps({"utc": stamp, "rerun_reason": rerun_reason}) + "\n")


# ── statistics ───────────────────────────────────────────────────────────────


def _diff_ci(values: np.ndarray, groups: np.ndarray, keys: np.ndarray) -> Any:
    """Selected minus unselected mean, date-clustered by resampling event indices by date."""
    v, g = np.asarray(values, float), np.asarray(groups, bool)

    def stat(idx: np.ndarray) -> float:
        i = idx.astype(int)
        a, b = v[i][g[i]], v[i][~g[i]]
        return float(a.mean() - b.mean()) if a.size and b.size else float("nan")

    return date_clustered_ci(np.arange(v.size, dtype=float), keys, stat)


def _fmt(ci: Any) -> str:
    return f"[{ci.low:+.4f}, {ci.high:+.4f}]"


def _block_mask(d: pd.DataFrame, block: str) -> np.ndarray:
    if block == "2015-18":
        return np.isin(d["entry_date"].dt.year.to_numpy(), l4iter.DISCOVERY_YEARS)
    return (d["block"] == block).to_numpy()


def _book(
    y: np.ndarray, rv: np.ndarray, sel: np.ndarray, keys: np.ndarray, label: str
) -> dict[str, Any]:
    book: dict[str, Any] = {"n_pool": int(sel.size), "n_selected": int(sel.sum())}
    pool = date_clustered_ci(y, keys, np.mean)
    book["pool_mean"] = [pool.point, pool.low, pool.high]
    if not 0 < sel.sum() < sel.size:
        print(f"    book [{label}]: selected {int(sel.sum())} of {sel.size}; no comparison")
        return book
    lv = date_clustered_ci(y[sel], keys[sel], np.mean)
    sh = date_clustered_ci(y[sel], keys[sel], per_trade_sharpe)
    strat = ob.date_stratified_null(y, sel, keys, n_draws=N_BOOT, seed=SEED)
    flat = matched_random_null(y, sel, np.mean)
    rvd = _diff_ci(rv, sel, keys)
    hd = _diff_ci(y, sel, keys)
    book.update(
        selected_mean=[lv.point, lv.low, lv.high],
        selected_sharpe_per_trade=[sh.point, sh.low, sh.high],
        null_pct_date_stratified=strat.percentile,
        null_median_date_stratified=float(np.median(strat.null)),
        null_pct_pool=flat.percentile,
        sel_minus_unsel_H=[hd.point, hd.low, hd.high],
        sel_minus_unsel_rv=[rvd.point, rvd.low, rvd.high],
        selection_pass=bool(strat.percentile >= NULL_PASS_PCT),
        economic_pass=bool(lv.low > 0),
        clusters_selected=lv.clusters,
    )
    print(
        f"    book [{label}]: selected {book['n_selected']} of {book['n_pool']}; mean H_corr "
        f"{lv.point:+.3f}% of m0 {_fmt(lv)} per trade, net at the touch; Sharpe per trade "
        f"{sh.point:+.3f} {_fmt(sh)}; pool {pool.point:+.3f}% {_fmt(pool)}\n"
        f"      date-stratified null pct {strat.percentile:.1f} (null median "
        f"{np.median(strat.null):+.3f}); pool null pct {flat.percentile:.1f}; selected minus "
        f"unselected H {hd.point:+.3f} {_fmt(hd)}, residual value {rvd.point:+.3f} {_fmt(rvd)}"
    )
    return book


def score_block(
    d: pd.DataFrame, rm: ob.OnlineRun, rb: ob.OnlineRun, block: str, tname: str
) -> dict[str, Any]:
    em, eb = rm.events, rb.events
    sc = (
        _block_mask(d, block)
        & em["scored"].to_numpy()
        & eb["scored"].to_numpy()
        & em["log_score"].notna().to_numpy()
        & eb["log_score"].notna().to_numpy()
    )
    keys = d["announce_date"].to_numpy()[sc]
    diff = (em["log_score"] - eb["log_score"]).to_numpy()[sc]
    ci = date_clustered_ci(diff, keys, np.mean)
    res: dict[str, Any] = {
        "block": block,
        "target": tname,
        "N": ci.n,
        "clusters": ci.clusters,
        "diff_mean": ci.point,
        "diff_low": ci.low,
        "diff_high": ci.high,
        "diff_median": float(np.median(diff)),
        "model_mean_log_score": float(em.loc[sc, "log_score"].mean()),
        "baseline_mean_log_score": float(eb.loc[sc, "log_score"].mean()),
        "pass": bool(ci.low > 0),
    }
    yr = d["entry_date"].dt.year.to_numpy()[sc]
    res["diff_by_year"] = {int(y): float(diff[yr == y].mean()) for y in np.unique(yr)}
    for tag, e in (("model", em), ("baseline", eb)):
        cov = date_clustered_ci(e.loc[sc, "covered"].to_numpy(float), keys, np.mean)
        pit = e.loc[sc, "pit"].to_numpy(float)
        ph = ob.pit_histogram(pit, C.ONLINE_BAYES.pit_bins)
        res[f"{tag}_coverage90"] = [cov.point, cov.low, cov.high]
        res[f"{tag}_pit_counts"] = ph["counts"]
        res[f"{tag}_pit_chi2_p_indep"] = ph["p_indep"]
        res[f"{tag}_pit_tails"] = [float((pit < 0.05).mean()), float((pit > 0.95).mean())]
    print(
        f"  [{tname} {block}] log score model minus baseline {ci} nats per event; median "
        f"{res['diff_median']:+.4f}; model {res['model_mean_log_score']:.4f}, baseline "
        f"{res['baseline_mean_log_score']:.4f} -> {'PASS' if res['pass'] else 'FAIL'}\n"
        f"    by year {json.dumps({k: round(v, 4) for k, v in res['diff_by_year'].items()})}\n"
        f"    90% coverage model {res['model_coverage90'][0]:.3f} "
        f"[{res['model_coverage90'][1]:.3f}, {res['model_coverage90'][2]:.3f}], baseline "
        f"{res['baseline_coverage90'][0]:.3f}; PIT tails (<5%, >95%) model "
        f"{res['model_pit_tails']}, baseline {res['baseline_pit_tails']}\n"
        f"    PIT model {res['model_pit_counts']}"
    )
    if tname != "H_corr":
        return res
    y = l4lib.target(d, "H_corr", C.ONLINE_BAYES)[sc]
    rv = d["residual_value"].to_numpy(float)[sc] * C.ONLINE_BAYES.pct_per_unit
    for key, (col, label) in RULES.items():
        res[key] = _book(y, rv, em[col].to_numpy(bool)[sc], keys, label)
    return res


def _gauge_summary(g: pd.DataFrame, label: str) -> dict[str, Any]:
    last = g.iloc[-1]
    crossed = g.loc[g["p_mean_pos_deff"] > 0.5, "date"]
    out = {
        "label": label,
        "date": str(pd.Timestamp(last["date"]).date()),
        "n_settled": int(last["n_settled"]),
        "intercept": float(last["intercept"]),
        "p_mean_pos": float(last["p_mean_pos"]),
        "ci": [float(last["ci_low"]), float(last["ci_high"])],
        "deff": float(last["deff"]),
        "p_mean_pos_deff": float(last["p_mean_pos_deff"]),
        "ci_deff": [float(last["ci_low_deff"]), float(last["ci_high_deff"])],
        "monitor_counts": g["monitor"].value_counts().to_dict(),
        "first_stop": str(g.loc[g["monitor"] == "stop", "date"].min()),
        "first_promote": str(g.loc[g["monitor"] == "promote", "date"].min()),
        "dates_above_half_deff": int(crossed.size),
        "first_above_half_deff": str(crossed.min()) if crossed.size else "never",
        "max_p_mean_pos_deff": float(g["p_mean_pos_deff"].max()),
    }
    print(
        f"  [gauge {label}] {out['date']}, N settled {out['n_settled']}: intercept "
        f"{out['intercept']:+.3f}, P(mean > 0) {out['p_mean_pos']:.3f} raw, 95% "
        f"[{out['ci'][0]:+.3f}, {out['ci'][1]:+.3f}]; with design effect {out['deff']:.2f}: "
        f"P {out['p_mean_pos_deff']:.3f}; dates above 0.5 {out['dates_above_half_deff']} "
        f"(max {out['max_p_mean_pos_deff']:.3f}); monitor {out['monitor_counts']}"
    )
    return out


def _book_mean_gauge(rb: ob.OnlineRun, d: pd.DataFrame, cfg: Any) -> pd.DataFrame:
    """Event-weighted book mean of settled H_corr through time, with a date-clustered interval.

    The interval is the analytic cluster-robust one (the sum of squared within-date residual
    sums), normal at 95%, so it can be recomputed on each of several hundred update dates; it
    is the monitor's companion to the intercept gauge, not a trial.
    """
    ev = rb.events
    y = l4lib.target(d, "H_corr", cfg)
    upd = ev["update_date"]
    clus = d["announce_date"].to_numpy()
    rows = []
    for t in np.sort(upd.dropna().unique()):
        m = (upd <= t).to_numpy() & np.isfinite(y)
        yy = y[m]
        mu = float(yy.mean())
        _, inv = np.unique(clus[m], return_inverse=True)
        g = np.bincount(inv, weights=yy - mu)
        se = float(np.sqrt((g * g).sum()) / yy.size)
        rows.append({"date": pd.Timestamp(t), "n": int(yy.size), "mean": mu,
                     "low": mu - 1.96 * se, "high": mu + 1.96 * se})  # fmt: skip
    return pd.DataFrame(rows)


def _trial(row: dict[str, Any]) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rerun-reason")
    args = ap.parse_args(argv)
    frozen = verify_freeze()
    print("[freeze] note, scorer, module, l4lib, l4iter, panel, search log and configs verified")
    _guard(args.rerun_reason)
    d = l4iter.load_all()
    D = l4iter.Design(d)
    results: dict[str, Any] = {"frozen": frozen, "blocks": {}, "gauge": {}}
    for tname, (mname, bname) in FROZEN.items():
        mcfg, bcfg = getattr(C, mname), getattr(C, bname)
        mlv, blv = frozen[tname]["model"]["group_level"], frozen[tname]["baseline"]["group_level"]
        fam = "hedged_hold_H_corr" if tname == "H_corr" else "residual_value"
        for blk in HELDOUT:
            log_block_view(
                l4lib.BLOCKS_VIEWED,
                panel="base_corrected",
                period=blk,
                outcome_family=fam,
                feature_family="online_bayes_iteration_round_1",
                viewed_by=f"L4 score_heldout ({tname}, frozen champion)",
                kind="trial",
            )
        y = l4lib.target(d, tname, mcfg)
        rm = D.run(mcfg, y, with_features=True, group_level=mlv, quiet=False)
        rb = D.run(bcfg, y, with_features=False, group_level=blv, quiet=False)
        disc = l4iter.score(rm, d, l4iter.discovery_mask(d, D.usable, y))
        results[f"{tname} discovery reproduced"] = disc["mean_log_score"]
        print(
            f"  [{tname}] discovery 2015-18 mean log score reproduced {disc['mean_log_score']:+.5f}"
            f" (search {frozen[tname]['model']['score']:+.5f})"
        )
        for blk in BLOCKS:
            results["blocks"][f"{tname} {blk}"] = score_block(d, rm, rb, blk, tname)
        keep = ["ticker", "entry_date", "expiry", "block", "announce_date"]
        ev = d[keep].join(rm.events.add_prefix("m_")).join(rb.events.add_prefix("b_"))
        ev.join(rm.deltas).to_parquet(HERE / f"run_{tname}.parquet")
        rm.path.to_csv(HERE / f"coef_path_{tname}.csv", index=False)
        rm.gauge.to_csv(HERE / f"gauge_model_{tname}.csv", index=False)
        rb.gauge.to_csv(HERE / f"gauge_baseline_{tname}.csv", index=False)
        if tname == "H_corr":
            results["gauge"]["baseline"] = _gauge_summary(rb.gauge, "baseline intercept")
            results["gauge"]["model"] = _gauge_summary(rm.gauge, "model intercept")
            bm = _book_mean_gauge(rb, d, bcfg)
            bm.to_csv(HERE / "gauge_book_mean.csv", index=False)
            last = bm.iloc[-1]
            results["gauge"]["book_mean_event_weighted"] = {
                "date": str(last["date"].date()),
                "n": int(last["n"]),
                "mean": float(last["mean"]),
                "ci": [float(last["low"]), float(last["high"])],
                "dates_low_above_zero": int((bm["low"] > 0).sum()),
            }
            fs = list(ob.FEATURE_SETS[mcfg.feature_set])
            fm = D.raw[mcfg.feature_set][fs].to_numpy(float)
            ps = D.raw["declared"]["premium_share"].to_numpy(float)
            gmap = {}
            if mlv != "none":
                gmap = {
                    str(t): g for t, g in zip(d["ticker"], D.ind[mlv], strict=True) if g is not None
                }
            meta = {
                "config": asdict(mcfg),
                "group_level": mlv,
                "group_map": gmap,
                "feature_mean": np.nanmean(fm, axis=0).tolist(),
                "feature_sd": np.nanstd(fm, axis=0, ddof=1).tolist(),
                "premium_share_pow_mean": float(np.nanmean(ps**mcfg.variance_power)),
                "asof": str(d["entry_date"].max().date()),
                "coef_names": D.coef_names(mcfg),
            }
            rm.state.to_npz(HERE / "posterior_frozen.npz", meta)
    OUT.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    for (kind, blk), tid in TRIAL_IDS.items():
        if kind in RULES:
            b = results["blocks"][f"H_corr {blk}"][kind]
            if "selected_mean" not in b:
                continue
            _trial(
                {
                    "trial_id": tid,
                    "idea": "L4 selected book (frozen champion)",
                    "rule": f"trade if {RULES[kind][1]}",
                    "block": blk,
                    "N": f"{b['n_selected']} of {b['n_pool']}",
                    "statistic": f"selected mean H_corr {b['selected_mean'][0]:+.4f} % of m0 "
                    f"per trade; date-stratified null pct {b['null_pct_date_stratified']:.1f}",
                    "interval": f"[{b['selected_mean'][1]:+.4f}, {b['selected_mean'][2]:+.4f}]",
                    "verdict": ("pass" if b["selection_pass"] and b["economic_pass"] else "fail")
                    + " (exploratory)",
                }
            )
            continue
        r = results["blocks"][f"{kind} {blk}"]
        _trial(
            {
                "trial_id": tid,
                "idea": f"L4 log predictive score ({kind}, frozen champion)",
                "rule": "frozen model minus frozen baseline, nats per event",
                "block": blk,
                "N": r["N"],
                "statistic": f"{r['diff_mean']:+.5f}",
                "interval": f"[{r['diff_low']:+.5f}, {r['diff_high']:+.5f}]",
                "verdict": ("pass" if r["pass"] else "fail") + " (exploratory)",
            }
        )
    print(f"written {OUT.name}, run_*.parquet, coef_path_*.csv, gauge_*.csv, posterior_frozen.npz")


if __name__ == "__main__":
    main()
