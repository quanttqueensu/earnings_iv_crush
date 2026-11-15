"""s03_score.py: lane G round 1 trials 1961-1968 on the panel from s02_build.py.

Each trial pairs an event-night outcome with controls matched on weekday, tenor, prior-close VIX
(within 15% relative) and calendar proximity (60 sessions), excluding nights whose exit session
carries a CPI, payrolls or FOMC release. Intervals are date-clustered (protocol.date_clustered_ci);
the null is a stratified placebo that replaces each event by a random member of its own matched
control set. Rows append to trials.csv as soon as scored.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneG-index-event-vol/s03_score.py [--round 1]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.engine.stats import nyse_sessions
from earnings_iv_crush.research.protocol import date_clustered_ci, matched_random_null

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
COLS = ["trial_id", "hypothesis", "mechanism", "block", "N", "effect", "ci_low", "ci_high", "t",
        "null_pct", "basis", "verdict"]
MATCH_WINDOW = 60  # sessions either side (frozen index study)
VIX_TOL = 0.15  # relative distance of prior-close VIX between event and control
MIN_CTL = 5  # frozen index study minimum
N_NULL = 2000
RNG = np.random.default_rng(0)
SESS = nyse_sessions(pd.Timestamp("2015-01-01"), pd.Timestamp("2026-12-31"))
POS = {d: i for i, d in enumerate(SESS)}


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def log_trial(row: dict[str, object]) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLS})


def _mean(v: np.ndarray) -> float:
    return float(np.mean(v))


def paired(
    d: pd.DataFrame, ev: pd.Series, col: str, dte_col: str | None, extra_keys: tuple[str, ...] = ()
) -> pd.DataFrame:
    """Event value minus mean of matched controls; keeps each event's control values."""
    d = d.assign(spos=d["entry"].map(POS))
    # controls carry no mega-cap release at all, whatever the event definition
    ctl = d[(d["n_rep"].fillna(0) == 0) & ~d["exit_macro"] & np.isfinite(d[col])]
    rows = []
    for r in d[ev & ~d["exit_macro"]].itertuples():
        v = getattr(r, col)
        if not np.isfinite(v):
            continue
        c = ctl[((ctl["spos"] - r.spos).abs() <= MATCH_WINDOW) & (ctl["weekday"] == r.weekday)]
        c = c[(c["vix_prev"] / r.vix_prev - 1).abs() <= VIX_TOL]
        if dte_col is not None:
            c = c[c[dte_col] == getattr(r, dte_col)]
        for k in extra_keys:
            c = c[c[k] == getattr(r, k)]
        rec = {"entry": r.entry, "event": v, "n_ctl": len(c), "W": r.W, "n_rep": r.n_rep,
               "reporters": r.reporters, "block": r.block, "ctl_vals": c[col].to_numpy()}
        if len(c) >= MIN_CTL:
            rec["control"] = float(c[col].mean())
            rec["diff"] = v - rec["control"]
        rows.append(rec)
    return pd.DataFrame(rows)


def placebo_pct(p: pd.DataFrame, sign: float) -> float:
    """Share of placebo draws (random own control replaces the event) below the observed mean."""
    p = p.dropna(subset=["diff"])
    obs = sign * p["diff"].mean()
    draws = np.empty(N_NULL)
    for b in range(N_NULL):
        draws[b] = np.mean([RNG.choice(cv) - cv.mean() for cv in p["ctl_vals"]])
    return float((sign * draws < obs).mean() * 100)


def summarise(p: pd.DataFrame, sign: float = 1.0) -> dict[str, float]:
    p = p.dropna(subset=["diff"])
    if len(p) < 5:
        return {"N": len(p)}
    ci = date_clustered_ci(p["diff"], p["entry"], _mean)
    lev = date_clustered_ci(p["event"], p["entry"], _mean)
    sd = p["diff"].std(ddof=1)
    return {
        "N": ci.n,
        "effect": ci.point,
        "ci_low": ci.low,
        "ci_high": ci.high,
        "t": ci.point / (sd / np.sqrt(ci.n)),
        "null_pct": placebo_pct(p, sign),
        "level": lev.point,
        "level_lo": lev.low,
        "level_hi": lev.high,
        "ctl_level": float(p["control"].mean()),
    }


