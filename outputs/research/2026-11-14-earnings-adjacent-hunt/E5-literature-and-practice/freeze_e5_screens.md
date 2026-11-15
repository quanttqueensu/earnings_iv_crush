# Freeze note: E5 stock-side screens (trials 2,802 and 2,803)

Written 2026-11-14, after the discovery read (2019-21) and before any held-out (2022-24) outcome.

Both trials failed discovery on their declared primaries (screens_discovery.json):
- 2,802 reversal: net -0.013% per trade [-0.420, +0.406], N=1,035; event gross below pseudo.
- 2,803 announcement premium: net +0.124% per trade [-0.109, +0.358], N=2,736; event gross
  above pseudo by 0.35 points.

No rule, window, cost or breakpoint is changed. The held-out block is read once, with the
declared rules exactly as scored on discovery, as an exploratory replication read of the
published effects on 2022-24. Because discovery failed, no held-out result can turn either
trial into a finding; the read only measures whether the published effect is present recently.

Search count: two configurations scored, no variants.

Held-out block check: block_is_clean(panel="crsp_event_windows", period="2022-24",
outcome_family="stock_return_direction", feature_family="pre_event_return_and_unconditional")
returned True with 0 clashes. The ledger has no stock-direction family; earlier
project studies read stock reactions on overlapping events with other features (P1 put skew,
parity forward, PEAD on SUE), so the block is clean for these features, not for every
stock-reaction feature.

screens.py sha256: 2f73e67dd687c54a10ebd8fec6fbe1c6b7e90ecc3ae62d423455b3e1a8aedb1b
note sha256: ca0609bc9eec24f41f160d673aec96c6a2dda7dcd81109dd4a4f7c35a09f37b0
