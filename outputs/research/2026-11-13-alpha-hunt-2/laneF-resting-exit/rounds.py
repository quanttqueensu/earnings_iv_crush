"""
rounds.py
Lane F trial slates. Each hypothesis and mechanism is written here before its round is run;
later rounds are added after the previous round's diagnosis in diagnosis.log.
"""

from __future__ import annotations

from lib import Rule

D = "disc_broad_2025"


def round1(ev, legs, trial) -> None:
    trial(
        1931,
        "R1 static: rest a buy at the 15:00 mid (rounded up) on both legs, cross the unfilled at "
        "the 15:59:00 ask; beats the 15:59:00 taker buy-back",
        "the reaction-session exit spread (about 3% of premium per side) is paid by takers; a bid "
        "at the mid is filled by retail and dealer sellers and captures up to half of it; risk: "
        "fills come when the option is falling (adverse selection), which the paired statistic "
        "includes because the alternative is the later 15:59 ask",
        Rule(), ev, legs, D,
    )
    trial(
        1932,
        "R2 re-peg: re-price the bid to the current mid at the top of every minute 15:00-15:58",
        "a static limit goes stale as the post-announcement price drifts; re-pegging keeps the "
        "order at the current mid so fills track the moving market and do not depend on a "
        "reversal to a stale price",
        Rule(repeg=True), ev, legs, D,
    )
    trial(
        1933,
        "R3 wide leg only: rest only the leg with the wider dollar spread at 15:00 (static mid), "
        "cross the other at 15:59:00",
        "after a large move the in-the-money leg carries most of the dollar spread; resting only "
        "there captures most of the saving while the cheap leg, whose spread is a tick, is "
        "crossed with no adverse-selection exposure",
        Rule(legs="wide"), ev, legs, D,
    )
    trial(
        1934,
        "C1 control, taker at 15:00: lift both asks at 15:00 instead of 15:59:00",
        "separates the clock from liquidity provision: if option prices drift between 15:00 and "
        "15:59 (continued crush or reversal), part of any resting gain is timing, not spread; "
        "expected near zero if the reaction-day afternoon has no drift",
        Rule(taker_at=0), ev, legs, D,
    )


def round2(ev, legs, trial) -> None:
    rp = Rule(repeg=True)
    trial(
        1935,
        "R2 re-peg minus the 15:00 taker (lift both asks at 15:00): liquidity provision net of "
        "the clock",
        "if the resting gain is spread capture rather than the time-of-day spread pattern, the "
        "re-peg beats a taker who trades when the order first goes in",
        rp, ev, legs, D, base_rule=Rule(taker_at=0), extra="; paired vs 15:00 ask taker",
    )
    trial(
        1936,
        "R2 re-peg minus the 15:30 taker (trial 1725's clock): liquidity provision net of the "
        "best known taker clock",
        "as 1935, against the exit clock round 1 already scored",
        rp, ev, legs, D, base_rule=Rule(taker_at=30), extra="; paired vs 15:30 ask taker",
    )
    trial(
        1937,
        "R2 re-peg under the through-only rule (a print strictly below the limit)",
        "a print at the limit does not prove a resting bid at that price would have been reached "
        "(queue); requiring a print through it is the conservative fill evidence",
        Rule(repeg=True, fill="through"), ev, legs, D,
    )
    trial(
        1938,
        "R2 re-peg under the clean-print rule (print at or below the limit and at or above the "
        "NBBO bid)",
        "prints below the NBBO bid are mostly complex-order legs that would not trade with a "
        "simple resting bid; dropping them removes spurious fills",
        Rule(repeg=True, fill="clean"), ev, legs, D,
    )
    trial(
        1939,
        "R2 re-peg with the tick schedule inferred from each class's own quotes (nickel/dime "
        "classes round the limit up to 0.05/0.10)",
        "the penny schedule overstates the capture on classes that quote in nickels",
        Rule(repeg=True, ticks="auto"), ev, legs, D,
    )
    trial(
        1940,
        "R4 late re-peg: rest from 15:45, re-peg each minute, cross at 15:59:00 "
        "(discovery-derived from the round-1 path diagnosis)",
        "the straddle mid drifts down through the afternoon and spreads blow out at 15:50-15:55; "
        "resting only in the last quarter-hour avoids paying the drift and captures the wider "
        "spread",
        Rule(start=45, repeg=True), ev, legs, D,
    )
    trial(
        1941,
        "R5 bid plus one tick, re-pegged each minute from 15:00",
        "a bid one tick above the NBBO bid is filled only by sellers who would have hit the bid; "
        "it captures nearly the whole spread when filled, at a lower fill rate",
        Rule(repeg=True, price="bid1"), ev, legs, D,
    )