def report(tid: int, hyp: str, mech: str, basis: str, p: pd.DataFrame, sign: float,
           blocks: tuple[str, ...] = ("M", "C", "P")) -> dict[str, dict[str, float]]:
    out = {}
    for b in blocks:
        s = summarise(p[p["block"] == b], sign)
        out[b] = s
        if "effect" not in s:
            log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": b,
                       "N": s["N"], "basis": basis, "verdict": "too few"})
            continue
        good = sign * s["effect"] > 0 and (s["ci_low"] > 0 if sign > 0 else s["ci_high"] < 0)
        lvl = s["level"] > 0
        verdict = ("pass-exploratory" if good and lvl else
                   "effect only, book negative" if good else "fail")
        log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": b,
                   "N": s["N"], "effect": f"{s['effect']:.5f}", "ci_low": f"{s['ci_low']:.5f}",
                   "ci_high": f"{s['ci_high']:.5f}", "t": f"{s['t']:.2f}",
                   "null_pct": f"{s['null_pct']:.1f}",
                   "basis": f"{basis}; event-book level {s['level']:.5f} "
                            f"[{s['level_lo']:.5f}, {s['level_hi']:.5f}], control {s['ctl_level']:.5f}",
                   "verdict": verdict + " (exploratory: blocks viewed by B2)"})
        print(f"  {tid} {b}: N={s['N']} diff={s['effect']:+.4f} [{s['ci_low']:+.4f},"
              f"{s['ci_high']:+.4f}] t={s['t']:+.2f} null%={s['null_pct']:.0f} | level "
              f"{s['level']:+.4f} [{s['level_lo']:+.4f},{s['level_hi']:+.4f}] ctl {s['ctl_level']:+.4f}")
    return out


def selector(tid: int, hyp: str, mech: str, basis: str, p: pd.DataFrame, mask_fn, sign: float):
    for b in ("M", "C", "P"):
        s = p[(p["block"] == b)].dropna(subset=["diff"])
        if len(s) < 10:
            continue
        m = mask_fn(s).to_numpy()
        if m.sum() < 3 or m.all():
            continue
        nc = matched_random_null(s["event"].to_numpy(), m, _mean)
        pct = float((sign * nc.null < sign * nc.observed).mean() * 100)
        sel = s[m]
        ci = date_clustered_ci(sel["event"], sel["entry"], _mean)
        rest = s[~m]["event"].mean()
        sd = sel["event"].std(ddof=1)
        log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": b,
                   "N": ci.n, "effect": f"{ci.point - rest:.5f}", "ci_low": f"{ci.low:.5f}",
                   "ci_high": f"{ci.high:.5f}", "t": f"{ci.point / (sd / np.sqrt(ci.n)):.2f}",
                   "null_pct": f"{pct:.1f}",
                   "basis": f"{basis}; effect = selected mean minus unselected event mean; CI is "
                            f"the selected book level {ci.point:.5f}",
                   "verdict": ("pass-exploratory" if pct >= 95 and ci.low > 0 else "fail")
                   + " (exploratory)"})
        print(f"  {tid} {b}: sel N={ci.n} level={ci.point:+.4f} [{ci.low:+.4f},{ci.high:+.4f}] "
              f"rest={rest:+.4f} null%={pct:.0f}")


