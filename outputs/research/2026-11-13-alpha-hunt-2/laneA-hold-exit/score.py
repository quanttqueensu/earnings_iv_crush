"""
score.py
Score lane-A trials on one simulated block and append them to ``trials.csv``.

Every rule maps each event to a per-trade outcome in units of m0, net at the touch, from the
columns of ``sim_<y0>_<y1>.parquet``. A decision rule picks, at the reaction-session close, between
the hedged hold (H) and the 15:59 buy-back (B); its null is the participation-matched random
choice of the same number of buy-backs (``matched_random_null`` on B - H). Hedge-mechanics variants
change H itself and have no selection null.

Trial specs (hypothesis and mechanism) are written in ``SPECS`` before the trial is scored; a spec
is never edited after its row exists in ``trials.csv``.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneA-hold-exit/score.py --block 2013 2018 \
        --trials 1781 1782
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci, matched_random_null  # noqa: E402

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
BASIS = "per trade, unit m0, net at the touch"
COLS = [
    "trial_id", "hypothesis", "mechanism", "block", "N", "effect", "ci_low", "ci_high", "t",
    "null_pct", "basis", "verdict", "level", "level_low", "level_high", "vs_B", "vs_B_low",
    "vs_B_high", "n_buyback", "label",
]


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def implied_move(d: pd.DataFrame) -> pd.Series:
    fwd0 = (d["m0"] - d["s0"]) / 0.20
    return d["mid0"] / fwd0


def decide(mask: pd.Series) -> Callable[[pd.DataFrame], pd.Series]:
    """Wrap a buy-back mask into an outcome: B where the mask fires, H elsewhere."""

    def f(d: pd.DataFrame) -> pd.Series:
        m = mask(d).fillna(False).astype(bool)
        return d["B"].where(m, d["H"]).rename("_buy").to_frame().assign(_m=m)

    return f


# ── trial specs: hypothesis, mechanism, rule ────────────────────────────────

SPECS: dict[int, dict] = {
    1781: dict(
        hyp="Buy back at the reaction close when the remaining extrinsic (straddle mid minus "
        "intrinsic at the parity forward) is below the exit half-spread; hold otherwise.",
        mech="Lead's candidate: nothing left to collect. Prior stated before scoring: holding saves "
        "the half-spread whatever the extrinsic, and small extrinsic means little gamma at risk, "
        "so this should LOSE to always holding.",
        rule=decide(lambda d: d["two_sided"].astype(bool) & (d["extr_mid"] < d["exit_ask"] - d["exit_mid"])),
        kind="decision",
    ),
    1782: dict(
        hyp="Buy back when the straddle's implied vol at the reaction-close ask is below a causal "
        "HAR forecast of realised vol over the remaining life; hold otherwise.",
        mech="Hold-or-buy is a price comparison: buying back costs the ask, holding costs the "
        "realised hedged payoff, whose expectation is the straddle valued at realised vol. Buy "
        "only when the ask is cheaper than expected realised cost. Predicts R - H > 0.",
        rule=decide(lambda d: d["iv_ask"] < d["rv_f"]),
        kind="decision",
    ),
    1783: dict(
        hyp="Close the in-the-money leg at its reaction-close ask and hold the out-of-the-money "
        "leg delta-hedged to expiry.",
        mech="Lead's candidate: the ITM leg is mostly intrinsic and delta, so its hedge is costly. "
        "Prior: by parity both legs carry the same extrinsic, and the ITM leg's dollar spread is "
        "the wider, so this pays the larger spread to give up half the theta. Predicts < H.",
        rule=lambda d: d["oto"].fillna(d["H"]),
        kind="mechanics",
    ),
    1784: dict(
        hyp="Close the out-of-the-money leg at its reaction-close ask and hold the in-the-money "
        "leg delta-hedged to expiry.",
        mech="The OTM leg's dollar spread is the narrower; holding the ITM leg keeps the same "
        "extrinsic as the OTM leg (parity). Predicts between B and H, above B.",
        rule=lambda d: d["ito"].fillna(d["H"]),
        kind="mechanics",
    ),
    1785: dict(
        hyp="Modelled stop: buy back the first close after the reaction close at which the "
        "post-reaction hedged loss exceeds 10% of m0.",
        mech="Post-shock vol clusters, so a straddle losing on the hedge is in a high-RV regime "
        "and the remaining gamma is worth cutting. Modelled at the reaction-close IV, which "
        "understates post-shock repricing and so flatters the stop.",
        rule=lambda d: d["stop10"],
        kind="mechanics",
    ),
    1786: dict(
        hyp="Rebalance the hedge only when the target straddle delta drifts by more than 0.05.",
        mech="Daily rebalancing pays the equity half-spread on noise; a band cuts equity cost "
        "(about 0.36% of m0 per trade) at the price of extra variance with zero-mean gamma P&L.",
        rule=lambda d: d["band05"],
        kind="mechanics",
    ),
    1787: dict(hyp="As 1786 with a 0.10 band.", mech="As 1786.", rule=lambda d: d["band10"],
               kind="mechanics"),
    1788: dict(hyp="As 1786 with a 0.20 band.", mech="As 1786.", rule=lambda d: d["band20"],
               kind="mechanics"),
    1789: dict(hyp="Rebalance every second session.", mech="As 1786, by clock.",
               rule=lambda d: d["freq2"], kind="mechanics"),
    1790: dict(hyp="Rebalance every fifth session.", mech="As 1786, by clock.",
               rule=lambda d: d["freq5"], kind="mechanics"),
    1791: dict(
        hyp="Hedge ratio from the causal HAR realised-vol forecast instead of implied vol.",
        mech="When implied exceeds realised vol, the realised-vol delta is the closer to the "
        "true delta of the payoff the holder actually faces (Ahmad and Wilmott 2005), giving "
        "a smoother path; expected P&L change near zero, some cost change.",
        rule=lambda d: d["rvdelta"].fillna(d["H"]),
        kind="mechanics",
    ),
    1792: dict(hyp="Hedge ratio from the mean of implied and HAR vols.", mech="As 1791.",
               rule=lambda d: d["mixdelta"].fillna(d["H"]), kind="mechanics"),
    1793: dict(hyp="Modelled stop at 5% of m0.", mech="As 1785.", rule=lambda d: d["stop05"],
               kind="mechanics"),
    1794: dict(hyp="Modelled stop at 20% of m0.", mech="As 1785.", rule=lambda d: d["stop20"],
               kind="mechanics"),
    1795: dict(
        hyp="Buy back at the reaction close when the reaction move exceeds twice the entry "
        "implied move (straddle mid over forward); hold otherwise.",
        mech="A large surprise raises post-event realised vol (vol clustering after shocks), "
        "which the reaction-close IV may underprice. Sign uncertain: the IV also reprices.",
        rule=decide(lambda d: d["abs_move"] > 2 * implied_move(d)),
        kind="decision",
    ),
    # ── round 2 (specs written after the round-1 diagnosis, before scoring) ──
    1796: dict(
        hyp="As 1782, with the HAR forecast scaled by a causal bias factor: the median of "
        "realised post-reaction vol over the HAR forecast across strictly earlier events whose "
        "expiry had passed before this reaction session (burn-in 200; hold until then).",
        mech="Round-1 diagnosis: realised post-reaction vol runs about 0.85 of the HAR forecast, "
        "so 1782 bought back options that were not cheap. Correcting the bias should cut the "
        "false buy-backs. Discovery-derived (the bias was read off the discovery block).",
        rule=decide(lambda d: d["iv_ask"] < d["rv_f"] * d["bias_c"]),
        kind="decision",
        label="exploratory, discovery-derived",
    ),
    1797: dict(
        hyp="Buy back when the front straddle's implied vol at the reaction-close ask is below "
        "the second post-event expiry's ATM mid implied vol (s2_iv); hold otherwise.",
        mech="Round-1 diagnosis: the second expiry's post-event IV forecasts the remaining "
        "realised vol best (log corr 0.32 against 0.25 for HAR). A front ask below the market's "
        "own post-event vol means the remaining option is cheap. Discovery-derived choice of "
        "forecast.",
        rule=decide(lambda d: d["iv_ask"] < d["s2_iv"]),
        kind="decision",
        label="exploratory, discovery-derived",
    ),
    1798: dict(
        hyp="Stack the two best round-1 mechanics: hold with a 0.10 delta band, and buy back "
        "where 1797 fires.",
        mech="Each recovers a separate cost (equity rebalancing, buying the rich remaining "
        "option); if both are real the gains add. Discovery-derived.",
        rule=lambda d: d["B"].where((d["iv_ask"] < d["s2_iv"]).fillna(False), d["band10"]),
        kind="mechanics",
        label="exploratory, discovery-derived",
    ),
}


def add_bias(d: pd.DataFrame, hist: pd.DataFrame, min_prior: int = 200) -> pd.DataFrame:
    """Causal bias factor: median rv_post / rv_f over events with expiry before this exit date."""
    h = hist.dropna(subset=["rv_post", "rv_f"])
    h = h[(h["rv_f"] > 0) & (h["n_hedge"] > 0)].sort_values("expiry")
    ex = pd.to_datetime(h["expiry"]).to_numpy()
    ratio = (h["rv_post"] / h["rv_f"]).to_numpy(float)
    c = []
    for t in pd.to_datetime(d["exit_date"]).to_numpy():
        k = int(np.searchsorted(ex, t, side="left"))  # expiry strictly before the reaction day
        c.append(float(np.median(ratio[:k])) if k >= min_prior else np.nan)
    n_un = int(np.isnan(c).sum())
    print(f"  bias factor: {n_un} of {len(d)} events in burn-in (rule holds there)")
    return d.assign(bias_c=c)


def _t(iv) -> float:
    se = (iv.high - iv.low) / (2 * 1.96)
    return float(iv.point / se) if se > 0 else float("nan")


def score_one(tid: int, d: pd.DataFrame, block: str) -> dict:
    sp = SPECS[tid]
    out = sp["rule"](d)
    if isinstance(out, pd.DataFrame):
        r, m = out["_buy"], out["_m"]
    else:
        r, m = out, None
    if r.isna().any():
        raise ValueError(f"trial {tid}: {int(r.isna().sum())} NaN outcomes")
    dates = pd.to_datetime(d["exit_date"])
    lev = date_clustered_ci(r.to_numpy(float), dates, _mean)
    dh = date_clustered_ci((r - d["H"]).to_numpy(float), dates, _mean)
    db = date_clustered_ci((r - d["B"]).to_numpy(float), dates, _mean)
    null_pct, nb = float("nan"), ""
    if m is not None:
        nb = int(m.sum())
        if 0 < nb < len(d):
            nc = matched_random_null((d["B"] - d["H"]).to_numpy(float), m.to_numpy(), _mean)
            null_pct = nc.percentile
    verdict = (
        "beats H" if dh.low > 0 else ("loses to H" if dh.high < 0 else "no difference from H")
    )
    verdict += "; book " + ("positive" if lev.low > 0 else "negative" if lev.high < 0 else "~0")
    return {
        "trial_id": tid, "hypothesis": sp["hyp"], "mechanism": sp["mech"], "block": block,
        "N": len(d), "effect": dh.point, "ci_low": dh.low, "ci_high": dh.high, "t": _t(dh),
        "null_pct": null_pct, "basis": BASIS + "; effect = R - H paired", "verdict": verdict,
        "level": lev.point, "level_low": lev.low, "level_high": lev.high, "vs_B": db.point,
        "vs_B_low": db.low, "vs_B_high": db.high, "n_buyback": nb,
        "label": sp.get("label", "exploratory (discovery block)"),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", type=int, nargs=2, required=True)
    ap.add_argument("--trials", type=int, nargs="+", required=True)
    ap.add_argument("--label", default=None)
    a = ap.parse_args(argv)
    y0, y1 = a.block
    d = pd.read_parquet(HERE / f"sim_{y0}_{y1}.parquet")
    rvp = sorted(HERE.glob("rvpost_*.parquet"))
    if rvp:
        hist = pd.concat([pd.read_parquet(p) for p in rvp]).drop_duplicates(["ticker", "entry_date"])
        d = d.merge(hist[["ticker", "entry_date", "rv_post"]], on=["ticker", "entry_date"],
                    how="left", validate="1:1")
        d = add_bias(d, hist)
    block = f"{y0}-{y1}"
    done = set()
    if TRIALS.exists():
        prev = pd.read_csv(TRIALS)
        done = set(zip(prev["trial_id"].astype(str), prev["block"].astype(str), strict=True))
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        for tid in a.trials:
            if (str(tid), block) in done:
                raise SystemExit(f"trial {tid} already scored on {block}; a re-score is a new id")
            row = score_one(tid, d, block)
            if a.label:
                row["label"] = a.label
            w.writerow(row)
            fh.flush()
            print(
                f"{tid} {block} N={row['N']} R-H {row['effect']:+.4f} "
                f"[{row['ci_low']:+.4f},{row['ci_high']:+.4f}] t={row['t']:+.2f} "
                f"null {row['null_pct']:.1f} | level {row['level']:+.4f} "
                f"[{row['level_low']:+.4f},{row['level_high']:+.4f}] | R-B {row['vs_B']:+.4f} "
                f"[{row['vs_B_low']:+.4f},{row['vs_B_high']:+.4f}] buyback {row['n_buyback']}"
            )


if __name__ == "__main__":
    main()
