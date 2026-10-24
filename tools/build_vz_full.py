"""Merge: the user's Volume Zones (repo v38 = the pasted script) + the lower window of pane v11, as ONE script.
The script becomes overlay=false (its pane = the lower window) and every main-chart drawing gets force_overlay=true."""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
base = open(os.path.join(HERE, "base_v38.pine"), encoding="utf-8").read()
pane = open(r"C:\project\options-agent\pine\volume_zones_pane.pine", encoding="utf-8").read()

# ---------- 1. the base: overlay=false + force_overlay on every main-chart drawing ----------
base = base.replace('indicator("Volume Zones", overlay=true, max_bars_back=5000, max_lines_count=500, max_boxes_count=500, max_labels_count=200)',
                    'indicator("Volume Zones · كامل", "VZ كامل", overlay=false, format=format.price, precision=2, max_bars_back=5000, max_lines_count=500, max_boxes_count=500, max_labels_count=200)')
FUNCS = ("plot(", "plotshape(", "bgcolor(", "line.new(", "box.new(", "label.new(", "table.new(")
def add_force(line):
    out = line; pos = 0
    while True:
        hit = None
        for f in FUNCS:
            i = out.find(f, pos)
            if i >= 0 and (hit is None or i < hit[0]):
                # must be a call, not part of another identifier (e.g. "plotcandle(" or "subplot(")
                prev = out[i - 1] if i > 0 else " "
                if prev.isalnum() or prev == "_" or prev == ".":
                    if not (f.startswith("line.") or f.startswith("box.") or f.startswith("label.") or f.startswith("table.")) or prev != ".":
                        if prev.isalnum() or prev == "_":
                            continue
                hit = (i, f)
        if hit is None:
            return out
        i, f = hit; j = i + len(f); depth = 1; k = j; in_str = False
        while k < len(out) and depth > 0:
            ch = out[k]
            if ch == '"' and out[k - 1] != "\\":
                in_str = not in_str
            elif not in_str:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            k += 1
        close = k - 1
        inner = out[j:close].strip()
        ins = (", " if inner else "") + "force_overlay=true"
        out = out[:close] + ins + out[close:]
        pos = close + len(ins) + 1
lines = base.split("\n"); n_force = 0; out_lines = []
for ln in lines:
    s = ln.lstrip()
    if s.startswith("//"):
        out_lines.append(ln); continue
    new = add_force(ln)
    if new != ln:
        n_force += new.count("force_overlay=true") - ln.count("force_overlay=true")
    out_lines.append(new)
base = "\n".join(out_lines)
# the heat map keeps room for the two strips of the lower window
base = base.replace("while array.size(heatBoxes) > math.max(50, 470 - 2 * rows)", "while array.size(heatBoxes) > math.max(50, 470 - 2 * rows - 2 * pWin - 10)")
assert "2 * pWin - 10" in base

# ---------- 2. the lower window from pane v11 ----------
def cut(s, a, b):
    i = s.index(a); j = s.index(b, i); return s[:i] + s[j:]
p = pane
# inputs: keep G_F + colours; drop pMode, G_O block
p = p[p.index('G_F = "النافذة الكاملة"'):]
p = cut(p, 'G_O = "الأوضاع الأخرى"', 'G_C = "الألوان"')
# drop the real-candles block (the base has o_/h_/l_/c_/trR/atrV) and the pane's newSess
p = cut(p, "// ═══════════════ الشموع الحقيقية", "// ═══════════════ RVOL حسب وقت اليوم")
# drop the old drawing modes: from "// ═══ الرسم" to the full-window header
p = cut(p, "// ═══════════════ الرسم ═══════════════", "// ═══════════════ النافذة الكاملة: الشموع والأدوات")
# drop the numbers table and the old alerts (re-added below)
p = p[:p.index("// numbers table")]
# renames against the base
p = re.sub(r"(?<![A-Za-z_])sH(?![A-Za-z_0-9])", "stripH", p)
assert re.search(r"(?<![A-Za-z_])sH(?![A-Za-z_0-9])", p) is None, "sH left"
p = p.replace("int nDn = math.round", "int exDnN = math.round").replace("int nUp = math.round", "int exUpN = math.round")
p = re.sub(r"\bnDn\b", "exDnN", p); p = re.sub(r"\bnUp\b", "exUpN", p)
p = p.replace("bool mFull = ", "bool mFull_unused = ")
p = "bool mFull = true\n" + p
# the pane used its own newSess (change of day); the base defines newSess = timeframe.isintraday and dayChg
p = p.replace("timeframe.isintraday and newSess and not na(veS2)", "newSess and not na(veS2)")
p = p.replace("// heat: rank against the same slot of the previous 20 sessions", "// heat: rank against the same slot of the previous 20 sessions (same-slot rank, reports/vol_engine_dev H6.1)")
# everything that referenced cNorm (colour input dropped with G_O): keep a local constant
p = p.replace('cUp   = input.color(#26a69a, "صعود", inline="pc", group=G_C)', 'cUp   = input.color(#26a69a, "صعود", inline="pc", group=G_C)\ncNorm = color.new(#5d606b, 0)')
p = p.replace('cNorm = input.color(#5d606b, "عادي", inline="pc", group=G_C)\n', '')
# the plot titles must not collide with the base's plot titles: prefix the lower-window ones
p = p.replace('"وقف متحرّك 0.75×", color=veHit', '"النافذة: وقف متحرّك 0.75×", color=veHit')
alerts = '''alertcondition(veSqzOn and not veSqzOn[1], "انضغاط", "دخل السعر في انضغاط (ATR14/ATR100 تحت عُشره المعتاد)")
alertcondition(not na(rvol) and rvol >= 2, "فوليوم عالٍ جدًا", "RVOL ≥ 2× لنفس الدقيقة")
alertcondition(veHit and not veHit[1], "ضُرب الوقف المتحرّك", "الإغلاق عبر الوقف المتحرّك للاتجاه الحالي")
'''
# the lower-window inputs go right after the base's indicator() line (pWin is used by the heat-map budget above)
inputs_blk = p[:p.index("// ═══════════════ RVOL حسب وقت اليوم")]
p = p[p.index("// ═══════════════ RVOL حسب وقت اليوم"):]
ind_line = [ln for ln in base.split("\n") if ln.startswith('indicator("Volume Zones · كامل"')][0]
base = base.replace(ind_line + "\n", ind_line + "\n\n// ═══════════════ مدخلات النافذة السفلية ═══════════════\n" + inputs_blk.rstrip("\n") + "\n", 1)
merged = base.rstrip("\n") + '''

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
// النافذة السفلية (مدموجة من «Volume Zones · لوحة» الإصدار 11، 2026-10-25): نفس الشموع + المروحة الموسمية
// والسلّم بنسب الاتجاه ومدى اليوم والمتبقّي حتى الإغلاق والوقف المتحرّك وأسهم الخروج، وتحت الرسم شريطا الحرارة
// والانضغاط، ومربّع «الحالة الآن». ثابتة على آخر N شمعة ومعزولة بمقياسها. كلّ ما فوقها (المؤشّر الأصلي) يُرسم على
// الشموع بـ force_overlay. القياسات: reports/vol_engine و reports/vol_engine_dev.
// ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
''' + p.rstrip("\n") + "\n" + alerts
open(r"C:\project\options-agent\pine\volume_zones_full.pine", "w", encoding="utf-8").write(merged)
print("force_overlay added:", n_force, "| lines:", len(merged.splitlines()))