def hold_trial(tid, hyp, mech, rule, ev, legs, block, kind) -> dict:
    """Comparisons with the hedged hold H (2026-11-02 tables, same ticker and entry date).

    kind 'vs_hold': resting buy-back level minus H. kind 'hybrid': rest; if no leg fills by
    15:59:00 hold hedged instead of crossing (any fill: cross the other leg), minus H.
    H uses the hold study's contract (strike nearest the parity forward); the subset where it is
    the same strike as the tick contract is reported beside the full read.
    """
    import numpy as np

    import run
    from lib import clustered_t, log_trial, mean_ci

    d = run.scored(ev, legs, rule)
    d = d[run.block_mask(d, block) & (d["measured"] == True)].copy()  # noqa: E712
    d = d.merge(run.hold_table(), on=["ticker", "entry_date"], how="left")
    n_all = len(d)
    d = d[d["H"].notna()].copy()
    if kind == "vs_hold":
        d["y"] = d["b_rule"] - d["H"]
    else:
        d["hyb"] = np.where(d["n_fill"] >= 1, d["b_rule"], d["H"])
        d["y"] = d["hyb"] - d["H"]
    out = {}
    for lab, g in (("all", d), ("same_strike", d[d["strike"] == d["strike_h"]])):
        ci = mean_ci(g["y"], g["exit_date"])
        lv = mean_ci(g["hyb"] if kind == "hybrid" else g["b_rule"], g["exit_date"])
        hv = mean_ci(g["H"], g["exit_date"])
        out[lab] = {"n": ci.n, "y": ci.point, "lo": ci.low, "hi": ci.high,
                    "t": clustered_t(g["y"], g["exit_date"]), "level": (lv.point, lv.low, lv.high),
                    "H": (hv.point, hv.low, hv.high)}
        print(f"[{tid} {block} {kind} {lab}] N={ci.n} of {n_all}: diff {ci}; level "
              f"{lv.point:+.5f} [{lv.low:+.5f},{lv.high:+.5f}]; H {hv.point:+.5f} "
              f"[{hv.low:+.5f},{hv.high:+.5f}]")
    if kind == "hybrid":
        nf = d["n_fill"] == 0
        print(f"   no-fill share {nf.mean():.3f}; on no-fill events H {d.loc[nf, 'H'].mean():+.5f} vs "
              f"B_rule {d.loc[nf, 'b_rule'].mean():+.5f}; on fill events H "
              f"{d.loc[~nf, 'H'].mean():+.5f} vs B_rule {d.loc[~nf, 'b_rule'].mean():+.5f}")
    a = out["all"]
    log_trial({
        "trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": block, "n": a["n"],
        "effect": round(a["y"], 6), "ci_low": round(a["lo"], 6), "ci_high": round(a["hi"], 6),
        "t": round(a["t"], 2), "null_percentile": "n/a (paired rule)",
        "basis": "per trade, m0 units, paired vs hedged hold H on the same event (H on its own "
                 "contract), net at touch or resting limit",
        "verdict": f"exploratory: {'beats H' if a['lo'] > 0 else ('worse than H' if a['hi'] < 0 else 'no difference from H')}; "
                   f"level {a['level'][0]:+.5f} [{a['level'][1]:+.5f}, {a['level'][2]:+.5f}] vs H "
                   f"{a['H'][0]:+.5f}; same-strike subset N={out['same_strike']['n']} diff "
                   f"{out['same_strike']['y']:+.5f} [{out['same_strike']['lo']:+.5f}, "
                   f"{out['same_strike']['hi']:+.5f}]",
    })
    return out