# â”€â”€ round 1 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def round1(panel: pd.DataFrame) -> None:
    q = panel[panel["ticker"] == "QQQ"].copy()
    ev = q["n_rep"].fillna(0) > 0

    # spread actually measured: front straddle half-spread over mid, 15:59 entry
    q["hs_front"] = ((q["c0a_d"] + q["p0a_d"]) - (q["c0b_d"] + q["p0b_d"])) / 2 / q["p0_d"]
    sp = q.groupby(["block", ev.rename("event")])["hs_front"].median().unstack()
    print("QQQ front straddle median half-spread / mid premium (15:59):\n", sp.round(4))
    sp.to_csv(HERE / "spread_qqq.csv")

    # D1: implied night variance J against realised excess variance
    print("1961 D1 implied J vs realised excess variance (QQQ)")
    q["move2"] = q["move_d"] ** 2
    pj = paired(q[np.isfinite(q["J"])], ev[np.isfinite(q["J"])], "J", None, ("n1", "n2"))
    pr = paired(q, ev, "move2", None)
    rows = []
    for b in ("P", "M", "C"):
        a = pj[(pj["block"] == b)].dropna(subset=["diff"])
        r = pr[(pr["block"] == b)].dropna(subset=["diff"])
        both = a.merge(r[["entry", "diff", "event"]], on="entry", suffixes=("_J", "_R"))
        if len(both) < 5:
            continue
        cj = date_clustered_ci(both["diff_J"], both["entry"], _mean)
        cr = date_clustered_ci(both["diff_R"], both["entry"], _mean)
        vp = q.set_index("entry").loc[both["entry"], "V_pred"].mean()
        rows.append({"block": b, "N": len(both), "J_excess": cj.point, "J_lo": cj.low, "J_hi": cj.high,
                     "real_excess": cr.point, "real_lo": cr.low, "real_hi": cr.high,
                     "J_event_mean": both["event_J"].mean(), "move2_event_mean": both["event_R"].mean(),
                     "V_pred_mean": vp})
        log_trial({"trial_id": 1961, "hypothesis": "QQQ implied night variance J on mega-cap nights "
                   "exceeds realised excess one-session variance (buyers over-price the event)",
                   "mechanism": "earnings component over-priced in the index option", "block": b,
                   "N": len(both), "effect": f"{cj.point - cr.point:.3e}",
                   "ci_low": f"J {cj.low:.2e}..{cj.high:.2e}", "ci_high": f"real {cr.low:.2e}..{cr.high:.2e}",
                   "t": "", "null_pct": "",
                   "basis": "variance per night (log-return^2); effect = J excess minus realised excess, "
                            "both vs matched controls; descriptive",
                   "verdict": "descriptive"})
    d1 = pd.DataFrame(rows)
    print(d1.to_string())
    d1.to_csv(HERE / "d1_implied_vs_realised.csv", index=False)
    pj.drop(columns="ctl_vals").to_parquet(HERE / "d1_events_J.parquet")
    pr.drop(columns="ctl_vals").to_parquet(HERE / "d1_events_move2.parquet")

    # T1: short front, heavy nights, margin units
    wmed = float(q.loc[ev & (q["block"] == "M"), "W"].median())
    print(f"discovery event-night median W = {wmed:.3f} (feature only, no outcome)")
    heavy = ev & (q["W"] >= wmed)
    print("1962 T1 short front 15:59->15:59 on heavy nights, net touch, unit margin p0+0.15F")
    p1 = paired(q, heavy, "short_touch_net_rom_d", "dte_d")
    report(1962, f"short QQQ front straddle on heavy nights (W >= {wmed:.3f}) beats matched controls",
           "over-priced earnings component in the index; spread small",
           "per trade, net at touch, unit margin p0+0.15F, 15:59 to 15:59", p1, +1)
    p1.drop(columns="ctl_vals").to_parquet(HERE / "t1_events.parquet")

    # T2: dose-response within event nights (short, margin)
    print("1963 T2 heavy-half selector among event nights (short margin), random null")
    pall = paired(q, ev, "short_touch_net_rom_d", "dte_d")
    selector(1963, "within event nights, heavier reporter weight earns more on the short",
             "dose-response of over-pricing in reporter weight",
             "per trade, net at touch, unit margin, 15:59 to 15:59", pall,
             lambda s: s["W"] >= wmed, +1)

    # T3: long front 15:59 -> 10:00 on all event nights, unit debit
    print("1964 T3 long front 15:59 -> 10:00, all event nights, unit debit at the ask")
    p3 = paired(q, ev, "long_touch_net_debit_o", "dte_o")
    report(1964, "long QQQ front straddle 15:59 to 10:00 on mega-cap nights beats matched controls "
           "and is positive (DISCOVERY-DERIVED from B2 mechanism line)",
           "index under-prices the earnings jump; long captures the open gap before decay",
           "per trade, net at touch, unit debit (entry asks), 15:59 to next 10:00", p3, +1)
    p3.drop(columns="ctl_vals").to_parquet(HERE / "t3_events.parquet")

    # T4: long next-day expiry settled at intrinsic
    print("1965 T4 long next-day-expiry straddle to settlement, unit debit")
    p4 = paired(q, ev, "nde_long_net_debit", None)
    report(1965, "long next-day-expiry QQQ straddle settled at intrinsic on mega-cap nights beats "
           "controls and is positive (DISCOVERY-DERIVED)",
           "index under-prices the jump; one crossing only",
           "per trade, net at touch entry, intrinsic settle less 5bp disposal, unit debit", p4, +1)
    p4.drop(columns="ctl_vals").to_parquet(HERE / "t4_events.parquet")

    # T5: J-ratio selector on the T3 book
    jm = q.set_index("entry")["J"]
    vp = q.set_index("entry")["V_pred"]
    p3 = p3.assign(J=p3["entry"].map(jm), V_pred=p3["entry"].map(vp))
    p3["jr"] = p3["J"] / p3["V_pred"]
    med = float(p3.loc[p3["block"] == "M", "jr"].median())
    print(f"1966 T5 low implied-J/V_pred selector (discovery median ratio {med:.3f}, feature only)")
    selector(1966, "long front to 10:00 on event nights where implied J is low against V_pred",
             "index under-prices the constituent contribution most where J/V_pred is low",
             "per trade, net at touch, unit debit, 15:59 to 10:00",
             p3.dropna(subset=["jr"]), lambda s: s["jr"] <= med, +1)

    # T6/T7: SPY and IWM on the T3 construction
    for tid, tk, note in ((1967, "SPY", "SPY version"), (1968, "IWM", "IWM placebo")):
        s = panel[panel["ticker"] == tk].copy()
        e = s["n_rep"].fillna(0) > 0
        print(f"{tid} {note}: long front 15:59 -> 10:00")
        ps = paired(s, e, "long_touch_net_debit_o", "dte_o")
        report(tid, f"{note} of T3: long front straddle to 10:00 on mega-cap nights",
               "SPY: smaller weights, same mechanism; IWM: mega-caps absent, expect no effect",
               "per trade, net at touch, unit debit, 15:59 to next 10:00", ps, +1)


