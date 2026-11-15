"""
write_trials.py
Lane D1: writes ``trials.csv`` from the held-out result files, one row per read and per
economic rule scored, with the trial numbers fixed below (block 3,142 to 3,181). Recomputes
nothing; reads ``heldout/results_*.json`` only.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/write_trials.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ["trial_id", "idea", "rule", "block", "N", "statistic", "interval", "verdict"]
#: (which, block) -> first trial number; log score, then H_net book, then residual_value book.
IDS = {
    ("primary", "2019-24"): 3142,
    ("secondary", "2019-24"): 3145,
    ("control_primary", "2019-24"): 3148,
    ("control_secondary", "2019-24"): 3151,
    ("primary", "2025-26"): 3154,
    ("secondary", "2025-26"): 3157,
    ("control_primary", "2025-26"): 3160,
    ("control_secondary", "2025-26"): 3163,
}
NAMES = {
    "primary": "D1b surface network boosting L4 (frozen r2_02)",
    "secondary": "D1a surface network (frozen r2_07)",
    "control_primary": "D1b no-surface twin (comparator r2_00)",
    "control_secondary": "D1a no-surface twin (comparator r2_01)",
}


def _f(x: float, nd: int = 4) -> str:
    return f"{x:+.{nd}f}"


def _addendum() -> list[list[object]]:
    """Rows for the addendum (requested after the held-out reads): fill control and mask arm."""
    rows: list[list[object]] = []
    for blk, tid in (("2019-24", 3166), ("2025-26", 3167)):
        p = HERE / "heldout" / f"results_fill_control_{blk}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        g, d = r["vs_L4_model"]["gain"], r["primary_minus_fill_control"]["gain"]
        rows.append(
            [
                tid,
                "fill-rate control: D1b with only fill_front and fill_next over L4",
                f"primary minus control, nats per event (control vs L4 {_f(g['point'])} "
                f"[{_f(g['low'])}, {_f(g['high'])}])",
                blk,
                d["N"],
                _f(d["point"]),
                f"[{_f(d['low'])}, {_f(d['high'])}]",
                "primary not larger than the fill control (exploratory, added after the "
                "held-out reads)",
            ]
        )
    for which, tid in (("primary", 3168), ("secondary", 3169)):
        p = HERE / "heldout" / f"mask_occlusion_{which}_2019-24.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        z, m = r["change_mask_zero"], r["change_mask_mean"]
        rows.append(
            [
                tid,
                f"mask occlusion, {NAMES[which]} refit",
                f"change in log score, mask zeroed (mask at training mean "
                f"{_f(m['point'], 5)} [{_f(m['low'], 5)}, {_f(m['high'], 5)}]); refit "
                f"reproduces stored scores, max gap {r['reproducibility_vs_stored_cards']['max_abs']}",
                "2019-24",
                r["N"],
                _f(z["point"], 5),
                f"[{_f(z['low'], 5)}, {_f(z['high'], 5)}]",
                "no effect (exploratory, added after the held-out reads)",
            ]
        )
    return rows


def main() -> None:
    rows = []
    for (which, blk), tid in IDS.items():
        p = HERE / "heldout" / f"results_{which}_{blk}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        g = r["vs_L4_model"]["gain"]
        # Every read is exploratory: 2019-24 was viewed before for the hedged-hold outcome
        # family (slate-tests rule 5), and 2025-26 is exploratory by the brief.
        expl = True
        if which.startswith("control"):
            verdict = "comparator, exploratory"
        elif blk == "2025-26":
            # The 4-of-6-years criterion is defined on 2019-24 only; report the interval.
            verdict = "above zero" if g["low"] > 0 else "not above zero"
            verdict += " (exploratory; criterion 1 is defined on 2019-24)"
        else:
            verdict = "pass" if r["forecaster_pass"] else "fail"
            verdict += " (exploratory)" if expl else ""
        yp = f"{r['vs_L4_model']['years_positive']} of {r['vs_L4_model']['n_years']} years positive"
        rows.append(
            [
                tid,
                NAMES[which],
                f"log density of H_net minus L4's, nats per event; {yp}",
                blk,
                g["N"],
                _f(g["point"]),
                f"[{_f(g['low'])}, {_f(g['high'])}]",
                verdict,
            ]
        )
        for k, (tgt, lab) in enumerate((("H_net", "H_net"), ("residual_value", "residual_value"))):
            e = r["economic"][tgt]
            d = e["selected_minus_tight"]
            v = "pass" if e["pass"] else "fail"
            v = f"comparator, {v}" if which.startswith("control") else v
            rows.append(
                [
                    tid + 1 + k,
                    NAMES[which],
                    f"trade if quadrature E[H_net] > 0; selected minus tight-spread-per-date "
                    f"screen, mean {lab} % of m0 per trade; selected {e['N_selected']} of "
                    f"{e['N_pool']}, selected mean {_f(e['selected_mean']['point'], 3)}, null "
                    f"percentile {e['null_mean']['percentile']}",
                    blk,
                    e["N_selected"],
                    _f(d["point"], 3),
                    f"[{_f(d['low'], 3)}, {_f(d['high'], 3)}]",
                    v + (" (exploratory)" if expl else ""),
                ]
            )
    rows += _addendum()
    with (HERE / "trials.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        w.writerows(sorted(rows))
    print(f"wrote {len(rows)} trial rows")


if __name__ == "__main__":
    main()
