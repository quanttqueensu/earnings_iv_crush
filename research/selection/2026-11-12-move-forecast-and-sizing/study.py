"""
study.py
Forecasting the size of the earnings move, and sizing the book on it (trials 1,623 to 1,628).

Part A asks whether non-price information forecasts the log absolute reaction better than the
implied move alone, walk-forward out of sample. Part B compares six sizing schemes for the
unconditional next-day buy-back book on per-date Sharpe and scale-free tail statistics, against
the live rule of fixed contracts. Scores ``prereg.md`` exactly as frozen; every run is a trial.

Usage
-----
    python research/selection/2026-11-12-move-forecast-and-sizing/study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci, verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name

EVENTS = ROOT / "outputs/research/2026-11-02-hedged-event-hold/events.parquet"
CONFIRM = ROOT / "outputs/research/2026-11-02-hedged-event-hold/events_confirm_2025_26.parquet"
FEATURES = ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
CHARS = Path.home() / "FIAM_Hackathon_2026/temp/chars_final_with_names.parquet"

# ── frozen parameters (prereg) ──
COST_IN, COST_OUT = 0.012714, 0.030182  # measured 15:59 cost per side, fraction of the mark
FEE = 0.0065  # USD per share per leg (0.65 per contract)
MOVE_FLOOR = 0.001  # floor on |move| before logs
CHARS_MAX_AGE_D = 62
HIST_N, HIST_MIN = 8, 4
FIRST_OOS_YEAR = 2016
A_BLOCKS = {"2016-2024": (2016, 2024), "2025-26": (2025, 2026)}
B_BLOCKS = {
    "2016-2020": (2016, 2020),
    "2021-2024": (2021, 2024),
    "2025-26": (2025, 2026),
    "2016-2024": (2016, 2024),
}
CHAR_COLS = ["me", "rvol_21d", "ivol_capm_21d", "turnover_126d", "ret_1_0", "age"]
PCT_COLS = ["earnings_variability", "prc_highprc_252d"]
M1_COLS = [
    "log_im",
    "hist_move",
    "hist_ratio",
    "jump_share",
    "log_me",
    "rvol_21d",
    "ivol_capm_21d",
    "turnover_126d",
    "ret_1_0",
    "age",
    "earnings_variability_pct",
    "prc_highprc_252d_pct",
]
SCHEMES = [
    "S1_fixed_contracts",
    "S2_equal_margin",
    "S3_equal_premium",
    "S4_forecast_parity",
    "S5_margin_daily_budget",
    "S6_premium_daily_budget",
]


# ── data ──


def load_events() -> pd.DataFrame:
    """Scorable events with returns on both bases, implied move, target and permno."""
    main = pd.read_parquet(EVENTS)
    conf = pd.read_parquet(CONFIRM)
    ev = pd.concat([main[main["status"] == "ok"], conf[conf["status"] == "ok"]], ignore_index=True)
    fcols = [
        "ticker",
        "entry_date",
        "permno",
        "front_fwd",
        "front_iv",
        "front_t",
        "jsplit_jump_var",
        "jsplit_valid",
    ]
    feat = pd.read_parquet(FEATURES, columns=fcols)
    ev = ev.merge(feat, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    for c in ("entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).astype("datetime64[ns]")
    # 2025-26 rows carry no permno: map each ticker to its latest earlier permno.
    known = (
        feat.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    )
    miss = ev["permno"].isna()
    ev.loc[miss, "permno"] = ev.loc[miss, "ticker"].map(known)
    print(
        f"funnel permno: {int(miss.sum())} missing, {int(ev.loc[miss, 'permno'].notna().sum())} "
        f"mapped from ticker history; {int(ev['permno'].isna().sum())} still missing"
    )
    ev["im"] = ev["mid0"] / ev["front_fwd"]
    ev = ev[np.isfinite(ev["im"]) & (ev["im"] > 0) & np.isfinite(ev["abs_move"])].copy()
    x = ev["exit_mid"].where(np.isfinite(ev["exit_mid"]), ev["exit_ask"])
    n_ask = int((~np.isfinite(ev["exit_mid"]) & np.isfinite(ev["exit_ask"])).sum())
    ev["r_meas"] = (ev["mid0"] * (1 - COST_IN) - x * (1 + COST_OUT) - 4 * FEE) / ev["m0"]
    ev["r_touch"] = ev["B"]
    print(
        f"funnel returns: {len(ev)} events; exit at ask (no two-sided mid) {n_ask}; "
        f"measured return undefined {int(ev['r_meas'].isna().sum())}, "
        f"touch undefined {int(ev['r_touch'].isna().sum())}"
    )
    ev["y"] = np.log(np.maximum(ev["abs_move"], MOVE_FLOOR))
    ev["log_im"] = np.log(ev["im"])
    tot = ev["front_iv"] ** 2 * ev["front_t"]
    ev["jump_share"] = np.where(
        ev["jsplit_valid"].astype(bool) & (tot > 0), ev["jsplit_jump_var"] / tot, np.nan
    )
    ev["year"] = ev["entry_date"].dt.year
    return ev.sort_values("entry_date").reset_index(drop=True)


def attach_chars(ev: pd.DataFrame) -> pd.DataFrame:
    """Latest month-end characteristics strictly before entry, at most 62 days old."""
    ch = pd.read_parquet(CHARS, columns=["permno", "eom"] + CHAR_COLS + PCT_COLS)
    ch["eom"] = pd.to_datetime(ch["eom"]).astype("datetime64[ns]")
    for c in PCT_COLS:
        ch[f"{c}_pct"] = ch.groupby("eom")[c].rank(pct=True)
    ch = ch.dropna(subset=["permno"]).sort_values("eom")
    ch["permno"] = ch["permno"].astype("int64")
    left = ev[ev["permno"].notna()][["ticker", "entry_date", "permno"]].copy()
    left["permno"] = left["permno"].astype("int64")
    m = pd.merge_asof(
        left.sort_values("entry_date"),
        ch.rename(columns={"eom": "chars_eom"}),
        left_on="entry_date",
        right_on="chars_eom",
        by="permno",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=CHARS_MAX_AGE_D),
    )
    keep = ["ticker", "entry_date", "chars_eom"] + CHAR_COLS + [f"{c}_pct" for c in PCT_COLS]
    out = ev.merge(m[keep], on=["ticker", "entry_date"], how="left")
    out["log_me"] = np.log(out["me"].where(out["me"] > 0))
    print(f"funnel chars: matched {int(out['chars_eom'].notna().sum())} of {len(out)}")
    return out


def add_history(ev: pd.DataFrame) -> pd.DataFrame:
    """Mean log move and mean log ratio over the name's last eight events closed before entry."""
    hm = np.full(len(ev), np.nan)
    hr = np.full(len(ev), np.nan)
    for _, g in ev.groupby("ticker"):
        exits = g["exit_date"].to_numpy()
        y = g["y"].to_numpy()
        ratio = (g["y"] - g["log_im"]).to_numpy()
        for idx, d in zip(g.index, g["entry_date"].to_numpy()):
            prior = np.where(exits < d)[0]
            if len(prior) >= HIST_MIN:
                last = prior[-HIST_N:]
                hm[idx], hr[idx] = y[last].mean(), ratio[last].mean()
    ev["hist_move"], ev["hist_ratio"] = hm, hr
    return ev