# ── round 2 ──────────────────────────────────────────────────────────────────
def causal_richness(q: pd.DataFrame) -> pd.Series:
    """J minus the prior-60-session non-event mean J (same n1, n2), less a causal forecast of the
    realised excess variance: k_t * V_pred, k_t = realised excess / V_pred over strictly earlier
    event nights, realised excess measured against the prior-60-session non-event mean move^2."""
    q = q.sort_values("entry").reset_index(drop=True)
    q["spos"] = q["entry"].map(POS)
    ev = q["n_rep"].fillna(0) > 0
    non = q[~ev]
    jx, rx = [], []
    for r in q.itertuples():
        base = non[(non["spos"] < r.spos) & (non["spos"] >= r.spos - MATCH_WINDOW)]
        bj = base[(base["n1"] == r.n1) & (base["n2"] == r.n2)]["J"].dropna()
        jx.append(r.J - bj.mean() if len(bj) >= 3 and np.isfinite(r.J) else np.nan)
        rx.append(r.move_d**2 - (base["move_d"] ** 2).mean() if len(base) >= 20 else np.nan)
    q["J_ex_causal"], q["real_ex"] = jx, rx
    k = []
    for i, r in q.iterrows():
        prior = q[(q["entry"] < r["entry"]) & ev & q["real_ex"].notna() & (q["V_pred"] > 0)]
        k.append(prior["real_ex"].sum() / prior["V_pred"].sum() if len(prior) >= 8 else np.nan)
    q["k"] = k
    q["rich"] = q["J_ex_causal"] - q["k"] * q["V_pred"]
    return q.set_index("entry")["rich"]


