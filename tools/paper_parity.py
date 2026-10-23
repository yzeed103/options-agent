"""Phase 0 parity: the Python signals (vzones/assistant/signals.py) against the indicator itself, on TradingView's own bars.

For each symbol x timeframe: the visible chart tab is switched to regular candles + that symbol / timeframe, a temporary
copy of the saved Volume Zones script is added, its signal series and the chart's bars are read, the copy is removed
and the chart restored (symbol, timeframe, candle type, visibility of the user's own instance). Read-only otherwise.

    python tools/paper_parity.py                              # default 5 symbols x 5m, 15m
    python tools/paper_parity.py --symbols SPY --tf 5
Writes reports/paper/parity.txt and runtime/parity_*.json (raw readings).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd
import websocket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import signals as S  # noqa: E402
from vzones.assistant.data import resample15  # noqa: E402

SCRIPT = "USER;d519afe2d45a47c493a321e75859d475"
TITLES = {"ta_up": "تنبيه اتجاه صاعد", "ta_dn": "تنبيه اتجاه هابط", "wb_up": "ارتداد حوت صعود", "wb_dn": "ارتداد حوت هبوط",
          "st": "انكسار الترند (Supertrend)", "tl_up": "كسر خط الترند الهابط", "tl_dn": "كسر خط الترند الصاعد"}

JS = r"""(async (SYM, RES, PINE, VER, TITLES) => {
  const a = window.TradingViewApi; const ch = a.activeChart(); const sleep = ms => new Promise(r => setTimeout(r, ms));
  const back = {sym: ch.symbol(), res: ch.resolution(), type: ch.chartType()};
  const out = {back}; let id = null; const hidden = [];
  try {
    for (const s of ch.getAllStudies()) if (/Volume Zones/i.test(s.name)) { const st = ch.getStudyById(s.id); if (st.isVisible()) { st.setVisible(false); hidden.push(s.id); } }
    if (back.type !== 1) { ch.setChartType(1); await sleep(3000); }
    await new Promise(r => ch.setSymbol(SYM, r)); await new Promise(r => ch.setResolution(RES, r)); await sleep(5000);
    const ms = ch._chartWidget.model().mainSeries();
    for (let k = 0, last = -1; k < 8; k++) { const n = ms.bars().size(); if (n === last) break; last = n; ms.requestMoreData(2000); await sleep(6000); }
    out.nBars = ms.bars().size();
    const before = new Set(ch.getAllStudies().map(s => s.id));
    await ch._chartWidget.insertStudy({type: "pine", pineId: PINE, pineVersion: VER}, []);
    for (let i = 0; i < 90 && !id; i++) { await sleep(1000); const n = ch.getAllStudies().filter(s => !before.has(s.id)); if (n.length) id = n[0].id; }
    if (!id) throw new Error("copy did not appear");
    const st = ch.getStudyById(id);
    for (let i = 0; i < 120; i++) { await sleep(1000); if (!st.isLoading()) break; }
    await sleep(4000);
    out.error = st.hasError();
    const m = st._study.metaInfo(); const col = {};
    m.plots.forEach((p, i) => { const t = m.styles && m.styles[p.id] && m.styles[p.id].title; for (const k in TITLES) if (t === TITLES[k] && p.type !== "text_colorer") col[k] = i + 1; });
    out.col = col;
    const b = ch._chartWidget.model().mainSeries().bars(); const d = st._study.data(); const rows = [];
    for (let i = b.firstIndex(); i <= b.lastIndex(); i++) { const v = b.valueAt(i); if (!v) continue; const r = d.valueAt(i);
      const g = k => (r && col[k] !== undefined && r[col[k]] != null && !Number.isNaN(r[col[k]])) ? r[col[k]] : 0;
      rows.push([v[0], v[1], v[2], v[3], v[4], v[5], g("ta_up"), g("ta_dn"), g("wb_up"), g("wb_dn"), g("st"), g("tl_up"), g("tl_dn")]); }
    out.rows = rows; out.sym = ch.symbol(); out.res = ch.resolution();
    // the indicator builds its sideways ranges from TradingView's DAILY bars (official high / low / close), which
    // differ slightly from daily bars built out of intraday bars: read them too
    if (id) { ch.removeEntity(id); id = null; }
    await new Promise(r => ch.setResolution("D", r)); await sleep(4000);
    const ds = ch._chartWidget.model().mainSeries();
    for (let k = 0, last = -1; k < 4; k++) { const n = ds.bars().size(); if (n === last) break; last = n; ds.requestMoreData(1000); await sleep(4000); }
    const db = ds.bars(); const daily = [];
    for (let i = db.firstIndex(); i <= db.lastIndex(); i++) { const v = db.valueAt(i); if (v) daily.push([v[0], v[2], v[3], v[4]]); }
    out.daily = daily;
  } catch (e) { out.err = String(e).slice(0, 300); }
  try { if (id) ch.removeEntity(id); } catch (e) {}
  try { await new Promise(r => ch.setSymbol(back.sym, r)); await new Promise(r => ch.setResolution(back.res, r)); if (back.type !== 1) ch.setChartType(back.type); } catch (e) { out.restoreErr = String(e); }
  for (const x of hidden) { const s = ch.getStudyById(x); if (s) s.setVisible(true); }
  out.after = {sym: ch.symbol(), res: ch.resolution(), type: ch.chartType()};
  return JSON.stringify(out);
})(%s, %s, %s, %s, %s)"""


def visible_page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5)):
        if t["type"] != "page" or "/chart/" not in t["url"]:
            continue
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=600, suppress_origin=True)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "document.visibilityState", "returnByValue": True}}))
        if json.loads(ws.recv())["result"]["result"]["value"] == "visible":
            return ws
        ws.close()
    raise SystemExit("no visible TradingView chart tab")


def evaluate(ws, expr: str):
    ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 2:
            return json.loads(m["result"]["result"]["value"])


def compare(rows: list, tf_min: int, daily: list | None = None, warm_days: int = 25) -> dict:
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume", "ta_up", "ta_dn", "wb_up", "wb_dn", "st", "tl_up", "tl_dn"])
    df.index = pd.to_datetime(df.t, unit="s", utc=True).dt.tz_convert("America/New_York")
    mins = df.index.hour * 60 + df.index.minute
    df = df[(mins >= 570) & (mins < 960)]
    bars = df[["open", "high", "low", "close", "volume"]]
    src15 = resample15(bars) if tf_min < 15 else bars
    day = None
    if daily:
        dv = pd.DataFrame(daily, columns=["t", "high", "low", "close"])
        dv.index = list(pd.to_datetime(dv.t, unit="s", utc=True).dt.tz_convert("America/New_York").dt.date)
        first = df.index[0].date()
        before = [d for d in dv.index if d < first]
        if before:                                     # Pine's first daily row is the day before the first chart bar
            day = dv[dv.index >= before[-1]][["high", "low", "close"]]
    out = S.compute(bars, src15, day_bars=day)
    tv = {"ta": np.where(df.ta_up > 0, 1, np.where(df.ta_dn > 0, -1, 0)),
          "wb": np.where(df.wb_up > 0, 1, np.where(df.wb_dn > 0, -1, 0)),
          "st": (df.st > 0).astype(int).to_numpy(),
          "tl": np.where(df.tl_up > 0, 1, np.where(df.tl_dn > 0, -1, 0))}
    py = {"ta": out.sig_ta.to_numpy(), "wb": out.sig_wb.to_numpy(), "st": (out.sig_st != 0).astype(int).to_numpy(), "tl": out.sig_tl.to_numpy()}
    days = sorted(set(df.index.date))
    keep = df.index.date >= days[min(warm_days, len(days) - 1)]
    # whale levels depend on the first completed sideways range after the data start (chart start in TradingView,
    # 2025-04-01 in the assistant): measured on SPY 5m, every event matches once ~90 sessions have passed
    keep_wb = df.index.date >= days[min(90, len(days) - 1)]
    res = {"bars": int(keep.sum()), "days": len(days) - warm_days, "wb_days": max(0, len(days) - 90)}
    for k in tv:
        kk = keep_wb if k == "wb" else keep
        a, b = tv[k][kk], py[k][kk]
        ev = (a != 0) | (b != 0)
        res[k] = dict(tv=int((a != 0).sum()), py=int((b != 0).sum()), both=int(((a == b) & (a != 0)).sum()),
                      match=round(float(((a == b) & ev).sum() / ev.sum()), 3) if ev.sum() else None,
                      first_diff=[str(t) for t in df.index[kk][(a != b)][:3]])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BATS:SPY", "BATS:QQQ", "BATS:NVDA", "BATS:UNH", "BATS:HOOD"])
    ap.add_argument("--tf", nargs="+", default=["5", "15"])
    ap.add_argument("--version", default="20.0")
    a = ap.parse_args()
    ws = visible_page()
    lines, allres = [], {}
    for sym in a.symbols:
        sym = sym if ":" in sym else f"BATS:{sym}"
        for tf in a.tf:
            r = evaluate(ws, JS % (json.dumps(sym), json.dumps(tf), json.dumps(SCRIPT), json.dumps(a.version), json.dumps(TITLES)))
            if r.get("err") or not r.get("rows"):
                lines.append(f"{sym} {tf}m: ERROR {r.get('err')} restore={r.get('after')}")
                print(lines[-1], flush=True); continue
            json.dump(r, open(os.path.join(ROOT, "runtime", f"parity_{sym.split(':')[1]}_{tf}.json"), "w"))
            res = compare(r["rows"], int(tf), r.get("daily"))
            allres[f"{sym} {tf}"] = res
            lines.append(f"{sym} {tf}m: bars {res['bars']} ({res['days']} days after warm-up) | " + " | ".join(
                f"{k} tv {res[k]['tv']} py {res[k]['py']} match {res[k]['match']}" for k in ("tl", "st", "ta", "wb"))
                + f" | indicator error {r.get('error')} | chart back to {r['after']}")
            print(lines[-1], flush=True)
    ws.close()
    os.makedirs(os.path.join(ROOT, "reports", "paper"), exist_ok=True)
    tot = {k: [sum(v[k]["both"] for v in allres.values()), sum(max(v[k]["tv"], v[k]["py"]) for v in allres.values())] for k in ("tl", "st", "ta", "wb")}
    lines.append("overall match (events agreeing / events either side): " + ", ".join(
        f"{k} {b}/{e} = {b / e:.1%}" if e else f"{k} no events" for k, (b, e) in tot.items()))
    open(os.path.join(ROOT, "reports", "paper", "parity.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(allres, open(os.path.join(ROOT, "runtime", "parity_summary.json"), "w"), indent=1, default=str)
    print(lines[-1])


if __name__ == "__main__":
    main()
