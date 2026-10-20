# Volume Zones indicator

Heatmap (TradingView): Viridis strips without smoothing (`Show heatmap`, on by default) + optional buy/sell layer (`Buy / Sell layer`). Python: `vzones.heatmap()` + `split_profile()`; previews in `reports/styles/` (`H_recommended*.png`).

Python: `vzones/` · TradingView: `pine/volume_zones.pine` · Backtest: `python run_backtest.py` · API: `GET /api/vzones/SPY?interval=1d`

Signals (all computed from past bars only):

| column | meaning |
|---|---|
| `poc`, `vah`, `val`, `hvn_above/below` | rolling volume profile: point of control, value area, nearest high-volume zones |
| `weak_volume` | volume / SMA(20) below `weak_ratio` |
| `pool_active` | several weak bars in a tight range (weak-volume pool) |
| `pool_break` ±1 | pool broken with volume ≥ `break_ratio` × SMA |
| `hunt` ±1, `target` | break + ADX ≥ `adx_strong` + EMA20/50 aligned + a previous HVN/POC/VA edge 1–12 ATR ahead |
| `magnet` ±1 | open hunt still progressing toward the target |
| `rejection` ±1 | wick into an HVN edge and close back away from it |

## Backtest results (see `reports/summary.md`)

Data: SPY 1h, SPY 1d, QQQ 1d from the QuantConnect Lean public sample (1998–2021-03), 60/40 train/test.
Yahoo Finance was blocked in the build environment; `--source yahoo` uses it when reachable.

Honest conclusion: **no robust edge.** `hunt` is rare (≈1 trade/year on hourly, almost none on daily) and
flips from PF 1.85 (train) to 0.94 (test). Raw `rejection` loses badly in 1998–2011 and wins in 2012–2021,
i.e. it is regime-dependent. Every variant badly lags buy & hold. Use it as a context/levels tool, not a standalone system.
