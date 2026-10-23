"""Analysis of the eyes-round events against reports/eyes/DEFINITIONS.md: tables, verdicts, HISTORY.md, pictures."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .data import ROOT
from .eyes import WALLS, boot_diff, boot_excess, boot_two_sets, group_of

OUT = os.path.join(ROOT, "reports", "eyes")
TINY_RATE, TINY_ATR = 0.02, 0.10
V_AR = {"holds": "ثابتة", "partly": "جزئيًا", "does not hold": "لا تثبت", "does not hold (opposite)": "لا تثبت (العكس)"}
TYPE_AR = {"cw": "جدار الكول CW", "pw": "جدار البوت PW", "cwoi": "جدار الفائدة CWOI", "pwoi": "جدار الفائدة PWOI",
           "flip": "الانقلاب FLIP", "dflip": "انقلاب الدلتا DFLIP", "pin": "التثبيت PIN", "whale_poc": "POC الحوت",
           "whale_vah": "VAH الحوت", "whale_val": "VAL الحوت", "whale_peak": "عمود الحوت"}


def _period(ev_days: list, dates: pd.Series) -> pd.Series:
    days = sorted(ev_days)
    cut = days[int(len(days) * 0.6)]
    return pd.Series(np.where(dates < cut, "define", "confirm"), index=dates.index), cut


def _real(r, sign):
    return (r["lo"] > 0) if sign > 0 else (r["hi"] < 0)


def _verdict(checks: list[dict], sign: int, tiny: float, group_signs: list[float] | None = None) -> tuple[str, str]:
    """checks: dicts with mean/diff, lo, hi, and a label. Rules of DEFINITIONS.md."""
    val = lambda r: r.get("mean", r.get("diff"))  # noqa: E731
    ok = [r for r in checks if np.isfinite(r["lo"]) and _real(r, sign)]
    opp = [r for r in checks if np.isfinite(r["lo"]) and _real(r, -sign)]
    big = all(abs(val(r)) >= tiny for r in ok)
    gok = group_signs is None or sum(1 for g in group_signs if np.isfinite(g) and np.sign(g) == sign) >= 2
    if checks and len(ok) == len(checks) and big and gok:
        return "holds", "حقيقي بالاتجاه المتوقّع في كل الفترات والفريمات"
    if ok:
        why = []
        if len(ok) < len(checks):
            why.append("حقيقي في: " + "، ".join(r["label"] for r in ok))
        if not big:
            why.append("حقيقي لكنه صغير عمليًا")
        if not gok:
            why.append("لا يتكرّر في مجموعتين من ثلاث")
        return "partly", "؛ ".join(why)
    if opp and len(opp) >= len(checks) / 2:
        return "does not hold (opposite)", "حقيقي بالاتجاه المعاكس في: " + "، ".join(r["label"] for r in opp)
    return "does not hold", "لا فرق حقيقي عن المعدّل الطبيعي"


def analyse(ev: dict) -> dict:
    res = {"days": [str(ev["days"][0]), str(ev["days"][-1])], "n_days": len(ev["days"])}
    _, cut = _period(ev["days"], pd.Series([ev["days"][0]]))
    res["cut"] = str(cut)

    # ---- thesis 1 ----
    te = pd.DataFrame(ev["trend"])
    te["period"], _ = _period(ev["days"], te["date"])
    te["group"] = te["sym"].map(group_of)
    t1 = []
    for (tf, var, per), g in te.groupby(["tf", "variant", "period"]):
        dec = g[np.isfinite(g.hitA)]
        a = boot_excess(dec, "hitA", "baseA")
        r = boot_excess(g, "run", "base_run")
        t1.append(dict(tf=int(tf), variant=var, period=per, n=len(g), decided=len(dec), hit=float(dec.hitA.mean()) if len(dec) else np.nan,
                       base=float(dec.baseA.mean()) if len(dec) else np.nan, ex=a["mean"], lo=a["lo"], hi=a["hi"],
                       run_ex=r["mean"], run_lo=r["lo"], run_hi=r["hi"]))
    te["exA"] = te.hitA - te.baseA
    cmp = []
    for (tf, per), g in te[np.isfinite(te.exA)].groupby(["tf", "period"]):
        for N in (3, 6):
            b = boot_two_sets(g[g.variant == f"tl+all{N}"], g[g.variant == "tl"], "exA")
            cmp.append(dict(tf=int(tf), period=per, N=N, all_ex=b["rate"], tl_ex=b["base"], diff=b["diff"], lo=b["lo"], hi=b["hi"]))
    grp1 = []
    for (tf, var, gname), g in te[(te.period == "confirm") & te.variant.isin(["tl", "tl+all6"]) & np.isfinite(te.hitA)].groupby(["tf", "variant", "group"]):
        a = boot_excess(g, "hitA", "baseA")
        grp1.append(dict(tf=int(tf), variant=var, group=gname, n=a["n"], ex=a["mean"], lo=a["lo"], hi=a["hi"]))
    res["t1"], res["t1_cmp"], res["t1_groups"] = t1, cmp, grp1
    checks = [dict(mean=r["ex"], lo=r["lo"], hi=r["hi"], label=f"{r['tf']}د {r['period']}") for r in t1 if r["variant"] == "tl+all6"]
    checks += [dict(diff=r["diff"], lo=r["lo"], hi=r["hi"], label=f"أفضل من الكسر وحده {r['tf']}د {r['period']}") for r in cmp if r["N"] == 6]
    gs = [r["ex"] for r in grp1 if r["variant"] == "tl+all6"]
    res["v1"] = _verdict(checks, +1, TINY_RATE, gs)

    # ---- thesis 2 ----
    tw = pd.DataFrame(ev["wall"])
    t2, grp2 = [], []
    if len(tw):
        tw["period"], _ = _period(ev["days"], tw["date"])
        tw["group"] = tw["sym"].map(group_of)
        for (tf, var, per), g in tw.groupby(["tf", "variant", "period"]):
            a = boot_excess(g, "hit", "base")
            nb = g[g.near_wall_behind]
            b = boot_excess(nb, "hit", "base") if len(nb) >= 5 else dict(n=len(nb), mean=np.nan, lo=np.nan, hi=np.nan)
            t2.append(dict(tf=int(tf), variant=var, period=per, n=len(g), hit=float(g.hit.mean()), base=float(g.base.mean()),
                           ex=a["mean"], lo=a["lo"], hi=a["hi"], hit_before_opposite=float(g.hit_opp.mean()),
                           dist_med=float(g.dist.median()), near_n=b["n"], near_ex=b["mean"], near_lo=b["lo"], near_hi=b["hi"]))
        for (tf, gname), g in tw[(tw.period == "confirm") & (tw.variant == "tl")].groupby(["tf", "group"]):
            a = boot_excess(g, "hit", "base")
            grp2.append(dict(tf=int(tf), group=gname, n=a["n"], ex=a["mean"], lo=a["lo"], hi=a["hi"]))
    res["t2"], res["t2_groups"] = t2, grp2
    checks = [dict(mean=r["ex"], lo=r["lo"], hi=r["hi"], label=f"{r['tf']}د {r['period']}") for r in t2 if r["variant"] == "tl"]
    res["v2"] = _verdict(checks, +1, TINY_RATE, [r["ex"] for r in grp2])

    # ---- thesis 3 ----
    fd = pd.DataFrame(ev["flip"])
    lv = pd.DataFrame(ev["level"])
    t3, grp3, chg = [], [], []
    if len(fd):
        fd["period"], _ = _period(ev["days"], fd["date"])
        fd["above"] = fd.side > 0
        fd["group"] = fd["sym"].map(group_of)
        wt = lv[(lv.real == 1) & lv.type.isin(WALLS) & (lv.tf == 5)].copy()
        wt = wt[[t.hour * 60 + t.minute >= 600 for t in wt.time]]
        for level in ("flip", "dflip"):
            f = fd[fd.level == level]
            side = {(r.sym, r.date): r.above for r in f.itertuples()}
            w = wt.copy()
            w["above"] = [side.get((s, d_)) for s, d_ in zip(w.sym, w.date)]
            w = w[w.above.notna()]
            w["above"] = w.above.astype(bool)
            w["period"], _ = _period(ev["days"], w["date"]) if len(w) else (pd.Series(dtype=str), None)
            w["vixb"] = w.date.map({r.date: r.vix for r in f.itertuples()}) if len(w) else []
            for per in ("define", "confirm"):
                ff, ww = f[f.period == per], w[w.period == per] if len(w) else w
                for scope, fx, wx in (("all", ff, ww), ("vix<20", ff[ff.vix < 20], ww[ww.vixb < 20] if len(ww) else ww),
                                      ("vix>=20", ff[ff.vix >= 20], ww[ww.vixb >= 20] if len(ww) else ww)):
                    rg = boot_diff(fx, "range_atr", "above") if len(fx) else {}
                    br = boot_diff(fx, "tl_breaks", "above") if len(fx) else {}
                    rj = boot_diff(wx, "rejected", "above") if len(wx) else {}
                    t3.append(dict(level=level, period=per, scope=scope, days_above=rg.get("n1", 0), days_below=rg.get("n0", 0),
                                   range_above=rg.get("m1"), range_below=rg.get("m0"), range_diff=rg.get("diff"), range_lo=rg.get("lo"), range_hi=rg.get("hi"),
                                   breaks_above=br.get("m1"), breaks_below=br.get("m0"), breaks_diff=br.get("diff"), breaks_lo=br.get("lo"), breaks_hi=br.get("hi"),
                                   touches_above=rj.get("n1", 0), touches_below=rj.get("n0", 0), rej_above=rj.get("m1"), rej_below=rj.get("m0"),
                                   rej_diff=rj.get("diff"), rej_lo=rj.get("lo"), rej_hi=rj.get("hi")))
            c = f[f.changed]
            chg.append(dict(level=level, days=len(f), changed=len(c), share=float(len(c) / max(len(f), 1)),
                            per_bar_before=float(c.range_before_per_bar.mean()) if len(c) else np.nan,
                            per_bar_after=float(c.range_after_per_bar.mean()) if len(c) else np.nan))
        for gname, g in fd[(fd.level == "flip") & (fd.period == "confirm")].groupby("group"):
            r = boot_diff(g, "range_atr", "above")
            grp3.append(dict(group=gname, days=len(g), diff=r["diff"], lo=r["lo"], hi=r["hi"]))
    res["t3"], res["t3_groups"], res["t3_change"] = t3, grp3, chg
    fl = [r for r in t3 if r["level"] == "flip" and r["scope"] == "all"]
    checks = [dict(diff=r["range_diff"], lo=r["range_lo"], hi=r["range_hi"], label=f"المدى {r['period']}") for r in fl if r["range_diff"] is not None]
    rcheck = [dict(diff=r["rej_diff"], lo=r["rej_lo"], hi=r["rej_hi"], label=f"الارتداد {r['period']}") for r in fl if r["rej_diff"] is not None]
    v_range = _verdict(checks, -1, TINY_ATR, [r["diff"] for r in grp3])
    v_rej = _verdict(rcheck, +1, TINY_RATE)
    if v_range[0] == "holds" and v_rej[0] == "holds":
        res["v3"] = ("holds", "المدى أصغر والارتداد أكثر فوق الانقلاب، في الفترتين")
    elif v_range[0].startswith("does not") and v_rej[0].startswith("does not"):
        res["v3"] = ("does not hold" if "opposite" not in v_range[0] else v_range[0], f"المدى: {v_range[1]}. الارتداد: {v_rej[1]}")
    else:
        res["v3"] = ("partly", f"المدى: {V_AR[v_range[0]]} ({v_range[1]}). الارتداد عند الجدران: {V_AR[v_rej[0]]} ({v_rej[1]})")

    # ---- thesis 4 ----
    mg = pd.DataFrame(ev["magnet"])
    t4, bands, grp4 = [], [], []
    if len(mg):
        mg["period"], _ = _period(ev["days"], mg["date"])
        mg["group"] = mg["sym"].map(group_of)
        mg["band"] = pd.cut(mg.dist, [0, 0.5, 1, 2, 3], labels=["0-0.5", "0.5-1", "1-2", "2-3"], include_lowest=True)
        for (kind, tf, per), g in mg.groupby(["kind", "tf", "period"]):
            a = boot_excess(g, "hit", "base")
            t4.append(dict(kind=kind, tf=int(tf), period=per, n=a["n"], hit=float(g.hit.mean()), base=float(g.base.mean()),
                           ex=a["mean"], lo=a["lo"], hi=a["hi"]))
        for (kind, tf, band), g in mg[mg.period == "confirm"].groupby(["kind", "tf", "band"], observed=True):
            a = boot_excess(g, "hit", "base")
            bands.append(dict(kind=kind, tf=int(tf), band=str(band), n=a["n"], hit=float(g.hit.mean()), base=float(g.base.mean()),
                              ex=a["mean"], lo=a["lo"], hi=a["hi"]))
        for (kind, gname), g in mg[(mg.period == "confirm") & (mg.tf == 5)].groupby(["kind", "group"]):
            a = boot_excess(g, "hit", "base")
            grp4.append(dict(kind=kind, group=gname, n=a["n"], ex=a["mean"], lo=a["lo"], hi=a["hi"]))
    res["t4"], res["t4_bands"], res["t4_groups"] = t4, bands, grp4
    checks = [dict(mean=r["ex"], lo=r["lo"], hi=r["hi"], label=f"{r['kind']} {r['tf']}د {r['period']}") for r in t4]
    res["v4"] = _verdict(checks, +1, TINY_RATE, [r["ex"] for r in grp4 if r["kind"] == "4b"])

    # ---- level reactions ----
    lr = []
    if len(lv):
        lv["period"], _ = _period(ev["days"], lv["date"])
        for (typ, tf, per), g in lv.groupby(["type", "tf", "period"]):
            real, pseudo = g[g.real == 1], g[g.real == 0]
            if len(real) < 5 or len(pseudo) < 5:
                lr.append(dict(type=typ, tf=int(tf), period=per, n=len(real), n_base=len(pseudo), rate=np.nan, base=np.nan, diff=np.nan, lo=np.nan, hi=np.nan))
                continue
            b = boot_two_sets(real, pseudo, "rejected")
            lr.append(dict(type=typ, tf=int(tf), period=per, **b))
    res["levels"] = lr
    return res


# ---------------- writing ----------------
def _p(x, d=1):
    return "—" if x is None or not np.isfinite(x) else f"{100 * x:.{d}f}%"


def _pp(x, lo=None, hi=None):
    if x is None or not np.isfinite(x):
        return "—"
    s = f"{100 * x:+.1f}"
    if lo is not None and np.isfinite(lo):
        s += f" ({100 * lo:+.1f} إلى {100 * hi:+.1f})"
    return s


def _a(x, lo=None, hi=None, d=2):
    if x is None or not np.isfinite(x):
        return "—"
    s = f"{x:+.{d}f}"
    if lo is not None and np.isfinite(lo):
        s += f" ({lo:+.{d}f} إلى {hi:+.{d}f})"
    return s


def _tab(rows, head):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows])


PER_AR = {"define": "التعريف", "confirm": "التأكيد"}
GRP_AR = {"index": "صناديق المؤشرات", "mega": "الشركات الكبرى", "high_beta": "عالية التذبذب"}


def verdict_lines(res) -> str:
    names = {"v1": "1. الترند المؤكَّد (كسر + تقاطع + تأكيد)", "v2": "2. الجدران أهداف", "v3": "3. الانقلاب يكشف سلوك صانع السوق",
             "v4": "4. مناطق الحيتان تجذب السعر"}
    return "\n".join(f"- **{n}**: {V_AR[res[k][0]]}. {res[k][1]}" for k, n in names.items())


def write_history(res) -> str:
    os.makedirs(OUT, exist_ok=True)
    md = ["# العيون: اختبار النظرية على التاريخ", "",
          f"الفترة {res['days'][0]} إلى {res['days'][1]} ({res['n_days']} يوم تداول، 30 سهم، فريم 5 و15 دقيقة). "
          f"التعريف = قبل {res['cut']}، التأكيد = من {res['cut']}. القواعد في DEFINITIONS.md وكُتبت قبل التشغيل.", "",
          "الفرق بالنقاط المئوية (pp) أو بوحدة ATR اليومي، وبين القوسين مجال الثقة 95% (إعادة عيّنة بأيام الأسهم كاملة).", "",
          "## الحكم", "", verdict_lines(res), ""]

    # thesis 1
    rows = [[f"{r['tf']}د", r["variant"], PER_AR[r["period"]], r["decided"], _p(r["hit"]), _p(r["base"]), _pp(r["ex"], r["lo"], r["hi"]),
             _a(r["run_ex"], r["run_lo"], r["run_hi"])] for r in sorted(res["t1"], key=lambda r: (r["tf"], r["variant"], r["period"] != "define"))]
    md += ["## 1. الترند المؤكَّد", "",
           "النتيجة A: السعر يصل +1.5 ATR الفريم في اتجاه الإشارة قبل −1.5 قبل الإغلاق. المعدّل الطبيعي: نفس الشي من أي شمعة في نفس نصف الساعة.",
           "النتيجة B: أبعد مسافة في الاتجاه حتى الإغلاق، ناقص المعدّل الطبيعي (ATR يومي).", "",
           _tab(rows, ["الفريم", "الإعداد", "الفترة", "أحداث", "نجاح A", "الطبيعي", "الفرق pp", "الفرق B (ATR)"]), "",
           "**هل التأكيد الكامل أفضل من الكسر وحده؟** (فرق الزيادة على الطبيعي)", "",
           _tab([[f"{r['tf']}د", f"N={r['N']}", PER_AR[r["period"]], _pp(r["all_ex"]), _pp(r["tl_ex"]), _pp(r["diff"], r["lo"], r["hi"])]
                 for r in res["t1_cmp"]], ["الفريم", "N", "الفترة", "زيادة الكامل", "زيادة الكسر وحده", "الفرق"]), "",
           _tab([[f"{r['tf']}د", r["variant"], GRP_AR[r["group"]], r["n"], _pp(r["ex"], r["lo"], r["hi"])] for r in res["t1_groups"]],
                ["الفريم", "الإعداد", "المجموعة (التأكيد)", "أحداث", "الفرق pp"]), ""]

    # thesis 2
    rows = [[f"{r['tf']}د", r["variant"], PER_AR[r["period"]], r["n"], f"{r['dist_med']:.2f}", _p(r["hit"]), _p(r["base"]),
             _pp(r["ex"], r["lo"], r["hi"]), _p(r["hit_before_opposite"]), f"{r['near_n']}: {_pp(r['near_ex'], r['near_lo'], r['near_hi'])}"]
            for r in sorted(res["t2"], key=lambda r: (r["tf"], r["variant"], r["period"] != "define"))]
    md += ["## 2. الجدران أهداف", "",
           "بعد كل كسر (وكل دخول مؤكَّد): هل يصل السعر للجدار التالي في الاتجاه قبل الإغلاق؟ مقارنةً بالوصول لنفس المسافة من أي شمعة في نفس الوقت.", "",
           _tab(rows, ["الفريم", "الإعداد", "الفترة", "أحداث", "المسافة (ATR)", "وصل", "الطبيعي", "الفرق pp", "قبل الجدار المعاكس", "بدأ قرب جدار خلفه"]), "",
           _tab([[f"{r['tf']}د", GRP_AR[r["group"]], r["n"], _pp(r["ex"], r["lo"], r["hi"])] for r in res["t2_groups"]],
                ["الفريم", "المجموعة (التأكيد، الكسر)", "أحداث", "الفرق pp"]), ""]

    # thesis 3
    rows = [[r["level"].upper(), PER_AR[r["period"]], r["scope"], f"{r['days_above']}/{r['days_below']}",
             f"{(r['range_above'] or np.nan):.2f} / {(r['range_below'] or np.nan):.2f}", _a(r["range_diff"], r["range_lo"], r["range_hi"]),
             _a(r["breaks_diff"], r["breaks_lo"], r["breaks_hi"], 1),
             f"{_p(r['rej_above'], 0)} / {_p(r['rej_below'], 0)}", _pp(r["rej_diff"], r["rej_lo"], r["rej_hi"])] for r in res["t3"]]
    md += ["## 3. الانقلاب وسلوك صانع السوق", "",
           "الجانب = إغلاق 10:00 فوق أو تحت المستوى. بعد 10:00: مدى اليوم (ATR يومي)، عدد كسور خط الترند (5د)، نسبة الارتداد عند الجدران.",
           "المتوقّع لو النظرية صحيحة: فوق الانقلاب مدى أصغر (فرق سالب) وارتداد أكثر (فرق موجب).", "",
           _tab(rows, ["المستوى", "الفترة", "النطاق", "أيام فوق/تحت", "المدى فوق / تحت", "فرق المدى", "فرق الكسور", "ارتداد فوق / تحت", "فرق الارتداد pp"]), "",
           _tab([[GRP_AR[r["group"]], r["days"], _a(r["diff"], r["lo"], r["hi"])] for r in res["t3_groups"]], ["المجموعة (FLIP، التأكيد)", "أيام", "فرق المدى"]), "",
           _tab([[r["level"].upper(), r["days"], r["changed"], _p(r["share"]), f"{r['per_bar_before']:.4f}" if np.isfinite(r["per_bar_before"]) else "—",
                  f"{r['per_bar_after']:.4f}" if np.isfinite(r["per_bar_after"]) else "—"] for r in res["t3_change"]],
                ["المستوى", "أيام", "غيّر جانبه", "النسبة", "المدى لكل شمعة قبل", "بعد"]), ""]

    # thesis 4
    rows = [[r["kind"], f"{r['tf']}د", PER_AR[r["period"]], r["n"], _p(r["hit"]), _p(r["base"]), _pp(r["ex"], r["lo"], r["hi"])] for r in res["t4"]]
    md += ["## 4. مناطق الحيتان", "",
           "4a: بعد كل كسر، أقرب خط حوت في الاتجاه (حتى 3 ATR). 4b: من كل شمعة على رأس نصف الساعة، أقرب خط فوق وأقرب خط تحت.",
           "المقارنة: الوصول لنفس المسافة من نفس الوقت، أي سعر عشوائي على نفس البعد.", "",
           _tab(rows, ["النوع", "الفريم", "الفترة", "أحداث", "وصل", "الطبيعي", "الفرق pp"]), "",
           _tab([[r["kind"], f"{r['tf']}د", r["band"], r["n"], _p(r["hit"]), _p(r["base"]), _pp(r["ex"], r["lo"], r["hi"])] for r in res["t4_bands"]],
                ["النوع", "الفريم", "البعد (ATR)", "أحداث", "وصل", "الطبيعي", "الفرق pp (التأكيد)"]), "",
           _tab([[r["kind"], GRP_AR[r["group"]], r["n"], _pp(r["ex"], r["lo"], r["hi"])] for r in res["t4_groups"]], ["النوع", "المجموعة (5د، التأكيد)", "أحداث", "الفرق pp"]), ""]

    # levels
    rows = [[TYPE_AR[r["type"]], f"{r['tf']}د", PER_AR[r["period"]], r["n"], _p(r["rate"]), _p(r["base"]), _pp(r["diff"], r["lo"], r["hi"])]
            for r in sorted(res["levels"], key=lambda r: (r["type"], r["tf"], r["period"] != "define"))]
    md += ["## ردّة الفعل عند كل مستوى (أول لمسة)", "",
           "ارتداد = ما في إغلاق خلف المستوى خلال 4 شموع من اللمسة. المقارنة: نفس القاعدة على أسعار عشوائية قريبة (±0.25 إلى 1 ATR).", "",
           _tab(rows, ["المستوى", "الفريم", "الفترة", "لمسات", "ارتداد", "عشوائي", "الفرق pp"]), "",
           "## ملاحظات على الطريقة", "",
           "- بيانات IEX من Alpaca، مو شموع BATS في TradingView؛ منطق الإشارات مطابق 99.8–100% على شموع TradingView نفسها.",
           "- مستويات الخيارات: CW / PW / FLIP متاحة لنحو 560 يوم في 7 أسهم كبيرة، ونحو 40 يوم في أغلب البقية. CWOI / PWOI / PIN / DFLIP لآخر نحو 58 يوم فقط (الصفوف الأقدم بلا جدول عقود). لذلك أغلب أحداث الجدران في فترة التأكيد.",
           "- الشمعة التي تلمس الحاجزين معًا تُحسب ضد الإشارة (نفس قاعدة المحاكي). هذه تفصيلة لم تُذكر في DEFINITIONS.md.",
           "- أداة التأكيد اللحظية (EMA 9/21 + DMI 7) منقولة من كود المؤشر لكنها لا تُرسم، فلم تُطابَق مع TradingView مباشرة.",
           "- «المدى قبل وبعد تغيّر جانب الانقلاب» وصفي فقط: الشموع بعد الظهر أهدأ في كل الأيام، فانخفاض المدى بعد التغيّر لا يثبت إن الانقلاب هو السبب.",
           "- مع نحو 44 مقارنة لردّة الفعل عند المستويات، نتوقّع 2 تقريبًا تطلع حقيقية بالصدفة عند 95%.", ""]
    text = "\n".join(md)
    open(os.path.join(OUT, "HISTORY.md"), "w", encoding="utf-8").write(text)
    json.dump(res, open(os.path.join(OUT, "history.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (float(x) if isinstance(x, (np.floating,)) else (int(x) if isinstance(x, np.integer) else str(x))))
    return text


# ---------------- pictures ----------------
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
C_REAL, C_BASE = "#4fc3f7", "#5d6472"


def _ax(ax, title):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    ax.set_title(title, color=TX, fontsize=12, loc="left"); ax.yaxis.label.set_color(MUT)


def _bars(ax, labels, vals, lo, hi, sign=+1):
    """Effect bars with 95% intervals. Green = real and in the claim's direction, red = real and against it,
    grey = not distinguishable from zero. Empty entries are dropped."""
    keep = [k for k, v in enumerate(vals) if v is not None and np.isfinite(v)]
    labels, vals = [labels[k] for k in keep], [vals[k] for k in keep]
    lo, hi = [lo[k] for k in keep], [hi[k] for k in keep]
    x = np.arange(len(labels))
    v = np.array(vals, float) * 100
    sup = lambda l_, h_: (l_ > 0) if sign > 0 else (h_ < 0)  # noqa: E731
    con = lambda l_, h_: (h_ < 0) if sign > 0 else (l_ > 0)  # noqa: E731
    cols = [("#26a69a" if sup(a, b) else ("#ef5350" if con(a, b) else C_BASE)) for a, b in zip(lo, hi)]
    ax.bar(x, v, 0.6, color=cols)
    ax.errorbar(x, v, yerr=[v - np.array(lo) * 100, np.array(hi) * 100 - v], fmt="none", ecolor=TX, capsize=3, lw=1)
    ax.axhline(0, color=MUT, lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30, ha="right", color=MUT, fontsize=9)


def pictures(res, ev) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(OUT, exist_ok=True)
    paths = []
    order = ["tl", "tl+IT", "tl+ST", "tl+MA3", "tl+MA6", "tl+all3", "tl+all6"]
    fig, axs = plt.subplots(2, 2, figsize=(15, 9), facecolor=BG)
    for ax, (tf, per) in zip(axs.flat, [(5, "define"), (5, "confirm"), (15, "define"), (15, "confirm")]):
        rr = {r["variant"]: r for r in res["t1"] if r["tf"] == tf and r["period"] == per}
        lab = [v for v in order if v in rr]
        _bars(ax, lab, [rr[v]["ex"] for v in lab], [rr[v]["lo"] for v in lab], [rr[v]["hi"] for v in lab])
        _ax(ax, f"Thesis 1 · {tf}m · {per}: follow-through vs base rate (pp, 95% CI)")
    fig.tight_layout(); p = os.path.join(OUT, "thesis1_trend.png"); fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig); paths.append(p)

    fig, ax = plt.subplots(figsize=(14, 6), facecolor=BG)
    rr = sorted(res["t2"], key=lambda r: (r["tf"], r["variant"], r["period"] != "define"))
    _bars(ax, [f"{r['tf']}m {r['variant']} {r['period']}" for r in rr], [r["ex"] for r in rr], [r["lo"] for r in rr], [r["hi"] for r in rr])
    _ax(ax, "Thesis 2 · next wall reached before the close: excess over the same distance from a random bar (pp, 95% CI)")
    fig.tight_layout(); p = os.path.join(OUT, "thesis2_walls.png"); fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig); paths.append(p)

    fig, axs = plt.subplots(1, 2, figsize=(15, 6), facecolor=BG)
    rr = [r for r in res["t3"] if r["scope"] in ("all", "vix<20", "vix>=20")]
    lab = [f"{r['level']} {r['period']} {r['scope']}" for r in rr]
    _bars(axs[0], lab, [r["range_diff"] if r["range_diff"] is not None else np.nan for r in rr],
          [r["range_lo"] if r["range_lo"] is not None else np.nan for r in rr], [r["range_hi"] if r["range_hi"] is not None else np.nan for r in rr], sign=-1)
    _ax(axs[0], "Thesis 3 · range after 10:00, above minus below the flip (x100 = daily ATR %)")
    _bars(axs[1], lab, [r["rej_diff"] if r["rej_diff"] is not None else np.nan for r in rr],
          [r["rej_lo"] if r["rej_lo"] is not None else np.nan for r in rr], [r["rej_hi"] if r["rej_hi"] is not None else np.nan for r in rr])
    _ax(axs[1], "Thesis 3 · wall rejection rate, above minus below the flip (pp)")
    fig.tight_layout(); p = os.path.join(OUT, "thesis3_flip.png"); fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig); paths.append(p)

    fig, axs = plt.subplots(1, 2, figsize=(15, 6), facecolor=BG)
    for ax, kind in zip(axs, ("4a", "4b")):
        rr = [r for r in res["t4_bands"] if r["kind"] == kind]
        lab = [f"{r['tf']}m {r['band']} ATR" for r in rr]
        x = np.arange(len(rr))
        ax.bar(x - 0.2, [100 * r["base"] for r in rr], 0.4, color=C_BASE, label="random price, same distance and time")
        ax.bar(x + 0.2, [100 * r["hit"] for r in rr], 0.4, color=C_REAL, label="whale level")
        ax.set_xticks(x); ax.set_xticklabels(lab, rotation=30, ha="right", color=MUT, fontsize=9)
        ax.legend(facecolor=BG, labelcolor=TX, fontsize=9)
        _ax(ax, f"Thesis 4{kind[1]} · reached before the close (%, confirm period)")
    fig.tight_layout(); p = os.path.join(OUT, "thesis4_whale.png"); fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig); paths.append(p)

    fig, ax = plt.subplots(figsize=(15, 6), facecolor=BG)
    rr = sorted([r for r in res["levels"] if r["period"] == "confirm" and r["tf"] == 5 and np.isfinite(r.get("diff", np.nan))], key=lambda r: r["type"])
    _bars(ax, [r["type"] for r in rr], [r["diff"] for r in rr], [r["lo"] for r in rr], [r["hi"] for r in rr])
    _ax(ax, "Level reactions · rejection on first touch, real level minus random nearby price (pp, 5m, confirm)")
    fig.tight_layout(); p = os.path.join(OUT, "levels_rejection.png"); fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig); paths.append(p)
    try:
        paths.append(example_day("SPY"))
    except Exception:  # noqa: BLE001 - the example is a picture, not a test
        pass
    return paths


def example_day(sym: str = "SPY", day=None) -> str:
    """A real day: 5-minute candles, the options walls and flip, whale lines, first touches (o = rejection,
    x = pass-through) and confirmed entries (triangles). Drawn from the stored bars with the same rules."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from . import eyes, eyes_live
    from .data import load_bars
    b = load_bars(sym)
    fr = eyes.build(sym, b, tfs=(5,), paths=False)
    d = fr[5]
    day = day or d["session"].iat[-1]
    t = d[d["session"] == day]
    obs = eyes_live.observe_day(sym, fr, day, session_over=True)
    fig, ax = plt.subplots(figsize=(16, 9), facecolor=BG)
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    o, h, l, c = (t[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    for i in range(len(t)):
        col = "#26a69a" if c[i] >= o[i] else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-3), color=col))
    lo_, hi_ = l.min(), h.max()
    pad = 0.6 * (hi_ - lo_)
    style = {"cw": ("#00c853", "-"), "pw": ("#ff1744", "-"), "cwoi": ("#69f0ae", "--"), "pwoi": ("#ff8a80", "--"),
             "flip": ("#ffd600", "--"), "dflip": ("#80d8ff", ":"), "pin": ("#e0e0e0", ":")}
    shown = {}
    for col, (cc, ls) in style.items():
        v = float(t[col].iat[0])
        if np.isfinite(v) and lo_ - pad <= v <= hi_ + pad:
            ax.axhline(v, color=cc, ls=ls, lw=1.4)
            shown.setdefault(round(v, 2), []).append((col.upper(), cc))
    for v, names in shown.items():                 # levels at the same price share one label
        ax.text(len(t) + 0.5, v, " · ".join(n for n, _ in names) + f" {v:g}", color=names[0][1], va="center", fontsize=10, fontweight="bold")
    for v in eyes._whale_list(day, fr["whale"], fr["whale_va"]):
        if lo_ - pad <= v <= hi_ + pad:
            ax.axhline(v, color="#ff6d00", lw=0.7, alpha=0.6)
    pos = {ts: k for k, ts in enumerate(t.index)}
    for ob in obs:
        if ob["kind"] == "touch" and ob["time"]:
            k = pos.get(pd.Timestamp(ob["time"]))
            if k is not None:
                ax.plot(k, ob["level"], "o" if ob["outcome"] == "ارتداد" else "x", color=TX, ms=7, mfc="none")
        if ob["kind"] == "entry":
            k = pos.get(pd.Timestamp(ob["time"]))
            if k is not None:
                ax.plot(k, ob["level"], "^" if ob["side"] > 0 else "v", color="#4fc3f7", ms=12)
    ax.set_xlim(-1, len(t) + 6); ax.set_ylim(lo_ - pad, hi_ + pad)
    ticks = [k for k, ts in enumerate(t.index) if ts.minute == 0]
    ax.set_xticks(ticks); ax.set_xticklabels([t.index[k].strftime("%H:%M") for k in ticks], color=MUT)
    ax.set_title(f"{sym} 5m {day} (real bars) · walls / flip / pin, orange = whale lines, o = rejection on first touch, "
                 f"x = pass-through, triangles = confirmed trend entries", color=TX, fontsize=11, loc="left")
    fig.tight_layout()
    p = os.path.join(OUT, f"example_{sym}_{day}.png")
    fig.savefig(p, dpi=80, facecolor=BG); plt.close(fig)
    return p
