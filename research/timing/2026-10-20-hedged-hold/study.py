"""
study.py
Delta-hedged short straddles held to expiry (S1 pre-event, S2 post-event) and the HAR selector
(S3a, S3b), scored exactly as frozen in ``prereg.md``.

Stages follow the pre-registration: discovery (entry dates 2013-2018) for every candidate,
validation (2019-2024) only for a candidate that passes discovery. Run once; every run is a trial.

Usage
-----
    python research/timing/2026-10-20-hedged-hold/study.py
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
from scipy.stats import mannwhitneyu  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"

BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024)}
N_TRIALS = 1539  # 1,532 conservative prior count plus this date's seven declared trials
SR_TRIALS_STD = 0.127475  # recorded dispersion of trial Sharpes ("arms x cost")


# ── paths ────────────────────────────────────────────────────────────────────


class Paths:
    """CRSP daily rows by permno, with a market calendar from the union of all dates."""

    def __init__(self, crsp: pd.DataFrame) -> None:
        crsp = crsp.sort_values(["permno", "date"])
        self.calendar = np.array(sorted(crsp["date"].unique()), dtype="datetime64[ns]")
        self.by = {int(p): g.set_index("date") for p, g in crsp.groupby("permno")}

    def window(self, permno: float, start: pd.Timestamp, end: pd.Timestamp) -> tuple:
        """Rows from ``start`` to the last session on or before ``end``; reason if unusable."""
        if not np.isfinite(permno) or int(permno) not in self.by:
            return None, "no_permno"
        g = self.by[int(permno)]
        cal = self.calendar[
            (self.calendar >= np.datetime64(start)) & (self.calendar <= np.datetime64(end))
        ]
        if cal.size < 2 or cal[0] != np.datetime64(pd.Timestamp(start).normalize()):
            return None, "path_incomplete"
        w = g.reindex(pd.DatetimeIndex(cal))
        if w["prc"].isna().any() or w["ret"].isna().any():
            return None, "path_incomplete"
        if w["cfacpr"].nunique(dropna=False) != 1:
            return None, "distribution_in_window"
        return w, "ok"


def _half_spreads(w: pd.DataFrame) -> tuple[np.ndarray, bool]:
    px = w["prc"].abs()
    hs = (w["ask"] - w["bid"]) / 2.0 / px
    hs = hs.where((w["bid"] > 0) & (w["ask"] > w["bid"]))
    filled = bool(hs.isna().any())
    if filled:
        # a missing closing quote takes the name's median over the same window, counted
        hs = hs.fillna(hs.median())
    return hs.to_numpy(float), filled


def hold(
    paths: Paths,
    permno: float,
    start: pd.Timestamp,
    quote: dict,
    sigma_fn,
) -> tuple[dict | None, str]:
    """Score one hedged hold; ``quote`` carries expiry, fwd, strike, bid, mid, iv."""
    expiry = pd.Timestamp(quote["expiry"])
    w, why = paths.window(permno, start, expiry)
    if w is None:
        return None, why
    hs, filled = _half_spreads(w)
    if not np.isfinite(hs).all():
        return None, "no_quotes"
    dates = w.index
    closes = w["prc"].abs().to_numpy(float)
    rets = w["ret"].to_numpy(float)
    taus = np.array([(expiry.normalize() - d).days / 365.0 for d in dates])
    sig = np.array([sigma_fn(d) for d in dates])
    res = hh.hedged_short_straddle(
        sale_price=quote["bid"],
        sale_mid=quote["mid"],
        strike=quote["strike"],
        fwd=quote["fwd"],
        closes=closes[:-1],
        rets=rets[1:],
        taus=taus[:-1],
        sigmas=sig[:-1],
        half_spreads=hs[:-1],
        settle_close=float(closes[-1]),
    )
    vega = hh.straddle_vega(quote["fwd"], quote["strike"], quote["t"], quote["iv"])
    realised = float(np.sqrt(np.sum(np.log1p(rets[1:]) ** 2) / max(len(rets) - 1, 1) * 252))
    return {
        "net_rom": res.net_rom,
        "gross_rom_mid": res.gross_pnl_mid / res.margin,
        "net_pnl": res.net_pnl,
        "margin": res.margin,
        "hedge_pnl": res.hedge_pnl,
        "equity_cost": res.equity_cost,
        "net_volpts_per_vega": res.net_pnl / vega if vega > 0 else np.nan,
        "half_spread_premium": (quote["mid"] - quote["bid"]) / quote["mid"],
        "realised_vol": realised,
        "quote_filled": filled,
        "expiry": expiry,
    }, "ok"


# ── HAR signal ───────────────────────────────────────────────────────────────


def har_variance(
    paths: Paths, permno: float, decision: pd.Timestamp, expiry: pd.Timestamp, excl: set
) -> float:
    if not np.isfinite(permno) or int(permno) not in paths.by:
        return float("nan")
    g = paths.by[int(permno)]
    g = g[g.index < decision]
    r = np.log1p(g["ret"].to_numpy(float))
    r[np.isin(g.index.normalize(), list(excl))] = np.nan
    h = int(
        np.busday_count(
            (decision + pd.Timedelta(days=1)).date(), (expiry + pd.Timedelta(days=1)).date()
        )
    )
    return hh.har_annual_variance(r, h)


# ── scoring ──────────────────────────────────────────────────────────────────


def block_of(d: pd.Series) -> pd.Series:
    y = pd.to_datetime(d).dt.year
    out = pd.Series("other", index=d.index)
    for name, (a, b) in BLOCKS.items():
        out[(y >= a) & (y <= b)] = name
    return out


def score_book(df: pd.DataFrame, label: str) -> dict:
    r = df["net_rom"].to_numpy(float)
    mean_ci = date_clustered_ci(r, df["expiry"], stat=np.mean)
    sr_ci = date_clustered_ci(r, df["expiry"])
    mid = date_clustered_ci(df["gross_rom_mid"].to_numpy(float), df["expiry"], stat=np.mean)
    out = {
        "label": label,
        "n": int(len(r)),
        "clusters": mean_ci.clusters,
        "mean_net_rom": mean_ci.point,
        "mean_net_rom_ci": [mean_ci.low, mean_ci.high],
        "per_trade_sharpe": per_trade_sharpe(r),
        "sharpe_ci": [sr_ci.low, sr_ci.high],
        "dsr": float(deflated_sharpe_ratio(pd.Series(r), N_TRIALS, SR_TRIALS_STD)),
        "mean_gross_rom_mid": mid.point,
        "mean_gross_rom_mid_ci": [mid.low, mid.high],
        "median_net_rom": float(np.median(r)),
        "hit_rate": float((r > 0).mean()),
        "worst": float(r.min()),
        "median_half_spread_premium": float(df["half_spread_premium"].median()),
        "mean_implied_minus_realised_volpts": float(
            100 * (df["iv_sold"] - df["realised_vol"]).mean()
        ),
        "pass": bool(mean_ci.low > 0),
    }
    print(
        f"  {label}: N={out['n']} mean net RoM {mean_ci} | Sharpe {out['per_trade_sharpe']:+.3f}"
        f" [{sr_ci.low:+.3f}, {sr_ci.high:+.3f}] | DSR {out['dsr']:.3f} | at mid {mid.point:+.4f}"
        f" | hit {out['hit_rate']:.1%} | worst {out['worst']:+.3f}"
    )
    return out


def score_selector(df: pd.DataFrame, label: str) -> dict:
    d = df[df["bin"] >= 0]
    top, bot = d["bin"] == 2, d["bin"] == 0
    p, lo, hi = hh.top_minus_bottom_ci(d["net_volpts_per_vega"], top, bot, d["expiry"])
    null = matched_random_null(d["net_rom"].to_numpy(float), top.to_numpy(), stat=np.mean)
    terc = d.groupby("bin").agg(
        n=("net_rom", "size"),
        volpts=("net_volpts_per_vega", "mean"),
        net_rom=("net_rom", "mean"),
    )
    out = {
        "label": label,
        "n_assigned": int(len(d)),
        "tmb_volpts": p,
        "tmb_volpts_ci": [lo, hi],
        "top_mean_net_rom": null.observed,
        "null_percentile": null.percentile,
        "terciles": terc.reset_index().to_dict(orient="records"),
        "pass": bool(lo > 0 and null.percentile >= 95.0),
    }
    print(
        f"  {label}: assigned {len(d)}, top-minus-bottom {p:+.3f} vol pts per vega "
        f"[{lo:+.3f}, {hi:+.3f}]; top net RoM {null.observed:+.4f}, null pct "
        f"{null.percentile:.1f}"
    )
    print(terc.to_string())
    return out


def attrition(ev: pd.DataFrame, reasons: pd.Series, paths: Paths, label: str) -> dict:
    """Funnel by reason, and whether dropped events moved more on the reaction day."""
    counts = reasons.value_counts().to_dict()
    react = []
    for p, d in zip(ev["permno"], ev["exit_date"], strict=True):
        g = paths.by.get(int(p)) if np.isfinite(p) else None
        v = g["ret"].get(d, np.nan) if g is not None else np.nan
        react.append(abs(v))
    react = pd.Series(react, index=ev.index)
    kept, dropped = react[reasons == "ok"].dropna(), react[reasons != "ok"].dropna()
    pval = (
        float(mannwhitneyu(kept, dropped).pvalue)
        if len(kept) > 10 and len(dropped) > 10
        else float("nan")
    )
    out = {
        "funnel": {str(k): int(v) for k, v in counts.items()},
        "abs_reaction_kept_median": float(kept.median()),
        "abs_reaction_dropped_median": float(dropped.median()) if len(dropped) else float("nan"),
        "mannwhitney_p": pval,
    }
    print(f"  attrition {label}: {out}")
    return out


def run_book(ev: pd.DataFrame, paths: Paths, book: str) -> pd.DataFrame:
    rows, reasons = [], []
    for _, e in ev.iterrows():
        if book == "S1":
            q = {k: e[f"s1_{k}"] for k in ("expiry", "t", "fwd", "strike", "bid", "mid", "iv")}
            start = e["entry_date"]
            sd = np.sqrt(e["s1split_sd2"]) if bool(e["s1split_valid"]) else e["s1_iv"]
            exit_d = e["exit_date"]

            def sigma_fn(d, iv=e["s1_iv"], sd=sd, exit_d=exit_d):
                return iv if d < exit_d else sd

        else:
            q = {k: e[f"s2_{k}"] for k in ("expiry", "t", "fwd", "strike", "bid", "mid", "iv")}
            start = e["exit_date"]

            def sigma_fn(d, iv=e["s2_iv"]):
                return iv

        if not (pd.notna(q["expiry"]) and np.isfinite(q["iv"]) and q["bid"] > 0):
            rows.append(None)
            reasons.append("no_quote")
            continue
        r, why = hold(paths, e["permno"], start, q, sigma_fn)
        if r is not None:
            r["iv_sold"] = q["iv"]
        rows.append(r)
        reasons.append(why)
    reasons_s = pd.Series(reasons, index=ev.index)
    res = pd.DataFrame([r if r is not None else {} for r in rows], index=ev.index)
    res["reason"] = reasons_s
    return res


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    feat = pd.read_parquet(OUT / "features.parquet")
    crsp = pd.read_parquet(OUT / "crsp_paths.parquet")
    paths = Paths(crsp)
    feat["block"] = block_of(feat["entry_date"])
    ev = feat[feat["block"].isin(list(BLOCKS))].reset_index(drop=True)
    print(f"events in declared blocks: {len(ev)} ({ev['block'].value_counts().to_dict()})")
    excl_by_ticker = (
        pd.read_parquet(EVENTS, columns=["ticker", "exit_date"])
        .assign(exit_date=lambda x: pd.to_datetime(x["exit_date"]).dt.normalize())
        .groupby("ticker")["exit_date"]
        .apply(set)
        .to_dict()
    )
    summary: dict = {"prereg_sha256": verify_prereg(PREREG, RECORD), "results": {}}

    for book, sel in (("S1", "S3a"), ("S2", "S3b")):
        print(f"\n== {book} ==")
        res = run_book(ev, paths, book)
        d = pd.concat([ev, res], axis=1)
        summary["results"][f"{book}_attrition"] = attrition(ev, res["reason"], paths, book)
        print(f"  closing quotes filled from window median: {int(d['quote_filled'].sum())}")
        ok = d[d["reason"] == "ok"].copy()
        # selector signal on every scored event, computed from strictly earlier returns
        sig = []
        for _, e in ok.iterrows():
            decision = e["entry_date"] if book == "S1" else e["exit_date"]
            excl = {x for x in excl_by_ticker.get(e["ticker"], set()) if x < decision}
            hv = har_variance(paths, e["permno"], decision, pd.Timestamp(e["expiry"]), excl)
            if book == "S1":
                num = e["s1split_sd2"] if bool(e["s1split_valid"]) else np.nan
            else:
                num = e["s2_iv"] ** 2
            sig.append(num / hv if hv > 0 else np.nan)
        ok["signal"] = sig
        print(f"  {sel} signal finite on {int(np.isfinite(ok['signal']).sum())} of {len(ok)}")
        date_col = "entry_date" if book == "S1" else "exit_date"
        ok["bin"] = hh.causal_bins(ok["signal"], ok[date_col], 3, HEDGED.tercile_min_prior)
        ok.to_parquet(OUT / f"{book}_events.parquet", index=False)

        disc = score_book(ok[ok["block"] == "discovery"], f"{book} discovery")
        summary["results"][f"{book}_discovery"] = disc
        if disc["pass"]:
            summary["results"][f"{book}_validation"] = score_book(
                ok[ok["block"] == "validation"], f"{book} validation"
            )
        else:
            print(f"  {book} fails discovery: validation not run (kill criterion)")
        sdisc = score_selector(ok[ok["block"] == "discovery"], f"{sel} discovery")
        summary["results"][f"{sel}_discovery"] = sdisc
        if sdisc["pass"]:
            summary["results"][f"{sel}_validation"] = score_selector(
                ok[ok["block"] == "validation"], f"{sel} validation"
            )
        else:
            print(f"  {sel} fails discovery: validation not run (kill criterion)")
        yearly = (
            ok[ok["block"] == "discovery"]
            .assign(year=lambda x: pd.to_datetime(x["entry_date"]).dt.year)
            .groupby("year")["net_rom"]
            .agg(["size", "mean"])
        )
        print(f"  {book} discovery by year:\n{yearly.to_string()}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"\nwrote {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
