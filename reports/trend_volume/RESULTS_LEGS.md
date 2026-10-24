# Heavy-volume legs end sooner? Result: **no**

Tested as its own pre-registered claim (PREREG_LEGS.md): at the 5th bar of every trend leg on the Hull average,
does the volume of those 5 bars (V5, slot RVOL) predict a shorter remaining life than the leg's speed does?
30 SIP symbols, test days 2026-03-10 onwards; `legs.json`, `legs.png`.

| timeframe | legs (test) | alive after 12 bars, by V5 quintile (light → heavy) | death lift, heaviest quintile | speed control's death lift | median life (bars) |
|---|---|---|---|---|---|
| 5m | 14,876 (12,685 with a 12-bar window) | 46.6, 49.6, 49.0, 50.4, 48.8% | **1.00 [0.97, 1.04]** | 0.90 [0.86, 0.93] | 9–10 everywhere |
| 15m | 5,263 (3,975) | 49.5, 46.8, 49.2, 47.6, 51.2% | **0.95 [0.89, 1.02]** | 0.83 [0.77, 0.89] | 9–10 |

Volume of the leg's first five bars tells nothing about how long the leg lives: flat across quintiles, death lift
1.00, same median life. Inside speed terciles the heaviest-volume quintile is not below the stratum mean. The
first-passage outcome is flat too (34–35% on 5m across V5 quintiles).

What does matter is **speed**, a price-only quantity: fast legs live longer (alive after 12 bars 45% in the slowest
quintile, 54% in the fastest on 5m; 41% vs 57% on 15m). That is the opposite sign of the volume effect seen on R3 in
RESULTS.md, which was measured at resumption bars with leg-volume measures that mix in the pullback and the
resumption; that side effect does **not** replicate when the claim is tested cleanly on its own events.

Nothing is added to the indicator (no warning line): the rule required "confirmed".