def round3(ev, legs, trial) -> None:
    rp = Rule(repeg=True)
    hold_trial(
        1942,
        "Resting re-peg buy-back (R2) is competitive with the hedged hold: B_R2 minus H",
        "resting recovers part of the exit half-spread; the hold avoids the exit spread entirely "
        "and keeps collecting post-event decay; competitive only if the recovered spread is most "
        "of H - B (about 2-3% of m0)",
        rp, ev, legs, D, "vs_hold",
    )
    hold_trial(
        1943,
        "Hybrid complement: rest R2 on the reaction session; if no leg fills, hold hedged instead "
        "of crossing (any fill: cross the other leg); minus always-hold H",
        "fills arrive when sellers push option prices down; on the events with no fill the "
        "option is bid up and the buy-back is expensive, which is where holding should help most",
        rp, ev, legs, D, "hybrid",
    )
    lad = Rule(repeg=True, price="bid1", ladder_at=45)
    trial(
        1944,
        "R6 ladder: bid plus one tick re-pegged 15:00-15:44, then the mid re-pegged 15:45-15:58, "
        "cross at 15:59:00 (discovery-derived from 1932 and 1941)",
        "patient bid-plus-tick fills carry a small markout (-0.35 half-spreads in 1941); "
        "escalating to the mid late fills most of the remainder before the cross",
        lad, ev, legs, D,
    )
    trial(
        1945,
        "R6 ladder minus the 15:30 taker: liquidity provision net of the best known clock",
        "as 1936 for the ladder",
        lad, ev, legs, D, base_rule=Rule(taker_at=30), extra="; paired vs 15:30 ask taker",
    )
    trial(
        1946,
        "R6 ladder under the through-only rule",
        "conservative fill evidence for the ladder",
        Rule(repeg=True, price="bid1", ladder_at=45, fill="through"), ev, legs, D,
    )


def random_taker_null(ev, legs, rule, block, n_draws=2000, seed=0):
    """Timing-matched null for an execution rule: each event lifts both asks at a minute drawn
    uniformly from the rule's own resting window, against the same 15:59:00 baseline."""
    import numpy as np

    import run
    from lib import END, ask_at, quote_at

    d = run.scored(ev, legs, rule)
    d = d[run.block_mask(d, block) & (d["measured"] == True)].copy()  # noqa: E712
    mins = list(range(rule.start, min(rule.cross_at, 59)))
    mat = np.full((len(d), len(mins)), np.nan)
    for i, e in enumerate(d.itertuples(index=False)):
        lc, lp = legs[(e.eid, "C")], legs[(e.eid, "P")]
        base = ask_at(lc, END) + ask_at(lp, END)
        for j, m in enumerate(mins):
            t = m * 60.0
            ac = ask_at(lc, t) or (quote_at(lc, t) or (0, np.nan))[1]
            ap = ask_at(lp, t) or (quote_at(lp, t) or (0, np.nan))[1]
            mat[i, j] = (base - ac - ap) / e.m0
    rng = np.random.default_rng(seed)
    rows = np.arange(len(d))
    draws = np.array([np.nanmean(mat[rows, rng.integers(0, len(mins), len(d))])
                      for _ in range(n_draws)])
    return d, mat, draws


