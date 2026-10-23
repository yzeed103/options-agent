"""Reports in short Arabic with tables (reports/paper/) and the local assistant page (runtime/paper_view.html)."""
from __future__ import annotations

import html
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .data import ROOT, RUNTIME
from .sim import NAMES_AR

OUT = os.path.join(ROOT, "reports", "paper")
VIEW = os.path.join(RUNTIME, "paper_view.html")
NY = ZoneInfo("America/New_York")
VERDICT_AR = {"promoted": "معتمدة", "candidate": "مرشّحة", "watching": "تحت المراقبة", "dead": "ميتة", "demoted": "سقطت"}
BUCKET_AR = {"side": "الاتجاه", "time": "الوقت", "trend": "المتوسطات", "va": "منطقة قيمة الأمس", "rvol": "الفوليوم النسبي",
             "gex_wall": "قرب جدار", "gex_flip": "مستوى الانقلاب", "vix": "VIX", "gap": "الفجوة"}


def _f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def _table(rows: list[list], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def gross_by_signal(c) -> pd.DataFrame:
    return pd.read_sql_query("select signal, tf, count(*) n, avg(r) net, avg(r + cost_r) gross, avg(cost_r) cost "
                             "from trades where status='closed' and source!='live' group by signal, tf", c)


def history_report(c, ev: pd.DataFrame, st: dict) -> str:
    g = gross_by_signal(c).set_index(["signal", "tf"])
    base = ev[ev.rule == "all"].sort_values(["signal", "tf"])
    rows = []
    for _, r in base.iterrows():
        gg = g.loc[(r.signal, r.tf)] if (r.signal, r.tf) in g.index else None
        ci = r.get("held_ci")
        rows.append([f"{NAMES_AR[r.signal]} ({r.signal})", f"{r.tf}د", int(r.tuning_n + r.get("held_n", 0)),
                     _f(gg.gross if gg is not None else None), _f(gg.cost if gg is not None else None),
                     _f(r.tuning_mean), _f(r.get("held_mean")), _f(r.get("held_t")),
                     f"{_f(ci[0])} إلى {_f(ci[1])}" if isinstance(ci, list) else "—", VERDICT_AR[r.verdict]])
    cnt = ev.verdict.value_counts()
    best = ev[(ev.rule != "all") & (ev.held_n >= 100)].sort_values("held_t", ascending=False).head(8)
    brows = [[f"{r.signal} {r.tf}د", r.rule, int(r.tuning_n), _f(r.tuning_mean), int(r.held_n), _f(r.held_mean), _f(r.held_t),
              VERDICT_AR[r.verdict]] for _, r in best.iterrows()]
    md = [f"# حكم المساعد على التاريخ", "",
          f"الفترة: {st.get('history', ['?', '?'])[0]} إلى {st.get('history', ['?', '?'])[1]}. "
          f"التعلّم من البداية حتى {st.get('split')}، والاختبار المحجوز بعدها. القواعد مجمّدة منذ {st.get('frozen_at', '—')[:16]}.", "",
          "القيم بوحدة R (مضاعف المخاطرة). «قبل التكاليف» = لو كان الدخول والخروج بلا فرق سعر.", "",
          "## كل إشارة لوحدها", "",
          _table(rows, ["الإشارة", "الفريم", "صفقات", "متوسط قبل التكاليف", "التكلفة", "متوسط التعلّم", "متوسط المحجوز",
                        "t المحجوز", "مجال الثقة 95%", "الحكم"]), "",
          f"## القواعد ({len(ev)} قاعدة)", "",
          _table([[VERDICT_AR.get(k, k), int(v)] for k, v in cnt.items()], ["الحكم", "العدد"]), "",
          "تنبيه: مع هذا العدد من القواعد، نحو 2 إلى 3% منها تتجاوز t = 2 بالصدفة. لذلك المرشّحة لا تُعتمد إلا بعد 30 صفقة حيّة.", "",
          "## أعلى القواعد في الاختبار المحجوز (100 صفقة على الأقل)", "",
          _table(brows, ["الإشارة", "الشرط", "صفقات التعلّم", "متوسط التعلّم", "صفقات المحجوز", "متوسط المحجوز", "t", "الحكم"]), ""]
    os.makedirs(OUT, exist_ok=True)
    text = "\n".join(md)
    open(os.path.join(OUT, "history_verdict.md"), "w", encoding="utf-8").write(text)
    return text


def graveyard(ev: pd.DataFrame) -> None:
    dead = ev[ev.verdict == "dead"].sort_values(["signal", "tf", "held_mean"])
    rows = [[f"{r.signal} {r.tf}د", r.rule, int(r.tuning_n), _f(r.tuning_mean), int(r.held_n), _f(r.held_mean)]
            for _, r in dead.iterrows()]
    text = "\n".join(["# مقبرة الأفكار", "", "قواعد سالبة في التعلّم وفي المحجوز معًا (30 صفقة على الأقل في كل منهما). لا تُعاد بدون سبب جديد.", "",
                      _table(rows, ["الإشارة", "الشرط", "صفقات التعلّم", "متوسط التعلّم R", "صفقات المحجوز", "متوسط المحجوز R"]), ""])
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "graveyard.md"), "w", encoding="utf-8").write(text)


