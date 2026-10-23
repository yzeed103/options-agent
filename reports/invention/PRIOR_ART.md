# Prior art (searched 2026-10-23, before any model was fitted)

Question: is "use dealer options positioning to forecast the day's volatility, and let that forecast set the stop,
target, timeframe and a no-trade decision" new?

| Source | What it does | Overlap with the proposed engine |
|---|---|---|
| SqueezeMetrics, *Gamma Exposure (GEX)* white paper, 2017 ([copy](https://slopeofhope.com/wp-content/uploads/2020/11/GEX-white_paper.pdf)) | Aggregates dealer gamma from open interest (dealers long calls / short puts); GEX quartiles separate next-day S&P 500 return dispersion better than VIX | **Positioning -> volatility forecast is published.** Daily, index level, no execution mapping |
| Barbon & Buraschi, *Gamma Fragility* ([paper](https://abarbon.com/papers/gamma-fragility), [unisg](https://www.alexandria.unisg.ch/261487)) | Dealer gamma imbalance -> intraday momentum (negative) or reversal (positive), intraday volatility, strongest in illiquid stocks | **Positioning -> intraday volatility and autocorrelation, single stocks: published** |
| Baltussen, Da, Lammers & Martens, *Hedging Demand and Market Intraday Momentum*, JFE 142 (2021) ([EUR](https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/)) | Short-gamma hedging explains last-30-minute momentum across 60+ futures | Intraday hedging effect, direction of the close; no volatility-to-execution coupling |
| Zarattini, Aziz & Barbon, *Beat the Market: intraday momentum for SPY* (SFI 24-97, 2024) ([SFI](https://www.sfi.ch/fr/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy)) | Intraday momentum strategy with volatility-scaled noise bands; tests dealer gamma imbalance as a profitability predictor | **Volatility-scaled intraday execution + gamma conditioning: published (SPY)** |
| Dim, Eraker & Vilkov, *0DTEs: Trading, Gamma Risk and Volatility Propagation* (2024, SSRN 4692190) ([summary](https://harbourfrontquant.substack.com/p/the-rise-of-0dte-options-cause-for-concern-or)) | High 0DTE open-interest gamma linked to *lower* intraday index volatility; no amplification | Same variable, contrary evidence on amplification |
| Maurer (2026), via OptionMetrics ([page](https://optionmetrics.com/research/dealer-gamma-exposure-and-overnight-gap-risk-incremental-information-in-low-volatility-regimes/)) | Against a HAR baseline, dealer gamma forecasts only overnight gap size in low-VIX regimes, not intraday volatility | **Incremental value of gamma over a proper volatility baseline is weak** |
| FlashAlpha, 8-year SPY backtest ([page](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control)) | Raw GEX-volatility link exists, goes quiet once ATM IV is controlled for | Same weakness |
| SpotGamma "Volatility Trigger" / implied moves ([page](https://spotgamma.com/negative-gamma-volatility/)) | Commercial gamma-flip level; above = suppressed volatility, below = amplified; publishes expected moves | **Flip side as a volatility regime switch: commercial product** |
| FlashAlpha / MenthorQ GEX trading guides ([FlashAlpha](https://flashalpha.com/articles/gex-trading-guide-gamma-exposure-api-spy-tsla), [MenthorQ](https://menthorq.com/guide/gamma-in-the-real-world/)) | Positive gamma -> range tactics; negative gamma -> trend tactics with wider stops | **Regime-dependent stops: public practitioner advice** |
| US7418416B2, *Gamma trading tool* ([Google Patents](https://patents.google.com/patent/US7418416B2/en)) | Optimises the P&L of delta-hedging an option book | Different problem (the hedger's own book) |
| Glassnode, taker-flow GEX for crypto ([page](https://research.glassnode.com/gamma-exposure/)) | Estimates dealer side from tagged trades instead of the long-call/short-put assumption | Better positioning estimate; crypto only |

## What this means before any test
- **Not new:** positioning -> volatility (2017 onward), the flip as a regime switch (commercial), regime-dependent
  stops (public advice), volatility-scaled intraday execution (published).
- **Possibly new, and narrow:** a per-symbol, intraday-updated (10:00 / 11:00 / 12:00) forecast of the *remaining*
  range that (1) is scored against strong baselines including the morning's own range, (2) maps the forecast to a
  stop / target and a cost-based no-trade rule, and (3) re-rates the instant the flip changes sides. Each piece has a
  near neighbour above; the combination may still be "obvious" to an examiner (combining known elements for their
  known purpose).
- **Evidence risk:** two independent studies find little incremental value of gamma once a proper volatility baseline
  is used. Our own earlier finding (rest-of-day range narrower above the flip: -0.15 daily ATR, then -0.05) had no
  morning-range or VIX-level control. The pre-registered test below includes both.
- The patent search here is a web search, not a professional freedom-to-operate or patentability search.