def round4(ev, legs, trial) -> None:
    import numpy as np

    import run
    from lib import clustered_t, log_trial, mean_ci

    rp = Rule(repeg=True)
    d, mat, draws = random_taker_null(ev, legs, rp, D)
    rand_mean_per_event = np.nanmean(mat, axis=1)
    y = d["imp"].to_numpy() - rand_mean_per_event
    ci = mean_ci(y, d["exit_date"])
    pct = float(100 * (draws < d["imp"].mean()).mean())
    print(f"[1947] R2 minus random-minute taker: {ci}; null mean {draws.mean():+.5f}, "
          f"R2 {d['imp'].mean():+.5f}, percentile {pct:.1f}")
    log_trial({
        "trial_id": 1947,
        "hypothesis": "R2 re-peg beats a taker who lifts the asks at a random minute of the same "
                      "15:00-15:58 window (timing-matched null for an execution rule)",
        "mechanism": "a resting bid trades when a seller arrives; if that timing carries no "
                     "information beyond the time-of-day spread pattern the rule equals a random "
                     "taker; it beats it only by capturing spread net of adverse selection",
        "block": D, "n": ci.n, "effect": round(ci.point, 6), "ci_low": round(ci.low, 6),
        "ci_high": round(ci.high, 6), "t": round(clustered_t(y, d["exit_date"]), 2),
        "null_percentile": round(pct, 1),
        "basis": "per trade, m0 units, R2 improvement minus the event's mean random-minute taker "
                 "improvement (both vs 15:59:00 ask); null = 2,000 draws of one random minute per event",
        "verdict": f"exploratory: {'beats random-time taker' if ci.low > 0 else 'no difference'}",
    })
    trial(
        1948,
        "R7 rest the re-pegged mid 15:00-15:44 and lift unfilled asks at 15:45 "
        "(discovery-derived from the path diagnosis)",
        "spreads are narrow until 15:45 and blow out at 15:50-15:55; crossing the remainder at "
        "15:45 avoids the spike that the 15:59 cross pays",
        Rule(repeg=True, cross_at=45), ev, legs, D,
    )
    # same-contract reads against the hold: B_h (hold study's contract) plus the tick improvement
    for tid, kind in ((1949, "vs_hold"), (1950, "hybrid")):
        g = run.scored(ev, legs, rp)
        g = g[run.block_mask(g, D) & (g["measured"] == True)].merge(  # noqa: E712
            run.hold_table(), on=["ticker", "entry_date"], how="left")
        g = g[g["H"].notna() & g["B_h"].notna()].copy()
        g["b_rest_h"] = g["B_h"] + g["imp"]
        if kind == "vs_hold":
            g["y"] = g["b_rest_h"] - g["H"]
            lvl = g["b_rest_h"]
        else:
            lvl = np.where(g["n_fill"] >= 1, g["b_rest_h"], g["H"])
            g["y"] = lvl - g["H"]
        c = mean_ci(g["y"], g["exit_date"])
        lv = mean_ci(lvl, g["exit_date"])
        hb = mean_ci(g["H"] - g["B_h"], g["exit_date"])
        print(f"[{tid}] {kind} same-contract: {c}; level {lv}; H-B_h {hb}")
        log_trial({
            "trial_id": tid,
            "hypothesis": ("Same-contract read: resting buy-back (B on the hold contract plus the "
                           "R2 improvement) minus H" if kind == "vs_hold" else
                           "Same-contract hybrid: rest R2; no fill -> hold hedged; minus H"),
            "mechanism": "fixes 1942/1943, which mixed the tick contract's level with the hold "
                         "contract's H; the improvement is transferred, the levels are not",
            "block": D, "n": c.n, "effect": round(c.point, 6), "ci_low": round(c.low, 6),
            "ci_high": round(c.high, 6), "t": round(clustered_t(g["y"], g["exit_date"]), 2),
            "null_percentile": "n/a (paired rule)",
            "basis": "per trade, m0 of the hold contract, net, paired vs H on the same event",
            "verdict": f"exploratory: {'beats H' if c.low > 0 else ('worse than H' if c.high < 0 else 'no difference')}; "
                       f"level {lv.point:+.5f} [{lv.low:+.5f}, {lv.high:+.5f}]; H-B_h {hb.point:+.5f}",
        })