def _verdict_map(c) -> dict:
    return {r: v for r, v in c.execute(
        "select rule, verdict from verdicts v where ts = (select max(ts) from verdicts w where w.rule = v.rule)")}


def daily_report(c, day: str | None = None) -> str:
    day = day or datetime.now(NY).date().isoformat()
    t = pd.read_sql_query("select * from trades where substr(signal_time, 1, 10) = ? and source != 'replay'", c, params=(day,))
    op = pd.read_sql_query("select * from trades where status = 'open'", c)
    lv = pd.read_sql_query("select signal, tf, count(*) n, avg(r) mean, sum(r) total, avg(r > 0) win from trades "
                           "where source = 'live' and status = 'closed' group by signal, tf", c)
    vm = _verdict_map(c)
    ev = pd.read_sql_query("select * from events where substr(ts, 1, 10) = ? and kind in ('verdict', 'anomaly')", c, params=(day,))
    closed = t[t.status == "closed"]
    rows_today = [[f"{NAMES_AR[r.signal]} {r.tf}د", r.sym, "شراء" if r.side > 0 else "بيع", r.signal_time[11:16], _f(r.entry),
                   r.reason or "مفتوحة", _f(r.r)] for _, r in t.sort_values("signal_time").iterrows()]
    rows_open = [[f"{NAMES_AR[r.signal]} {r.tf}د", r.sym, "شراء" if r.side > 0 else "بيع", r.entry_time[:16].replace("T", " "),
                  _f(r.entry), _f(r.stop), _f(r.target), _f(r.r)] for _, r in op.sort_values("entry_time").iterrows()]
    rows_live = [[f"{NAMES_AR[r.signal]} {r.tf}د", int(r.n), _f(r.win * 100, 0) + "%", _f(r["mean"]), _f(r.total, 1),
                  VERDICT_AR.get(vm.get(f"{r.signal}|{r.tf}|all"), "—")] for _, r in lv.iterrows()]
    md = [f"# تقرير المساعد {day}", "",
          f"صفقات اليوم: {len(t)} (أُغلقت {len(closed)}، مجموعها {_f(closed.r.sum() if len(closed) else 0.0, 1)}R). مفتوحة الآن: {len(op)}.", "",
          "## صفقات اليوم", "", _table(rows_today, ["الإشارة", "السهم", "الجهة", "الوقت", "الدخول", "الخروج", "النتيجة R"]) if rows_today else "لا يوجد.", "",
          "## المفتوحة", "", _table(rows_open, ["الإشارة", "السهم", "الجهة", "دخلت", "الدخول", "الوقف", "الهدف", "الآن R"]) if rows_open else "لا يوجد.", "",
          "## الحصيلة الحيّة منذ التجميد", "", _table(rows_live, ["الإشارة", "صفقات", "نسبة الربح", "متوسط R", "المجموع R", "الحكم"]) if rows_live else "لا صفقات حيّة مغلقة بعد.", ""]
    if len(ev):
        md += ["## تغيّرات اليوم", ""] + [f"- {r.kind}: {r.detail[:200]}" for _, r in ev.iterrows()] + [""]
    os.makedirs(OUT, exist_ok=True)
    text = "\n".join(md)
    open(os.path.join(OUT, f"{day}.md"), "w", encoding="utf-8").write(text)
    return text


