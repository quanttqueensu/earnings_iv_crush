# 0004. Licensed data never enters the repository
*Date: 2026-10-18 · Status: Accepted*

**Context:** The research inputs come from Databento (per-user licence) and the WRDS mirror (a
Queen's licence). The repository is public.

**Decision:** No raw vendor rows in any commit, findings note or figure data file. The research
caches are shared through the club's Cloudflare R2 bucket and verified by the hashed manifest in
manifest pinned by `data/MANIFEST.pin.json` (`python -m earnings_iv_crush.data.sync`). The project's own computed
aggregates, the pre-registration hash records, the ticker universe and the three-row
`fills_rescore.csv` are tracked.

**Consequences:** A clone reproduces a real number only after `sync pull`. The synthetic demo and
the test suite run without it.
