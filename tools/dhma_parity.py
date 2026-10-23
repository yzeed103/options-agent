"""Parity of the damped Hull line in pine/volume_zones.pine against vzones.hma_successor.dhma, on the real chart.

    python tools/dhma_parity.py --version 38.0 [--length 68 --g 0.85]

Adds a temporary copy of the script to the visible chart, switches its "average 1" to the damped Hull on `close`,
reads the plotted values and the chart's bars, repeats with the chart switched to Heikin Ashi, then restores the chart
(copy removed, user's copies visible, chart type and timeframe back). Prints the share of bars within 1e-6."""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import hma_successor as HS  # noqa: E402
import tv_pine_test as T  # noqa: E402

JS = """(async (pineId, ver, length, g, haType) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const ch = window.TradingViewApi.activeChart();
  const back = {res: ch.resolution(), type: ch.chartType()};
  const hidden = ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name) && ch.getStudyById(s.id).isVisible()).map(s => s.id);
  hidden.forEach(id => ch.getStudyById(id).setVisible(false));
  const out = {runs: {}};
  let id = null;
  try {
    for (const mode of ["regular", "ha"]) {
      const want = mode === "ha" ? haType : 1;            // 1 = regular candles
      if (ch.chartType() !== want) { ch.setChartType(want); await sleep(3000); }
      const ms = ch._chartWidget.model().mainSeries();
      ms.requestMoreData(2000); await sleep(5000);
      const before = new Set(ch.getAllStudies().map(s => s.id));
      await ch._chartWidget.insertStudy({type: "pine", pineId: pineId, pineVersion: ver}, []);
      for (let i = 0; i < 60 && !id; i++) { await sleep(1000); const n = ch.getAllStudies().filter(s => !before.has(s.id)); if (n.length) id = n[0].id; }
      if (!id) throw new Error("copy did not appear");
      const st = ch.getStudyById(id);
      const info = st.getInputsInfo();
      const i1 = info.findIndex(x => x.name === "متوسط 1");
      const gI = info.find(x => /تخميد/.test(x.name));
      // the four inputs after the on/off switch: type, source, length, colour
      st.setInputValues([{id: info[i1].id, value: true}, {id: info[i1 + 1].id, value: "HMA مخمّد"}, {id: info[i1 + 3].id, value: length}, {id: gI.id, value: g}]);
      for (let i = 0; i < 90; i++) { await sleep(1000); if (!st.isLoading()) break; }
      await sleep(4000);
      const m = st._study.metaInfo(); let col = -1;
      m.plots.forEach((p, i) => { const t = m.styles && m.styles[p.id] && m.styles[p.id].title; if (t === "متوسط 1") col = i + 1; });
      const b = ms.bars(); const d = st._study.data(); const rows = [];
      for (let i = b.firstIndex(); i <= b.lastIndex(); i++) { const v = b.valueAt(i); if (!v) continue; const r = d.valueAt(i);
        rows.push([v[0], v[1], v[2], v[3], v[4], (r && r[col] != null) ? r[col] : null]); }
      out.runs[mode] = {rows: rows, col: col, error: st.hasError(), type: ch.chartType()};
      ch.removeEntity(id); id = null;
    }
  } catch (e) { out.err = String(e).slice(0, 300); }
  try { if (id) ch.removeEntity(id); } catch (e) {}
  try { if (ch.chartType() !== back.type) ch.setChartType(back.type); await new Promise(r => ch.setResolution(back.res, r)); } catch (e) { out.restoreErr = String(e); }
  hidden.forEach(x => { const s = ch.getStudyById(x); if (s) s.setVisible(true); });
  out.after = {res: ch.resolution(), type: ch.chartType(), vz: ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name)).map(s => [s.id, ch.getStudyById(s.id).isVisible()])};
  return JSON.stringify(out);
})(%s, %s, %s, %s, %s)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--length", type=int, default=68)
    ap.add_argument("--g", type=float, default=0.85)
    ap.add_argument("--ha-type", type=int, default=8, help="TradingView chart type id of Heikin Ashi")
    a = ap.parse_args()
    ws = T.page()
    ws.settimeout(400)
    out = json.loads(T.run(ws, JS % (json.dumps(T.SCRIPT), json.dumps(a.version), a.length, a.g, a.ha_type)))
    print("after:", out.get("after"), "| err:", out.get("err"), out.get("restoreErr"))
    res = {}
    for mode, r in out.get("runs", {}).items():
        rows = r["rows"]
        c = np.array([x[4] for x in rows], float)
        tv = np.array([np.nan if x[5] is None else x[5] for x in rows], float)
        py = HS.dhma(c, a.length, a.g)
        ok = np.isfinite(tv) & np.isfinite(py)
        ok[: 2 * a.length] = False
        diff = np.abs(tv[ok] - py[ok])
        share = float(np.mean(diff <= 1e-6)) if ok.any() else float("nan")
        res[mode] = dict(bars=len(rows), compared=int(ok.sum()), within_1e6=round(share, 5), max_abs_diff=float(diff.max()) if ok.any() else None,
                         chart_type=r["type"], error=r["error"], plot_col=r["col"])
        print(mode, res[mode])
    os.makedirs(os.path.join(ROOT, "reports", "hma_successor"), exist_ok=True)
    json.dump({"version": a.version, "length": a.length, "g": a.g, **res}, open(os.path.join(ROOT, "reports", "hma_successor", "parity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
