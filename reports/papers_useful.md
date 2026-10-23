# Useful papers in the library (C:\project\quant\quant_model\data\formula_batch\pdf)

Reviewed 2026-10-23: all 3,377 papers indexed (tools/papers_index.py); the 1,369 with finance or relevant statistics
content were read at abstract level in six batches and judged against the assistant's measured findings. 48 picks; the
strongest are below, grouped by what they would change. Abstracts of the top picks were checked by hand.
The library has **no paper on dealer gamma exposure, options open interest or pinning**.

| Group | arXiv | Paper | What we would do |
|---|---|---|---|
| Ceiling before testing | 1007.2593 | Empirical limitations on HFT profitability | Perfect-foresight upper bound on 5m bars with 2 bp/side: how much any rule could earn at all |
| | 1203.5957 | Optimal trading with linear costs | No-trade band and signal threshold set by the cost, not "trade every touch" |
| | 1408.1159 / 2003.10502 | Optimal trading rules without backtesting (OU) | Exits computed from a fitted process instead of tuned on the backtest |
| Honest nulls | 2608.30490 | Two kinds of nothing | Re-read every "no edge" result: does its interval rule out effects that matter (bounded) or not (vacuous)? |
| | 2209.05559 / 1905.05023 / 2602.00080 | Backtest overfitting tests (PBO, covariance penalty, GT-score) | Extra gates beside the cluster bootstrap and held-out battery |
| Volatility baselines | 2406.08041 | HARd to Beat | HAR (realized vol + VIX) with rolling refits as the benchmark any range forecast must beat |
| | 1410.3394 / 1905.04852 | Volatility is rough / Is volatility rough? | Second baseline, with a planted check first |
| | 1604.01338 / 2609.00943 | Vector MEM (RV, volume, trades) / Illiquidity at risk | Volume, trade-count, Amihud and jump features for the range |
| Calibrated ranges | 2208.08401, 2212.03463, 2602.03903, 2307.16895, 2606.18199 | Online / sequential / regime-weighted conformal | Deliver the day's range as an interval with measured coverage, upper and lower tails separately |
| New level type | 2102.12112 | Price clustering (5 and 10 cent multiples) | Round-number levels vs random nearby prices, same rules as the walls test |
| Order-flow sign | 1011.6402, 1312.0514, 2112.13213 | Order flow imbalance, quote imbalance, cross-impact | Needs quotes (Alpaca has IEX quotes): imbalance near a level as rejection-vs-break evidence |
| | 2608.30999, 1108.1632, 2504.20349 | Metaorder reconstruction from public data, order-sign persistence, ClusterLOB | Design ideas for inferring the true dealer side (the one open invention lead) |
| Regimes | 1801.00718, 0710.3742, 2606.23492 | ruptures, Bayesian online change points, HMM | Check whether the flip effect lives in one regime only |
| Trend theory | 2607.19497 | Science and practice of trend-following | Autocorrelation spectrum of vol-normalised 5m returns before shelving trend rules |
| Research hygiene | 2511.05524, 2605.19337, 2504.14765 | Evidence-bound agents, agentic trading evidence map, LLM memorisation | Gates for automated findings; never trust an LLM on pre-cutoff history |
