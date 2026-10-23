"""Save pine/volume_zones.pine to the user's TradingView script and test it on the real chart - no mouse, no paste.

Through TradingView Desktop's local debug port (start it with tools/start_tradingview.ps1):
  1. save the source to the saved script (TradingView compiles it on its servers; a compile error = nothing saved)
     and print the compiler warnings
  2. add a TEMPORARY copy of the new version to the visible chart, hide the user's copy
  3. on each timeframe, read the red / green trendlines the indicator actually drew (from the chart's line data)
     and whether the study reports an error
  4. remove the temporary copy, show the user's copy, restore the timeframe

    python tools/tv_pine_test.py                      # save + test on 1, 5, 15, 60, 240
    python tools/tv_pine_test.py --no-save --tf 5 15
"""
import argparse
import json
import os
import urllib.request

import websocket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = "USER;d519afe2d45a47c493a321e75859d475"      # "Volume Zones-v4"
NAME = "Volume Zones-v4"


def page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5)):
        if t["type"] != "page" or "/chart/" not in t["url"]:
            continue
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
        if run(ws, "document.visibilityState") == "visible":
            return ws
        ws.close()
    raise SystemExit("no visible TradingView chart (start it with tools/start_tradingview.ps1)")


def run(ws, js):
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True, "awaitPromise": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 1:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                raise RuntimeError(json.dumps(r["exceptionDetails"])[:500])
            return r.get("result", {}).get("value")


SAVE = """(async () => { const pe = window.TradingViewApi._pineEditorApi;
  const r = await pe.saveExistingScript({scriptIdPart: %s, source: %s, name: %s});
  window.__vzMeta = r && r.metaInfo;
  return JSON.stringify({ok: !!(r && r.success), version: r && r.metaInfo && r.metaInfo.pine.version,
    warnings: ((r && r.metaInfo && r.metaInfo.warnings) || []).map(w => w.message || JSON.stringify(w))}); })()"""

ADD = """(async () => { const ch = window.TradingViewApi.activeChart();
  window.__vzRes = ch.resolution();
  const before = new Set(ch.getAllStudies().map(s => s.id));
  window.__vzHidden = ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name)).map(s => s.id)
                        .filter(id => ch.getStudyById(id).isVisible());
  window.__vzHidden.forEach(id => ch.getStudyById(id).setVisible(false));
  await ch._chartWidget.insertStudy({type: "pine", pineId: %s, pineVersion: %s}, []);
  for (let i = 0; i < 30; i++) { await new Promise(r => setTimeout(r, 1000));
    const a = ch.getAllStudies().filter(s => !before.has(s.id)); if (a.length) { window.__vzTestId = a[0].id; return a[0].id; } }
  return null; })()"""

READ = """(async () => { const ch = window.TradingViewApi.activeChart();
  await new Promise(r => ch.setResolution(%s, r));
  const s0 = ch.getStudyById(window.__vzTestId);
  for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 1000)); if (!s0.isLoading()) break; }
  await new Promise(r => setTimeout(r, 3000));
  const g = s0._study.graphics(); const recs = []; const seen = new Set();
  const walk = (o, d) => { if (!o || typeof o !== "object" || seen.has(o) || d > 6) return; seen.add(o);
    if (o instanceof Map) { for (const v of o.values()) walk(v, d + 1); return; }
    if ("x1" in o && "y1" in o && "ci" in o) { recs.push(o); return; } for (const k of Object.keys(o)) walk(o[k], d + 1); };
  walk(g.dwglines(), 0);
  const pick = c => recs.filter(r => (r.ci >>> 0) === c && r.w === 2 && r.st === "sol" && (r.ex === "n" || r.ex === "r")).map(r => r.x2 - r.x1);
  return JSON.stringify({tf: ch.resolution(), symbol: ch.symbol(), error: s0.hasError(),
                         green: pick(0xFF76E600), red: pick(0xFF4417FF)}); })()"""      # ABGR of #00e676 / #ff1744

CLEAN = """(async () => { const ch = window.TradingViewApi.activeChart();
  if (window.__vzTestId) ch.removeEntity(window.__vzTestId);
  (window.__vzHidden || []).forEach(id => { const s = ch.getStudyById(id); if (s) s.setVisible(true); });
  if (window.__vzRes) await new Promise(r => ch.setResolution(window.__vzRes, r));
  return ch.resolution(); })()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--version", help="script version to test when --no-save")
    ap.add_argument("--tf", nargs="+", default=["1", "5", "15", "60", "240"])
    a = ap.parse_args()
    ws = page()
    version = a.version
    if not a.no_save:
        src = open(os.path.join(ROOT, "pine", "volume_zones.pine"), encoding="utf-8").read()
        res = json.loads(run(ws, SAVE % (json.dumps(SCRIPT), json.dumps(src), json.dumps(NAME))))
        print("saved:", res["ok"], "version", res["version"], "| compiler warnings:", res["warnings"] or "none")
        if not res["ok"]:
            raise SystemExit("save / compile failed")
        version = res["version"]
    if not version:
        raise SystemExit("--version is needed with --no-save")
    tid = run(ws, ADD % (json.dumps(SCRIPT), json.dumps(version)))
    if not tid:
        run(ws, CLEAN)
        raise SystemExit("could not add the test copy")
    try:
        for tf in a.tf:
            r = json.loads(run(ws, READ % json.dumps(tf)))
            print(f"{r['symbol']} {r['tf']:>4}: error={r['error']}  green lines {r['green']}  red lines {r['red']}")
    finally:
        print("restored timeframe:", run(ws, CLEAN))


if __name__ == "__main__":
    main()