def view(c, health: dict | None = None) -> None:
    """runtime/paper_view.html: open trades, today's closed ones, and the verdict of each signal."""
    op = pd.read_sql_query("select * from trades where status = 'open' order by entry_time desc", c)
    day = datetime.now(NY).date().isoformat()
    td = pd.read_sql_query("select * from trades where status = 'closed' and substr(signal_time, 1, 10) = ? and source != 'replay' "
                           "order by exit_time desc", c, params=(day,))
    vm = _verdict_map(c)
    base = sorted((k, v) for k, v in vm.items() if k.endswith("|all"))
    esc = html.escape

    def rows(df, live_r=True):
        out = []
        for _, r in df.iterrows():
            ctx = json.loads(r.context)
            lv = ", ".join(f"{BUCKET_AR[k]}: {v}" for k, v in ctx.items() if k in ("trend", "va", "gex_wall", "gex_flip") and v != "none")
            cls = "pos" if (r.r or 0) > 0 else "neg"
            out.append(f"<tr><td>{esc(NAMES_AR[r.signal])} <span class=m>{r.tf}د</span></td><td>{esc(r.sym)}</td>"
                       f"<td>{'شراء' if r.side > 0 else 'بيع'}</td><td class=n>{r.entry:.2f}</td><td class=n>{r.stop:.2f}</td>"
                       f"<td class=n>{r.target:.2f}</td><td class='n {cls}'>{(r.r or 0):+.2f}R</td>"
                       f"<td>{esc(VERDICT_AR.get(vm.get(f'{r.signal}|{r.tf}|all'), '—'))}</td><td class=m>{esc(lv)}</td></tr>")
        return "".join(out) or "<tr><td colspan=9 class=m>لا يوجد</td></tr>"
    head = "<tr><th>الإشارة</th><th>السهم</th><th>الجهة</th><th>الدخول</th><th>الوقف</th><th>الهدف</th><th>النتيجة</th><th>حكم الإشارة</th><th>السياق</th></tr>"
    vrows = "".join(f"<tr><td>{esc(NAMES_AR[k.split('|')[0]])} {k.split('|')[1]}د</td><td class={v}>{esc(VERDICT_AR[v])}</td></tr>" for k, v in base)
    hl = esc(json.dumps(health or {}, ensure_ascii=False))
    page = f"""<!doctype html><html lang=ar dir=rtl><head><meta charset=utf-8><meta http-equiv=refresh content=60>
<meta name=viewport content="width=device-width,initial-scale=1"><title>المساعد</title><style>
:root{{--bg:#0f1115;--fg:#e6e6e6;--mut:#8a8f9c;--line:#262a33;--pos:#26a69a;--neg:#ef5350}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,Tahoma;margin:16px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}}
th{{color:var(--mut);font-weight:500}}.n{{direction:ltr;unicode-bidi:isolate;text-align:left}}.m{{color:var(--mut);font-size:12px}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.dead{{color:var(--neg)}}.promoted{{color:var(--pos)}}.candidate{{color:#ffd54f}}
h1{{font-size:18px}}h2{{font-size:15px;color:var(--mut)}}</style></head><body>
<h1>المساعد: صفقات وهمية فقط</h1><div class=m>آخر تحديث {datetime.now(NY).strftime('%Y-%m-%d %H:%M')} نيويورك · {hl}</div>
<h2>المفتوحة ({len(op)})</h2><table>{head}{rows(op)}</table>
<h2>أُغلقت اليوم ({len(td)})</h2><table>{head}{rows(td)}</table>
<h2>حكم كل إشارة</h2><table><tr><th>الإشارة</th><th>الحكم</th></tr>{vrows}</table>
<div class=m>معتمدة = موجبة في التعلّم والمحجوز و30 صفقة حيّة. مرشّحة = تنتظر الصفقات الحيّة. ميتة = سالبة في التعلّم والمحجوز.</div>
</body></html>"""
    os.makedirs(RUNTIME, exist_ok=True)
    open(VIEW + ".tmp", "w", encoding="utf-8").write(page)
    os.replace(VIEW + ".tmp", VIEW)
