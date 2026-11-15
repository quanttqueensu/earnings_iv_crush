"""
s01_peer_nights.py
Build the peer-night table and count option-chain feasibility. No outcome is computed here.

A peer night is (bellwether event B, peer P): B reports (after the close of its entry session, or
before the open of its reaction session), P shares B's three-digit SIC code on B's entry date, and
P has no known report from two sessions before B's entry to six sessions after B's reaction.
"Lead" marks B as the first universe name in its SIC group to react in the prior 40 days.

The option count asks, for every peer night, whether a quote chain exists for P on B's entry
session and on B's reaction session, by cache, by filename.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s01_peer_nights.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

LEAD_LOOKBACK_DAYS = 40  # a reporting season's head start; a quarter's reports span ~6 weeks


def main() -> None:
    sess = lib.sessions()
    spos = {d: i for i, d in enumerate(sess)}
    ev = lib.events()
    ev = ev[(ev["exit_date"] >= sess.min()) & (ev["exit_date"] <= sess.max())].copy()
    ev = ev[ev["entry_date"].isin(spos) & ev["exit_date"].isin(spos)].copy()
    print(f"events inside CRSP sessions: {len(ev)}")
    names = lib.sic_history()
    univ = np.array(sorted(pd.read_parquet(lib.CRSP_SLICE, columns=["permno"])["permno"].unique()))
    ev["sic"] = lib.sic_at(names, ev["permno"].to_numpy(), ev["entry_date"].to_numpy())
    ev = ev.dropna(subset=["sic"])
    ev["sic3"] = (ev["sic"] // 10 ** (4 - lib.SIC_DIGITS)).astype(int)
    print(f"events with SIC: {len(ev)}")

    # lead flag: no other same-SIC3 universe event reacting in the prior LEAD_LOOKBACK_DAYS
    ev = ev.sort_values("exit_date").reset_index(drop=True)
    lead = np.zeros(len(ev), dtype=bool)
    for _, g in ev.groupby("sic3"):
        x = g["exit_date"].to_numpy()
        p = g["permno"].to_numpy()
        for k, i in enumerate(g.index):
            lo = x[k] - np.timedelta64(LEAD_LOOKBACK_DAYS, "D")
            prior = (x < x[k]) & (x >= lo) & (p != p[k])
            lead[i] = not prior.any()
    ev["lead"] = lead

    rep = lib.all_report_dates()

    # SIC for every universe permno at every event's entry date, via the name history
    ev["i0"] = ev["entry_date"].map(spos)
    ev["i1"] = ev["exit_date"].map(spos)
    ev = ev[(ev["i0"] - lib.PEER_CLEAR_BEFORE >= 0)
            & (ev["i1"] + lib.PEER_CLEAR_AFTER < len(sess))].copy()
    ev["w0"] = sess[(ev["i0"] - lib.PEER_CLEAR_BEFORE).to_numpy()]
    ev["w1s"] = sess[(ev["i1"] + lib.PEER_CLEAR_SHORT).to_numpy()]
    ev["w1"] = sess[(ev["i1"] + lib.PEER_CLEAR_AFTER).to_numpy()]
    nm = names[names["permno"].isin(univ)].dropna(subset=["siccd"])
    dates = pd.DataFrame({"entry_date": ev["entry_date"].unique()})
    x = dates.merge(nm, how="cross")
    x = x[(x["namedt"] <= x["entry_date"]) & (x["nameendt"] >= x["entry_date"])]
    x = x.sort_values("namedt").drop_duplicates(["entry_date", "permno"], keep="last")
    x["sic3"] = (x["siccd"].astype(int) // 10 ** (4 - lib.SIC_DIGITS)).astype(int)
    x = x.rename(columns={"permno": "p_permno", "ticker": "p_ticker"})[
        ["entry_date", "p_permno", "p_ticker", "sic3"]]
    cand = ev.rename(columns={"permno": "b_permno", "ticker": "b_ticker"}).merge(
        x, on=["entry_date", "sic3"])
    cand = cand[cand["p_permno"] != cand["b_permno"]].reset_index(drop=True)
    funnel = {"pairs_same_sic3": len(cand)}
    cand["cid"] = np.arange(len(cand))
    ov = cand[["cid", "p_permno", "w0", "w1s", "w1", "exit_date"]].merge(
        rep.rename(columns={"permno": "p_permno"}), on="p_permno")
    bad = set(ov.loc[(ov["d1"] >= ov["w0"]) & (ov["d0"] <= ov["w1s"]), "cid"])
    bad_long = set(ov.loc[(ov["d1"] >= ov["w0"]) & (ov["d0"] <= ov["w1"]), "cid"])
    # the peer's next own report window starting after B's reaction (Thomas-Zhang horizon)
    nxt = ov[ov["d0"] > ov["exit_date"]].groupby("cid")["d0"].min()
    funnel["peer_reporting_short_window"] = len(bad)
    funnel["peer_reporting_long_window"] = len(bad_long)
    cand["clear_long"] = ~cand["cid"].isin(bad_long)
    cand["p_next_report_d0"] = cand["cid"].map(nxt)
    pn = cand[~cand["cid"].isin(bad)][
        ["b_permno", "b_ticker", "entry_date", "exit_date", "amc", "sic3", "lead",
         "p_permno", "p_ticker", "clear_long", "p_next_report_d0"]].reset_index(drop=True)
    funnel["kept"] = len(pn)
    funnel["kept_clear_long"] = int(pn["clear_long"].sum())
    print(f"peer-night funnel: {funnel}")
    print(f"peer nights {len(pn)}; bellwether events with a peer {pn[['b_permno','exit_date']].drop_duplicates().shape[0]}"
          f"; lead {int(pn['lead'].sum())} peer nights")
    pn["year"] = pn["exit_date"].dt.year
    pn["b_event"] = pn["b_ticker"] + "_" + pn["exit_date"].dt.strftime("%Y-%m-%d")
    print(pn.groupby("year").agg(peer_nights=("p_permno", "size"),
                                 bellwether_events=("b_event", "nunique"),
                                 reaction_dates=("exit_date", "nunique"),
                                 lead_peer_nights=("lead", "sum"),
                                 clear_long=("clear_long", "sum")).to_string())
    pn.to_parquet(lib.HERE / "peer_nights.parquet", index=False)

    # ── option-chain feasibility, by filename only ───────────────────────────
    caches = {
        "backfill_1559": "data/cache/backfill_chains/*.parquet",
        "entry_1545": "data/cache/entry_1545_chains/*.parquet",
        "flow_sessions": "data/cache/flow/*/*.parquet",
        "dolthub_runup": "data/cache/dolthub_runup/*.parquet",
        "dolthub_spread": "data/cache/dolthub_spread/*.parquet",
        "dolthub_p2": "data/cache/dolthub_p2/chains/*.parquet",
        "alpaca_panel_lasttrade": "data/processed/alpaca_chain_panel_*.parquet",
        "alpaca_entry_lasttrade": "data/processed/alpaca_chain_entry_*.parquet",
    }
    feas = {}
    for k, g in caches.items():
        pat = str(lib.ROOT / g)
        idx = lib.file_index(pat)
        if k.startswith("alpaca"):
            idx = {(t.split("_")[-1], d) for t, d in idx}
        e0 = [(t, f"{d:%Y-%m-%d}") in idx for t, d in zip(pn["p_ticker"], pn["entry_date"], strict=True)]
        e1 = [(t, f"{d:%Y-%m-%d}") in idx for t, d in zip(pn["p_ticker"], pn["exit_date"], strict=True)]
        both = np.array(e0) & np.array(e1)
        feas[k] = {"files": len(idx), "entry_side": int(np.sum(e0)), "reaction_side": int(np.sum(e1)),
                   "both": int(both.sum()), "both_lead": int((both & pn["lead"].to_numpy()).sum())}
        print(f"{k:24s} files {len(idx):6d}  peer chain on B entry {sum(e0):5d}  on B reaction "
              f"{sum(e1):5d}  both {int(both.sum()):5d}")
    (lib.HERE / "feasibility.json").write_text(json.dumps(
        {"peer_nights": len(pn), "funnel": funnel, "caches": feas}, indent=2))


if __name__ == "__main__":
    main()
