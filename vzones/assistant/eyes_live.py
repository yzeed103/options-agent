"""The daily eyes: the DEFINITIONS.md rules on today's 5-minute bars, stored in runtime/paper.db (table eyes_obs).

Each observation has a stable key, so re-running a cycle (or restarting the agent) updates it instead of adding a
duplicate. Outcomes that need later bars are 'pending' until those bars exist; nothing decided at bar t uses later bars.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import eyes
from .data import ROOT, RUNTIME

NY = ZoneInfo("America/New_York")
OUT = os.path.join(ROOT, "reports", "eyes")
VIEW = os.path.join(RUNTIME, "eyes_view.html")
OBS_STORE = os.path.join(OUT, "observations.json")
SCHEMA = """create table if not exists eyes_obs (
  key text primary key, date text, sym text, kind text, time text, type text, level real, side int,
  outcome text, status text, score int, detail text, updated text);
create index if not exists ix_eyes_date on eyes_obs(date);"""
STATE = os.path.join(RUNTIME, "eyes_state.json")
GRP_AR = {"index": "صناديق المؤشرات", "mega": "الشركات الكبرى", "high_beta": "عالية التذبذب"}
# whale pass-through on the first touch is common (history: most first touches pass), so it scores low and the daily
# report counts it against the historical rate instead of listing each one
SCORE = {"group_sync": 100, "flip_changed": 90, "wall_held3": 80, "entry_wall": 70, "whale_pass": 15, "entry_whale": 50,
         "touch_wall": 40, "touch_flip": 35, "touch_whale": 25, "entry": 20, "flip_side": 10, "range": 5}


def connect_schema(c) -> None:
    c.executescript(SCHEMA)


def _iso(t) -> str:
    return pd.Timestamp(t).isoformat()


def observe_day(sym: str, fr: dict, day=None, session_over: bool | None = None) -> list[dict]:
    """Observations for one symbol on one session (default: the last one in the data)."""
    d = fr[5]
    if day is None:
        day = d["session"].iat[-1]
    t = d[d["session"] == day]
    if len(t) < 2:
        return []
    if session_over is None:
        last_end = t.index[-1] + pd.Timedelta(minutes=5)
        session_over = last_end.hour * 60 + last_end.minute >= 960
    c, h, l = (t[k].to_numpy(float) for k in ("close", "high", "low"))
    datr = float(t["datr"].iat[0])
    if not np.isfinite(datr) or datr <= 0:
        return []
    out = []
    ds = str(day)

    def add(kind, time, typ="", level=np.nan, side=0, outcome="", status="final", detail=None, score_kind=None):
        key = f"{ds}|{sym}|{kind}|{typ}|{'' if not np.isfinite(level) else f'{level:.4f}'}|{_iso(time) if time is not None else ''}|{side}"
        out.append(dict(key=key, date=ds, sym=sym, kind=kind, time=_iso(time) if time is not None else "", type=typ,
                        level=None if not np.isfinite(level) else float(level), side=int(side), outcome=outcome, status=status,
                        score=SCORE.get(score_kind or kind, 10), detail=json.dumps(detail or {}, ensure_ascii=False, default=str)))

    # range so far
    add("range", None, outcome=f"{(h.max() - l.min()) / datr:.2f}", status="final" if session_over else "pending",
        detail={"range_atr": round((h.max() - l.min()) / datr, 3), "move_atr": round((c[-1] - t["open"].iat[0]) / datr, 3), "bars": len(t)})

    # flip side at 10:00 and change of side
    minute = t["minute"].to_numpy()
    k10 = np.flatnonzero(minute == 25)
    for col in ("flip", "dflip"):
        F = float(t[col].iat[0])
        if not np.isfinite(F) or not len(k10):
            continue
        i10 = int(k10[0])
        side = 1 if c[i10] > F else -1
        add("flip_side", t.index[i10], col, F, side, "فوق" if side > 0 else "تحت")
        after = np.arange(i10 + 1, len(t))
        other = (c[after] - F) * side < 0
        for j in range(len(after) - 2):
            if other[j] and other[j + 1] and other[j + 2]:
                k = after[j + 2]
                bef = float(np.mean(h[i10 + 1:k + 1] - l[i10 + 1:k + 1]) / datr)
                aft = float(np.mean(h[k + 1:] - l[k + 1:]) / datr) if k + 1 < len(t) else np.nan
                add("flip_changed", t.index[k], col, F, -side, "عبر للجهة الأخرى", "final" if session_over else "pending",
                    {"per_bar_before": round(bef, 4), "per_bar_after": None if not np.isfinite(aft) else round(aft, 4)})
                break

    # first touches of every level (real + pseudo, same rule as history)
    lev = eyes.level_events(sym, 5, t, fr["whale"], fr["whale_va"], last_complete=session_over)
    for e in lev:
        typ = e["type"]
        kind = "touch" if e["real"] else "touch_base"
        sk = "touch_wall" if typ in eyes.WALLS else ("touch_flip" if typ in ("flip", "dflip", "pin") else "touch_whale")
        outcome = "pending" if e["pending"] else ("ارتداد" if e["rejected"] else "اختراق")
        add(kind, e["time"], typ, e["level"], e["approach"], outcome, "pending" if e["pending"] else "final", score_kind=sk if e["real"] else "range")
        if e["real"] and typ.startswith("whale") and not e["pending"]:
            ti = t.index.get_loc(e["time"])
            beyond = (c[ti] > e["level"]) if e["approach"] > 0 else (c[ti] < e["level"])
            if beyond:
                add("whale_pass", e["time"], typ, e["level"], e["approach"], "عبر بلا ردّة فعل")

    # a wall touched three times or more and held
    for col in eyes.WALLS:
        L = float(t[col].iat[0])
        if not np.isfinite(L):
            continue
        touch = np.r_[False, ((c[:-1] < L) & (h[1:] >= L)) | ((c[:-1] > L) & (l[1:] <= L))]
        n = int(touch.sum())
        if n >= 3:
            side0 = np.sign(c[np.flatnonzero(touch)[0] - 1] - L)
            held = not (((c - L) * side0 < 0) & (np.arange(len(c)) >= np.flatnonzero(touch)[0])).any()
            if held:
                add("wall_held3", t.index[np.flatnonzero(touch)[2]], col, L, int(side0), f"{n} لمسات وصمد", detail={"touches": n})

    # confirmed entries (tl+all6) today and whether they reached the next wall / whale level so far
    full = fr[5]
    pos0 = full.index.get_loc(t.index[0])
    sig, cr = full["sig_tl"].to_numpy(), eyes._cross(full)
    it, st = full["it_dir"].to_numpy(), full["st_state"].to_numpy()
    sess = full["session"].to_numpy()
    wl = eyes._whale_list(day, fr["whale"], fr["whale_va"])
    W = np.array([float(t[col].iat[0]) for col in eyes.WALLS])
    W = W[np.isfinite(W)]
    for i in range(pos0, pos0 + len(t)):
        if not sig[i]:
            continue
        s = int(sig[i])
        ks = [k for k in range(max(0, i - 6), min(len(full) - 1, i + 6) + 1) if cr[k] == s and sess[k] == day]
        if not ks:
            continue
        j = i if any(k <= i for k in ks) else min(ks)
        if j >= pos0 + len(t) or not (it[j] == s and st[j] == s):
            continue
        jj = j - pos0
        cj = c[jj]
        res = {}
        for name, arr in (("wall", W), ("whale", wl)):
            ahead = arr[(arr - cj) * s > 0] if len(arr) else arr
            if not len(ahead):
                continue
            L = ahead.min() if s > 0 else ahead.max()
            seg = h[jj + 1:] if s > 0 else l[jj + 1:]
            reached = bool((seg >= L).any()) if s > 0 else bool((seg <= L).any())
            res[name] = dict(level=float(L), dist_atr=round(abs(L - cj) / datr, 3), reached=reached)
        status = "final" if session_over or all(v["reached"] for v in res.values()) else "pending"
        add("entry", t.index[jj], "tl+all6", cj, s, "شراء" if s > 0 else "بيع", status, res,
            score_kind="entry_wall" if res.get("wall", {}).get("reached") else ("entry_whale" if res.get("whale", {}).get("reached") else "entry"))
    return out


def upsert(c, obs: list[dict], now: str) -> int:
    connect_schema(c)
    for o in obs:
        c.execute("insert into eyes_obs values (?,?,?,?,?,?,?,?,?,?,?,?,?) on conflict(key) do update set "
                  "outcome=excluded.outcome, status=excluded.status, score=excluded.score, detail=excluded.detail, updated=excluded.updated",
                  (o["key"], o["date"], o["sym"], o["kind"], o["time"], o["type"], o["level"], o["side"], o["outcome"], o["status"],
                   o["score"], o["detail"], now))
    c.commit()
    return len(obs)


def group_sync(c, day: str, now: str) -> list[dict]:
    """An index group in sync: >= 80% of its symbols moved the same way from the open by more than 0.3 daily ATR."""
    rows = c.execute("select sym, detail from eyes_obs where date=? and kind='range'", (day,)).fetchall()
    mv = {s: json.loads(dj).get("move_atr", 0.0) for s, dj in rows}
    out = []
    for g in ("index", "mega", "high_beta"):
        ms = [v for s, v in mv.items() if eyes.group_of(s) == g]
        if len(ms) < 2:
            continue
        up = sum(1 for v in ms if v > 0.3) / len(ms)
        dn = sum(1 for v in ms if v < -0.3) / len(ms)
        if max(up, dn) >= 0.8:
            out.append(dict(key=f"{day}|{g}|group_sync", date=day, sym=g, kind="group_sync", time="", type=g, level=None,
                            side=1 if up >= dn else -1, outcome=f"{max(up, dn):.0%} {'صعود' if up >= dn else 'هبوط'}",
                            status="pending", score=SCORE["group_sync"], detail=json.dumps({"n": len(ms)})))
    upsert(c, out, now)
    return out


# ---------------- reports ----------------
TYPE_AR = {"cw": "CW", "pw": "PW", "cwoi": "CWOI", "pwoi": "PWOI", "flip": "FLIP", "dflip": "DFLIP", "pin": "PIN",
           "whale_poc": "POC حوت", "whale_vah": "VAH حوت", "whale_val": "VAL حوت", "whale_peak": "عمود حوت", "tl+all6": "دخول مؤكَّد"}
KIND_AR = {"group_sync": "مجموعة تتحرّك معًا", "flip_changed": "الانقلاب غيّر جانبه", "wall_held3": "جدار صمد 3 لمسات+",
           "whale_pass": "خط حوت انعبر بلا ردّة فعل", "entry": "دخول مؤكَّد", "touch": "لمسة مستوى", "flip_side": "جانب الانقلاب 10:00"}


def _load(c, day=None) -> pd.DataFrame:
    connect_schema(c)
    q = "select * from eyes_obs" + (" where date=?" if day else "")
    return pd.read_sql_query(q, c, params=(day,) if day else ())


def live_start() -> str:
    """The first day the eyes watched live (set once). Earlier days in the table were filled in after the fact and are
    not counted as live evidence."""
    st = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    if not st.get("live_start"):
        st["live_start"] = datetime.now(NY).date().isoformat()
        os.makedirs(RUNTIME, exist_ok=True)
        json.dump(st, open(STATE, "w", encoding="utf-8"))
    return st["live_start"]


def _live(o: pd.DataFrame) -> pd.DataFrame:
    return o[o.date >= live_start()] if len(o) else o


def tallies(c) -> list[dict]:
    """Live running numbers next to the history numbers (reports/eyes/history.json)."""
    o = _live(_load(c))
    hist = json.load(open(os.path.join(OUT, "history.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "history.json")) else {}
    rows = []
    if o.empty:
        return rows
    tch = o[o.kind.isin(["touch", "touch_base"]) & (o.status == "final")]
    for name, types in (("الجدران", eyes.WALLS), ("خطوط الحيتان", ("whale_poc", "whale_vah", "whale_val", "whale_peak")),
                        ("الانقلاب", ("flip", "dflip"))):
        r = tch[tch.type.isin(types)]
        real, base = r[r.kind == "touch"], r[r.kind == "touch_base"]
        rr = (real.outcome == "ارتداد").mean() if len(real) else np.nan
        rb = (base.outcome == "ارتداد").mean() if len(base) else np.nan
        hl = [x for x in hist.get("levels", []) if x["type"] in types and x["tf"] == 5 and x["period"] == "confirm" and x.get("n")]
        hr = np.average([x["rate"] for x in hl if x.get("rate") is not None], weights=[x["n"] for x in hl if x.get("rate") is not None]) if hl else np.nan
        hb = np.average([x["base"] for x in hl if x.get("base") is not None], weights=[x["n_base"] for x in hl if x.get("base") is not None]) if hl else np.nan
        rows.append(dict(what=f"ارتداد أول لمسة: {name}", live_n=len(real), live=rr, live_base=rb, hist=hr, hist_base=hb))
    en = o[(o.kind == "entry") & (o.status == "final")]
    if len(en):
        reached = [json.loads(x).get("wall", {}).get("reached") for x in en.detail]
        reached = [x for x in reached if x is not None]
        h2 = [x for x in hist.get("t2", []) if x["tf"] == 5 and x["variant"] == "tl+all6" and x["period"] == "confirm"]
        rows.append(dict(what="الدخول المؤكَّد يصل الجدار التالي", live_n=len(reached), live=np.mean(reached) if reached else np.nan,
                         live_base=np.nan, hist=h2[0]["hit"] if h2 else np.nan, hist_base=h2[0]["base"] if h2 else np.nan))
    return rows


def daily_report(c, day: str) -> str:
    o = _load(c, day)
    real = o[~o.kind.isin(["touch_base", "range"])] if len(o) else o
    if len(real):
        real = real.copy()
        g = real.kind == "group_sync"
        real.loc[g, "sym"] = real.loc[g, "sym"].map(GRP_AR).fillna(real.loc[g, "sym"])
        real.loc[g, "type"] = ""
    md = [f"# العيون {day}", ""]
    if day < live_start():
        md += ["هذا اليوم عُبّئ بعد انتهائه (قبل بدء المراقبة الحيّة)، فلا يدخل في الحصيلة الحيّة.", ""]
    if real.empty:
        md += ["لا ملاحظات اليوم.", ""]
    else:
        top, seen = [], {}
        for _, r in real.sort_values(["score", "time"], ascending=[False, True]).iterrows():
            if seen.get(r.sym, 0) >= 2 or (r.kind == "touch" and r.outcome == "pending"):
                continue
            top.append(r); seen[r.sym] = seen.get(r.sym, 0) + 1
            if len(top) == 5:
                break
        rows = []
        for r in top:
            det = json.loads(r.detail or "{}")
            nxt = r.outcome
            if r.kind == "entry":
                parts = [f"{'وصل' if v['reached'] else 'لم يصل'} {('الجدار' if k == 'wall' else 'خط الحوت')} {v['level']:.2f} ({v['dist_atr']} ATR)" for k, v in det.items()]
                nxt = f"{r.outcome}؛ " + "، ".join(parts) if parts else r.outcome
            rows.append([KIND_AR.get(r.kind, r.kind), r.sym, (r.time or "")[11:16], TYPE_AR.get(r.type, r.type or ""),
                         f"{r.level:.2f}" if pd.notna(r.level) else "—", nxt])
        md += ["## أهم 5 أشياء اليوم", "", "| الملاحظة | السهم | الوقت | المستوى | السعر | وش صار بعدها |", "|---|---|---|---|---|---|"]
        md += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows] + [""]
        flags = real[real.kind.isin(["group_sync", "flip_changed", "wall_held3"])]
        md += [f"## أشياء غير عادية ({len(flags)})", ""]
        md += [f"- {KIND_AR[r.kind]}: {r.sym} {(r.time or '')[11:16]} {TYPE_AR.get(r.type, r.type or '')} {r.outcome}" for _, r in flags.iterrows()] or ["لا شي."]
        wp = real[real.kind == "whale_pass"]
        wt = real[(real.kind == "touch") & real.type.str.startswith("whale") & (real.status == "final")]
        if len(wt):
            hist = json.load(open(os.path.join(OUT, "history.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "history.json")) else {}
            hl = [x for x in hist.get("levels", []) if str(x["type"]).startswith("whale") and x["tf"] == 5 and x["period"] == "confirm" and x.get("rate") is not None]
            hp = 1 - np.average([x["rate"] for x in hl], weights=[x["n"] for x in hl]) if hl else np.nan
            md += [f"- خطوط الحيتان: {len(wp)} من {len(wt)} أول لمسة انعبرت من نفس الشمعة. هذا عادي: في التاريخ نحو "
                   f"{100 * hp:.0f}% من أول اللمسات تنعبر خلال 4 شموع." if np.isfinite(hp) else
                   f"- خطوط الحيتان: {len(wp)} من {len(wt)} أول لمسة انعبرت من نفس الشمعة."]
        md += [""]
        fs = o[o.kind == "flip_side"]
        if len(fs):
            md += [f"جانب الانقلاب 10:00: فوق {int((fs.side > 0).sum())}، تحت {int((fs.side < 0).sum())} (FLIP و DFLIP).", ""]
    tl = tallies(c)
    if tl:
        f = lambda x: "—" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"  # noqa: E731
        md += ["## الحصيلة الحيّة مقابل التاريخ", "", "| البند | حيّ (عدد) | حيّ | عشوائي حيّ | التاريخ | عشوائي التاريخ |", "|---|---|---|---|---|---|"]
        md += [f"| {r['what']} | {r['live_n']} | {f(r['live'])} | {f(r['live_base'])} | {f(r['hist'])} | {f(r['hist_base'])} |" for r in tl] + [""]
    os.makedirs(OUT, exist_ok=True)
    text = "\n".join(md)
    open(os.path.join(OUT, f"{day}.md"), "w", encoding="utf-8").write(text)
    return text


# ---------------- durable observations ----------------
def _store():
    return json.load(open(OBS_STORE, encoding="utf-8")) if os.path.exists(OBS_STORE) else {"items": []}


def seed_observations(res: dict, today: str) -> None:
    """Add the history findings to the observation list (once each; existing items are never removed)."""
    st = _store()
    have = {it["id_key"]: it for it in st["items"]}
    V = {"holds": "ثابتة", "partly": "جزئيًا", "does not hold": "لا تثبت", "does not hold (opposite)": "لا تثبت (العكس)"}
    # what the data showed, by verdict (the item states the finding, not the hope)
    text = {
        "v1": {"holds": "الترند المؤكَّد (كسر + تقاطع 20/50 + أداة التأكيد + Supertrend) يتفوّق على المعدّل الطبيعي",
               "partly": "الترند المؤكَّد يتفوّق على المعدّل الطبيعي في جزء من البيانات فقط",
               "no": "الترند المؤكَّد (كسر + تقاطع 20/50 + أداة التأكيد + Supertrend) لا يتفوّق على شمعة عشوائية في نفس الوقت"},
        "v2": {"holds": "الجدار التالي هدف: السعر يصله أكثر من سعر عشوائي على نفس البعد",
               "partly": "الجدار التالي يُوصَل أكثر من سعر عشوائي في جزء من البيانات فقط",
               "no": "الجدار التالي ليس هدفًا: السعر يصله مثل سعر عشوائي على نفس البعد أو أقل قليلًا"},
        "v3": {"holds": "فوق الانقلاب بقية اليوم أهدأ والجدران ترتدّ أكثر",
               "partly": "فوق الانقلاب بقية اليوم أضيق قليلًا (أوضح في SPY و QQQ)، لكن الجدران لا ترتدّ أكثر",
               "no": "جانب الانقلاب لا يغيّر مدى بقية اليوم ولا الارتداد عند الجدران"},
        "v4": {"holds": "خطوط الحيتان تجذب السعر أكثر من سعر عشوائي على نفس البعد",
               "partly": "خطوط الحيتان تجذب السعر بفرق صغير جدًا، وفي الفترة الأولى فقط",
               "no": "خطوط الحيتان لا تجذب السعر أكثر من سعر عشوائي على نفس البعد"}}
    for k in ("v1", "v2", "v3", "v4"):
        v = res[k][0]
        tx = text[k]["holds" if v == "holds" else ("partly" if v == "partly" else "no")]
        ev = f"التاريخ: {V[v]}. {res[k][1]}"
        if f"history:{k}" in have:                 # refresh from the latest history run; number and date stay
            it = have[f"history:{k}"]
            it.update(text=tx, evidence=ev, verdict=v)
            continue
        st["items"].append(dict(id=len(st["items"]) + 1, id_key=f"history:{k}", added=today, text=tx,
                                evidence=ev, verdict=v, status="holding", live=""))
    lv = [x for x in res.get("levels", []) if x["tf"] == 5 and x["period"] == "confirm" and x.get("n", 0) >= 30
          and x.get("lo") is not None and np.isfinite(x["lo"]) and (x["lo"] > 0 or x["hi"] < 0)]
    for x in lv:
        key = f"history:level:{x['type']}"
        sign = "أكثر" if x["lo"] > 0 else "أقل"
        tx = (f"أول لمسة لـ {TYPE_AR.get(x['type'], x['type'])} ترتدّ {sign} من سعر عشوائي قريب "
              f"(فترة واحدة وعيّنة صغيرة: تنتظر التأكيد الحيّ)")
        ev = (f"5د، التأكيد: {x['n']} لمسة، ارتداد {100 * x['rate']:.0f}% مقابل {100 * x['base']:.0f}% "
              f"(الفرق {100 * x['diff']:+.1f} pp، {100 * x['lo']:+.1f} إلى {100 * x['hi']:+.1f})")
        if key in have:
            have[key].update(text=tx, evidence=ev, hist_diff=x["diff"])
            continue
        st["items"].append(dict(id=len(st["items"]) + 1, id_key=key, added=today, text=tx, evidence=ev,
                                verdict="level", status="holding", live="", hist_diff=x["diff"], level_type=x["type"]))
    os.makedirs(OUT, exist_ok=True)
    json.dump(st, open(OBS_STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_observations()


def update_observations(c) -> None:
    """Live status of each level observation: holding / weakening / refuted (30 live touches minimum)."""
    st = _store()
    o = _live(_load(c))
    if o.empty:
        return
    tch = o[o.kind.isin(["touch", "touch_base"]) & (o.status == "final")]
    for it in st["items"]:
        if it.get("verdict") != "level":
            continue
        r = tch[tch.type == it["level_type"]]
        real, base = r[r.kind == "touch"], r[r.kind == "touch_base"]
        if len(real) < 30 or len(base) < 30:
            it["live"] = f"حيّ: {len(real)} لمسة (أقل من 30، الحكم ينتظر)"
            continue
        a, b = (real.outcome == "ارتداد").mean(), (base.outcome == "ارتداد").mean()
        se = np.sqrt(a * (1 - a) / len(real) + b * (1 - b) / len(base))
        diff, lo, hi = a - b, a - b - 1.96 * se, a - b + 1.96 * se
        h = it.get("hist_diff", 0)
        it["status"] = "holding" if lo <= h <= hi or (np.sign(diff) == np.sign(h) and (lo > 0 or hi < 0)) else (
            "refuted" if (lo > 0 > h) or (hi < 0 < h) else "weakening")
        it["live"] = f"حيّ: {len(real)} لمسة، الفرق {100 * diff:+.1f} pp ({100 * lo:+.1f} إلى {100 * hi:+.1f})"
    json.dump(st, open(OBS_STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_observations()


def write_observations() -> None:
    st = _store()
    S_AR = {"holding": "ثابتة", "weakening": "تضعف", "refuted": "انتقضت"}
    md = ["# ملاحظات دائمة", "", "قائمة تُحدَّث ولا تُعاد كتابتها: الرقم والتاريخ ثابتان، والحالة تتغيّر مع البيانات الحيّة.", ""]
    for it in st["items"]:
        md += [f"{it['id']}. **{it['text']}** — أُضيفت {it['added']}. الحالة: {S_AR.get(it['status'], it['status'])}.",
               f"   - الدليل: {it['evidence']}"] + ([f"   - {it['live']}"] if it.get("live") else [])
    open(os.path.join(OUT, "OBSERVATIONS.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")


def view(c, day: str) -> None:
    import html
    o = _load(c, day)
    hist = json.load(open(os.path.join(OUT, "history.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "history.json")) else {}
    V = {"holds": ("ثابتة", "pos"), "partly": ("جزئيًا", "mid"), "does not hold": ("لا تثبت", "neg"), "does not hold (opposite)": ("لا تثبت (العكس)", "neg")}
    names = {"v1": "الترند المؤكَّد", "v2": "الجدران أهداف", "v3": "الانقلاب وسلوك صانع السوق", "v4": "الحيتان تجذب السعر"}
    score = "".join(f"<tr><td>{n}</td><td class={V[hist[k][0]][1]}>{V[hist[k][0]][0]}</td><td class=m>{html.escape(hist[k][1])}</td></tr>"
                    for k, n in names.items() if k in hist)
    real = o[~o.kind.isin(["touch_base", "range"])].sort_values(["score", "time"], ascending=[False, False]) if len(o) else o
    rows = "".join(f"<tr><td>{html.escape(KIND_AR.get(r.kind, r.kind))}</td><td>{r.sym}</td><td class=n>{(r.time or '')[11:16]}</td>"
                   f"<td>{html.escape(TYPE_AR.get(r.type, r.type or ''))}</td><td class=n>{'' if pd.isna(r.level) else f'{r.level:.2f}'}</td>"
                   f"<td>{html.escape(r.outcome or '')}</td></tr>" for _, r in real.head(60).iterrows()) or "<tr><td colspan=6 class=m>لا شي بعد</td></tr>"
    page = f"""<!doctype html><html lang=ar dir=rtl><head><meta charset=utf-8><meta http-equiv=refresh content=60>
