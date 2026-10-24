# Heavy-volume legs end sooner: pre-registration (2026-10-24, before any run)

Claim to test (it came out of the trend-volume study as a side effect on R3, so it must be tested on its own with
events and a target defined before looking): **a trend leg that carries heavy volume in its first 5 bars ends sooner
than a light one, beyond what the leg's speed explains.**

## Events
Trend state as in PREREG.md (HMA 67 / 66 on 5m / 15m, close on one side of M with M's slope of that sign on 3 bars).
Event = the **5th consecutive trend bar** of a leg (the first time a run reaches 5 in a session); one event per leg.
Measured at that bar, past only: **V5** = mean slot RVOL of the 5 leg bars; **speed** (price-only control) =
dir × (close − close 4 bars earlier) / ATR; **extension** = dir × (close − M) / ATR (reported, not the control).

## Targets (future only)
**life** = bars after the event until the first close beyond M against the trend by 0.3 ATR (same session; censored
at the session end; cap 48). **alive12** = life ≥ 12 (defined only when ≥ 12 bars remain in the session); alive24
likewise. **fp** = +1 ATR before −1 ATR within 2 hours (24 bars on 5m, 8 on 15m), as before.

## Metrics
Quintiles of V5 and of speed from **train** events (first 60% of days); on **test** events: death rate
(1 − alive12) by V5 quintile; **death lift** = death(top V5 quintile) / death(all), paired against the same lift for
speed (`trend_volume.paired_lift` with hit = death), intervals by bootstrap over symbol-days; a V5-quintile × speed-
tercile table of alive12, to show the effect inside speed strata; survival curves (alive share by bars, censoring
counted as alive up to the censor bar) for the top and bottom V5 quintiles; the same on fp (hit = reached +1 ATR).

## Rule
**confirmed**: on both 5m and 15m, death lift of the top V5 quintile > 1 with interval excluding 1 **and** the
paired difference against speed has a lower bound > 0 **and** inside every speed tercile the top V5 quintile's alive12
is below the tercile's mean. **partly**: one timeframe, or only with the paired interval including 0. **no**: otherwise.
If confirmed, the indicator gets a warning only (a panel note "ساق ثقيلة بالفوليوم: تنتهي أسرع عادة" with the numbers),
never a signal.

## Changes after writing
(none yet)
