"""Explainer: the three volume profiles inside the Pine indicator, each drawn alone (synthetic prices)."""
import pathlib, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
ROOT = pathlib.Path(__file__).resolve().parent.parent
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
rng = np.random.default_rng(7); n = 200; p = 100.0; c = []
for i in range(n):
    p += rng.normal(0.25 if 70 < i < 95 else 0, .6); p = np.clip(p, 92, 112) if i < 70 else p; c.append(p)
c = np.array(c); o = np.r_[c[0], c[:-1]]; h = np.maximum(o, c) + rng.uniform(.1, .6, n); l = np.minimum(o, c) - rng.uniform(.1, .6, n)
def candles(ax, a=0, b=n):
    for i in range(a, b):
        col = "#26a69a" if c[i] >= o[i] else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, lw=.6); ax.add_patch(Rectangle((i - .3, min(o[i], c[i])), .6, max(abs(c[i] - o[i]), .02), color=col))
def style(ax, t, sub):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=7); [s.set_color(GR) for s in ax.spines.values()]
    ax.set_title(t, color=TX, fontsize=14, loc="right", weight="bold"); ax.text(.99, .03, sub, color=TX, fontsize=10.5, ha="right", va="bottom", transform=ax.transAxes, linespacing=1.6, bbox=dict(fc="#1e222d", ec=GR, boxstyle="round,pad=.5"), zorder=10)
fig, axs = plt.subplots(3, 1, figsize=(16, 19), facecolor=BG)
# 1 rolling
ax = axs[0]; candles(ax); style(ax, "١) البروفايل المتحرك: آخر 120 شمعة من فريم الشارت، 40 صف",
 "يتحرك مع كل شمعة ويتغير مع تغيير الفريم\nيرسم: POC أحمر و VAH / VAL سماوي، الخريطة الحرارية، أقوى 3 مناطق، والبروفايل الأزرق والذهبي على اليمين\nتعتمد عليه إشارات: HUNT، عودة، انعكاس؟، ارتداد")
poc = np.array([c[max(0, i - 29):i + 1].mean() for i in range(n)]); ax.step(range(120, n), poc[120:], color="#ff4d4d", lw=1.5); ax.step(range(120, n), poc[120:] + 3, color="#26c6da", lw=1.2); ax.step(range(120, n), poc[120:] - 3, color="#26c6da", lw=1.2)
for y, t in ((poc[-1], "POC"), (poc[-1] + 3, "VAH"), (poc[-1] - 3, "VAL")): ax.text(n + 1, y, t, color="#ff4d4d" if t == "POC" else "#26c6da", fontsize=10, va="center", weight="bold")
ax.add_patch(Rectangle((n - 120, l[-120:].min()), 120, h[-120:].max() - l[-120:].min(), fill=False, ec=MUT, ls=":", lw=1)); ax.text(n - 118, h[-120:].max() + .3, "نافذة آخر 120 شمعة", color=MUT, fontsize=10)
bins = np.linspace(l[-120:].min(), h[-120:].max(), 41); hv, _ = np.histogram(c[-120:], bins, weights=np.ones(120)); hv = hv / hv.max() * 18
for k in range(40): ax.add_patch(Rectangle((n + 6, bins[k]), hv[k] * .55, bins[1] - bins[0], color="#2f7fd1")); ax.add_patch(Rectangle((n + 6 + hv[k] * .55, bins[k]), hv[k] * .45, bins[1] - bins[0], color="#c9a227"))
ax.set_xlim(-2, n + 28)
# 2 prior day
ax = axs[1]; style(ax, "٢) بروفايل اليوم السابق: جلسة أمس كاملة، 30 صف (على الفريمات اللحظية فقط)",
 "ثابت طوال اليوم ويتجدد مع بداية كل جلسة\nيرسم: VAH / VAL أزرق و POC أحمر لجلسة أمس\nتعتمد عليه إشارة: تنبيه اتجاه ↑ ↓ (إغلاقان خارج منطقة قيمة الأمس مع الترند)")
candles(ax, 0, n)
for k in range(0, n, 40): ax.axvline(k - .5, color=GR, lw=1)
for k in range(40, n, 40):
    seg = c[k - 40:k]; pp, va, vb = np.median(seg), np.percentile(seg, 85), np.percentile(seg, 15)
    ax.hlines([va, vb], k, k + 40, color="#5c8dff", lw=1.5); ax.hlines(pp, k, k + 40, color="#ff4d4d", lw=1.5)
ax.text(161, va + .4, "VAH أمس", color="#5c8dff", fontsize=10); ax.text(161, vb - 1, "VAL أمس", color="#5c8dff", fontsize=10); ax.text(161, pp + .3, "POC أمس", color="#ff4d4d", fontsize=10)
ax.set_xlim(-2, n + 10)
# 3 whale
ax = axs[2]; candles(ax); style(ax, "٣) بروفايل الحيتان: كل منطقة عرضية على الشموع اليومية، 200 صف من بيانات الساعة",
 "مخفي، لا يُرسم البروفايل نفسه. ثابت على كل الفريمات\nيرسم: مستطيل المنطقة، POC أحمر عريض، VAH / VAL برتقالي، وأعمدة طويلة بنفسجية\nتعتمد عليه إشارة: حوت ↑ ↓ (تحت الاختبار)")
for a, b, live in ((0, 70, False), (95, n, True)):
    lo, hi = l[a:b].min(), h[a:b].max(); md = np.median(c[a:b])
    ax.add_patch(Rectangle((a, lo), b - a, hi - lo, fc="#ffb02012", ec="#ffb020", ls="--", lw=1.2)); ax.text(a + 1, hi + .3, "منطقة قيد التكوين" if live else "منطقة عرضية مكتملة", color="#ffb020", fontsize=10)
    for y in (md + 4.5, md - 3.5): ax.hlines(y, a, n + 10, color="#9b5cff", lw=1)
    ax.hlines(md, a, n + 10, color="#ff3b3b", lw=3); ax.hlines([md + 2.5, md - 2.5], a, n + 10, color="#ffb020", lw=2)
    for y, t, cl in ((md, "POC", "#ff3b3b"), (md + 2.5, "VAH", "#ffb020"), (md - 2.5, "VAL", "#ffb020")): ax.text(a - 1, y, t, color=cl, fontsize=10, ha="right", va="center", weight="bold")
ax.set_xlim(-12, n + 12)
fig.tight_layout(h_pad=3); fig.savefig(ROOT / "reports/styles/S_three_profiles.png", dpi=90, facecolor=BG)