<meta name=viewport content="width=device-width,initial-scale=1"><title>العيون</title><style>
:root{{--bg:#0f1115;--fg:#e6e6e6;--mut:#8a8f9c;--line:#262a33}}body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,Tahoma;margin:16px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}}
th{{color:var(--mut);font-weight:500}}.n{{direction:ltr;unicode-bidi:isolate}}.m{{color:var(--mut);font-size:12px}}
.pos{{color:#26a69a}}.neg{{color:#ef5350}}.mid{{color:#ffd54f}}h1{{font-size:18px}}h2{{font-size:15px;color:var(--mut)}}</style></head><body>
<h1>العيون: ملاحظات بلا صفقات</h1><div class=m>آخر تحديث {datetime.now(NY).strftime('%Y-%m-%d %H:%M')} نيويورك · {len(real)} ملاحظة اليوم</div>
<h2>حكم النظرية على التاريخ</h2><table>{score}</table>
<h2>ملاحظات اليوم (الأهم أولًا)</h2><table><tr><th>الملاحظة</th><th>السهم</th><th>الوقت</th><th>المستوى</th><th>السعر</th><th>النتيجة</th></tr>{rows}</table>
</body></html>"""
    os.makedirs(RUNTIME, exist_ok=True)
    open(VIEW + ".tmp", "w", encoding="utf-8").write(page)
    os.replace(VIEW + ".tmp", VIEW)
