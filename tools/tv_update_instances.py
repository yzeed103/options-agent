"""Upgrade every Volume Zones instance on every open TradingView chart tab to a new script version, KEEPING the user's
settings. Dry run by default.

Only inputs the user changed (value != that old version's default) are carried over, matched to the new version by
(input name, name of the input before it) - this tells apart repeated names such as «السماكة» - then by (name,
occurrence). New inputs keep their new defaults. The new instance takes the old one's visibility; the old is removed.

    python tools/tv_update_instances.py --new-inputs runtime/vz_inputs_9.0.json --version 9.0          # dry run
    python tools/tv_update_instances.py --new-inputs runtime/vz_inputs_9.0.json --version 9.0 --apply
"""
import argparse
import json
import urllib.request

import websocket

SCRIPT = "USER;d519afe2d45a47c493a321e75859d475"

JS = r"""(async (NEW, VER, PINE, APPLY) => {
  const api = window.TradingViewApi; if (!api) return JSON.stringify({skip: "no api"});
  const out = [];
  const keyed = list => {               // [{id,name,...}] -> keys "name|prev" and "name#occ"
    const occ = {}; let prev = "";
    return list.map(x => { occ[x.name] = (occ[x.name] || 0) + 1;
      const k = {id: x.id, type: x.type, k1: x.name + "|" + prev, k2: x.name + "#" + occ[x.name]}; prev = x.name; return k; });
  };
  // colors come back as ABGR integers while defaults are "#rrggbb[aa]": compare them in one form
  const norm = (v, type) => {
    if (type !== "color") return JSON.stringify(v);
    const s = String(v).trim();
    if (/^\d+$/.test(s)) { const n = Number(s) >>> 0; const h = x => x.toString(16).padStart(2, "0");
      const a = (n >>> 24) & 255, b = (n >>> 16) & 255, g = (n >>> 8) & 255, r = n & 255;
      return "#" + h(r) + h(g) + h(b) + (a === 255 ? "" : h(a)); }
    const t = s.toLowerCase(); return t.length === 9 && t.endsWith("ff") ? t.slice(0, 7) : t;
  };
  const nk = keyed(NEW);
  const by1 = {}, by2 = {}, dup1 = new Set();
  for (const x of nk) { if (by1[x.k1]) dup1.add(x.k1); by1[x.k1] = x; by2[x.k2] = x; }
  const n = api.chartsCount ? api.chartsCount() : 1;
  for (let c = 0; c < n; c++) {
    const ch = api.chartsCount ? api.chart(c) : api.activeChart();
    for (const s of ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name))) {
      const st = ch.getStudyById(s.id);
      const meta = st._study.metaInfo();
      if (!meta.pine || meta.scriptIdPart !== PINE) continue;
      if (meta.pine.version === VER) { out.push({id: s.id, sym: ch.symbol(), ver: VER, note: "already new"}); continue; }
      const info = st.getInputsInfo().filter(x => !x.isHidden);
      const vals = {}; for (const v of st.getInputValues()) vals[v.id] = v.value;
      const ok = keyed(info);
      const carry = [], lost = [];
      info.forEach((x, i) => {
        const v = vals[x.id];
        if (v === undefined || norm(v, x.type) === norm(x.defval, x.type)) return;   // not changed by the user
        const k = ok[i];
        const t = (!dup1.has(k.k1) && by1[k.k1]) || by2[k.k2];
        if (t && t.type === x.type) carry.push({id: t.id, value: v, name: x.name});
        else lost.push(x.name);
      });
      const rec = {id: s.id, sym: ch.symbol(), tf: ch.resolution(), ver: meta.pine.version, visible: st.isVisible(),
                   changed: carry.length + lost.length, carry: carry.map(c => c.name), lost};
      if (APPLY) {
        const before = new Set(ch.getAllStudies().map(x => x.id));
        await ch._chartWidget.insertStudy({type: "pine", pineId: PINE, pineVersion: VER}, []);
        let nid = null;
        for (let i = 0; i < 30 && !nid; i++) { await new Promise(r => setTimeout(r, 1000));
          const a = ch.getAllStudies().filter(x => !before.has(x.id)); if (a.length) nid = a[0].id; }
        if (!nid) { rec.error = "could not add new version"; out.push(rec); continue; }
        const ns = ch.getStudyById(nid);
        if (carry.length) ns.setInputValues(carry.map(c => ({id: c.id, value: c.value})));
        if (!rec.visible) ns.setVisible(false);
        ch.removeEntity(s.id);
        rec.newId = nid;
      }
      out.push(rec);
    }
  }
  return JSON.stringify(out);
})(%s, %s, %s, %s)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-inputs", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    new = json.load(open(a.new_inputs, encoding="utf-8"))["inputs"]
    expr = JS % (json.dumps(new), json.dumps(a.version), json.dumps(SCRIPT), "true" if a.apply else "false")
    tabs = [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5))
            if t["type"] == "page" and "/chart/" in t["url"]]
    total = {"instances": 0, "upgraded": 0, "already": 0, "lost": set()}
    for t in tabs:
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=180, suppress_origin=True)
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == 1:
                    break
            ws.close()
            v = m.get("result", {}).get("result", {}).get("value")
            recs = json.loads(v) if isinstance(v, str) else []
        except Exception as e:  # noqa: BLE001
            print(t["id"][:8], "error", type(e).__name__)
            continue
        if isinstance(recs, dict):
            continue
        for r in recs:
            total["instances"] += 1
            if r.get("note"):
                total["already"] += 1
                continue
            total["upgraded"] += bool(r.get("newId"))
            total["lost"].update(r["lost"])
            print(f"{t['id'][:8]} {r['sym']:>16} {r.get('tf', ''):>4} v{r['ver']} -> v{a.version}  changed {r['changed']}"
                  f"  carried {len(r['carry'])}  not found {r['lost']}" + (f"  NEW {r['newId']}" if r.get("newId") else "")
                  + (f"  ERROR {r['error']}" if r.get("error") else ""))
    print(f"\ninstances {total['instances']}, already new {total['already']}, upgraded {total['upgraded']}"
          f"{'' if a.apply else ' (dry run - nothing changed)'}; settings with no place in the new version: "
          f"{sorted(total['lost']) or 'none'}")


if __name__ == "__main__":
    main()
