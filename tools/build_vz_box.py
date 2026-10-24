"""Volume Zones · مربّع: the user's v38 indicator (overlay, untouched) + the window drawn INSIDE a blue box at the bottom
of the price pane (picture-in-picture in price space), not a separate pane."""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
base = open(os.path.join(HERE, "base_v38.pine"), encoding="utf-8").read()
merged = open(r"C:\project\options-agent\pine\volume_zones_full.pine", encoding="utf-8").read()
# computations of the window (RVOL, trend state, vol engine v2, heat, exits, trailing, day range, remaining) from the merged script
comp = merged[merged.index("// ═══════════════ RVOL حسب وقت اليوم"):merged.index("// ═══════════════ النافذة الكاملة: الشموع والأدوات")]
inputs = '''
// ═══════════════ مدخلات المربّع الأزرق (نافذة الأدوات أسفل الشارت) ═══════════════
G_F = "المربّع الأزرق أسفل الشارت"
pBoxOn  = input.bool(true, "إظهار المربّع الأزرق", tooltip="مربّع في أسفل نافذة الشارت نفسها، فيه آخر N شمعة مصغّرة مع المروحة الموسمية والسلّم ومدى اليوم والمتبقّي حتى الإغلاق والوقف المتحرّك وأسهم الخروج، وتحتها شريطا الحرارة والانضغاط. يُرسم على مقياس السعر تحت أدنى سعر معروض، ويضاف هامش أسفل الشارت تلقائيًّا", group=G_F)
pWin    = input.int(50, "عدد الشموع داخل المربّع", minval=20, maxval=200, group=G_F)
pBoxH   = input.float(1.5, "ارتفاع المربّع (% من السعر)", minval=0.3, maxval=10, step=0.1, tooltip="نسبة من السعر: 1.5% على سهم بـ524 = نحو 8 نقاط. ثابتة مهما كان الفريم، فتناسب المساحة الفارغة أسفل الشارت. المربّع يجلس تحت الشموع وتحت أيّ مستوى قريب منها؛ المستويات البعيدة تُتجاهل", group=G_F)
pBoxGap = input.float(0.25, "المسافة تحت الشموع (% من السعر)", minval=0, maxval=5, step=0.05, group=G_F)
pBoxAhead = input.int(30, "مساحة المروحة يمين المربّع (شموع)", minval=24, maxval=120, group=G_F)
pFan    = input.bool(true, "المروحة الموسمية ±1σ و±2σ", group=G_F)
pLadder = input.bool(true, "سلّم الوقف والهدف", group=G_F)
pDay    = input.bool(true, "خطّا مدى اليوم", group=G_F)
pRem    = input.bool(true, "المتبقّي حتى الإغلاق (5 دقائق)", group=G_F)
pTrail  = input.bool(true, "وقف متحرّك للاتجاه الحالي", group=G_F)
pExits  = input.bool(true, "أسهم الخروج من النطاق ▲▼", group=G_F)
pStrips = input.bool(true, "شريطا الحرارة والانضغاط", group=G_F)
pBox    = input.bool(true, "مربّع «الحالة الآن»", group=G_F)
pCompact = input.bool(true, "وضع مضغوط", group=G_F)
pBoxPos = input.string("أسفل اليمين", "موقع مربّع الحالة", options=["أسفل اليمين", "أسفل اليسار", "وسط اليمين", "أعلى اليمين"], group=G_F)
G_C = "ألوان المربّع الأزرق"
cWinB = input.color(#1e88e5, "إطار المربّع", inline="pc0", group=G_C)
cWinF = input.color(#0d1b2a, "خلفيته", inline="pc0", group=G_C)
cUp   = input.color(#26a69a, "صعود", inline="pc", group=G_C)
cNorm = color.new(#5d606b, 0)
cDn   = input.color(#ef5350, "هبوط", inline="pc", group=G_C)
cHot  = input.color(#ffd600, "عالٍ جدًا", inline="pc", group=G_C)
cMove = input.color(#29b6f6, "المروحة", inline="pc2", group=G_C)
cSqz  = input.color(#ab47bc, "الانضغاط", inline="pc2", group=G_C)
cDay  = input.color(#b388ff, "مدى اليوم", inline="pc2", group=G_C)
cTgt  = input.color(#c6ff00, "الأهداف", inline="pc3", group=G_C)
cTrail = input.color(#ff7043, "الوقف المتحرّك", inline="pc3", group=G_C)
'''
draw = r'''
// ═══════════════ المربّع الأزرق: النافذة مرسومة داخل نافذة الشارت نفسها ═══════════════
// price-space picture-in-picture: the last pWin candles and the tools are rescaled into a box that sits pBoxGap ATR
// under the lowest low of the window and is pBoxH ATR tall. A faint plot at the box floor makes the chart's auto-scale
// include it (boxes alone do not stretch the scale).
float wLo = ta.lowest(l_, pWin)
float wHi = ta.highest(h_, pWin)
float wSpan = math.max(wHi - wLo, 4 * atrV)
// only levels NEAR the candles (within 1.5 spans below the lowest low) push the box down; far ones are ignored
float nearMin = wLo
for x in lvNow
    if not na(x) and x < wLo and x > wLo - 0.01 * c_
        nearMin := math.min(nearMin, x)
for x in gpK
    if x < wLo and x > wLo - 0.01 * c_
        nearMin := math.min(nearMin, x)
for i = 0 to 7
    float gxx = array.get(gxV, i)
    if not na(gxx) and gxx < wLo and gxx > wLo - 0.01 * c_
        nearMin := math.min(nearMin, gxx)
if not na(pdVAL) and pdVAL < wLo and pdVAL > wLo - 0.01 * c_
    nearMin := math.min(nearMin, pdVAL)
if not na(val) and val < wLo and val > wLo - 0.01 * c_
    nearMin := math.min(nearMin, val)
float boxH = pBoxH / 100 * c_
float boxTop = nearMin - pBoxGap / 100 * c_
float boxBot = boxTop - boxH
plot(pBoxOn ? boxBot - 0.03 * boxH : na, "قاع المربّع الأزرق", color=color.new(cWinB, 85), linewidth=1)
var box winBox = na
var line[] wLines = array.new_line()
var box[] wBoxes = array.new_box()
var label[] wLabels = array.new_label()
var float[] wTrail = array.new_float()   // trailing stop of the last pWin bars (na when none)
var bool[] wHit = array.new_bool()
var float[] wHeat = array.new_float()
var bool[] wSqz = array.new_bool()
var bool[] wExU = array.new_bool()
var bool[] wExD = array.new_bool()
if barstate.isconfirmed
    array.push(wTrail, veTrailStop), array.push(wHit, veHit), array.push(wHeat, vePct), array.push(wSqz, veSqzOn), array.push(wExU, exitUp), array.push(wExD, exitDn)
    if array.size(wTrail) > pWin
        array.shift(wTrail), array.shift(wHit), array.shift(wHeat), array.shift(wSqz), array.shift(wExU), array.shift(wExD)
int exDnN = math.round(math.sum(exitDn ? 1.0 : 0.0, 12))
int exUpN = math.round(math.sum(exitUp ? 1.0 : 0.0, 12))
if pBoxOn and barstate.islast and not na(veMove) and not na(atrV) and atrV > 0
    for ln in wLines
        line.delete(ln)
    for bx in wBoxes
        box.delete(bx)
    for lb in wLabels
        label.delete(lb)
    array.clear(wLines), array.clear(wBoxes), array.clear(wLabels)
    box.delete(winBox)
    // the price range mapped into the box: the window's candles, the fan, the day lines, the trailing stop
    float pMin = math.min(wLo, c_ - 2 * veMove)
    float pMax = math.max(wHi, c_ + 2 * veMove)
    if pDay and not na(veDayHi)
        pMin := math.min(pMin, veDayLo), pMax := math.max(pMax, veDayHi)
    float span = math.max(pMax - pMin, syminfo.mintick)
    // leave room under the candles for the two strips (18% of the box) and a little air on top
    float yb = boxBot + 0.20 * boxH
    float yt = boxTop - 0.03 * boxH
    float kk = (yt - yb) / span
    int x0 = bar_index - pWin + 1
    int x1 = bar_index + pBoxAhead
    winBox := box.new(x0 - 2, boxTop, x1 + 2, boxBot, border_color=cWinB, border_width=2, bgcolor=color.new(cWinF, 20), text="النافذة: آخر " + str.tostring(pWin) + " شمعة", text_color=color.new(cWinB, 30), text_size=size.tiny, text_halign=text.align_left, text_valign=text.align_top)
    // mini candles
    for j = pWin - 1 to 0
        float yo = yb + (o_[j] - pMin) * kk
        float yc = yb + (c_[j] - pMin) * kk
        float yh = yb + (h_[j] - pMin) * kk
        float yl = yb + (l_[j] - pMin) * kk
        color cc = c_[j] >= o_[j] ? cUp : cDn
        array.push(wLines, line.new(bar_index - j, yl, bar_index - j, yh, color=cc, width=1))
        array.push(wBoxes, box.new(bar_index - j, math.max(yo, yc), bar_index - j, math.min(yo, yc), border_color=cc, bgcolor=cc, border_width=2))
    // exits
    if pExits
        int nE = array.size(wExU)
        for j = 0 to nE - 1
            int xb = bar_index - (nE - 1 - j)
            if array.get(wExD, j)
                array.push(wLabels, label.new(xb, yb + (l_[nE - 1 - j] - pMin) * kk, "▼", style=label.style_label_up, color=color.new(cDn, 100), textcolor=cDn, size=size.tiny))
            if array.get(wExU, j)
                array.push(wLabels, label.new(xb, yb + (h_[nE - 1 - j] - pMin) * kk, "▲", style=label.style_label_down, color=color.new(cUp, 100), textcolor=cUp, size=size.tiny))
    // trailing stop as segments between consecutive bars
    if pTrail
        int nT = array.size(wTrail)
        for j = 1 to nT - 1
            float a = array.get(wTrail, j - 1)
            float b = array.get(wTrail, j)
            if not na(a) and not na(b)
                color tc = array.get(wHit, j) ? color.new(#78909c, 20) : cTrail
                array.push(wLines, line.new(bar_index - (nT - j), yb + (a - pMin) * kk, bar_index - (nT - 1 - j), yb + (b - pMin) * kk, color=tc, width=2, style=array.get(wHit, j) ? line.style_dotted : line.style_solid))
        if not na(veTrailStop)
            array.push(wLabels, label.new(bar_index + 1, yb + (veTrailStop - pMin) * kk, "وقف متحرّك" + (veHit ? " · ضُرب" : ""), style=label.style_label_left, color=color.new(cTrail, 100), textcolor=veHit ? #78909c : cTrail, size=size.tiny))
    // day lines
    if pDay and not na(veDayHi)
        float yDH = yb + (veDayHi - pMin) * kk
        float yDL = yb + (veDayLo - pMin) * kk
        array.push(wLines, line.new(x0, yDH, x1, yDH, color=color.new(cDay, 20), style=line.style_dashed, width=1))
        array.push(wLines, line.new(x0, yDL, x1, yDL, color=color.new(cDay, 20), style=line.style_dashed, width=1))
        array.push(wLabels, label.new(x0, yDH, "أعلى اليوم المتوقّع", style=label.style_label_lower_right, color=color.new(cDay, 100), textcolor=cDay, size=size.tiny))
        array.push(wLabels, label.new(x0, yDL, "أدنى اليوم المتوقّع", style=label.style_label_upper_right, color=color.new(cDay, 100), textcolor=cDay, size=size.tiny))
    // fan + ladder + remaining
    float yC = yb + (c_ - pMin) * kk
    int xe = bar_index + veK
    if pFan
        array.push(wBoxes, box.new(bar_index, yb + (c_ + 2 * veMove - pMin) * kk, xe, yb + (c_ - 2 * veMove - pMin) * kk, border_color=color.new(cMove, 80), bgcolor=color.new(cMove, 88)))
        array.push(wBoxes, box.new(bar_index, yb + (c_ + veMove - pMin) * kk, xe, yb + (c_ - veMove - pMin) * kk, border_color=color.new(cMove, 70), bgcolor=color.new(cMove, 78)))
        for m = 1 to 2
            array.push(wLines, line.new(bar_index, yC, xe, yb + (c_ + m * veMove - pMin) * kk, color=color.new(cMove, m == 1 ? 10 : 50), width=m == 1 ? 2 : 1, style=line.style_dashed))
            array.push(wLines, line.new(bar_index, yC, xe, yb + (c_ - m * veMove - pMin) * kk, color=color.new(cMove, m == 1 ? 10 : 50), width=m == 1 ? 2 : 1, style=line.style_dashed))
            array.push(wLabels, label.new(xe, yb + (c_ + m * veMove - pMin) * kk, "+" + str.tostring(m) + "σ", style=label.style_label_left, color=color.new(cMove, 100), textcolor=cMove, size=size.tiny))
            array.push(wLabels, label.new(xe, yb + (c_ - m * veMove - pMin) * kk, "−" + str.tostring(m) + "σ", style=label.style_label_left, color=color.new(cMove, 100), textcolor=cMove, size=size.tiny))
        array.push(wLines, line.new(bar_index, yC, xe + 3, yC, color=color.new(cDn, 30), width=1, style=line.style_dotted))
        array.push(wLabels, label.new(xe + 3, yC, str.tostring(c_, format.mintick), style=label.style_label_left, color=cDn, textcolor=color.white, size=size.tiny))
    if pLadder
        float y1 = yb + (c_ + veMove - pMin) * kk
        float y2 = yb + (c_ + 2 * veMove - pMin) * kk
        float ys = yb + (c_ - 0.75 * veMove - pMin) * kk
        array.push(wLines, line.new(bar_index, y1, xe, y1, color=cTgt, width=2, style=line.style_dashed))
        array.push(wLines, line.new(bar_index, y2, xe, y2, color=cTgt, width=2, style=line.style_dashed))
        array.push(wLines, line.new(bar_index, ys, xe, ys, color=cDn, width=2))
        array.push(wLabels, label.new(xe + 4, y1, "هدف 1× · " + veP1 + (veP1 != "25%" ? " (قوة الاتجاه)" : ""), style=label.style_label_left, color=color.new(cTgt, 100), textcolor=cTgt, size=size.tiny))
        array.push(wLabels, label.new(xe + 4, y2, "هدف 2× · " + veP2, style=label.style_label_left, color=color.new(cTgt, 100), textcolor=cTgt, size=size.tiny))
        array.push(wLabels, label.new(xe + 4, ys, "وقف 0.75× · يُضرب 5%", style=label.style_label_left, color=color.new(cDn, 100), textcolor=cDn, size=size.tiny))
    if pRem and not na(veRemMove) and slotNow >= 0
        int xend = math.min(x1, bar_index + (nSlots - 1 - slotNow))
        float yr1 = yb + (c_ + veRemMove - pMin) * kk
        float yr2 = yb + (c_ - veRemMove - pMin) * kk
        array.push(wLines, line.new(bar_index, yr1, xend, yr1, color=color.new(cMove, 30), width=1, style=line.style_dotted))
        array.push(wLines, line.new(bar_index, yr2, xend, yr2, color=color.new(cMove, 30), width=1, style=line.style_dotted))
        array.push(wLabels, label.new(xend, yr2, "حتى الإغلاق ±" + str.tostring(veRemMove, format.mintick), style=label.style_label_up, color=color.new(cMove, 100), textcolor=color.new(cMove, 10), size=size.tiny))
    // strips under the candles, inside the box
    if pStrips
        float sTop = boxBot + 0.17 * boxH
        float sMid = boxBot + 0.10 * boxH
        float sBot = boxBot + 0.02 * boxH
        int nH = array.size(wHeat)
        for j = 0 to nH - 1
            int xb = bar_index - (nH - 1 - j)
            float hp = array.get(wHeat, j)
            bool sq = array.get(wSqz, j)
            color hc = sq ? cSqz : na(hp) ? cNorm : hp < 50 ? color.from_gradient(hp, 0, 50, #1a1a2e, #1e88e5) : color.from_gradient(hp, 50, 100, #1e88e5, #ffd600)
            array.push(wBoxes, box.new(xb, sTop, xb + 1, sMid + 0.01 * boxH, border_color=color.new(hc, 100), bgcolor=hc))
            array.push(wBoxes, box.new(xb, sMid - 0.01 * boxH, xb + 1, sBot, border_color=color.new(cSqz, 100), bgcolor=sq ? cSqz : color.new(#2a2e39, 0)))
        array.push(wLabels, label.new(bar_index + 1, (sTop + sMid) / 2, "حرارة التذبذب حسب وقت اليوم" + (na(vePct) ? "" : ": الآن " + str.tostring(vePct, "#") + "%") + (veAccel ? " ↑ تتسارع" : ""), style=label.style_label_left, color=color.new(cHot, 100), textcolor=cHot, size=size.tiny))
        array.push(wLabels, label.new(bar_index + 1, (sMid + sBot) / 2, "الانضغاط" + (veSqzOn ? ": نعم منذ " + str.tostring(veSqzBars) + " شمعة · اصبر" : " (بنفسجي عند حدوثه)"), style=label.style_label_left, color=color.new(cSqz, 100), textcolor=cSqz, size=size.tiny))
// the state box (compact, 6 rows)
bPos = pBoxPos == "أسفل اليمين" ? position.bottom_right : pBoxPos == "أسفل اليسار" ? position.bottom_left : pBoxPos == "وسط اليمين" ? position.middle_right : position.top_right
var table sb = table.new(bPos, 2, 6, bgcolor=color.new(#1e222d, 8), border_color=color.new(#3a3f4b, 0), border_width=1, frame_color=color.new(#1e88e5, 0), frame_width=1)
if pBoxOn and pBox and barstate.islast
    string dirW = tvState > 0 ? "صاعد" : tvState < 0 ? "هابط" : "لا اتجاه"
    color dirC = tvState > 0 ? cUp : tvState < 0 ? cDn : #9598a1
    bool hot = not na(vePct) and vePct >= 80
    string verdict = tvState != 0 and veHit ? "الاتجاه " + dirW + " لكنّ وقفه المتحرّك ضُرب: لا صفقة جديدة حتى حالة جديدة" + (hot ? "؛ اليوم ساخن فصغّر الحجم" : "") : tvState != 0 ? "الاتجاه " + dirW + ": الصفقات معه فقط، الوقف المتحرّك " + str.tostring(veTrailStop, format.mintick) + "، هدف 1× " + veP1 + (hot ? "؛ اليوم ساخن فصغّر الحجم" : "") : "لا اتجاه: استعمل الوقف والهدف فقط" + (hot ? "؛ اليوم ساخن" : "")
    if veSqzOn
        verdict += "؛ انضغاط: اصبر"
    string sTrail = na(veTrailStop) ? "-" : str.tostring(veTrailStop, format.mintick) + (veHit ? " ضُرب" : "")
    size_t tsz = pCompact ? size.tiny : size.small
    table.cell(sb, 1, 0, "الآن " + str.format_time(time, "HH:mm", syminfo.timezone) + " · " + dirW, text_color=dirC, text_size=pCompact ? size.small : size.normal, text_halign=text.align_right)
    table.cell(sb, 0, 0, "", text_size=tsz)
    table.merge_cells(sb, 0, 0, 1, 0)
    table.cell(sb, 1, 1, "الحركة", text_color=#9598a1, text_size=tsz, text_halign=text.align_right)
    table.cell(sb, 0, 1, "±" + str.tostring(veMove, format.mintick) + " (" + str.tostring(veMovePct, "#.00") + "%)" + (na(veRemMove) ? "" : " · حتى الإغلاق ±" + str.tostring(veRemMove, format.mintick)), text_color=cMove, text_size=tsz, text_halign=text.align_left)
    table.cell(sb, 1, 2, "هدف / وقف", text_color=#9598a1, text_size=tsz, text_halign=text.align_right)
    table.cell(sb, 0, 2, veP1 + " / " + veP2 + " · وقف " + str.tostring(tvState < 0 ? c_ + 0.75 * veMove : c_ - 0.75 * veMove, format.mintick), text_color=cTgt, text_size=tsz, text_halign=text.align_left)
    table.cell(sb, 1, 3, "متحرّك", text_color=#9598a1, text_size=tsz, text_halign=text.align_right)
    table.cell(sb, 0, 3, sTrail + (na(veFuel) ? "" : " · مدى اليوم " + str.tostring(100 * veFuel, "#") + "%"), text_color=veHit ? #78909c : cTrail, text_size=tsz, text_halign=text.align_left)
    table.cell(sb, 1, 4, "حرارة / انضغاط", text_color=#9598a1, text_size=tsz, text_halign=text.align_right)
    table.cell(sb, 0, 4, (na(vePct) ? "-" : str.tostring(vePct, "#") + "%" + (vePct >= 80 ? " ساخن" : "") + (veAccel ? " ↑" : "")) + " · " + (veSqzOn ? "انضغاط منذ " + str.tostring(veSqzBars) : "لا انضغاط") + " · خروج " + str.tostring(exDnN) + "▼ " + str.tostring(exUpN) + "▲", text_color=cHot, text_size=tsz, text_halign=text.align_left)
    table.cell(sb, 0, 5, verdict, text_color=cHot, text_size=tsz, text_halign=text.align_right)
    table.merge_cells(sb, 0, 5, 1, 5)
alertcondition(veSqzOn and not veSqzOn[1], "انضغاط", "دخل السعر في انضغاط (ATR14/ATR100 تحت عُشره المعتاد)")
alertcondition(not na(rvol) and rvol >= 2, "فوليوم عالٍ جدًا", "RVOL ≥ 2× لنفس الدقيقة")
alertcondition(veHit and not veHit[1], "ضُرب الوقف المتحرّك", "الإغلاق عبر الوقف المتحرّك للاتجاه الحالي")
'''
draw = draw.replace("size_t tsz = ", "tsz = ")
# the base keeps its name but gets a new title; heat-map budget leaves room for the window's boxes (3 per candle incl. strips + fan)
base = base.replace('indicator("Volume Zones", overlay=true,', 'indicator("Volume Zones · مربّع", "VZ مربّع", overlay=true,')
base = base.replace("while array.size(heatBoxes) > math.max(50, 470 - 2 * rows)", "while array.size(heatBoxes) > math.max(50, 470 - 2 * rows - 3 * pWin - 10)")
ind_line = [ln for ln in base.split("\n") if ln.startswith('indicator("Volume Zones · مربّع"')][0]
base = base.replace(ind_line + "\n", ind_line + "\n" + inputs, 1)
comp = comp.replace("newSess and not na(veS2)", "newSess and not na(veS2)")
out = base.rstrip("\n") + "\n\n// ═══════════════ حسابات النافذة (نموذج الاتجاه، محرّك التذبذب v2، الحرارة، الخروج، الوقف المتحرّك، مدى اليوم) ═══════════════\n" + comp.rstrip("\n") + "\n" + draw
open(r"C:\project\options-agent\pine\volume_zones_box.pine", "w", encoding="utf-8").write(out)
print("lines", len(out.splitlines()))