# ── Part A ──


def _ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xx = np.column_stack([np.ones(len(x)), x])
    return np.linalg.lstsq(xx, y, rcond=None)[0]


def _pred(beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return beta[0] + x @ beta[1:]


def walk_forward(ev: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Out-of-sample predictions of M0 (all events) and M1 (events with every input defined)."""
    ev = ev.copy()
    ev["yhat_m0"] = np.nan
    ev["yhat_m1"] = np.nan
    full = ev[M1_COLS].notna().all(axis=1) & np.isfinite(ev[M1_COLS]).all(axis=1)
    ev["m1_defined"] = full
    last: dict[str, object] = {}
    for yr in range(FIRST_OOS_YEAR, int(ev["year"].max()) + 1):
        train = ev["exit_date"] < pd.Timestamp(f"{yr}-01-01")
        test = ev["year"] == yr
        b0 = _ols(ev.loc[train, ["log_im"]].to_numpy(), ev.loc[train, "y"].to_numpy())
        ev.loc[test, "yhat_m0"] = _pred(b0, ev.loc[test, ["log_im"]].to_numpy())
        tr1 = train & full
        if tr1.sum() < 200:
            raise ValueError(f"M1 training set for {yr} has {int(tr1.sum())} events")
        b1 = _ols(ev.loc[tr1, M1_COLS].to_numpy(), ev.loc[tr1, "y"].to_numpy())
        te1 = test & full
        ev.loc[te1, "yhat_m1"] = _pred(b1, ev.loc[te1, M1_COLS].to_numpy())
        last = {
            "year": yr,
            "n_train_m1": int(tr1.sum()),
            "m0": b0.tolist(),
            "m1": dict(zip(["const"] + M1_COLS, b1.tolist())),
        }
    # standardised M1 coefficients on the last training set, descriptive only
    tr = full & (ev["exit_date"] < pd.Timestamp(f"{int(ev['year'].max())}-01-01"))
    z = (ev.loc[tr, M1_COLS] - ev.loc[tr, M1_COLS].mean()) / ev.loc[tr, M1_COLS].std()
    bz = _ols(z.to_numpy(), ev.loc[tr, "y"].to_numpy())
    last["m1_standardised"] = dict(zip(M1_COLS, np.round(bz[1:], 4).tolist()))
    return ev, last


def score_a(ev: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    for name, (lo, hi) in A_BLOCKS.items():
        b = ev[
            (ev["year"] >= lo)
            & (ev["year"] <= hi)
            & ev["m1_defined"]
            & ev["yhat_m0"].notna()
            & ev["yhat_m1"].notna()
        ]
        e0 = (b["y"] - b["yhat_m0"]) ** 2
        e1 = (b["y"] - b["yhat_m1"]) ** 2
        diff = date_clustered_ci((e0 - e1).to_numpy(), b["entry_date"], np.mean)
        sst = ((b["y"] - b["y"].mean()) ** 2).sum()
        m2 = np.exp(2 * b["y"])

        def qlike(yh: pd.Series) -> float:
            h = np.exp(2 * yh)
            return float((m2 / h - np.log(m2 / h) - 1).mean())

        allb = ev[(ev["year"] >= lo) & (ev["year"] <= hi) & ev["yhat_m0"].notna()]
        out[name] = {
            "n_common": int(len(b)),
            "n_all_m0": int(len(allb)),
            "mse_gain": [diff.point, diff.low, diff.high],
            "oos_r2_m0": float(1 - e0.sum() / sst),
            "oos_r2_m1": float(1 - e1.sum() / sst),
            "qlike_m0": qlike(b["yhat_m0"]),
            "qlike_m1": qlike(b["yhat_m1"]),
            "passes": bool(diff.low > 0) if name == "2016-2024" else bool(diff.point > 0),
        }
    return out


# ── Part B ──


def weights(ev: pd.DataFrame) -> pd.DataFrame:
    """Dollar P&L per event under each scheme, per unit of return (multiply by r)."""
    n_date = ev.groupby("entry_date")["ticker"].transform("size")
    f_hat = np.exp(ev["yhat_m1"].where(ev["yhat_m1"].notna(), ev["yhat_m0"]))
    w = pd.DataFrame(index=ev.index)
    w["S1_fixed_contracts"] = 100 * ev["m0"]
    w["S2_equal_margin"] = 100.0
    w["S3_equal_premium"] = 100 * ev["m0"] / ev["mid0"]
    w["S4_forecast_parity"] = 100 * ev["m0"] / (ev["front_fwd"] * f_hat)
    w["S5_margin_daily_budget"] = 100.0 / n_date
    w["S6_premium_daily_budget"] = w["S3_equal_premium"] / n_date
    return w


def _sharpe(x: np.ndarray) -> float:
    s = x.std(ddof=1)
    return float(x.mean() / s) if s > 0 else float("nan")


def tail_stats(daily: np.ndarray, event_pnl: np.ndarray) -> dict[str, float]:
    sd = daily.std(ddof=1)
    cum = np.cumsum(daily)
    dd = float(np.max(np.maximum.accumulate(cum) - cum) / sd)
    k = max(1, int(np.ceil(0.01 * len(daily))))
    es = float(np.sort(daily)[:k].mean() / sd)
    losses = np.sort(np.clip(-event_pnl, 0, None))[::-1]
    ke = max(1, int(np.ceil(0.01 * len(event_pnl))))
    return {
        "max_dd_sd": dd,
        "worst_date_sd": float(daily.min() / sd),
        "es1_sd": es,
        "worst1pct_event_loss_share": float(losses[:ke].sum() / losses.sum()),
    }


def score_b(ev: pd.DataFrame, w: pd.DataFrame, basis: str) -> dict[str, object]:
    out: dict[str, object] = {}
    r = ev[basis]
    for name, (lo, hi) in B_BLOCKS.items():
        m = (ev["year"] >= lo) & (ev["year"] <= hi) & r.notna() & ev["yhat_m0"].notna()
        pnl = w[m].mul(r[m], axis=0)
        daily = pnl.groupby(ev.loc[m, "entry_date"]).sum().sort_index()
        years = (daily.index.max() - daily.index.min()).days / 365.0
        per_year = len(daily) / years if years > 0 else float("nan")
        idx = np.arange(len(daily), dtype=float)
        base = daily["S1_fixed_contracts"].to_numpy()
        blk: dict[str, object] = {
            "events": int(m.sum()),
            "dates": int(len(daily)),
            "dates_per_year": per_year,
        }
        for s in SCHEMES:
            x = daily[s].to_numpy()
            res: dict[str, object] = {
                "mean_per_date": float(x.mean()),
                "sharpe_per_date": _sharpe(x),
                "sharpe_annualised_by_dates": _sharpe(x) * np.sqrt(per_year),
                **tail_stats(x, pnl[s].to_numpy()),
            }
            if s != "S1_fixed_contracts":
                ci = date_clustered_ci(
                    idx,
                    daily.index,
                    lambda i, x=x: _sharpe(x[i.astype(int)]) - _sharpe(base[i.astype(int)]),
                )
                res["sharpe_diff_vs_S1"] = [ci.point, ci.low, ci.high]
            blk[s] = res
        out[name] = blk
    verdict = {}
    for s in SCHEMES[1:]:
        pooled = out["2016-2024"][s]["sharpe_diff_vs_S1"]
        each = all(
            out[b][s]["sharpe_diff_vs_S1"][0] > 0 for b in ("2016-2020", "2021-2024", "2025-26")
        )
        verdict[s] = bool(pooled[1] > 0 and each)
    out["passes"] = verdict
    return out


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = add_history(attach_chars(load_events()))
    ev, coefs = walk_forward(ev)
    n_oos = int(ev["yhat_m0"].notna().sum())
    n_m1 = int(ev["yhat_m1"].notna().sum())
    print(
        f"funnel Part A: {n_oos} out-of-sample events from {FIRST_OOS_YEAR}; M1 defined on {n_m1}"
        f" ({n_m1 / n_oos:.1%}); S4 uses M0 on the rest"
    )
    a = score_a(ev)
    for k, v in a.items():
        g = v["mse_gain"]
        print(
            f"A {k}: N {v['n_common']} MSE gain {g[0]:+.4f} [{g[1]:+.4f}, {g[2]:+.4f}] "
            f"R2 M0 {v['oos_r2_m0']:.3f} M1 {v['oos_r2_m1']:.3f} QLIKE {v['qlike_m0']:.3f}/"
            f"{v['qlike_m1']:.3f} {'PASS' if v['passes'] else 'fail'}"
        )
    print("A last-fit M0 [const, slope on log im]:", np.round(coefs["m0"], 3).tolist())
    print("A last-fit M1 standardised:", coefs["m1_standardised"])
    w = weights(ev)
    b = {basis: score_b(ev, w, basis) for basis in ("r_meas", "r_touch")}
    for basis, res in b.items():
        for blk in B_BLOCKS:
            r = res[blk]
            print(
                f"B {basis} {blk}: events {r['events']} dates {r['dates']} ({r['dates_per_year']:.0f}/yr)"
            )
            for s in SCHEMES:
                x = r[s]
                d = x.get("sharpe_diff_vs_S1")
                ds = f" vs S1 {d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}]" if d else ""
                print(
                    f"   {s:24s} SR/date {x['sharpe_per_date']:+.3f} (ann {x['sharpe_annualised_by_dates']:+.2f})"
                    f" maxDD {x['max_dd_sd']:6.1f}sd worst {x['worst_date_sd']:+.1f}sd ES1 {x['es1_sd']:+.1f}sd"
                    f" top1%loss {x['worst1pct_event_loss_share']:.0%}{ds}"
                )
        print(f"B {basis} verdicts:", res["passes"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(
        json.dumps({"A": a, "A_coefs": coefs, "B": b}, indent=2, default=float)
    )
    print(f"written {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