def round2(panel: pd.DataFrame) -> None:
    q = panel[panel["ticker"] == "QQQ"].copy()
    iw = panel[panel["ticker"] == "IWM"].set_index("entry")
    ev = q["n_rep"].fillna(0) > 0

    # 1969 DiD: QQQ short minus IWM short on the same night (margin units each)
    q["did_rom"] = q["short_touch_net_rom_d"] - q["entry"].map(iw["short_touch_net_rom_d"])
    print("1969 DiD short QQQ minus short IWM, event vs matched controls")
    p = paired(q, ev, "did_rom", "dte_d")
    report(1969, "QQQ-minus-IWM short (margin) is higher on mega-cap nights than controls",
           "QQQ-specific event over-pricing net of the reporting-season effect seen in the IWM placebo",
           "per night, net at touch, margin units, QQQ short minus IWM short, 15:59 to 15:59", p, +1)

    # 1970 short front 15:59 -> 10:00 on event nights
    print("1970 short QQQ front 15:59 -> 10:00 on event nights, margin")
    p = paired(q, ev, "short_touch_net_rom_o", "dte_o")
    report(1970, "short QQQ front straddle 15:59 to 10:00 on mega-cap nights is positive and beats controls",
           "jump variance is released at the open; overnight premium (Muravyev and Ni 2020); "
           "no next-session exposure", "per trade, net at touch, unit margin p0+0.15F, 15:59 to 10:00",
           p, +1)

    # 1971 short next-day expiry, settle
    print("1971 short QQQ next-day expiry settled at intrinsic on event nights, margin")
    p = paired(q, ev, "nde_short_rom", None)
    report(1971, "short QQQ next-day-expiry straddle on mega-cap nights, settled, is positive and beats "
           "controls", "event premium concentrated in the contract that holds only the night; one crossing",
           "per trade, net at touch entry, intrinsic settle less 5bp, unit margin p0+0.15F", p, +1)

    # 1972 causal richness selector on short front (margin) among event nights
    rich = causal_richness(q)
    q["rich"] = q["entry"].map(rich)
    pall = paired(q, ev, "short_touch_net_rom_d", "dte_d")
    pall["rich"] = pall["entry"].map(rich)
    med = float(pall.loc[pall["block"] == "M", "rich"].median())
    print(f"1972 richness selector (discovery median {med:.2e}, feature only)")
    selector(1972, "within event nights, short QQQ front when implied excess J beats the causal "
             "forecast of realised excess", "rich index event premium relative to a pass-through forecast",
             "per trade, net at touch, unit margin, 15:59 to 15:59", pall.dropna(subset=["rich"]),
             lambda s: s["rich"] >= med, +1)
    q[["entry", "rich"]].to_parquet(HERE / "richness.parquet")

    # 1973 several reporters literally
    print("1973 short QQQ front on nights with >= 2 reporters, margin")
    p = paired(q, q["n_rep"].fillna(0) >= 2, "short_touch_net_rom_d", "dte_d")
    report(1973, "short QQQ front straddle on nights with two or more mega-cap reporters beats controls",
           "several reporters diversify idiosyncratic jumps; buyers price the sum",
           "per trade, net at touch, unit margin p0+0.15F, 15:59 to 15:59", p, +1)


# ── round 3 ──────────────────────────────────────────────────────────────────
IH = HERE.parents[1] / "2026-11-02-index-hedged-hold" / "trades.parquet"


