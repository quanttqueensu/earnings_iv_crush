# Pre-registration: replicating the Kalshi maker result on series it has never seen

Frozen before any price or trade for the new series is pulled. SHA-256 recorded in
`outputs/research/prereg_kalshi_maker_replication.json`.

## Why

On the seven original release series, resting bids on favourites returned +1.64% per filled bet
(CI [-2.20%, +6.92%], 66 fills, 50 events) against -2.03% for the same candidates bought at the ask.
Suggestive, not significant. Adding data to a near miss is a forking path unless the new data is
chosen before it is seen and the rule is unchanged; this is that replication.

## Series (mechanical rule, applied to metadata only)

Kalshi Economics-category series with monthly, weekly or quarterly frequency whose declared settlement
sources all lie in {bls.gov, bea.gov, census.gov, dol.gov, ismworld.org, adpemploymentreport.com,
conference-board.org}, whose title and ticker name no non-US economy or currency, excluding the seven
original series. 81 series, listed in `data/cache/kalshi/replication_series.json`. The rule admits a
few series that settle on market prices rather than statistical releases (for example a Treasury
yield, the effective funds rate, jet fuel); they are kept, not hand-pruned. **Every event whose
ticker appears in the original sample is removed.**

## Rule, unchanged

Snapshot, liquidity filter, 90% favourite threshold, taker and maker pricing, strictly-through fill
rule and fees exactly as in `kalshi_macro_tails_prereg.md` and `kalshi_maker_prereg.md`. Candles are
fetched only for ladder markets with positive lifetime volume (a contract that never traded cannot
pass the 24-hour volume filter).

## Success criterion

Maker book: mean return per filled bet, averaged within each **release date** first (releases on one
day share information), positive with a date-clustered 95% CI (5,000 draws, seed 0) excluding zero.
Mechanism check as before: filled win rate minus price paid positive with CI excluding zero, and no
significant adverse selection. Reported alongside: the taker book on the same candidates, and both
books excluding CPI release dates (the original sample's CPI days recur across BLS component series).
One trial.
