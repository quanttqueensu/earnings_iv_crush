"""
score_heldout.py
Lane E2: the single held-out read (entries 2025-01-01 to 2026-12-31, broad_2025_2026 pre files)
of the rules frozen in freeze_2026-11-14_reversed_delta_flow.md. Written before the freeze note; the
note records this file's SHA-256 and the run refuses to start if either hash has changed.

Frozen rules
------------
2,721 (primary): long the bottom causal quintile of S_delta, short the top quintile.
2,722 (secondary): the same book restricted to events with |K / F(15:50) - 1| <= 2%, with the
breakpoints built from every event.
S_delta (diagnosis.log entry 5), the window (15:00 to 15:50 on the entry session), the 10-signed-contract floor, the quintile
burn-in (200 events, breakpoints from strictly earlier entry dates, discovery events included),
the outcome (15:59 parity forwards, rule (a) of diagnosis.log entry 3) and the cost (stock
half-spread + 1 bp per side; half-spread = the name's 90th-percentile CRSP closing half-spread in
2024, else 3 bp) are as in diagnosis.log entries 1 to 5.

Pass (each rule): date-clustered 95% interval of the mean net return per position above zero and
the observed mean at or above the 95th percentile of both nulls (random direction, matched).
Two rules are read, so a Bonferroni reading at 97.5% is reported beside the 95% one.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/score_heldout.py
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import lib
import score_discovery as sd
import variants as va
from earnings_iv_crush.research.protocol import block_is_clean, date_clustered_ci, log_block_view

FREEZE = lib.HERE / "freeze_2026-11-14_reversed_delta_flow.md"
RESULT = lib.HERE / "heldout_result.json"
LANE_BLOCKS = lib.HERE / "lane_blocks.csv"
GLOBAL_BLOCKS = lib.ROOT / "research" / "ledger" / "blocks.csv"
PANEL, PERIOD = "flow_atm_ticks", "2025-01-01..2026-12-31"
OUTCOME_FAMILY, FEATURE_FAMILY = "stock_direction_next_session", "signed_atm_option_flow"
ZERO = "0" * 64


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze() -> None:
    if RESULT.exists():
        raise SystemExit("held-out already read (heldout_result.json exists); one read only")
    text = FREEZE.read_text(encoding="utf-8")
    m_self = re.search(r"self_sha256: ([0-9a-f]{64})", text)
    m_scr = re.search(r"scorer_sha256: ([0-9a-f]{64})", text)
    if not (m_self and m_scr):
        raise SystemExit("freeze note lacks its hashes")
    blank = text.replace(m_self.group(1), ZERO)
    if hashlib.sha256(blank.encode("utf-8")).hexdigest() != m_self.group(1):
        raise SystemExit("freeze note changed after freezing")
    if _sha(lib.HERE / "score_heldout.py") != m_scr.group(1):
        raise SystemExit("scorer changed after freezing")
    for name in ("lib.py", "score_discovery.py", "variants.py", "build_features.py"):
        m = re.search(rf"{re.escape(name)}: ([0-9a-f]{{64}})", text)
        if not m or _sha(lib.HERE / name) != m.group(1):
            raise SystemExit(f"{name} changed after freezing")
    print("freeze verified")


def _fwds(rec: dict) -> dict:
    return sd._fwds(rec)


def half_spreads(tickers: list[str]) -> dict[str, float]:
    pm = lib.permno_map()
    c = lib.load_crsp().reset_index()
    c = c[c["date"].dt.year == 2024]
    out = {}
    for t in tickers:
        p = pm.get(t)
        g = c[c["permno"] == p]["half"].dropna() if p is not None else pd.Series(dtype=float)
        out[t] = float(g.quantile(0.90)) if len(g) >= 20 else lib.DEFAULT_HALF_BPS / 1e4
    n_def = sum(1 for t in tickers if out[t] == lib.DEFAULT_HALF_BPS / 1e4)
    print(f"cost: {len(tickers)} names, {n_def} on the 3 bp default (no 2024 CRSP history)")
    return out


def main() -> None:
    verify_freeze()
    clean, hits = block_is_clean(GLOBAL_BLOCKS, panel=PANEL, period=PERIOD,
                                 outcome_family=OUTCOME_FAMILY, feature_family=FEATURE_FAMILY)
    print(f"block_is_clean (global ledger): {clean}; clashes {len(hits)}")
    if LANE_BLOCKS.exists():
        c2, h2 = block_is_clean(LANE_BLOCKS, panel=PANEL, period=PERIOD,
                                outcome_family=OUTCOME_FAMILY, feature_family=FEATURE_FAMILY)
        if not c2:
            raise SystemExit("held-out block already viewed by this lane")

    # features (signals only) for the held-out block
    if not (lib.HERE / "features_heldout.parquet").exists():
        subprocess.run([sys.executable, str(lib.HERE / "build_features.py"), "--block", "heldout"],
                       check=True, cwd=lib.HERE)
    fh = pd.read_parquet(lib.HERE / "features_heldout.parquet")
    print("funnel: held-out feature status", fh["status"].value_counts().to_dict())
    fh = fh[fh["status"] == "ok"].copy()

    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(_fwds, fh[["ticker", "entry_date", "exit_date", "expiry"]]
                             .to_dict("records"), chunksize=8))
    o = pd.DataFrame(rows)
    print("funnel: entry forward", o["st_e"].value_counts().to_dict(),
          "| exit forward", o["st_x"].value_counts().to_dict())
    o["R_prim"] = o["F_x"] / o["F_e"] - 1
    fh = fh.merge(o[["ticker", "entry_date", "R_prim"]], on=["ticker", "entry_date"], how="left")
    hs = half_spreads(sorted(fh["ticker"].unique()))
    fh["cost"] = 2 * (fh["ticker"].map(hs) + lib.EXTRA_BPS / 1e4)
    fh["block"] = "heldout"

    # causal breakpoints: discovery events are strictly earlier and enter the burn-in history
    fh = lib.add_delta_signal(fh)
    cols = ["ticker", "entry_date", "S_delta", "moneyness", "n_signed", "R_prim", "cost", "block"]
    fd = lib.add_delta_signal(sd.frame("R_co"))
    fd["block"] = "discovery"
    allx = pd.concat([fd[cols], fh[cols]], ignore_index=True)
    allx = allx.sort_values("entry_date", kind="stable").reset_index(drop=True)
    v = allx["S_delta"].where(allx["n_signed"] >= lib.MIN_SIGNED)
    from earnings_iv_crush.research.hedged_hold import causal_bins

    allx["bin"] = causal_bins(v.to_numpy(), allx["entry_date"], lib.N_BINS, lib.MIN_PRIOR)
    h = allx[allx["block"] == "heldout"].copy()
    print(f"funnel: held-out events {len(h)}, with signal {int((h['bin'] >= 0).sum())}, "
          f"with outcome {int(h['R_prim'].notna().sum())}")
    nos = h["R_prim"].isna() & (h["bin"] >= 0)
    print(f"attrition: {int(nos.sum())} signalled events without an outcome")
    log_block_view(LANE_BLOCKS, panel=PANEL, period=PERIOD, outcome_family=OUTCOME_FAMILY,
                   feature_family=FEATURE_FAMILY, viewed_by="E2 trials 2,721 and 2,722 held-out",
                   kind="trial")
    pool = h[(h["bin"] >= 0) & h["R_prim"].notna()]
    out: dict = {}
    full_pool = pool
    for tid in (2721, 2722):
        pool = full_pool if tid == 2721 else full_pool[full_pool["moneyness"].abs() <= 0.02]
        pos = pool[pool["bin"].isin([0, lib.N_BINS - 1])]
        s = np.where(pos["bin"] == 0, 1.0, -1.0)
        net = s * pos["R_prim"].to_numpy() - pos["cost"].to_numpy()
        m = lib.mean_ci(net, pos["entry_date"])
        m975 = date_clustered_ci(net, pos["entry_date"], stat=np.mean, n_boot=lib.N_DRAW,
                                 seed=lib.SEED, ci=0.975)
        sh = lib.sharpe_ci(net, pos["entry_date"])
        nl, ns = int((s > 0).sum()), int((s < 0).sum())
        p_dir = lib.null_random_direction(None, pos["R_prim"].to_numpy(), pos["cost"].to_numpy(),
                                          m.point)
        p_mat = lib.null_matched(pool["R_prim"].to_numpy(), pool["cost"].to_numpy(), nl, ns,
                                 m.point)
        sdb = (m.high - m.low) / (2 * 1.96)
        passed = bool(m.low > 0 and p_dir >= 95 and p_mat >= 95)
        res = {"n": len(pos), "n_long": nl, "n_short": ns, "clusters": m.clusters,
               "effect": m.point, "ci_low": m.low, "ci_high": m.high, "ci975_low": m975.low,
               "ci975_high": m975.high, "t": m.point / sdb, "sharpe": sh.point,
               "sharpe_lo": sh.low, "sharpe_hi": sh.high,
               "gross": float(np.mean(s * pos["R_prim"].to_numpy())),
               "cost_rt": float(pos["cost"].mean()), "null_dir_pct": p_dir,
               "null_matched_pct": p_mat, "pass_95": passed,
               "pass_bonferroni": bool(m975.low > 0 and p_dir >= 97.5 and p_mat >= 97.5)}
        out[str(tid)] = res
        print(f"{tid} held-out: N={res['n']} ({nl}L/{ns}S, {m.clusters} dates) net "
              f"{m.point*100:+.3f}% [{m.low*100:+.3f}, {m.high*100:+.3f}] (97.5%: "
              f"[{m975.low*100:+.3f}, {m975.high*100:+.3f}]) t {res['t']:+.2f} | Sharpe "
              f"{sh.point:+.3f} [{sh.low:+.3f}, {sh.high:+.3f}] | gross {res['gross']*100:+.3f}% "
              f"cost {res['cost_rt']*1e4:.1f} bp rt | null dir {p_dir:.1f} matched {p_mat:.1f} "
              f"| pass {passed}")
        lib.log_trial({"trial_id": tid, "hypothesis": va.SPEC[tid], "block":
                       "held-out 2025-01-01..2026-12-31 (broad_2025_2026)", "n": res["n"],
                       "effect": f"{m.point:.6f}", "ci_low": f"{m.low:.6f}",
                       "ci_high": f"{m.high:.6f}", "t": f"{res['t']:.2f}",
                       "sharpe": f"{sh.point:.4f}", "null_dir_pct": f"{p_dir:.1f}",
                       "null_matched_pct": f"{p_mat:.1f}", "basis": sd.BASIS,
                       "verdict": "PASS" if passed else "FAIL",
                       "label": "held-out, single read after freeze"})
    q = full_pool.groupby("bin")["R_prim"].agg(["count", "mean"])
    print("held-out gross next-session return by causal quintile (descriptive):",
          {int(k): (int(r["count"]), round(r["mean"] * 100, 3)) for k, r in q.iterrows()})
    out["quintiles"] = {int(k): [int(r["count"]), float(r["mean"])] for k, r in q.iterrows()}
    RESULT.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"wrote {RESULT.name}")


if __name__ == "__main__":
    main()
