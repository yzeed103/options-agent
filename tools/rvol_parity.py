"""Parity of the indicator's slot RVOL (pine/volume_zones.pine) against vzones.volume_tool.rvol_set on TradingView's
own bars, and the TradingView-vs-Alpaca SIP volume difference.

    python tools/rvol_parity.py --version 39.0 [--symbol SPY --tf 5]

Switches the visible chart to the symbol / timeframe, loads ~60 sessions of bars, adds a temporary copy of the
script, reads its "RVOL" plot and the bars, then restores the chart (copy removed, user's copies visible, symbol,
timeframe and chart type back). Writes reports/volume_tool/parity.json."""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import volume_tool as VT  # noqa: E402
import tv_pine_test as T  # noqa: E402

JS = """(async (pineId, ver, sym, tf) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const ch = window.TradingViewApi.activeChart();
  const back = {sym: ch.symbol(), res: ch.resolution(), type: ch.chartType()};
  const hidden = ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name) && ch.getStudyById(s.id).isVisible()).map(s => s.id);
  hidden.forEach(id => ch.getStudyById(id).setVisible(false));
  const out = {back: back};
  let id = null;
  try {
    if (ch.chartType() !== 1) { ch.setChartType(1); await sleep(2000); }
    await new Promise(r => ch.setSymbol(sym, r)); await new Promise(r => ch.setResolution(tf, r)); await sleep(4000);
    const ms = ch._chartWidget.model().mainSeries();
    for (let k = 0, last = -1; k < 6; k++) { const n = ms.bars().size(); if (n === last) break; last = n; ms.requestMoreData(2000); await sleep(5000); }
    const before = new Set(ch.getAllStudies().map(s => s.id));
    await ch._chartWidget.insertStudy({type: "pine", pineId: pineId, pineVersion: ver}, []);
    for (let i = 0; i < 60 && !id; i++) { await sleep(1000); const n = ch.getAllStudies().filter(s => !before.has(s.id)); if (n.length) id = n[0].id; }
    if (!id) throw new Error("copy did not appear");
    const st = ch.getStudyById(id);
    for (let i = 0; i < 120; i++) { await sleep(1000); if (!st.isLoading()) break; }
    await sleep(4000);
    const m = st._study.metaInfo(); let col = -1;
    m.plots.forEach((p, i) => { const t = m.styles && m.styles[p.id] && m.styles[p.id].title; if (t && t.startsWith("RVOL")) col = i + 1; });
    const b = ms.bars(); const d = st._study.data(); const rows = [];
    for (let i = b.firstIndex(); i <= b.lastIndex(); i++) { const v = b.valueAt(i); if (!v) continue; const r = d.valueAt(i);
      rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[col] != null) ? r[col] : null]); }
    out.rows = rows; out.col = col; out.error = st.hasError(); out.sym = ch.symbol(); out.res = ch.resolution();
  } catch (e) { out.err = String(e).slice(0, 300); }
  try { if (id) ch.removeEntity(id); } catch (e) {}
  try { await new Promise(r => ch.setSymbol(back.sym, r)); await new Promise(r => ch.setResolution(back.res, r)); if (ch.chartType() !== back.type) ch.setChartType(back.type); } catch (e) { out.restoreErr = String(e); }
  hidden.forEach(x => { const s = ch.getStudyById(x); if (s) s.setVisible(true); });
  out.after = {sym: ch.symbol(), res: ch.resolution(), type: ch.chartType(), vz: ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name)).map(s => [s.id, ch.getStudyById(s.id).isVisible()])};
  return JSON.stringify(out);
})(%s, %s, %s, %s)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--symbol", default="BATS:SPY")
    ap.add_argument("--tf", default="5")
    a = ap.parse_args()
    ws = T.page(); ws.settimeout(600)
    out = json.loads(T.run(ws, JS % (json.dumps(T.SCRIPT), json.dumps(a.version), json.dumps(a.symbol), json.dumps(a.tf))))
    print("after:", out.get("after"), "| err:", out.get("err"), out.get("restoreErr"))
    rows = out["rows"]
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], unit="s", utc=True)).tz_convert("America/New_York")
    d = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}, index=idx)
    tv = np.array([np.nan if r[6] is None else r[6] for r in rows], float)
    import datetime as dt
    reg = (d.index.time >= dt.time(9, 30)) & (d.index.time < dt.time(16, 0))
    d = d[reg]; tv = tv[reg]
    py = VT.rvol_set(d, int(a.tf))[0]
    ok = np.isfinite(tv) & np.isfinite(py)
    diff = np.abs(tv[ok] - py[ok])
    res = dict(version=a.version, symbol=out.get("sym"), tf=out.get("res"), bars=len(d), sessions=len(set(d.index.date)), compared=int(ok.sum()),
               within_1e6=round(float(np.mean(diff <= 1e-6)), 5) if ok.any() else None, within_1e3=round(float(np.mean(diff <= 1e-3)), 5) if ok.any() else None,
               max_abs_diff=float(diff.max()) if ok.any() else None, error=out.get("error"))
    # TradingView volume vs the Alpaca SIP bars we measured on
    try:
        from vzones.assistant import data as D
        sym = out.get("sym", "").split(":")[-1]
        a5 = D.load_bars(sym)
        if a.tf != "5":
            a5 = a5.groupby(a5.index.floor(f"{a.tf}min")).agg(volume=("volume", "sum"))
        j = d[["volume"]].join(a5[["volume"]], how="inner", lsuffix="_tv", rsuffix="_alp")
        if len(j):
            ratio = (j["volume_tv"] / j["volume_alp"]).replace([np.inf], np.nan).dropna()
            res["volume_vs_alpaca"] = dict(bars=len(j), median_ratio_tv_over_alpaca=round(float(ratio.median()), 4), p10=round(float(ratio.quantile(.1)), 4), p90=round(float(ratio.quantile(.9)), 4))
    except Exception as e:  # noqa: BLE001
        res["volume_vs_alpaca"] = f"not compared: {type(e).__name__}"
    print(res)
    json.dump(res, open(os.path.join(ROOT, "reports", "volume_tool", "parity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
