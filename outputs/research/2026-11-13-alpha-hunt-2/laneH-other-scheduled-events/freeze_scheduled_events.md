# Freeze: scheduled non-earnings events, held-out read (2026-11-13)

Written before any held-out (2022-01-01 to 2024-11-08) outcome was computed. Measurement is the
round-4 pipeline exactly as on disk (`price3.py` with `EXIT_MODE="smile"`, `price4.py`,
`lib_score.usable`): fixed calendar windows (entry latest DoltHub snapshot D-5..D-1, exit earliest
D+1..D+7 sharing an expiry at least 2 days after exit), entry strike nearest the parity forward,
unquoted exit strikes marked by Black-76 on the interpolated exit smile plus the ATM half-spread,
earnings windows dropped, controls at D-28 and D-56 with no earnings or other listed event.

## F1, trials 2,014 and 2,015: long straddle across megacap product events

Provenance: discovery-derived (reversal of the failed short, round 3/4, N=6 to 7). Mechanism stated
in advance: Apple events and WWDC, Google I/O, Microsoft Build and Nvidia GTC realise about three
times the control-window move while the entry term structure prices almost no jump.
- 2,014 primary: paired event minus mean of same-name controls, long straddle net at the touch,
  share of premium paid. Confirmatory only if CI low > 0, t >= 3, null percentile >= 95.
- 2,015 level: long straddle net at the touch, share of premium paid, mean > 0. A paired pass with
  a negative level is cost recovery, not alpha.

## F2, trials 2,016 and 2,017: short straddle across FDA advisory committee meetings

Provenance: pre-stated (H-A1, H-A2), unchanged since the trial log; scored on the held-out block so
the lane's central question gets one clean read.
- 2,016: short straddle net at the touch, share of m0, mean > 0.
- 2,017: paired event minus control, gross at the mid, share of m0, > 0 with null >= 95.

Expected held-out N: about 13 product and 19 AdComm event windows before screens. Power is low:
at the discovery dispersion a t of 3 needs an effect of roughly 0.10 of premium (F1) or 0.15 of m0
(F2). Every result is a descriptive pilot whatever its sign.
