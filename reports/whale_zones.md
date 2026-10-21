# Whale zones test (15m, 7 symbols, 2025-04-01 .. 2026-10-21)
Whale bar = volume >= k x the average of the same time of day over the previous 20 sessions (k = 2, 3, 5).
Whale zone = that bar's high-low range. Control = zones from ordinary bars (relative volume 0.8-1.2), and a
width-matched control (ordinary zones re-weighted to the whale zones' width). Script: `whale_zones.py`, output
`whale_zones.txt`, events `whale_zones_events.csv`.

| Claim | Whale x2 | Whale x3 | Whale x5 | Ordinary |
|---|---|---|---|---|
| Zones | 4,894 | 1,590 | 393 | 19,687 |
| Revisited within 5 sessions | 87% | 88% | 86% | 87% |
| Held 1 h after first revisit (width-matched ordinary 51%) | 51% | 51% | **56%** (z = 1.9) | 51% |
| Broken 1 h after first revisit (width-matched ordinary ~19-20%) | 21% | 20% | 16% | 24% |
| Move to close in the bar's direction vs baseline (ATR) | -0.04 | -0.06 | -0.07 | -0.01 |

- **Magnet: no.** Whale zones are revisited exactly as often as ordinary zones.
- **Support/resistance: no for x2 and x3.** Only the rare x5 zones held more often (56% vs 51%), similar in both
  halves (55% / 57%) but inconsistent by symbol (SPY 71%, UNH 65%, INTU 59%, HOOD 54% vs QQQ 46%, COST 42%,
  JNJ 41%). About 300 events: a hint, not proof.
- **Direction: no.** After a whale bar price drifts slightly against the bar (not significant).
