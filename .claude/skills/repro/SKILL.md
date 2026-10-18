---
name: repro
description: Reproduce a recorded number from its source before quoting or building on it. Use before citing any figure, and on joining the project.
argument-hint: [the figure or study]
---

# Reproduce before quoting

1. Find the figure's owner: its findings file under `research/<line>/findings/`, or
   `docs/SYSTEM.md` section 2, which names the source of each headline row.
2. Check it is not in `docs/RESEARCH_STATE.md` section 4 (never quote).
3. Check the inputs are present: `python -m earnings_iv_crush.data.sync verify`.
4. Rerun the integrity check, then the study's scorer:
   ```bash
   python scripts/validate_screen.py          # must print PASS on N=391 and the frozen Sharpe
   python research/<line>/<study>.py --help   # then run it as its findings note describes
   ```
5. Compare to the recorded value. Quote it with N, the interval, the basis and the file. If it
   does not reproduce, say so with both values and stop; do not quote either.
