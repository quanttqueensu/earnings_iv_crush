---
name: orient
description: Report the measured state of the project (repo, data present, paper book switches and positions, gateway, trial count) and say what needs attention. Use at the start of a session or when asked where things stand.
---

# Orient

Run:

```bash
python -m earnings_iv_crush.ops.orient
```

Then report, in this order:

1. Anything that needs action now: `HALT` or `STOP` present, an unexpected `TRANSMIT_OK`, a gateway
   down on a trading day before 15:20 ET, open positions due today, incomplete order lifecycles.
2. Whether the research caches are present (if not, `sync pull` needs the bucket keys).
3. The trial count as measured, and that later declarations are in `docs/RESEARCH_STATE.md`.

Quote only what orient printed. A section that says `UNMEASURED` is reported as unmeasured with
its reason, never filled in from memory.
