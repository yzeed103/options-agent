"""Trend analysis after Sepp & Lucic (arXiv 2607.19497): a trend system earns gross alpha only when the volatility-
normalised returns carry positive (kernel-weighted) autocorrelation; costs decide whether a short-memory edge survives.

For 5m, 15m, 60m (regular session, no overnight return) and daily bars of every symbol:
  - autocorrelation of volatility-normalised returns, lags 1..20, pooled over symbols with a 95% interval (resampling symbols);
  - the "European" trend system of the paper: position = EWMA(span) of normalised returns (scaled to unit variance),
    P&L = position x next normalised return; gross Sharpe per span, and the break-even cost in basis points per unit
    of turnover (gross P&L / turnover, converted back to price units with each bar's volatility).
Runs on the source of VZ_TAG. Writes <reports>/trend_spectrum.json and trend_spectrum.png.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data  # noqa: E402

SPANS = (3, 5, 10, 20, 50, 100)
LAGS = 20


def returns(b5: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Normalised returns z, raw returns r and volatility sig (price-return units) for one timeframe."""
    if tf == "1d":
        c = b5.close.groupby(b5.index.date).last()
        r = np.log(c).diff().dropna()
        slot = pd.Series(0, index=r.index)
    else:
        m = {"5m": "5min", "15m": "15min", "60m": "60min"}[tf]
        key = b5.index.floor(m) if tf != "60m" else b5.index.floor("30min") - pd.to_timedelta(((b5.index.hour * 60 + b5.index.minute - 570) // 30 % 2) * 30, "m")
        bars = b5.groupby(key).agg(open=("open", "first"), close=("close", "last"))
        sess = np.array([t.date() for t in bars.index])
        first = np.r_[True, sess[1:] != sess[:-1]]
        r = pd.Series(np.where(first, np.log(bars.close / bars.open), np.log(bars.close / bars.close.shift(1))), index=bars.index)
        slot = pd.Series(bars.index.hour * 60 + bars.index.minute, index=bars.index)
    # remove the time-of-day volatility profile, then a slow EWMA level (past only)
    prof = r.abs().groupby(slot).transform(lambda x: x.shift(1).expanding(20).median())
    u = r / prof
    lvl = u.abs().ewm(span=200, min_periods=50).mean().shift(1)
    sig = prof * lvl
    z = (r / sig).replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame({"z": z, "r": r, "sig": sig}).dropna()


def acf(z: np.ndarray, lags: int) -> np.ndarray:
    z = z - z.mean()
    v = (z * z).mean()
    return np.array([(z[k:] * z[:-k]).mean() / v for k in range(1, lags + 1)])


def tf_system(z: np.ndarray, sig: np.ndarray, span: int) -> dict:
    a = 2 / (span + 1)
    pos = pd.Series(z).ewm(alpha=a, adjust=False).mean().to_numpy()
    pos = pos / np.sqrt(a / (2 - a))                     # unit variance under white noise
    pos = np.clip(pos, -3, 3)
    pnl = pos[:-1] * z[1:]                                 # in volatility units
    turn = np.abs(np.diff(pos))[:-0 or None]
    # cost of one unit of turnover in volatility units = c / sig; break-even c (bp) where mean pnl = mean(turn * c / sig)
    w = turn / sig[1:]
    be_bp = 1e4 * pnl.mean() / w.mean() if w.mean() > 0 else np.nan
    return dict(sharpe_per_bar=float(pnl.mean() / pnl.std()), mean_pnl=float(pnl.mean()), breakeven_bp=float(be_bp))


def main():
    syms = sorted(f[:-7] for f in os.listdir(data.BARS) if f.endswith("_5m.csv"))
    res = {"source": data.FEED, "tf": {}}
    per_sym = {}
    for s in syms:
        b = data.load_bars(s)
        if len(b) < 2000:
            continue
        for tf in ("5m", "15m", "60m", "1d"):
            x = returns(b, tf)
            per_sym.setdefault(tf, []).append((s, acf(x.z.to_numpy(), LAGS),
                                               {sp: tf_system(x.z.to_numpy(), x.sig.to_numpy(), sp) for sp in SPANS}))
        print(s, flush=True)
    rng = np.random.default_rng(0)
    for tf, items in per_sym.items():
        A = np.array([a for _, a, _ in items])
        boot = A[rng.integers(0, len(A), (2000, len(A)))].mean(1)
        sp = {}
        for span in SPANS:
            sh = np.array([d[span]["sharpe_per_bar"] for _, _, d in items])
            be = np.array([d[span]["breakeven_bp"] for _, _, d in items])
            bs = sh[rng.integers(0, len(sh), (2000, len(sh)))].mean(1)
            sp[span] = dict(sharpe_per_bar=float(sh.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                            symbols_positive=int((sh > 0).sum()), breakeven_bp_median=float(np.nanmedian(be)))
        res["tf"][tf] = dict(symbols=len(items), acf=A.mean(0).round(4).tolist(), acf_lo=np.percentile(boot, 2.5, axis=0).round(4).tolist(),
                             acf_hi=np.percentile(boot, 97.5, axis=0).round(4).tolist(), systems=sp)
    os.makedirs(data.REPORTS, exist_ok=True)
    json.dump(res, open(os.path.join(data.REPORTS, "trend_spectrum.json"), "w"), indent=1)
    picture(res)
    for tf, r in res["tf"].items():
        print(tf, "acf1-5", r["acf"][:5], "| lo", r["acf_lo"][:5])
        for span, v in r["systems"].items():
            print(f"   span {span:3}: sharpe/bar {v['sharpe_per_bar']:+.4f} ({v['lo']:+.4f} to {v['hi']:+.4f}) positive {v['symbols_positive']}/{r['symbols']}  break-even {v['breakeven_bp_median']:+.2f} bp")


def picture(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
    fig, axs = plt.subplots(1, 2, figsize=(15, 6), facecolor=BG)
    cols = {"5m": "#4fc3f7", "15m": "#26a69a", "60m": "#ffd54f", "1d": "#ef5350"}
    for tf, r in res["tf"].items():
        x = np.arange(1, LAGS + 1)
        axs[0].plot(x, r["acf"], "o-", color=cols[tf], label=tf, ms=3)
        axs[0].fill_between(x, r["acf_lo"], r["acf_hi"], color=cols[tf], alpha=0.15)
        sp = list(r["systems"].keys())
        axs[1].plot([str(s) for s in sp], [r["systems"][s]["breakeven_bp_median"] for s in sp], "o-", color=cols[tf], label=tf)
    axs[0].axhline(0, color=MUT, lw=0.8); axs[0].set_title("Autocorrelation of volatility-normalised returns (95% CI)", color=TX, loc="left")
    axs[1].axhline(2, color="#ef5350", ls="--", lw=1); axs[1].text(0, 2.3, "our cost: 2 bp per side", color="#ef5350")
    axs[1].axhline(0, color=MUT, lw=0.8); axs[1].set_title("Trend system break-even cost (bp per unit turnover), by span", color=TX, loc="left")
    for ax in axs:
        ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.legend(facecolor=BG, labelcolor=TX)
    fig.tight_layout(); fig.savefig(os.path.join(data.REPORTS, "trend_spectrum.png"), dpi=80, facecolor=BG); plt.close(fig)


if __name__ == "__main__":
    main()
