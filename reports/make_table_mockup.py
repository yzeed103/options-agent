"""Mockup: current status table explained + proposed Arabic status panel."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

def ar(t): return t  # matplotlib >= 3.10 shapes Arabic and applies bidi itself
BG, PANEL, GR, TX, MUT = "#131722", "#1e222d", "#2a2e39", "#d1d4dc", "#8a8f9c"
G, R, Y, O, C, P = "#00e676", "#ff5252", "#f0c419", "#ff9800", "#00bcd4", "#b388ff"
plt.rcParams["font.family"] = "DejaVu Sans"
fig = plt.figure(figsize=(17, 10), facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 170); ax.set_ylim(0, 100); ax.axis("off")

def box(x, y, w, h, fc=PANEL, ec=GR, lw=1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3", fc=fc, ec=ec, lw=lw))

# ---------------- LEFT: current table explained ----------------
ax.text(40, 95, ar("الجدول الحالي: ماذا يعني كل سطر"), color=TX, fontsize=16, ha="center", weight="bold")
rows = [("Trend", "RANGE", MUT, "الاتجاه: عرضي، لا يوجد ترند واضح"),
        ("ADX", "14", TX, "قوة الترند: أقل من 20 تعني ترندا ضعيفا"),
        ("Volume", "4.47x STRONG", G, "فوليوم الشمعة الحالية 4.5 أضعاف المتوسط"),
        ("In zone", "HVN (slow)", TX, "السعر داخل منطقة تداول كثيف، الحركة غالبا بطيئة"),
        ("Zone above", "7726.85", O, "أقرب مقاومة من مناطق الفوليوم"),
        ("Zone below", "7700.28", C, "أقرب دعم من مناطق الفوليوم"),
        ("Signal", "WEAK POOL forming", R, "تجمع فوليوم ضعيف يتكون، أي انتظار كسر")]
box(3, 22, 27, 64)
for i, (a, b, c, ex) in enumerate(rows):
    y = 80 - i * 8.6
    ax.text(5, y, a, color=MUT, fontsize=11, va="center")
    ax.text(29, y, b, color=c, fontsize=10.5, va="center", ha="right", weight="bold")
    ax.annotate("", xy=(31, y), xytext=(35, y), arrowprops=dict(arrowstyle="->", color=GR, lw=1.2))
    ax.text(77, y, ar(ex), color=TX, fontsize=11.5, va="center", ha="right")
box(3, 4, 74, 13, fc="#2a1a1a", ec=R)
ax.text(75, 13.3, ar("مشكلة: الجدول يقول تجمع ضعيف، والفوليوم قوي جدا في نفس اللحظة"), color=R, fontsize=11.5, ha="right", weight="bold")
ax.text(75, 7.8, ar("الصحيح: الشمعة القوية داخل التجمع تنهيه أو تختبره، وسأصلح هذا في النسخة الجديدة"), color=TX, fontsize=11, ha="right")

# ---------------- RIGHT: proposed panel ----------------
X0, W = 92, 74
ax.text(X0 + W / 2, 95, ar("النموذج المقترح: لوحة حالة بالعربية"), color=TX, fontsize=16, ha="center", weight="bold")
box(X0, 4, W, 86)
ax.add_patch(Rectangle((X0 - .3, 83), W + .6, 7.3, color="#262b38"))
ax.text(X0 + W - 1.5, 86.6, ar("مناطق الفوليوم"), color=TX, fontsize=13, ha="right", va="center", weight="bold")
ax.text(X0 + 1.5, 86.6, "SPX · 15m · 7713.71", color=MUT, fontsize=11, va="center")

def bar(x, y, n, filled, col):
    for k in range(n):
        ax.add_patch(Rectangle((x + k * 2.1, y - 1.1), 1.7, 2.2, color=col if k < filled else "#3a3f4f"))

def row(y, label, value, col, sub=None, meter=None):
    ax.text(X0 + W - 1.5, y, ar(label), color=MUT, fontsize=11.5, ha="right", va="center")
    ax.text(X0 + W - 17, y, ar(value), color=col, fontsize=12, ha="right", va="center", weight="bold")
    if meter: bar(X0 + 2, y, 5, meter, col)
    if sub: ax.text(X0 + W - 17, y - 3.1, ar(sub), color=MUT, fontsize=9.5, ha="right", va="center")

row(78, "الاتجاه", "عرضي", MUT, "قوة الترند 14 من 100، ضعيفة", meter=1)
row(70, "الفوليوم", "قوي جدا", G, "4.5 أضعاف المتوسط، الشمعة الحالية", meter=5)
row(62, "موقع السعر", "داخل المنطقة 1", Y, "النطاق 7707.9 إلى 7726.9، يمثل 41% من التداول")
row(54, "أقرب مقاومة", "7726.85", O, "فوق السعر بـ 13.1 نقطة، 0.17%")
row(46, "أقرب دعم", "7700.28", C, "تحت السعر بـ 13.4 نقطة، 0.17%")
row(38, "آخر إشارة", "هبوط ← 7673.72", R, "قبل 112 شمعة، الهدف تحقق ✓")

# HUNT readiness checklist
ax.plot([X0 + 2, X0 + W - 2], [33.5, 33.5], color=GR, lw=1)
ax.text(X0 + W - 1.5, 30.5, ar("جاهزية إشارة HUNT"), color=TX, fontsize=12, ha="right", va="center", weight="bold")
ax.text(X0 + 1.5, 30.5, "2 / 4", color=Y, fontsize=12, va="center", weight="bold")
checks = [("تجمع فوليوم ضعيف", True), ("هدف أمام السعر", True), ("كسر بفوليوم قوي", False), ("ترند قوي", False)]
for i, (t, ok) in enumerate(checks):
    cx = X0 + W - 3 - (i % 2) * 36; cy = 25.5 - (i // 2) * 5
    ax.text(cx, cy, ar(t), color=TX if ok else MUT, fontsize=11, ha="right", va="center")
    ax.text(cx + 1.6, cy, "✓" if ok else "✗", color=G if ok else R, fontsize=13, ha="center", va="center", weight="bold")

# verdict
box(X0 + 1.5, 6, W - 3, 9.5, fc="#2b2610", ec=Y, lw=1.5)
ax.text(X0 + W - 3, 12.7, ar("الخلاصة: انتظار"), color=Y, fontsize=13, ha="right", va="center", weight="bold")
ax.text(X0 + W - 3, 8.6, ar("السعر داخل منطقة كثيفة بدون ترند. راقب إغلاقا فوق 7726.9 أو تحت 7700.3 بفوليوم قوي"),
        color=TX, fontsize=10.5, ha="right", va="center")
fig.savefig("/home/user/options-agent/reports/styles/I_status_panel.png", dpi=100, facecolor=BG)
print("ok")
