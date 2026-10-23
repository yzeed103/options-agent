"""Finish / repair a Volume Zones instance upgrade on every open TradingView chart tab (see tv_update_instances.py).

Per tab, per chart:
  - old + new present  : copy the user's changed settings old -> new (if the new still has defaults), remove the old
  - old only           : add the new version (waits up to 150 s: hidden tabs load slowly), copy settings, remove the old
  - new only           : nothing
Dry run by default; --apply to change. Each tab is verified after the change (exactly one instance, new version).

    python tools/tv_finish_upgrade.py --new-inputs runtime/vz_inputs_9.0.json --version 9.0 [--apply]
"""
import argparse
import json
import urllib.request

import websocket

SCRIPT = "USER;d519afe2d45a47c493a321e75859d475"

JS = r"""(async (NEW, VER, PINE, APPLY, CANON) => {
  const api = window.TradingViewApi; if (!api) return JSON.stringify({skip: "no api"});
  const norm = (v, type) => {
    if (type !== "color") return JSON.stringify(v);
    const s = String(v).trim();
    if (/^\d+$/.test(s)) { const n = Number(s) >>> 0; const h = x => x.toString(16).padStart(2, "0");
      const a = (n >>> 24) & 255, b = (n >>> 16) & 255, g = (n >>> 8) & 255, r = n & 255;
      return "#" + h(r) + h(g) + h(b) + (a === 255 ? "" : h(a)); }
    const t = s.toLowerCase(); return t.length === 9 && t.endsWith("ff") ? t.slice(0, 7) : t;
  };
  const keyed = list => { const occ = {}; let prev = "";
    return list.map(x => { occ[x.name] = (occ[x.name] || 0) + 1;
      const k = {id: x.id, type: x.type, k1: x.name + "|" + prev, k2: x.name + "#" + occ[x.name]}; prev = x.name; return k; }); };
  const nk = keyed(NEW); const by1 = {}, by2 = {}, dup1 = new Set();
  for (const x of nk) { if (by1[x.k1]) dup1.add(x.k1); by1[x.k1] = x; by2[x.k2] = x; }
  const changed = st => { const carry = [], lost = [];
    if (CANON) {   // the user's settings, read once from an original instance
      for (const c of CANON) { const t = (!dup1.has(c.k1) && by1[c.k1]) || by2[c.k2];
        if (t && t.type === c.type) carry.push({id: t.id, value: c.value}); else lost.push(c.k1); }
      return {carry, lost}; }
    const info = st.getInputsInfo().filter(x => !x.isHidden); const vals = {};
    for (const v of st.getInputValues()) vals[v.id] = v.value; const ok = keyed(info);
    info.forEach((x, i) => { const v = vals[x.id]; if (v === undefined || norm(v, x.type) === norm(x.defval, x.type)) return;
      const k = ok[i]; const t = (!dup1.has(k.k1) && by1[k.k1]) || by2[k.k2];
      if (t && t.type === x.type) carry.push({id: t.id, value: v}); else lost.push(x.name); });
    return {carry, lost}; };
  // apply settings and verify by reading back; retry the ones that did not stick (one setInputValues batch
  // was observed to keep only 8 of 16 values)
  const applyVerified = async (st, carry) => { let todo = carry; let tries = 0;
    while (todo.length && tries < 4) { st.setInputValues(todo); tries++;
      await new Promise(r => setTimeout(r, 2500));
      for (let i = 0; i < 30; i++) { if (!st.isLoading()) break; await new Promise(r => setTimeout(r, 1000)); }
      const vals = {}; for (const v of st.getInputValues()) vals[v.id] = v.value;
      const typeOf = {}; for (const x of st.getInputsInfo()) typeOf[x.id] = x.type;
      todo = todo.filter(c => norm(vals[c.id], typeOf[c.id]) !== norm(c.value, typeOf[c.id])); }
    return {applied: carry.length - todo.length, failed: todo.map(c => c.id), tries}; };
  const out = [];
  const n = api.chartsCount ? api.chartsCount() : 1;
  for (let c = 0; c < n; c++) {
    const ch = api.chartsCount ? api.chart(c) : api.activeChart();
    const vz = ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name)).map(s => {
      const st = ch.getStudyById(s.id); let v = null; try { const m = st._study.metaInfo(); if (m.scriptIdPart === PINE) v = m.pine.version; } catch (e) {}
      return {id: s.id, st, v}; }).filter(x => x.v);
    const olds = vz.filter(x => x.v !== VER), news = vz.filter(x => x.v === VER);
    const rec = {sym: ch.symbol(), tf: ch.resolution(), old: olds.length, new: news.length};
    if (!olds.length) {
      rec.action = news.length ? "ok" : "none";
      if (news.length && CANON && APPLY) { const ch_ = changed(news[0].st); const ap = await applyVerified(news[0].st, ch_.carry);
        rec.action = "settings"; rec.carry = ch_.carry.length; rec.applied = ap.applied; rec.failed = ap.failed; rec.verified = !ap.failed.length; rec.after = [VER]; }
      out.push(rec); continue; }
    const old = olds[0]; const ch_ = changed(old.st); rec.carry = ch_.carry.length; rec.lost = ch_.lost;
    rec.action = news.length ? "repair" : "upgrade";
    if (!APPLY) { out.push(rec); continue; }
    let nw = news[0] ? news[0].st : null;
    if (!nw) {
      const before = new Set(ch.getAllStudies().map(x => x.id));
      await ch._chartWidget.insertStudy({type: "pine", pineId: PINE, pineVersion: VER}, []);
      let nid = null;
      for (let i = 0; i < 150 && !nid; i++) { await new Promise(r => setTimeout(r, 1000)); const a = ch.getAllStudies().filter(x => !before.has(x.id)); if (a.length) nid = a[0].id; }
      if (!nid) { rec.error = "new version did not appear in 150 s"; out.push(rec); continue; }
      nw = ch.getStudyById(nid);
    }
    if (ch_.carry.length) { const ap = await applyVerified(nw, ch_.carry); rec.applied = ap.applied; rec.failed = ap.failed; rec.tries = ap.tries; }
    if (!old.st.isVisible()) nw.setVisible(false);
    for (const o of olds) ch.removeEntity(o.id);
    for (const extra of news.slice(1)) ch.removeEntity(extra.id);
    await new Promise(r => setTimeout(r, 1000));
    const left = ch.getAllStudies().filter(s => /Volume Zones/i.test(s.name));
    rec.after = left.map(s => { try { return ch.getStudyById(s.id)._study.metaInfo().pine.version; } catch (e) { return "?"; } });
    rec.verified = left.length === 1 && rec.after[0] === VER && !(rec.failed || []).length;
    out.push(rec);
  }
  return JSON.stringify(out);
})(%s, %s, %s, %s, %s)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-inputs", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--settings", help="runtime/vz_user_settings.json: the user's changed inputs, applied to every new instance")
    a = ap.parse_args()
    new = json.load(open(a.new_inputs, encoding="utf-8"))["inputs"]
    canon = json.load(open(a.settings, encoding="utf-8"))["changed"] if a.settings else None
    expr = JS % (json.dumps(new), json.dumps(a.version), json.dumps(SCRIPT), "true" if a.apply else "false", json.dumps(canon))
    tabs = [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5))
            if t["type"] == "page" and "/chart/" in t["url"]]
    tally = {}
    bad = []
    for t in tabs:
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=400, suppress_origin=True)
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
            bad.append((t["id"][:8], type(e).__name__))
            continue
        if isinstance(recs, dict):
            continue
        for r in recs:
            tally[r["action"]] = tally.get(r["action"], 0) + 1
            if r.get("error") or r.get("lost") or (a.apply and r["action"] != "ok" and not r.get("verified")):
                bad.append((t["id"][:8], r))
            print(f"{t['id'][:8]} {r['sym']:>16} {r['tf']:>4} old {r['old']} new {r['new']} -> {r['action']}"
                  + (f" carry {r.get('carry')}" if "carry" in r else "")
                  + (f" applied={r.get('applied')}/{r.get('carry')} verified={r.get('verified')} after={r.get('after')}" if a.apply and r["action"] != "ok" else "")
                  + (f" ERROR {r['error']}" if r.get("error") else ""), flush=True)
    print("\nsummary:", tally, "" if a.apply else "(dry run)")
    print("problems:", bad if bad else "none")


if __name__ == "__main__":
    main()
