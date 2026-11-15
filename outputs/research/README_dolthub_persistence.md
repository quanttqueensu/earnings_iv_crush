# Do not quote `dolthub_sp500_persistence.csv`

The figures in `dolthub_sp500_persistence.csv` (unconditional per-trade Sharpe +0.626,
rich overlay +1.144) are computed on an **incomplete universe** and must not be reported.

`research_dolthub_sp500_persistence.py` is a resumable, checkpointed, per-ticker build with
a `--names` limit. The checkpoint on disk, `dolthub_sp500_events.parquet`, stopped part way
through the alphabet: it holds **64 tickers spanning A to CHD**, of which 38 clear the
minimum event count. The run was never completed.

The universe is therefore alphabetically truncated, not a random or representative sample of
the S&P 500. That is the most likely explanation for why these Sharpes are roughly three
times those of the completed megacap study in `name_persistence.csv` (+0.201 unconditional,
+0.380 rich overlay, 2019-2024), which is the validated result and the one to cite.

## What to use instead

| Purpose | File |
|---|---|
| Name-persistence evidence | `name_persistence.csv` (validated, 901 events, 45 names) |
| Live richness seed | `../../data/rich_set.csv`, built by `scripts/build_rich_seed.py` |

The live seed is built from the three validated event tables (megacap Databento, broad 2024,
broad 2025) pooled to 5,350 events over 346 names, and deliberately does **not** use the
DoltHub checkpoint.

## To make these figures usable

Finish the build (`--build` with no `--names` limit, resumable, free but rate-limited at
roughly 0.2 calls/second) and re-run the report over the complete universe. Until then this
file is a partial intermediate, not a result.
