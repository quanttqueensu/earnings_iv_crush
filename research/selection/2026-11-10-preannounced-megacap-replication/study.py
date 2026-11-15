"""
study.py
Replication of the pre-announced-release selector on the megacap hedged-hold ledger.
Scores ``prereg.md`` exactly as frozen.

Usage
-----
    python research/selection/2026-11-10-preannounced-megacap-replication/study.py [--dry]

References
----------
Rogers, J. L., Skinner, D. J. and Van Buskirk, A. (2009). Earnings guidance and market
uncertainty. Journal of Accounting and Economics 48(1), 90-109.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
MEGA = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events_megacap.parquet"
ZOO = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
_spec = importlib.util.spec_from_file_location(
    "panels", HERE.parent / "2026-11-10-hackathon-panels" / "study.py"
)
assert _spec and _spec.loader
hp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp)
vol = hp.vol

BLOCK = ("2015-04-01", "2024-12-31")


def load() -> pd.DataFrame:
    """Megacap hedged-hold events with dates, permno, cells and the filing flag."""
    m = pd.read_parquet(MEGA)
    n0 = len(m)
    m = m[m["status"] == "ok"].copy()
    z = pd.read_parquet(ZOO, columns=["ticker", "entry_date", "announce_date"])
    f = pd.read_parquet(vol.FEATURES, columns=["ticker", "entry_date", "permno"])
    for x in (m, z, f):
        x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = m.merge(z, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d = d.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    c = pd.read_parquet(hp.CHARS, columns=["permno", "ticker", "eom"]).sort_values("eom")
    tmap = c.drop_duplicates("ticker", keep="last").set_index("ticker")["permno"]
    d["permno"] = d["permno"].fillna(d["ticker"].map(tmap))
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d["F0"] = (d["m0"] - d["s0"]) / vol.MARGIN_SPOT_FRAC
    d["implied_move"] = d["mid0"] / d["F0"]
    dte = (pd.to_datetime(d["expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
    d["tenor"] = pd.cut(dte, vol.TENOR_EDGES, labels=vol.TENOR_LABELS).astype(str)
    d["y"] = d["H"] * d["m0"] / d["mid0"]
    d = d.sort_values("announce_date").reset_index(drop=True)
    d["im_bin"] = causal_bins(d["implied_move"].to_numpy(float), d["announce_date"], 3, 200)
    d["cell"] = d["im_bin"] * 10 + pd.Categorical(d["tenor"], vol.TENOR_LABELS).codes
    print(f"funnel: {n0} megacap rows, {len(d)} ok, permno {int(d['permno'].notna().sum())}")
    d = hp.attach_preannounced(d)
    inb = d["announce_date"].between(pd.Timestamp(BLOCK[0]), pd.Timestamp(BLOCK[1]))
    return d.assign(M1=d["P1"], M1_def=d["P1_cov"] & inb)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="counts only, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = load()
    ok = d["M1_def"] & (d["im_bin"] >= 0)
    print(f"scored {int(ok.sum())}, treated {int((ok & d['M1']).sum())}")
    if args.dry:
        return
    vol.BLOCKS["M1"] = {"megacap 2015-24": (2015, 2024)}
    r = vol.score_block(d, "M1", "megacap 2015-24")
    ok_pass = bool(r.get("delta_ci", [-1])[0] > 0 and r.get("null_pct", 0) >= 95)
    print(f"  VERDICT: {'REPLICATED' if ok_pass else 'NOT REPLICATED'}")
    print("  secondary, excluding TSLA:")
    d2 = d[d["ticker"] != "TSLA"].assign()
    vol.BLOCKS["M1"] = {"ex TSLA": (2015, 2024)}
    vol.score_block(d2, "M1", "ex TSLA")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(r, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
