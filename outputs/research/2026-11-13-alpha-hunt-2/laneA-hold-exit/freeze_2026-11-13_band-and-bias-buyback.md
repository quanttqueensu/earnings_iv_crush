# Freeze: delta band 0.10 and bias-corrected buy-back, held-out read on 2019-24

Frozen 2026-11-13, before any 2019-24 outcome of either rule was computed or printed. The 2019-24
simulation file is built by `simulate.py`, which prints only the reconciliation of the re-simulated
hold to the stored H; `diag.py --quiet` writes realised post-reaction vol without printing any
outcome.

## Rules, unchanged from discovery

- **1787, band 0.10.** Hedged hold to expiry as the 2026-11-02 study, except that the stock hedge
  is reset to the target straddle delta (reaction-close mid IV) only when the target has drifted by
  more than 0.10 from the hedge held; always set at the reaction close, unwound at settlement.
- **1796, bias-corrected buy-back.** At the reaction close, buy the straddle back at the 15:59 asks
  when its implied vol at the ask is below the HAR realised-vol forecast (CRSP returns to the entry
  date, earlier reaction days blanked) times the median ratio of realised post-reaction vol to that
  forecast over every earlier event whose expiry fell before this reaction session, with history
  from 2013 onward (burn-in 200 events). Hold otherwise.

## Mechanisms (stated in discovery)

The band saves equity rebalancing cost, whose whole size is about 0.36% of m0; it cannot gain more.
The buy-back purchases the remaining option only when its ask is below its expected hedged cost.

## Test and success criteria

Block 2019-24 by reaction-session year, N about 5,113. Effect: paired R - H per trade, unit m0,
net at the touch, date-clustered 95% interval. A rule passes if the interval lies above zero; it is
labelled exploratory held-out whatever the result, because the outcome levels of this block were
viewed by earlier studies. Level of the book reported beside it. Expected result stated now: gains of
at most a few hundredths of a per cent, a level near -1.3%, and no positive book. Neither rule can
answer the lane question positively: the perfect-foresight hold-or-buy ceiling on this block is
-0.06% of m0 and the band family is capped by the equity cost.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneA-hold-exit\freeze_2026-11-13_band-and-bias-buyback.md