def round3(panel: pd.DataFrame) -> None:
    rel = pd.read_parquet(HERE / "releases.parquet")
    rel_days = np.array(sorted(rel["release_date"].unique()), dtype="datetime64[ns]")
    ih = pd.read_parquet(IH)
    ih = ih[ih["status"] == "ok"][["ticker", "entry", "IH_rom"]]

    # 1974 hedged hold to expiry, windows that contain mega-cap nights vs windows that contain none
    q = panel[panel["ticker"] == "QQQ"].merge(ih, on=["ticker", "entry"], how="left")
    exp = q["entry"] + pd.to_timedelta(q["dte_d"], unit="D")
    q["n_rel_win"] = [
        int(((rel_days >= np.datetime64(a)) & (rel_days < np.datetime64(b))).sum()) if pd.notna(b)
        else 0 for a, b in zip(q["entry"], exp)
    ]
    # controls must carry no release anywhere in their hold window
    q["n_rep_orig"] = q["n_rep"]
    q["n_rep"] = q["n_rel_win"]
    print("1974 QQQ hedged hold to expiry, windows with mega-cap releases vs none, margin")
    p = paired(q, q["n_rel_win"] > 0, "IH_rom", "dte_d")
    report(1974, "QQQ short straddle delta-hedged to expiry earns more when its window holds "
           "mega-cap releases", "the hedged hold collects the event crush without an exit crossing "
           "(the single-name structural lever, moved to the index)",
           "per trade, hedged to expiry at closes, settle intrinsic, unit margin p0+0.15F", p, +1)

    # 1975 SPY short front 15:59 -> 10:00 on event nights
    s = panel[panel["ticker"] == "SPY"].copy()
    print("1975 SPY short front 15:59 -> 10:00 on mega-cap nights, margin")
    p = paired(s, s["n_rep"].fillna(0) > 0, "short_touch_net_rom_o", "dte_o")
    report(1975, "SPY short front 15:59 to 10:00 on mega-cap nights is positive and beats controls",
           "tightest spread of the three ETFs; event share of SPY smaller but cost smaller still",
           "per trade, net at touch, unit margin p0+0.15F, 15:59 to 10:00", p, +1)

    # 1976 IWM short front 15:59 -> 15:59 on mega-cap nights (reporting-season richness)
    w = panel[panel["ticker"] == "IWM"].copy()
    print("1976 IWM short front 15:59 -> 15:59 on mega-cap nights, margin (DISCOVERY-DERIVED)")
    p = paired(w, w["n_rep"].fillna(0) > 0, "short_touch_net_rom_d", "dte_d")
    report(1976, "IWM short front on mega-cap nights beats controls (DISCOVERY-DERIVED from the 1968 "
           "placebo)", "index options rich in the reporting season while realised index variance is "
           "not (falling implied-realised correlation gap)",
           "per trade, net at touch, unit margin p0+0.15F, 15:59 to 15:59", p, +1)

    # descriptive: event-night short at the mid and the share of the spread in the touch loss
    q2 = panel[panel["ticker"] == "QQQ"].copy()
    e = q2["n_rep"].fillna(0) > 0
    rows = []
    for b in ("P", "M", "C"):
        for lab, m in (("event", e), ("control", ~e)):
            x = q2[m & (q2["block"] == b) & ~q2["exit_macro"]]
            rows.append({"block": b, "set": lab, "N": len(x),
                         "short_mid_d_prem": x["short_mid_d"].mean(),
                         "short_touch_net_d_prem": x["short_touch_net_d"].mean(),
                         "short_mid_o_prem": x["short_mid_o"].mean(),
                         "short_touch_net_o_prem": x["short_touch_net_o"].mean()})
    dd = pd.DataFrame(rows)
    print(dd.round(4).to_string())
    dd.to_csv(HERE / "mid_vs_touch_qqq.csv", index=False)


# ── round 4 ──────────────────────────────────────────────────────────────────
def intraday_frame(panel: pd.DataFrame, tk: str) -> pd.DataFrame:
    """Session d = the session after night t; event = a mega-cap release after t's close."""
    it = pd.read_parquet(HERE / "intraday.parquet")
    it = it[(it["ticker"] == tk) & (it["status"] == "ok")].copy()
    macro = pd.read_csv(HERE.parents[3] / "data" / "cache" / "index_events"
                        / "macro_releases_2016_2026.csv", parse_dates=["date"])
    vix = pd.read_parquet(HERE / "vix_fred.parquet").set_index("date")["vix"]
    pn = panel[panel["ticker"] == tk][["entry", "n_rep", "reporters", "W"]].copy()
    pn["day"] = pn["entry"].map(lambda t: SESS[POS[t] + 1])
    it = it.merge(pn.drop(columns="entry"), on="day", how="left")
    print(f"  {tk} intraday rows {len(it)}, without a prior-night panel row "
          f"{int(it['n_rep'].isna().sum())}")
    it["n_rep"] = it["n_rep"].fillna(0)
    it["entry"] = it["day"]  # the decision and the hold are on d
    it["weekday"] = it["day"].dt.weekday
    it["vix_prev"] = it["day"].map(lambda d: vix.get(SESS[POS[d] - 1], np.nan))
    it["exit_macro"] = it["day"].isin(set(macro["date"]))
    it["block"] = np.select([it["day"] < "2019-01-01", it["day"] < "2025-01-01"], ["P", "M"], "C")
    return it