def round5(ev, legs, trial) -> None:
    """Held-out read, once, as frozen in freeze_2026-11-13_repeg-exit.md."""
    import json

    import numpy as np
    import pandas as pd

    import run
    from lib import HERE, clustered_t, log_trial, mean_ci

    rp = Rule(repeg=True)
    ids = {"hold_broad_2026": (1951, 1952, 1955), "hold_megacap_2023_24": (1953, 1954, 1956)}
    summary = {}
    for blk, (t1, t2, t3) in ids.items():
        r, sel = trial(
            t1, "HELD-OUT H1: R2 re-peg improvement over the 15:59:00 ask buy-back (frozen)",
            "as trial 1932", rp, ev, legs, blk,
        )
        d, mat, draws = random_taker_null(ev, legs, rp, blk)
        y = d["imp"].to_numpy() - np.nanmean(mat, axis=1)
        ci = mean_ci(y, d["exit_date"])
        pct = float(100 * (draws < d["imp"].mean()).mean())
        tt = clustered_t(y, d["exit_date"])
        print(f"[{t2} {blk}] H2 R2 minus random-minute taker {ci}; t {tt:.2f}; percentile {pct:.1f}")
        log_trial({
            "trial_id": t2, "hypothesis": "HELD-OUT H2: R2 minus random-minute taker (frozen)",
            "mechanism": "as trial 1947", "block": blk, "n": ci.n, "effect": round(ci.point, 6),
            "ci_low": round(ci.low, 6), "ci_high": round(ci.high, 6), "t": round(tt, 2),
            "null_percentile": round(pct, 1),
            "basis": "per trade, m0 units, vs mean random-minute taker improvement",
            "verdict": "exploratory held-out: " + ("pass" if ci.low > 0 and pct >= 95 else "fail"),
        })
        g = run.scored(ev, legs, rp)
        g = g[run.block_mask(g, blk) & (g["measured"] == True)].merge(  # noqa: E712
            run.hold_table(), on=["ticker", "entry_date"], how="left")
        g = g[g["H"].notna() & g["B_h"].notna()].copy()
        g["y"] = g["B_h"] + g["imp"] - g["H"]
        c = mean_ci(g["y"], g["exit_date"])
        lv = mean_ci(g["B_h"] + g["imp"], g["exit_date"])
        hb = mean_ci(g["H"] - g["B_h"], g["exit_date"])
        print(f"[{t3} {blk}] same-contract resting buy-back minus H {c}; level {lv}; H-B {hb}")
        log_trial({
            "trial_id": t3,
            "hypothesis": "HELD-OUT descriptive: same-contract resting buy-back (B + R2 improvement) "
                          "minus H",
            "mechanism": "as trial 1949", "block": blk, "n": c.n, "effect": round(c.point, 6),
            "ci_low": round(c.low, 6), "ci_high": round(c.high, 6),
            "t": round(clustered_t(g["y"], g["exit_date"]), 2), "null_percentile": "n/a",
            "basis": "per trade, m0 of the hold contract, net, paired vs H",
            "verdict": f"descriptive: level {lv.point:+.5f} [{lv.low:+.5f}, {lv.high:+.5f}]; "
                       f"H-B {hb.point:+.5f} [{hb.low:+.5f}, {hb.high:+.5f}]",
        })
        summary[blk] = {"H1": r, "H2": {"point": ci.point, "lo": ci.low, "hi": ci.high, "t": tt,
                                        "pct": pct},
                        "vs_hold": {"point": c.point, "lo": c.low, "hi": c.high,
                                    "level": [lv.point, lv.low, lv.high],
                                    "H_minus_B": [hb.point, hb.low, hb.high]}}
    # coverage reweighting of H1 on the broad block: weight covered events to the universe's
    # distribution of reaction moves (abs_move quintiles of the 2026 hold-table universe)
    hc = pd.read_parquet(run.HH / "events_confirm_2025_26.parquet")
    hc["entry_date"] = pd.to_datetime(hc["entry_date"])
    uni = hc[hc["entry_date"].dt.year == 2026].dropna(subset=["abs_move"])
    edges = np.quantile(uni["abs_move"], [0, 0.2, 0.4, 0.6, 0.8, 1.0])
    edges[0], edges[-1] = -np.inf, np.inf
    g = run.scored(ev, legs, rp)
    g = g[run.block_mask(g, "hold_broad_2026") & (g["measured"] == True)].merge(  # noqa: E712
        hc[["ticker", "entry_date", "abs_move"]], on=["ticker", "entry_date"], how="left")
    g = g.dropna(subset=["abs_move"])
    g["bin"] = pd.cut(g["abs_move"], edges, labels=False)
    ub = pd.cut(uni["abs_move"], edges, labels=False).value_counts(normalize=True)
    cb = g["bin"].value_counts(normalize=True)
    g["w"] = g["bin"].map(ub / cb)
    by = g.groupby("bin").agg(n=("imp", "size"), imp=("imp", "mean"), lvl=("b_rule", "mean"))
    wmean = float(np.average(g["imp"], weights=g["w"]))
    wlvl = float(np.average(g["b_rule"], weights=g["w"]))
    print(f"coverage reweighting (broad 2026, N={len(g)}): H1 unweighted {g['imp'].mean():+.5f}, "
          f"weighted {wmean:+.5f}; level unweighted {g['b_rule'].mean():+.5f}, weighted {wlvl:+.5f}")
    print(by.assign(univ_share=ub.sort_index(), cov_share=cb.sort_index()).to_string())
    summary["reweight_broad_2026"] = {"n": len(g), "imp_w": wmean, "level_w": wlvl,
                                      "by_bin": by.reset_index().to_dict("records")}
    (HERE / "results" / "heldout_summary.json").write_text(json.dumps(summary, indent=1,
                                                                      default=str))


def round6(ev, legs, trial) -> None:
    """Post-freeze sensitivity (not part of the frozen criteria): the frozen rule under the
    through-only fill rule, which never credits a print at the limit (queue position)."""
    for tid, blk in ((1957, "hold_broad_2026"), (1958, "hold_megacap_2023_24")):
        trial(
            tid, "POST-FREEZE SENSITIVITY: R2 re-peg under the through-only fill rule",
            "as trial 1937; tests whether the held-out gain survives without at-limit prints",
            Rule(repeg=True, fill="through"), ev, legs, blk,
        )
