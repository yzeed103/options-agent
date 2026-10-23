# Pre-registration B: order flow imbalance at level touches (written 2026-10-23, before any quote was fetched)

Paper: Cont, Kukanov & Stoikov, *The price impact of order book events* (arXiv 1011.6402): over short intervals
price changes are linear in the order flow imbalance (OFI) at the best bid and ask, and trades add little after it.
Question: when price first touches one of our levels, does the OFI just before the touch tell whether it passes
through or is rejected? And is that any different at our levels than at random nearby prices?

## Data
- Consolidated feed (SIP) from Alpaca: 5-minute bars for the levels and touches; quotes (best bid/ask with sizes) and
  trades for the touch windows.
- Symbols: SPY, QQQ, AAPL, AMZN, META, NVDA, TSLA, AMD (liquid, with options-level history). Days: the last 60
  trading days with options levels.
- Levels: CW, PW, CWOI, PWOI, FLIP and whale POC / VAH / VAL (whale peaks left out: too many for the quote budget).
  Real levels and the two pseudo-levels per real level, exactly as in reports/eyes/DEFINITIONS.md.
- Event: the first touch per session (eyes rule, 5-minute bars). Outcome: pass-through or rejection (eyes rule).

## Measurement
- Touch moment: the first SIP trade in the touch bar at or through the level.
- OFI over the 60 seconds before the touch moment: sum over quote updates of
  e_n = 1{Pb_n >= Pb_n-1} qb_n - 1{Pb_n <= Pb_n-1} qb_n-1 - 1{Pa_n <= Pa_n-1} qa_n + 1{Pa_n >= Pa_n-1} qa_n-1,
  divided by the window's average depth (qb + qa) / 2. Signed with the approach: positive = pressure toward passing.
- Nothing after the touch moment enters the feature.

## Tests (cluster bootstrap over symbol-days, 2,000 draws)
- **H1 (primary)**: at real levels, pass rate when signed OFI > 0 minus pass rate when <= 0.
  **Success**: at least 5 percentage points with the interval above zero.
- **H2**: the same difference at pseudo-levels. If H1 succeeds and H2 is just as large, the effect is general
  microstructure (known), not about our levels.
- **H3**: top third vs bottom third of signed OFI at real levels (reported, no threshold).

## Changes after writing
(none yet)