def round4(panel: pd.DataFrame) -> None:
    for tid, tk, note in ((1977, "QQQ", ""), (1978, "SPY", " SPY version"),
                          (1979, "IWM", " IWM placebo")):
        it = intraday_frame(panel, tk)
        e = it["n_rep"] > 0
        sp = it.groupby(["block", e.rename("event")])[["hs_entry", "hs_exit", "long_mid"]].mean()
        print(f"{tid}{note}: long front straddle 10:00 to 15:59 on the session after a release")
        print(sp.round(4).to_string())
        p = paired(it, e, "long_net_debit", "dte")
        report(tid, f"long {tk} front straddle 10:00 to 15:59 on the day after a mega-cap release "
               "beats matched days and is positive (DISCOVERY-DERIVED: mid decomposition seen on "
               "all blocks)", "post-announcement index variance stays high through the next session "
               "while the option re-prices down at the open (spillover and price discovery)",
               "per trade, net at touch, unit debit (10:00 asks), 10:00 to 15:59 same session", p, +1)
        p.drop(columns="ctl_vals").to_parquet(HERE / f"r4_{tk}_events.parquet")
        pm = paired(it, e, "long_mid", "dte")
        s = pm.dropna(subset=["diff"])
        for b in ("P", "M", "C"):
            x = s[s["block"] == b]
            print(f"    mid {b}: N={len(x)} event {x['event'].mean():+.4f} ctl "
                  f"{x['control'].mean():+.4f} diff {x['diff'].mean():+.4f} (gross at mid, descriptive)")


# ── round 5 (discovery block M only) and the frozen held-out read ───────────
def gap_frame(panel: pd.DataFrame, tk: str) -> pd.DataFrame:
    it = intraday_frame(panel, tk)
    pn = panel[panel["ticker"] == tk].copy()
    pn["day"] = pn["entry"].map(lambda t: SESS[POS[t] + 1])
    gap = np.log(pn["fwd1_o"] / pn["fwd0_o"]).abs()  # 15:59 on t to 10:00 on d, same contract
    it["gap"] = it["day"].map(pd.Series(gap.to_numpy(), index=pn["day"]))
    print(f"  {tk}: days without a gap {int(it['gap'].isna().sum())} of {len(it)}")
    return it


def round5(panel: pd.DataFrame, blocks: tuple[str, ...] = ("M",)) -> None:
    it = gap_frame(panel, "QQQ")
    e = it["n_rep"] > 0
    g_star = float(it.loc[e & (it["block"] == "M"), "gap"].median())
    w_star = float(it.loc[e & (it["block"] == "M"), "W"].median())
    print(f"discovery event-day median gap {g_star:.4%}, median W {w_star:.3f} (features only)")
    basis = "per trade, net at touch, unit debit (10:00 asks), 10:00 to 15:59 same session"

    big = e & (it["gap"] >= g_star)
    print("1980 long intraday after a release with overnight gap >= g*")
    p = paired(it, big, "long_net_debit", "dte")
    report(1980, f"long QQQ 10:00-15:59 after a mega-cap release when the overnight gap >= {g_star:.4%} "
           "beats matched days (DISCOVERY-DERIVED)", "large announcement gaps continue through the "
           "session; the 10:00 straddle under-prices the persistence", basis, p, +1, blocks)

    it2 = it.copy()
    it2["exit_macro"] = it2["exit_macro"] | (~e & (it2["gap"] < g_star))  # big-gap controls only
    print("1981 right-driver: event big-gap days against NON-event big-gap days")
    p = paired(it2, big, "long_net_debit", "dte")
    report(1981, "after a mega-cap release, the big-gap intraday long beats big-gap days without a "
           "release (event, not volatility clustering, carries 1980)",
           "event-specific persistence of announcement variance", basis, p, +1, blocks)

    heavy = e & (it["W"] >= w_star)
    print("1982 long intraday after heavy nights (W >= median)")
    p = paired(it, heavy, "long_net_debit", "dte")
    report(1982, f"long QQQ 10:00-15:59 after heavy release nights (W >= {w_star:.3f}) beats matched "
           "days", "more reporter weight, more post-announcement index variance", basis, p, +1, blocks)


def round5b(panel: pd.DataFrame, blocks: tuple[str, ...] = ("M",)) -> None:
    """1983: the gap rule on days with no release (right-driver check with full power)."""
    it = gap_frame(panel, "QQQ")
    e = it["n_rep"] > 0
    g_star = float(it.loc[e & (it["block"] == "M"), "gap"].median())
    x = it.copy()
    x["exit_macro"] = x["exit_macro"] | e  # release days leave the pool entirely
    x["n_rep"] = (x["gap"] >= g_star).astype(float)  # pseudo-event: big gap, no release
    x["W"] = 0.0
    x["reporters"] = ""
    print(f"1983 non-release days: gap >= {g_star:.4%} against matched small-gap days")
    p = paired(x, x["n_rep"] > 0, "long_net_debit", "dte")
    report(1983, "on days WITHOUT a release, the big-gap intraday long beats small-gap days "
           "(if so, volatility clustering, not the event, carries 1980)",
           "volatility clustering after any large overnight gap",
           "per trade, net at touch, unit debit (10:00 asks), 10:00 to 15:59 same session", p, +1,
           blocks)


