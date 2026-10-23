"""IEX (what we measured on) vs SIP (the whole market): volume, prices, and how many indicator signals change.

    python tools/source_compare.py
Reads runtime/bars (IEX) and runtime_sip/bars (SIP). Writes reports/sip/source_compare.json.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load(dirname, sym):
    p = os.path.join(ROOT, dirname, "bars", f"{sym}_5m.csv")
    d = pd.read_csv(p)
    d.index = pd.to_datetime(d["time"], utc=True).dt.tz_convert("America/New_York")
    return d[["open", "high", "low", "close", "volume"]].astype(float)


def main():
    from vzones.assistant import signals as S
    from vzones.assistant.data import resample15
    syms = sorted(f[:-7] for f in os.listdir(os.path.join(ROOT, "runtime_sip", "bars")) if f.endswith("_5m.csv"))
    rows, sig = [], []
    for s in syms:
        a, b = load("runtime", s), load("runtime_sip", s)
        j = a.join(b, lsuffix="_iex", rsuffix="_sip", how="inner")
        rows.append(dict(sym=s, bars=len(j), only_sip=len(b) - len(j), vol_ratio=float(j.volume_sip.sum() / j.volume_iex.sum()),
                         close_diff_bp=float((1e4 * (j.close_iex - j.close_sip).abs() / j.close_sip).median()),
                         high_diff_bp=float((1e4 * (j.high_iex - j.high_sip).abs() / j.high_sip).median()),
                         vol_corr=float(np.corrcoef(np.log1p(j.volume_iex), np.log1p(j.volume_sip))[0, 1])))
        ca, cb = S.compute(a, resample15(a)), S.compute(b, resample15(b))
        k = ca.index.intersection(cb.index)
        for name in ("sig_tl", "sig_st", "sig_ta", "sig_wb"):
            x, y = ca.loc[k, name].to_numpy(), cb.loc[k, name].to_numpy()
            ev = (x != 0) | (y != 0)
            sig.append(dict(sym=s, signal=name[4:], iex=int((x != 0).sum()), sip=int((y != 0).sum()),
                            same=int(((x == y) & (x != 0)).sum()), events=int(ev.sum())))
        print(s, rows[-1]["vol_ratio"], flush=True)
    r = pd.DataFrame(rows); g = pd.DataFrame(sig).groupby("signal")[["iex", "sip", "same", "events"]].sum()
    g["agree"] = g.same / g.events
    out = {"symbols": len(r), "vol_ratio_median": float(r.vol_ratio.median()), "vol_ratio_range": [float(r.vol_ratio.min()), float(r.vol_ratio.max())],
           "close_diff_bp_median": float(r.close_diff_bp.median()), "high_diff_bp_median": float(r.high_diff_bp.median()),
           "vol_corr_median": float(r.vol_corr.median()), "per_symbol": rows, "signals": g.reset_index().to_dict("records")}
    os.makedirs(os.path.join(ROOT, "reports", "sip"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "reports", "sip", "source_compare.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_symbol"}, indent=1))


if __name__ == "__main__":
    main()
