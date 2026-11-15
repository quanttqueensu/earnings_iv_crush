"""
ledger_entries.py
Append the 2026-11-13 niche hunt (other markets) to the research ledgers: one ``trials.csv`` row
per lane that used trial numbers, pointing at the lane's own trial log, and one ``blocks.csv`` row
per outcome block a lane viewed. Append-only, refuses to run twice, and recounts each lane's trial
log before writing so the ledger total matches the files on disk.

The hunt froze with notes that hash themselves and their scorers but were not filed as
pre-registrations under ``outputs/research/prereg_*``, so its rows carry the regime
``exploratory-unhashed`` and no LOND index, as the two alpha hunts of the same day do.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/ledger_entries.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

LEDGER = ROOT / "research" / "ledger"
HUNT = "outputs/research/2026-11-13-niche-hunt"
REGIME = "exploratory-unhashed"
DECLARED = "2026-11-13"

# ── trials: (lane folder, verdict) ───────────────────────────────────────────

TRIALS = [
    ("N02-livestock-usda", "abandoned unscored; no free data"),
    ("N03-natgas-storage", "held-out fail; storage-day excess gone after 2018"),
    ("N04-crude-eia-opec", "held-out fail; seller test uninformative; Yahoo trials withdrawn"),
    ("N05-treasuries-macro", "held-out fail (index level); Cboe rebuild 2,218-2,221"),
    ("N06-sofr-fomc", "held-out fail, underpowered by construction (synthetic settle marks)"),
    ("N08-index-macro-cached", "held-out fail at the touch; 2,313-2,314 rebuild biased, not cited"),
    ("N09-vix-complex", "held-out fail; published FOMC VX trade decayed"),
    ("N10-crypto-scheduled", "held-out fail; discovery pass was a statistic switch"),
    ("N11-forecastex-event-contracts", "both hypotheses held-out fail"),
    ("N12-metals-macro", "held-out fail (index level)"),
    ("N13-softs-ice", "held-out fail (settle)"),
    ("N14-bank-stress-tests-and-regulatory", "fail; stage A unfrozen, stage B 2-4 clusters"),
    ("N15-adr-overnight-reporters", "held-out fail at the touch"),
    ("N16-country-etf-politics", "held-out fail (index level)"),
    ("N17-commodity-etf-options", "held-out fail; GLD/SLV/TLT rows descriptive (viewed block)"),
]

# ── blocks: (panel, period, outcome family, feature family, viewed by) ───────

BLOCKS = [
    ("index_chains_macro", "2016-24", "macro_straddle", "release_and_tenor", "N08"),
    ("index_chains_macro", "2025-26", "macro_straddle", "release_and_tenor", "N08"),
    ("adr_foreign_chains", "2025", "event_straddle", "foreign_reporter", "N15"),
    ("adr_foreign_chains", "2026", "event_straddle", "foreign_reporter", "N15"),
    ("forecastex_kalshi", "pre-2026", "event_contract", "cross_venue_and_favourite", "N11"),
    ("forecastex_kalshi", "2026", "event_contract", "cross_venue_and_favourite", "N11"),
    ("vx_futures_settles", "2008-16", "macro_vx_short", "fomc_cpi_nfp", "N09"),
    ("vx_futures_settles", "2017-26", "macro_vx_short", "fomc_cpi_nfp", "N09"),
    ("deribit_btc", "2020-22", "expiry_friday_straddle", "monthly_expiry", "N10"),
    ("deribit_btc", "2023-26", "expiry_friday_straddle", "monthly_expiry", "N10"),
    ("ng_settles", "2002-18", "event_variance", "eia_storage", "N03"),
    ("ng_settles", "2019-24", "event_variance", "eia_storage", "N03"),
    ("wti_ovx", "2009-19", "event_variance", "eia_petroleum", "N04"),
    ("wti_ovx", "2021-26", "event_variance", "eia_petroleum", "N04"),
    ("tlt_vxtlt", "2016-20", "macro_variance", "cpi_nfp_fomc", "N05"),
    ("tlt_vxtlt", "2021-26", "macro_variance", "cpi_nfp_fomc", "N05, N17"),
    ("sofr_atlanta_fed_tracker", "2023-24", "fomc_variance", "fomc", "N06"),
    ("sofr_atlanta_fed_tracker", "2025-26", "fomc_variance", "fomc", "N06"),
    ("metals_gvz_vxslv", "2016-21", "macro_variance", "cpi_nfp_fomc", "N12"),
    ("metals_gvz_vxslv", "2022-26", "macro_variance", "cpi_nfp_fomc", "N12, N17"),
    ("softs_settles", "2000-13", "event_variance", "wasde", "N13"),
    ("softs_settles", "2014-26", "event_variance", "wasde", "N13"),
    ("country_etf_vol_indices", "discovery", "event_variance", "copom_elections", "N16"),
    ("country_etf_vol_indices", "held-out", "event_variance", "copom_elections", "N16"),
    ("bank_closes_and_dolthub", "2015-19", "event_variance", "stress_test", "N14"),
    ("bank_closes_and_dolthub", "2020-26", "event_variance", "stress_test", "N14"),
    ("commodity_etf_vol_indices", "2009-20", "event_straddle", "eia_and_macro", "N17"),
    ("commodity_etf_vol_indices", "2021-26", "event_straddle", "eia_and_macro", "N17"),
]


def _count(lane: str) -> tuple[int, str]:
    """Distinct trial numbers in a lane's trials.csv, and their range for the label."""
    path = ROOT / HUNT / lane / "trials.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[1:]
    ids = sorted({int(r[0]) for r in rows if r and re.fullmatch(r"\d{4}", r[0].strip())})
    if not ids:
        raise ValueError(f"{lane}: no trial numbers found in {path}")
    return len(ids), f"{ids[0]:,}-{ids[-1]:,}"


def main() -> None:
    trials_csv = LEDGER / "trials.csv"
    if f"{HUNT}/N08-index-macro-cached" in trials_csv.read_text(encoding="utf-8"):
        raise SystemExit("niche hunt rows already in trials.csv; refusing to append twice")
    counted = [(lane, *_count(lane), verdict) for lane, verdict in TRIALS]
    total = sum(n for _, n, _, _ in counted)
    for lane, n, span, _ in counted:
        print(f"{lane:40s} {n:3d}  {span}")
    print(f"total {total}")
    with trials_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for lane, n, span, verdict in counted:
            w.writerow(
                [
                    f"{HUNT}/{lane}/trials.csv",
                    f"niche hunt {span}",
                    n,
                    DECLARED,
                    REGIME,
                    "",
                    "",
                    "",
                    verdict,
                ]
            )
    for panel, period, outcome, feature, who in BLOCKS:
        log_block_view(
            LEDGER / "blocks.csv",
            panel=panel,
            period=period,
            outcome_family=outcome,
            feature_family=feature,
            viewed_by=f"niche hunt 2026-11-13, {who}",
            kind="trial",
        )
    print(f"appended {len(counted)} trial rows ({total} trials) and {len(BLOCKS)} block rows")


if __name__ == "__main__":
    main()