def round_reg(panel: pd.DataFrame, blocks: tuple[str, ...] = ("M",)) -> None:
    """1984: OLS of the intraday long on release-day flag, |gap|, prior VIX, dte and weekday
    dummies; day-resampled bootstrap for the release coefficient (one observation per day)."""
    it = gap_frame(panel, "QQQ")
    it = it[~it["exit_macro"] & it["gap"].notna() & it["vix_prev"].notna()].copy()
    it["ev"] = (it["n_rep"] > 0).astype(float)
    for b in blocks:
        x = it[it["block"] == b]
        dummies = pd.get_dummies(x[["weekday"]].astype(str).assign(
            dte=np.minimum(x["dte"], 5).astype(str)), drop_first=True).astype(float)
        X = np.column_stack([np.ones(len(x)), x["ev"], x["gap"] * 100, x["vix_prev"] / 10,
                             dummies.to_numpy()])
        y = x["long_net_debit"].to_numpy()
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        rng = np.random.default_rng(0)
        bs = np.empty((2000, 3))
        for i in range(2000):
            ix = rng.integers(0, len(y), len(y))
            bs[i] = np.linalg.lstsq(X[ix], y[ix], rcond=None)[0][1:4]
        lo, hi = np.quantile(bs[:, 0], [0.025, 0.975])
        se = bs[:, 0].std(ddof=1)
        print(f"  1984 {b}: N={len(y)} release coef {beta[1]:+.4f} [{lo:+.4f},{hi:+.4f}] "
              f"t={beta[1] / se:+.2f}; gap per 1pp {beta[2]:+.4f} "
              f"[{np.quantile(bs[:, 1], 0.025):+.4f},{np.quantile(bs[:, 1], 0.975):+.4f}]; "
              f"VIX per 10 {beta[3]:+.4f}")
        log_trial({"trial_id": 1984, "hypothesis": "release day adds to the intraday long after "
                   "controlling for |overnight gap|, prior VIX, dte and weekday (right-driver test)",
                   "mechanism": "event-specific persistence vs plain volatility clustering",
                   "block": b, "N": len(y), "effect": f"{beta[1]:.5f}", "ci_low": f"{lo:.5f}",
                   "ci_high": f"{hi:.5f}", "t": f"{beta[1] / se:.2f}", "null_pct": "",
                   "basis": f"OLS coefficient, per trade, net at touch, unit debit, 10:00-15:59; "
                            f"gap coef per 1pp {beta[2]:.5f}",
                   "verdict": ("event adds (exploratory)" if lo > 0 else "event adds nothing "
                               "beyond gap at 95% (exploratory)")})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=1)
    args = ap.parse_args()
    panel = pd.read_parquet(HERE / "panel.parquet")
    if args.round == 1:
        round1(panel)
    elif args.round == 2:
        round2(panel)
    elif args.round == 3:
        round3(panel)
    elif args.round == 4:
        round4(panel)
    elif args.round == 5:
        round5(panel)
    elif args.round == 6:
        round5b(panel)
    elif args.round == 7:
        round_reg(panel)
    elif args.round == 8:  # held-out read, frozen in freeze_2026-11-13_post-release-intraday-long.md
        it = gap_frame(panel, "QQQ")
        e = it["n_rep"] > 0
        g_star = 0.006094  # frozen discovery median gap
        p = paired(it, e & (it["gap"] >= g_star), "long_net_debit", "dte")
        report(1980, "HELD-OUT READ of frozen 1980", "as frozen",
               "per trade, net at touch, unit debit (10:00 asks), 10:00 to 15:59 same session",
               p, +1, ("C", "P"))
        p.drop(columns="ctl_vals").to_parquet(HERE / "heldout_1980_events.parquet")
        round_reg(panel, ("C", "P"))


if __name__ == "__main__":
    main()



