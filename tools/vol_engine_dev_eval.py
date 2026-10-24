"""Tests of reports/vol_engine_dev/PREREG.md (volatility engine v2).

    python tools/vol_engine_dev_eval.py planted      # family planted tests on synthetic worlds -> planted.json
    python tools/vol_engine_dev_eval.py frames       # build and cache the 30 real frames (+ daily validation frames)
    python tools/vol_engine_dev_eval.py p1 | p2 | p3 | p4 | map    # phases -> verdict.json (merged)
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import regimes as RG  # noqa: E402
from vzones import vol_engine_dev as D  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
from vzones import vol_engine as VE  # noqa: E402

OUT = os.path.join(ROOT, "reports", "vol_engine_dev"); CACHE = os.path.join(OUT, "cache"); UNI = os.path.join(ROOT, "runtime_sip", "daily_universe")
os.makedirs(CACHE, exist_ok=True)
MIN_BLOCKS = 200
K = D.K


def jdump(obj, name):
    json.dump(obj, open(os.path.join(OUT, name), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))


def merge_verdict(part: dict):
    p = os.path.join(OUT, "verdict.json"); cur = json.load(open(p)) if os.path.exists(p) else {}
    cur.update(part); jdump(cur, "verdict.json")


def blocks_of(F, idx):
    return np.array([f"{F['sym']}|{F['date'][i]}" for i in idx])


def cat(frames, key):
    return np.concatenate([F[key] for F in frames])


# ====================================================================================
# real frames
# ====================================================================================
def build_real_frames():
    from vzones.assistant import data as DA
    from vzones import trend_volume_model as TM
    import breakout_volume_eval as BE
    import volume_tool_eval as E
    syms = sorted(f[:-7] for f in os.listdir(DA.BARS) if f.endswith("_5m.csv"))
    # the train cut: first 60% of all sessions (same rule as vol_engine_eval.tf_block)
    alldays = set()
    raw = {}
    for s in syms:
        d = E.frames(s)[5]; raw[s] = d; alldays |= set(d.index.date)
    days = sorted(alldays); cut = days[int(0.6 * len(days))]
    vix = pd.read_csv(os.path.join(UNI, "_VIX.csv"), index_col=0, parse_dates=True)["close"]; v3 = pd.read_csv(os.path.join(UNI, "_VIX3M.csv"), index_col=0, parse_dates=True)["close"]
    vreg = RG.vix_regime(vix, v3)
    frames = []
    for s in syms:
        t0 = time.time(); d = raw[s]
        o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
        sess, slot = VT.sessions_slots(d.index, 5); tod = RG.tod_bin(d.index)
        train = np.array([x < cut for x in sess])
        F = D.base_frame(o, h, l, c, v, sess, slot, tod, train)
        res = TM.run(d, 5, BE.day_levels(d, s)); bars = res["bars"]
        F = D.add_trend(F, bars, VT.rvol_set(d, 5)[0])
        br = res["breaks"]; F["breaks"] = br[br["type"].str.startswith("swing")][["t", "dir", "L", "type"]].reset_index(drop=True) if len(br) else pd.DataFrame(columns=["t", "dir", "L", "type"])
        F["sym"] = s; F["date"] = np.array([str(x) for x in sess])
        dl = BE.day_levels(d, s)                                   # prior-day pdh/pdl/poc/vah/val + today's cw/pw
        F["levels"] = {str(k): {kk: float(vv) for kk, vv in row.items()} for k, row in dl.iterrows()}
        ud = sorted(set(sess)); ev = RG.event_days(ud); vd = RG.vix_for_dates(ud, vreg)
        per_day = {str(dd): dict(event=bool(ev["event"][i]), fomc=bool(ev["fomc"][i]), vix_q=float(vd["vix_q"].iloc[i]), vix_pct=float(vd["vix_pct"].iloc[i]), backw=float(vd["backwardation"].iloc[i]) if "backwardation" in vd else np.nan) for i, dd in enumerate(ud)}
        F["event"] = np.array([per_day[x]["event"] for x in F["date"]]); F["vix_q"] = np.array([per_day[x]["vix_q"] for x in F["date"]]); F["vix_pct"] = np.array([per_day[x]["vix_pct"] for x in F["date"]])
        frames.append(F); print(s, F["n"], "train", int(train.sum()), "breaks", len(F["breaks"]), f"{time.time() - t0:.0f}s", flush=True)
    pickle.dump(dict(frames=frames, cut=str(cut)), open(os.path.join(CACHE, "frames5m.pkl"), "wb"))
    build_daily_frames(vreg)


def build_daily_frames(vreg):
    """daily validation frames 2020-2022 (k = 5): z5, exits, squeeze (daily thr), Hull state, heat"""
    from vzones import conviction_ma as CM
    from vzones import trend_volume as TV
    syms = sorted(f[:-4] for f in os.listdir(UNI) if f.endswith(".csv") and not f.startswith("_"))
    out = []
    for s in syms:
        d = pd.read_csv(os.path.join(UNI, f"{s}.csv"), index_col=0, parse_dates=True)
        d = d[(d.index.year >= 2018) & (d.index.year <= 2022)]
        if len(d) < 600:
            continue
        o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        n = len(c); r = np.r_[np.nan, np.diff(np.log(c))]; s2 = VE.ewma_var(r, 0.94); move = np.sqrt(5 * s2) * c
        comp, A = D.comp_ratio(h, l, c); heat = RG.percent_rank(move / c, 500); hb = RG.heat_bin(heat); sq, sq_in = RG.squeeze_state(comp, RG.SQZ_THR["D"], 5)
        M = CM.hma(c, 56); st = TV.trend_state(c, M)
        F = dict(n=n, o=o, h=h, l=l, c=c, r=r, s2=s2, move=move, A=A, comp=comp, heat=heat, hb=hb, sq=sq, sq_in=sq_in, st=st, conf=np.ones(n, bool), S0=np.full(n, np.nan),
                 slot=np.zeros(n, int), sess=np.arange(n), new=np.ones(n, bool), sym=s, date=np.array([x.strftime("%Y-%m-%d") for x in d.index]),
                 valid=np.array([x.year >= 2020 for x in d.index]), z5=D.forward(c, 5) / move, R5=D.fwd_range(h, l, 5))
        up = np.zeros(n, bool); dn = np.zeros(n, bool); up[5:] = c[5:] > c[:-5] + move[:-5]; dn[5:] = c[5:] < c[:-5] - move[:-5]
        F["exit_up"] = up & np.isfinite(move); F["exit_dn"] = dn & np.isfinite(move)
        out.append(F)
    pickle.dump(out, open(os.path.join(CACHE, "framesD.pkl"), "wb")); print("daily frames", len(out), flush=True)


def load_frames():
    d = pickle.load(open(os.path.join(CACHE, "frames5m.pkl"), "rb")); return d["frames"], d["cut"]


def load_daily():
    return pickle.load(open(os.path.join(CACHE, "framesD.pkl"), "rb"))


# ====================================================================================
# hypothesis machinery (works on any list of frames)
# ====================================================================================
def test_mask(F, warm=500):
    m = ~F["train"]; m[:warm] = False
    return m


def h11_fan(frames, zkey="z24", block_date="date"):
    """fat tails: train quantiles + Student-t, coverage and pinball on test overall and by heat bin"""
    ztr = np.concatenate([F[zkey][F["train"]] for F in frames]); Q = D.fan_quantiles(ztr)
    res = dict(train=Q)
    cov_e1, cov_e2, cov_g1, cov_g2, pb_e, pb_g, hb, blk = [], [], [], [], [], [], [], []
    for F in frames:
        m = test_mask(F); z = F[zkey]
        ce1, pe = D.band_stats(z, Q["q16"], Q["q84"], None); ce2, _ = D.band_stats(z, Q["q025"], Q["q975"], None)
        cg1, pg = D.band_stats(z, -1.0, 1.0, None); cg2, _ = D.band_stats(z, -2.0, 2.0, None)
        idx = np.where(m & np.isfinite(z))[0]
        cov_e1.append(ce1[idx]); cov_e2.append(ce2[idx]); cov_g1.append(cg1[idx]); cov_g2.append(cg2[idx]); pb_e.append(pe[idx]); pb_g.append(pg[idx]); hb.append(F["hb"][idx]); blk.append(blocks_of(F, idx))
    cov_e1, cov_e2, cov_g1, cov_g2, pb_e, pb_g, hb, blk = (np.concatenate(x) for x in (cov_e1, cov_e2, cov_g1, cov_g2, pb_e, pb_g, hb, blk))
    res["test"] = dict(n=int(len(blk)), empirical=dict(inner=D.boot_mean(cov_e1, blk), outer=D.boot_mean(cov_e2, blk)), gaussian=dict(inner=D.boot_mean(cov_g1, blk), outer=D.boot_mean(cov_g2, blk)),
                       pinball_emp_minus_gauss=D.boot_diff(pb_e, pb_g, blk))
    by = {}
    for b in range(5):
        sel = hb == b
        if len(np.unique(blk[sel])) >= MIN_BLOCKS:
            by[RG.HEAT_NAMES[b]] = dict(inner_emp=D.boot_mean(cov_e1[sel], blk[sel]), inner_gauss=D.boot_mean(cov_g1[sel], blk[sel]), outer_emp=D.boot_mean(cov_e2[sel], blk[sel]), blocks=int(len(np.unique(blk[sel]))))
        else:
            by[RG.HEAT_NAMES[b]] = dict(not_enough_data=True, blocks=int(len(np.unique(blk[sel]))))
    res["by_heat"] = by
    inner_ok = abs(res["test"]["empirical"]["inner"]["mean"] - 0.683) <= 0.02 and abs(res["test"]["empirical"]["outer"]["mean"] - 0.95) <= 0.02
    cells_ok = all(("not_enough_data" in v) or (abs(v["inner_emp"]["mean"] - 0.683) <= 0.02 and abs(v["outer_emp"]["mean"] - 0.95) <= 0.02) for v in by.values())
    pb_ok = D.excludes0(res["test"]["pinball_emp_minus_gauss"]) and res["test"]["pinball_emp_minus_gauss"]["mean"] < 0
    res["pass"] = bool(inner_ok and cells_ok and pb_ok); res["checks"] = dict(inner_outer_overall=bool(inner_ok), every_heat_cell=bool(cells_ok), pinball_better=bool(pb_ok))
    # H1.2 asymmetry: separate vs symmetric quantiles; asymmetry interval by block bootstrap of the train quantiles
    qs = (abs(Q["q16"]) + abs(Q["q84"])) / 2
    pb_s, pb_a, blk2 = [], [], []
    for F in frames:
        m = test_mask(F); z = F[zkey]; idx = np.where(m & np.isfinite(z))[0]
        _, ps = D.band_stats(z, -qs, qs, None); _, pa = D.band_stats(z, Q["q16"], Q["q84"], None); pb_s.append(ps[idx]); pb_a.append(pa[idx]); blk2.append(blocks_of(F, idx))
    pb_s, pb_a, blk2 = (np.concatenate(x) for x in (pb_s, pb_a, blk2))
    # train asymmetry by block bootstrap
    ztr_blk = np.concatenate([blocks_of(F, np.where(F["train"] & np.isfinite(F[zkey]))[0]) for F in frames])
    u, inv = np.unique(ztr_blk, return_inverse=True); rng = np.random.default_rng(0); asym = []
    order = np.argsort(inv); zs = ztr[order]; inv_s = inv[order]; starts = np.searchsorted(inv_s, np.arange(len(u) + 1))
    for _ in range(300):
        p = rng.integers(0, len(u), len(u)); zz = np.concatenate([zs[starts[i]:starts[i + 1]] for i in p])
        asym.append(np.percentile(zz, 84) + np.percentile(zz, 16))
    a12 = dict(asymmetry_q84_plus_q16=dict(mean=round(float(Q["q84"] + Q["q16"]), 4), lo=round(float(np.percentile(asym, 2.5)), 4), hi=round(float(np.percentile(asym, 97.5)), 4)),
               pinball_asym_minus_sym=D.boot_diff(pb_a, pb_s, blk2))
    a12["pass"] = bool(D.excludes0(a12["pinball_asym_minus_sym"]) and a12["pinball_asym_minus_sym"]["mean"] < 0 and D.excludes0(a12["asymmetry_q84_plus_q16"]))
    return res, a12


def h13_season(frames):
    out = dict(profiles={}); q_plain, q_seas, cov_s, blk = [], [], [], []
    for F in frames:
        prof = D.slot_profile(F); s2s, _ = D.seasonal_var(F, prof)
        r2 = np.where(np.isfinite(F["r"]), F["r"] ** 2, np.nan); V = pd.Series(r2).shift(-1)[::-1].rolling(K).sum()[::-1].to_numpy()
        m = test_mask(F); idx = np.where(m & np.isfinite(V) & (V > 0) & np.isfinite(s2s) & (s2s > 0) & (F["s2"] > 0))[0]
        vp = K * F["s2"][idx]; vs = K * s2s[idx]
        q_plain.append(np.log(vp) + V[idx] / vp); q_seas.append(np.log(vs) + V[idx] / vs)
        z = D.forward(F["c"], K) / (np.sqrt(K * s2s) * F["c"]); cov_s.append(np.where(np.isfinite(z[idx]), np.abs(z[idx]) <= 1, np.nan)); blk.append(blocks_of(F, idx))
        out["profiles"][F["sym"]] = [round(float(x), 3) for x in prof[::6]]
    q_plain, q_seas, cov_s, blk = (np.concatenate(x) for x in (q_plain, q_seas, cov_s, blk))
    out["qlike_seasonal_minus_plain"] = D.boot_diff(q_seas, q_plain, blk); out["coverage_1sigma_seasonal"] = D.boot_mean(cov_s, blk)
    out["pass"] = bool(D.excludes0(out["qlike_seasonal_minus_plain"]) and out["qlike_seasonal_minus_plain"]["mean"] < 0 and abs(out["coverage_1sigma_seasonal"]["mean"] - 0.683) <= 0.03)
    return out


def h14_horizon(frames):
    slopes = np.concatenate([D.horizon_alpha(F) for F in frames]); rng = np.random.default_rng(0)
    bs = [slopes[rng.integers(0, len(slopes), len(slopes))].mean() for _ in range(1000)]
    alpha = float(slopes.mean()); out = dict(alpha=dict(mean=round(alpha, 4), lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4), blocks=int(len(slopes))))
    out["by_k"] = {}; wins = 0
    for k in (6, 12, 48):
        ca, cs, blk = [], [], []
        for F in frames:
            m = test_mask(F); mv = D.forward(F["c"], k); sd = np.sqrt(F["s2"]) * F["c"]
            za = mv / (sd * k ** alpha); zs = mv / (sd * np.sqrt(k)); idx = np.where(m & np.isfinite(za))[0]
            ca.append((np.abs(za[idx]) <= 1).astype(float)); cs.append((np.abs(zs[idx]) <= 1).astype(float)); blk.append(blocks_of(F, idx))
        ca, cs, blk = (np.concatenate(x) for x in (ca, cs, blk))
        # |cov - 68.3| difference by block bootstrap
        u, inv = np.unique(blk, return_inverse=True); sa = np.bincount(inv, weights=ca); ss = np.bincount(inv, weights=cs); cnt = np.bincount(inv).astype(float)
        bs = []
        for _ in range(1000):
            p = rng.integers(0, len(u), len(u)); n_ = cnt[p].sum(); bs.append(abs(sa[p].sum() / n_ - 0.683) - abs(ss[p].sum() / n_ - 0.683))
        d = dict(cov_alpha=round(float(ca.mean()), 4), cov_sqrt=round(float(cs.mean()), 4), abs_err_diff=dict(mean=round(float(np.mean(bs)), 4), lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4)))
        d["better"] = bool(d["abs_err_diff"]["hi"] < 0); wins += d["better"]; out["by_k"][str(k)] = d
    out["pass"] = bool((out["alpha"]["lo"] > 0.5 or out["alpha"]["hi"] < 0.5) and wins >= 2)
    return out


def h15_events(frames, Q):
    cov, blk, vx, az, blk_tr, vx_tr = [], [], [], [], [], []
    for F in frames:
        z = F["z24"]; m = test_mask(F) & F["event"] & np.isfinite(z); idx = np.where(m)[0]
        cov.append(((z[idx] >= Q["q16"]) & (z[idx] <= Q["q84"])).astype(float)); blk.append(blocks_of(F, idx)); vx.append(F["vix_pct"][idx])
        mt = F["train"] & np.isfinite(z) & np.isfinite(F["vix_pct"]); it = np.where(mt)[0]; az.append(np.abs(z[it])); vx_tr.append(F["vix_pct"][it]); blk_tr.append(blocks_of(F, it))
    cov, blk, vx = (np.concatenate(x) for x in (cov, blk, vx)); az, vx_tr = np.concatenate(az), np.concatenate(vx_tr)
    out = dict(event_blocks=int(len(np.unique(blk))))
    if len(np.unique(blk)) < 100:
        out["not_enough_data"] = True; out["pass"] = False; return out
    out["coverage_event_days"] = D.boot_mean(cov, blk)
    if abs(out["coverage_event_days"]["mean"] - 0.683) <= 0.03:
        out["pass"] = True; out["widening"] = None; return out
    # widening w = a + b * vixpct from train: median |z| by VIX decile, normalized to mean 1
    dec = np.clip((vx_tr // 10).astype(int), 0, 9); med = np.array([np.nanmedian(az[dec == d_]) if (dec == d_).sum() > 100 else np.nan for d_ in range(10)])
    ok = np.isfinite(med); xs = np.arange(10)[ok] * 10 + 5; b, a = np.polyfit(xs, med[ok], 1); w = lambda v: (a + b * v) / (a + b * 50)
    cov_w = []
    for F in frames:
        z = F["z24"]; m = test_mask(F) & F["event"] & np.isfinite(z) & np.isfinite(F["vix_pct"]); idx = np.where(m)[0]; ww = w(F["vix_pct"][idx])
        cov_w.append(((z[idx] >= Q["q16"] * ww) & (z[idx] <= Q["q84"] * ww)).astype(float))
    cov_w = np.concatenate(cov_w); out["widening"] = dict(a=round(float(a), 4), b=round(float(b), 6), coverage_event_days_widened=D.boot_mean(cov_w, blk[:len(cov_w)]))
    out["pass"] = bool(abs(out["widening"]["coverage_event_days_widened"]["mean"] - 0.683) <= 0.03)
    return out


def h3_dayrange(frames):
    out = {}
    rng = np.random.default_rng(3)
    # H3.1 fuel thresholds and H3.4 touch
    ev = {thr: dict(rev12=[], rev24=[], rnd12=[], rnd24=[], blk=[]) for thr in (0.8, 1.0, 1.2)}; touch = dict(back=[], rnd=[], blk=[])
    for F in frames:
        m = test_mask(F); c, fuel, s_open = F["c"], F["fuel"], F["s_open"]; n = F["n"]
        pools = D.pools_by_slot(F, m & np.isfinite(F["z24"]))
        starts = np.where(F["new"])[0]; ends = np.r_[starts[1:], n]
        for a, b in zip(starts, ends):
            if not m[a]:
                continue
            seen = set()
            for t in range(a + 1, b - 24):
                side = np.sign(c[t] - s_open[t])
                if side == 0:
                    continue
                for thr in ev:
                    if thr not in seen and np.isfinite(fuel[t]) and fuel[t] >= thr:
                        seen.add(thr); j = D.matched_random(F, t, pools, rng)
                        if j is None:
                            continue
                        rev12 = float(np.sign(c[t + 12] - c[t]) == -side); rev24 = float(np.sign(c[t + 24] - c[t]) == -side)
                        sd = np.sign(c[j] - s_open[j]); r12 = np.mean(np.sign(c[j + 12] - c[j]) == -sd); r24 = np.mean(np.sign(c[np.minimum(j + 24, n - 1)] - c[j]) == -sd)
                        ev[thr]["rev12"].append(rev12); ev[thr]["rev24"].append(rev24); ev[thr]["rnd12"].append(r12); ev[thr]["rnd24"].append(r24); ev[thr]["blk"].append(f"{F['sym']}|{F['date'][t]}")
                if "touch" not in seen and (F["h"][t] >= F["day_hi"][t] or F["l"][t] <= F["day_lo"][t]):
                    seen.add("touch"); up = F["h"][t] >= F["day_hi"][t]; j = D.matched_random(F, t, pools, rng)
                    if j is None:
                        continue
                    back = float(c[t + 12] < F["day_hi"][t]) if up else float(c[t + 12] > F["day_lo"][t])
                    sd = np.sign(c[j] - s_open[j]); rr = np.mean(np.sign(c[j + 12] - c[j]) == -sd)
                    touch["back"].append(back); touch["rnd"].append(rr); touch["blk"].append(f"{F['sym']}|{F['date'][t]}")
    for thr, v in ev.items():
        bl = np.array(v["blk"])
        out[f"H3.1_fuel_{thr}"] = dict(n=len(bl), p_reversal_12=round(float(np.mean(v["rev12"])), 4) if bl.size else None, p_random_12=round(float(np.mean(v["rnd12"])), 4) if bl.size else None,
                                     lift12=D.boot_diff(v["rev12"], v["rnd12"], bl) if bl.size else None, lift24=D.boot_diff(v["rev24"], v["rnd24"], bl) if bl.size else None)
        out[f"H3.1_fuel_{thr}"]["pass"] = bool(bl.size and D.excludes0(out[f"H3.1_fuel_{thr}"]["lift12"]) and out[f"H3.1_fuel_{thr}"]["lift12"]["mean"] > 0)
    bl = np.array(touch["blk"]); out["H3.4_touch"] = dict(n=len(bl), p_back_inside_12=round(float(np.mean(touch["back"])), 4) if bl.size else None, p_random=round(float(np.mean(touch["rnd"])), 4) if bl.size else None, lift=D.boot_diff(touch["back"], touch["rnd"], bl) if bl.size else None)
    out["H3.4_touch"]["pass"] = bool(bl.size and D.excludes0(out["H3.4_touch"]["lift"]) and out["H3.4_touch"]["lift"]["mean"] > 0)
    # H3.2 remaining-range decay: y = (close_end - c_j) / (sqrt(s2_j) c_j); band sqrt(remaining) vs g(slot) = 68.3th pct of |y| on train
    ys, sl, tr, blk = [], [], [], []
    for F in frames:
        c = F["c"]; n = F["n"]; starts = np.where(F["new"])[0]; ends = np.r_[starts[1:], n]; y = np.full(n, np.nan)
        for a, b in zip(starts, ends):
            y[a:b] = (c[b - 1] - c[a:b]) / (np.sqrt(F["s2"][a:b]) * c[a:b])
        idx = np.where(np.isfinite(y))[0]; ys.append(y[idx]); sl.append(F["slot"][idx]); tr.append(F["train"][idx]); blk.append(blocks_of(F, idx))
    ys, sl, tr, blk = (np.concatenate(x) for x in (ys, sl, tr, blk))
    g = np.array([np.percentile(np.abs(ys[tr & (sl == j)]), 68.3) if (tr & (sl == j)).sum() > 100 else np.nan for j in range(D.NBAR)])
    te = ~tr & np.isfinite(g[np.clip(sl, 0, D.NBAR - 1)]) & (sl < D.NBAR - 1)
    rem = np.sqrt(D.NBAR - 1 - sl[te]); ce = (np.abs(ys[te]) <= g[sl[te]]).astype(float); cs = (np.abs(ys[te]) <= rem).astype(float); b2 = blk[te]
    u, inv = np.unique(b2, return_inverse=True); se = np.bincount(inv, weights=ce); ss = np.bincount(inv, weights=cs); cnt = np.bincount(inv).astype(float); bs = []
    for _ in range(1000):
        p = rng.integers(0, len(u), len(u)); n_ = cnt[p].sum(); bs.append(abs(se[p].sum() / n_ - 0.683) - abs(ss[p].sum() / n_ - 0.683))
    out["H3.2_remaining"] = dict(cov_empirical=round(float(ce.mean()), 4), cov_sqrt=round(float(cs.mean()), 4), abs_err_diff=dict(mean=round(float(np.mean(bs)), 4), lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4)), g_by_slot=[round(float(x), 3) for x in g[::6]])
    out["H3.2_remaining"]["pass"] = bool(out["H3.2_remaining"]["abs_err_diff"]["hi"] < 0)
    # H3.3 gap: first-bar variance s2 + lam gap^2 ; QLIKE over the next 12 bars, lam from train grid
    rows = []
    for F in frames:
        c, r = F["c"], F["r"]; r2 = np.where(np.isfinite(r), r ** 2, np.nan); starts = np.where(F["new"])[0]
        for a in starts:
            if a + 13 >= F["n"] or not np.isfinite(F["gap"][a]):
                continue
            V = np.nansum(r2[a + 1:a + 13]); rows.append((F["s2"][a], F["gap"][a] ** 2, V, F["train"][a], f"{F['sym']}|{F['date'][a]}"))
    s2a, g2, V, trn, bl = (np.array([x[i] for x in rows]) for i in range(5)); trn = trn.astype(bool); ok = (V > 0) & (s2a > 0)
    def ql(lam, sel):
        vh = 12 * (s2a[sel] + lam * g2[sel]); return np.log(vh) + V[sel] / vh
    grid = [0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]; best = min(grid, key=lambda L: np.nanmean(ql(L, ok & trn)))
    te = ok & ~trn; d = D.boot_diff(ql(best, te), ql(0, te), bl[te])
    out["H3.3_gap"] = dict(lambda_best_train=best, qlike_gap_minus_plain_test=d, n_sessions=int(te.sum()))
    out["H3.3_gap"]["pass"] = bool(best > 0 and D.excludes0(d) and d["mean"] < 0)
    return out


def h4_ladder(frames, d_grid=(0.5, 0.75, 1.0, 1.25, 1.5)):
    out = {}
    recs = []   # per entry: sym, date, heat bin, state, S0, pnl by d, outcome by d, mae, stop-out flags, structure variants, trailing, horizon variants
    for F in frames:
        for part, mask in (("train", F["train"] & np.isfinite(F["heat"])), ("test", test_mask(F))):
            for t, dr in D.trend_entries(F, mask):
                mv = F["move"][t]
                if not np.isfinite(mv) or mv <= 0:
                    continue
                rec = dict(sym=F["sym"], date=F["date"][t], part=part, hb=int(F["hb"][t]), st=dr, S0=float(F["S0"][t]), tod=int(F["tod"][t]), sq=int(F["sq"][t] in (2, 3)), vix_q=float(F.get("vix_q", np.full(F["n"], np.nan))[t]), event=bool(F.get("event", np.zeros(F["n"], bool))[t]), blk=f"{F['sym']}|{F['date'][t]}", mv=mv / F["c"][t])
                for d_ in d_grid:
                    p, oc, mae, nb = D.sim_trade(F, t, dr, d_ * mv, mv, K); rec[f"pnl_{d_}"] = p; rec[f"out_{d_}"] = oc
                p2, oc2, _, _ = D.sim_trade(F, t, dr, 0.75 * mv, 2 * mv, K); rec["out2x"] = oc2
                rem = max(1, D.NBAR - 1 - int(F["slot"][t])); p78, oc78, _, _ = D.sim_trade(F, t, dr, 0.75 * mv, mv, rem); rec["pnl_rest"] = p78
                pt, oct_, _, _ = D.sim_trade(F, t, dr, 0.75 * mv, mv, K, trail=0.75 * mv); rec["pnl_trail"] = pt; rec["out_trail"] = oct_
                lv = F.get("levels", {}).get(F["date"][t], {}); lv = {k: v for k, v in lv.items() if k in ("val", "vah", "poc", "cw", "pw")}
                dist = D.nearest_adverse_level(lv, F["c"][t], dr)
                sstop = max(0.75 * mv, dist + 0.1 * F["A"][t]) if np.isfinite(dist) else 0.75 * mv
                ps, ocs, _, _ = D.sim_trade(F, t, dr, sstop, mv, K); rec["pnl_struct"] = ps; rec["out_struct"] = ocs; rec["struct_wider"] = bool(sstop > 0.75 * mv)
                recs.append(rec)
    T = pd.DataFrame(recs); tr = T[T.part == "train"]; te = T[T.part == "test"]
    out["n_entries"] = dict(train=int(len(tr)), test=int(len(te)))
    out["base_expectancy_test"] = D.boot_mean(te["pnl_0.75"].to_numpy(), te["blk"].to_numpy())
    # H4.1 per cell heat x trend
    cells = {}
    for hb in range(5):
        for st in (1, -1):
            a = tr[(tr.hb == hb) & (tr.st == st)]; b = te[(te.hb == hb) & (te.st == st)]
            name = f"{RG.HEAT_NAMES[hb]}|{'up' if st > 0 else 'down'}"
            if len(a) < 50 or b["blk"].nunique() < MIN_BLOCKS:
                cells[name] = dict(not_enough_data=True, n_train=int(len(a)), test_blocks=int(b["blk"].nunique())); continue
            best = max(d_grid, key=lambda d_: a[f"pnl_{d_}"].mean())
            diff = D.boot_diff(b[f"pnl_{best}"].to_numpy(), b["pnl_0.75"].to_numpy(), b["blk"].to_numpy())
            cells[name] = dict(best_d_train=best, train_exp_by_d={str(d_): round(float(a[f"pnl_{d_}"].mean()), 5) for d_ in d_grid}, test_diff_vs_075=diff, n_test=int(len(b)), test_blocks=int(b["blk"].nunique()),
                               **{"pass": bool(best != 0.75 and D.excludes0(diff) and diff["mean"] > 0)})
    out["H4.1_cells"] = cells; out["H4.1_pass_any"] = any(v.get("pass") for v in cells.values())
    # H4.2 structure-aware stop vs the base (0.75; H4.1 winner is 0.75 unless a cell passed, handled by reporting both)
    so_b = (te["out_0.75"] == -1).astype(float).to_numpy(); so_s = (te["out_struct"] == -1).astype(float).to_numpy()
    out["H4.2_struct"] = dict(share_wider=round(float(te["struct_wider"].mean()), 4), stopout_struct_minus_base=D.boot_diff(so_s, so_b, te["blk"].to_numpy()), exp_struct_minus_base=D.boot_diff(te["pnl_struct"].to_numpy(), te["pnl_0.75"].to_numpy(), te["blk"].to_numpy()))
    e = out["H4.2_struct"]; e["pass"] = bool(D.excludes0(e["stopout_struct_minus_base"]) and e["stopout_struct_minus_base"]["mean"] < 0 and e["exp_struct_minus_base"]["lo"] >= 0 or (D.excludes0(e["stopout_struct_minus_base"]) and e["stopout_struct_minus_base"]["mean"] < 0 and not D.excludes0(e["exp_struct_minus_base"])))
    # H4.3 target odds by trend x S0 quintile (edges from train)
    edges = np.nanpercentile(tr["S0"], [20, 40, 60, 80]); te = te.assign(s0q=np.searchsorted(edges, te["S0"].to_numpy()))
    pooled1 = D.boot_mean((te["out_0.75"] == 1).astype(float).to_numpy(), te["blk"].to_numpy()); pooled2 = D.boot_mean((te["out2x"] == 1).astype(float).to_numpy(), te["blk"].to_numpy())
    odds = dict(pooled_1x=pooled1, pooled_2x=pooled2, cells={})
    for st in (1, -1):
        for q in range(5):
            b = te[(te.st == st) & (te.s0q == q)]; name = f"{'up' if st > 0 else 'down'}|S0q{q}"
            if b["blk"].nunique() < MIN_BLOCKS:
                odds["cells"][name] = dict(not_enough_data=True, test_blocks=int(b["blk"].nunique())); continue
            r1 = D.boot_mean((b["out_0.75"] == 1).astype(float).to_numpy(), b["blk"].to_numpy()); r2 = D.boot_mean((b["out2x"] == 1).astype(float).to_numpy(), b["blk"].to_numpy())
            odds["cells"][name] = dict(p_1x=r1, p_2x=r2, pass_1x=bool(r1["lo"] > pooled1["mean"] or r1["hi"] < pooled1["mean"]), pass_2x=bool(r2["lo"] > pooled2["mean"] or r2["hi"] < pooled2["mean"]))
    odds["pass_any"] = any(v.get("pass_1x") or v.get("pass_2x") for v in odds["cells"].values()); out["H4.3_odds"] = odds
    # H4.4 time stop (24) vs rest of session
    d44 = D.boot_diff(te["pnl_0.75"].to_numpy(), te["pnl_rest"].to_numpy(), te["blk"].to_numpy()); out["H4.4_timestop"] = dict(exp_24_minus_rest=d44, **{"pass": bool(D.excludes0(d44) and d44["mean"] > 0)})
    d45 = D.boot_diff(te["pnl_trail"].to_numpy(), te["pnl_0.75"].to_numpy(), te["blk"].to_numpy()); out["H4.5_trailing"] = dict(exp_trail_minus_fixed=d45, **{"pass": bool(D.excludes0(d45) and d45["mean"] > 0)})
    # H6.3 sizing and H6.4 heat x trend on the same entries
    te = te.assign(size=np.minimum(2.0, np.nanmedian(te["mv"]) / te["mv"]))
    daily_u = te.groupby("date")["pnl_0.75"].sum(); daily_s = (te["pnl_0.75"] * te["size"]).groupby(te["date"]).sum()
    rng = np.random.default_rng(6); days = daily_u.index.to_numpy(); bs = []
    for _ in range(1000):
        p = rng.integers(0, len(days), len(days)); a = daily_s.iloc[p]; b = daily_u.iloc[p]; bs.append(a.mean() / a.std() - b.mean() / b.std())
    sh = lambda s: round(float(s.mean() / s.std() * np.sqrt(252)), 3)
    out["H6.3_sizing"] = dict(sharpe_unsized=sh(daily_u), sharpe_sized=sh(daily_s), diff=dict(mean=round(float(np.mean(bs)) * np.sqrt(252), 3), lo=round(float(np.percentile(bs, 2.5)) * np.sqrt(252), 3), hi=round(float(np.percentile(bs, 97.5)) * np.sqrt(252), 3)), days=int(len(days)))
    out["H6.3_sizing"]["pass"] = bool(out["H6.3_sizing"]["diff"]["lo"] > 0)
    pooled = out["base_expectancy_test"]; byh = {}
    for hb in range(5):
        b = te[te.hb == hb]; name = RG.HEAT_NAMES[hb]
        if b["blk"].nunique() < MIN_BLOCKS:
            byh[name] = dict(not_enough_data=True, test_blocks=int(b["blk"].nunique())); continue
        e = D.boot_mean(b["pnl_0.75"].to_numpy(), b["blk"].to_numpy()); byh[name] = dict(expectancy=e, n=int(len(b)), **{"pass": bool(e["lo"] > pooled["mean"] or e["hi"] < pooled["mean"])})
    out["H6.4_heat_x_trend"] = dict(pooled=pooled, by_heat=byh, pass_any=any(v.get("pass") for v in byh.values()))
    out["_entries"] = te.drop(columns=[c for c in te.columns if c.startswith("out_") and c not in ("out_0.75",)]).to_dict("list")
    return out


def h2_exits(frames, daily=None):
    out = {}; rng = np.random.default_rng(2)
    rows = []
    for F in frames:
        up, dn = D.exits(F); m = test_mask(F); c, n = F["c"], F["n"]
        pools = D.pools_by_slot(F, m & np.isfinite(F["z24"]) & (np.arange(n) >= K))
        cnt = pd.Series((up | dn).astype(float)).rolling(K).sum().to_numpy()
        for t in np.where(m & (up | dn))[0]:
            if t + 24 >= n:
                continue
            dr = 1 if up[t] else -1; j = D.matched_random(F, t, pools, rng)
            if j is None:
                continue
            jd = np.sign(c[j] - c[j - K]); jd = np.where(jd == 0, 1, jd); jj = np.minimum(j + 24, n - 1)
            rows.append(dict(sym=F["sym"], blk=f"{F['sym']}|{F['date'][t]}", hb=int(F["hb"][t]), sq=int(F["sq"][t] in (2, 3)), st=int(F["st"][t]), dr=dr, with_trend=int(F["st"][t] == dr), against=int(F["st"][t] == -dr),
                             r6=dr * (c[t + 6] - c[t]) / c[t], r12=dr * (c[t + 12] - c[t]) / c[t], r24=dr * (c[t + 24] - c[t]) / c[t], R24=F["R24"][t],
                             q6=float(np.mean(jd * (c[j + 6] - c[j]) / c[j])), q12=float(np.mean(jd * (c[j + 12] - c[j]) / c[j])), q24=float(np.mean(jd * (c[jj] - c[j]) / c[j])), QR24=float(np.nanmean(F["R24"][j])),
                             cont12=float(np.sign(c[t + 12] - c[t]) == dr), cnt=float(cnt[t]), tod=int(F["tod"][t]), vix_q=float(F.get("vix_q", np.full(n, np.nan))[t]), event=bool(F.get("event", np.zeros(n, bool))[t])))
    E = pd.DataFrame(rows); out["n_exits_test"] = int(len(E)); bl = E["blk"].to_numpy()
    out["H2.1_pooled"] = {f"signed_r{k}_minus_random": D.boot_diff(E[f"r{k}"].to_numpy(), E[f"q{k}"].to_numpy(), bl) for k in (6, 12, 24)}
    out["H2.1_pooled"]["range_R24_minus_random"] = D.boot_diff(E["R24"].to_numpy(), E["QR24"].to_numpy(), bl)
    cells = {}
    for hb in range(5):
        for sq in (0, 1):
            b = E[(E.hb == hb) & (E.sq == sq)]; name = f"{RG.HEAT_NAMES[hb]}|{'squeeze' if sq else 'no_squeeze'}"
            if b["blk"].nunique() < MIN_BLOCKS:
                cells[name] = dict(not_enough_data=True, blocks=int(b["blk"].nunique())); continue
            d12 = D.boot_diff(b["r12"].to_numpy(), b["q12"].to_numpy(), b["blk"].to_numpy()); d24 = D.boot_diff(b["r24"].to_numpy(), b["q24"].to_numpy(), b["blk"].to_numpy()); dR = D.boot_diff(b["R24"].to_numpy(), b["QR24"].to_numpy(), b["blk"].to_numpy())
            cells[name] = dict(signed_r12=d12, signed_r24=d24, range_R24=dR, n=int(len(b)), direction_pass=bool(D.excludes0(d12) or D.excludes0(d24)))
    out["H2.1_cells"] = cells
    # daily validation: sign of the signed 5-day return after exits, 2020-22
    if daily is not None:
        rows = []
        for F in daily:
            c, n = F["c"], F["n"]; v = F["valid"]
            for t in np.where(v & (F["exit_up"] | F["exit_dn"]))[0]:
                if t + 5 >= n:
                    continue
                dr = 1 if F["exit_up"][t] else -1; rows.append(dict(blk=f"{F['sym']}|{F['date'][t][:7]}", r5=dr * (c[t + 5] - c[t]) / c[t], hb=int(F["hb"][t]), sq=int(F["sq"][t] in (2, 3))))
        V = pd.DataFrame(rows); out["H2.1_daily_validation"] = dict(n=int(len(V)), signed_r5=D.boot_mean(V["r5"].to_numpy(), V["blk"].to_numpy()))
        cells_v = {}
        for hb in range(5):
            for sq in (0, 1):
                b = V[(V.hb == hb) & (V.sq == sq)]; name = f"{RG.HEAT_NAMES[hb]}|{'squeeze' if sq else 'no_squeeze'}"
                cells_v[name] = D.boot_mean(b["r5"].to_numpy(), b["blk"].to_numpy()) if b["blk"].nunique() >= 50 else dict(not_enough_data=True)
        out["H2.1_daily_validation"]["cells"] = cells_v
        ship_dir = False
        for name, cell in cells.items():
            if cell.get("direction_pass"):
                sgn = np.sign(cell["signed_r12"]["mean"] if D.excludes0(cell["signed_r12"]) else cell["signed_r24"]["mean"]); vv = cells_v.get(name, {})
                if "mean" in vv and np.sign(vv["mean"]) == sgn and D.excludes0(vv):
                    ship_dir = True; cell["validated"] = True
        out["H2.1_pass_direction"] = bool(ship_dir)
    # H2.2 exit clustering: ic of count vs R24 within heat strata (residualize y within sym x heat bin)
    xs, ys, bls, sy = [], [], [], []
    for F in frames:
        up, dn = D.exits(F); cnt = pd.Series((up | dn).astype(float)).rolling(K).sum().to_numpy(); m = test_mask(F) & np.isfinite(F["R24"]) & np.isfinite(cnt) & (F["hb"] >= 0)
        idx = np.where(m)[0]; y = F["R24"][idx].copy(); hb = F["hb"][idx]
        for b in range(5):
            s = hb == b
            if s.any():
                y[s] = y[s] - y[s].mean()
        xs.append(cnt[idx]); ys.append(y); bls.append(blocks_of(F, idx)); sy.append(np.array([F["sym"]] * len(idx)))
    ic, (lo, hi), nb = VT.ic_pooled(np.concatenate(xs), np.concatenate(ys), np.concatenate(bls), np.concatenate(sy))
    out["H2.2_clustering"] = dict(ic=round(float(ic), 4), lo=round(float(lo), 4), hi=round(float(hi), 4), blocks=int(nb), **{"pass": bool(lo > 0)})
    # H2.3 trend vs shock
    a = E[E.with_trend == 1]; b = E[E.against == 1]
    ra = D.boot_mean(a["cont12"].to_numpy(), a["blk"].to_numpy()); rb = D.boot_mean(b["cont12"].to_numpy(), b["blk"].to_numpy())
    out["H2.3_trend_vs_shock"] = dict(with_trend=ra, against_trend=rb, **{"pass": bool(np.isfinite(ra["lo"]) and np.isfinite(rb["lo"]) and (ra["lo"] > rb["hi"] or rb["lo"] > ra["hi"]))})
    out["_exits"] = E.to_dict("list")
    return out


def slot_rank(x, sess, slot, n=20):
    """percent of the same slot's values over the previous n sessions that are below the current value"""
    df = pd.DataFrame({"x": x, "s": sess, "k": slot}); piv = df.pivot_table(index="s", columns="k", values="x", aggfunc="first")
    cols = {}
    for k in piv.columns:
        col = piv[k]; vals = col.to_numpy(); out = np.full(len(vals), np.nan)
        for i in range(len(vals)):
            prev = vals[max(0, i - n):i]; prev = prev[np.isfinite(prev)]
            if len(prev) >= 10 and np.isfinite(vals[i]):
                out[i] = 100 * np.mean(prev < vals[i])
        cols[k] = pd.Series(out, index=piv.index)
    base = pd.DataFrame(cols); lookup = base.stack(future_stack=True); key = pd.MultiIndex.from_arrays([df["s"], df["k"]])
    return lookup.reindex(key).to_numpy(float)


def ic_pair_diff(x1, x2, y, block, sym, draws=1000, seed=0):
    """paired block bootstrap of ic_pooled(x1,y) - ic_pooled(x2,y) with the same block sums machinery"""
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y, "b": block, "s": sym}).dropna()
    for col in ("x1", "x2", "y"):
        rk = df.groupby("s")[col].rank(); n_s = df.groupby("s")[col].transform("size"); df[col] = (rk - (n_s + 1) / 2) / n_s
    g = pd.DataFrame({"a": df["x1"] * df["y"], "aa": df["x1"] ** 2, "b2": df["x2"] * df["y"], "bb": df["x2"] ** 2, "yy": df["y"] ** 2}).groupby(df["b"].to_numpy()).sum().to_numpy(float)
    val = lambda M: M[:, 0].sum() / np.sqrt(M[:, 1].sum() * M[:, 4].sum()) - M[:, 2].sum() / np.sqrt(M[:, 3].sum() * M[:, 4].sum())
    rng = np.random.default_rng(seed); bs = [val(g[rng.integers(0, len(g), len(g))]) for _ in range(draws)]
    return dict(mean=round(float(val(g)), 4), lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4))


def h6_heat(frames):
    out = {}; X = {"rank500": [], "slot20": [], "vixcond": []}; Y, B, S, HB, DH = [], [], [], [], []
    for F in frames:
        m = test_mask(F) & np.isfinite(F["R24"]); x = F["move"] / F["c"]
        sr = slot_rank(x, F["sess"], F["slot"]); vc = RG.percent_rank(x / np.where(np.isfinite(F.get("vix_pct", np.full(F["n"], np.nan))), F["vix_pct"] + 1, np.nan), 500) if "vix_pct" in F else np.full(F["n"], np.nan)
        idx = np.where(m)[0]; X["rank500"].append(F["heat"][idx]); X["slot20"].append(sr[idx]); X["vixcond"].append(vc[idx]); Y.append(F["R24"][idx]); B.append(blocks_of(F, idx)); S.append(np.array([F["sym"]] * len(idx))); HB.append(F["hb"][idx])
        dh = F["heat"] - np.r_[np.full(12, np.nan), F["heat"][:-12]]; DH.append(dh[idx])
    Y, B, S, HB, DH = (np.concatenate(v) for v in (Y, B, S, HB, DH)); X = {k: np.concatenate(v) for k, v in X.items()}
    ics = {}
    for k, x in X.items():
        ic, (lo, hi), nb = VT.ic_pooled(x, Y, B, S); ics[k] = dict(ic=round(float(ic), 4), lo=round(float(lo), 4), hi=round(float(hi), 4), blocks=int(nb))
    best = max(ics, key=lambda k: ics[k]["ic"] if np.isfinite(ics[k]["ic"]) else -9)
    diffs = {o: ic_pair_diff(X[best], X[o], Y, B, S) for o in X if o != best}
    out["H6.1_normalization"] = dict(ics=ics, best=best, best_minus_others=diffs, **{"pass": all(v["lo"] > 0 for v in diffs.values())})
    # H6.2 acceleration within heat strata: residualize y within sym x heat bin
    yr = Y.copy()
    for s_ in np.unique(S):
        for b in range(5):
            sel = (S == s_) & (HB == b)
            if sel.any():
                yr[sel] -= yr[sel].mean()
    ic, (lo, hi), nb = VT.ic_pooled(DH, yr, B, S); out["H6.2_acceleration"] = dict(ic=round(float(ic), 4), lo=round(float(lo), 4), hi=round(float(hi), 4), blocks=int(nb), **{"pass": bool(lo > 0)})
    return out


def h5_squeeze(frames, daily=None):
    out = {}; rng = np.random.default_rng(5)
    # thresholds from train for bb and rv
    bbw_tr, rv_tr = [], []
    for F in frames:
        s = D.squeeze_defs(F); bbw_tr.append(s["bbw"][F["train"]]); rv_tr.append(s["rv"][F["train"]])
    thr_bb = float(np.nanpercentile(np.concatenate(bbw_tr), 10)); thr_rv = float(np.nanpercentile(np.concatenate(rv_tr), 10)); out["thresholds"] = dict(bb=thr_bb, rv=thr_rv, atr=RG.SQZ_THR[5])
    ev = {k: dict(real=[], rnd=[], blk=[]) for k in ("atr", "bb", "kin", "rvr")}; dur = dict(bin=[], exp=[], blk=[]); ex = dict(e12=[], r12=[], e24=[], r24=[], up=[], blk=[]); lunch = dict(l=[], e=[], blk=[]); lowv = dict(low=[], e=[], blk=[]); fade = []
    for F in frames:
        m = test_mask(F); c, h, l, n = F["c"], F["h"], F["l"], F["n"]; s = D.squeeze_defs(F, thr_bb, thr_rv)
        R12 = F["R12"]; med12 = VT.slot_baseline(R12, F["sess"], F["slot"]); R24 = F["R24"]; med24 = VT.slot_baseline(R24, F["sess"], F["slot"])
        exp12 = np.where(np.isfinite(R12) & np.isfinite(med12), (R12 > med12).astype(float), np.nan); exp24 = np.where(np.isfinite(R24) & np.isfinite(med24), (R24 > med24).astype(float), np.nan)
        pools = D.pools_by_slot(F, m & np.isfinite(exp12) & np.isfinite(exp24))
        for k in ev:
            for t in D.first_bars(s[k]):
                if not m[t] or not np.isfinite(exp12[t]):
                    continue
                j = D.matched_random(F, t, pools, rng)
                if j is None:
                    continue
                ev[k]["real"].append(exp12[t]); ev[k]["rnd"].append(float(np.nanmean(exp12[j]))); ev[k]["blk"].append(f"{F['sym']}|{F['date'][t]}")
        inside = F["sq_in"]
        for t in np.where(m & (inside > 0) & np.isfinite(exp12))[0]:
            b = 0 if inside[t] <= 5 else 1 if inside[t] <= 12 else 2 if inside[t] <= 24 else 3; dur["bin"].append(b); dur["exp"].append(exp12[t]); dur["blk"].append(f"{F['sym']}|{F['date'][t]}")
        for t in np.where(m & (F["sq"] == 4) & np.isfinite(exp12) & np.isfinite(exp24))[0]:
            j = D.matched_random(F, t, pools, rng)
            if j is None or t + 12 >= n:
                continue
            ex["e12"].append(exp12[t]); ex["r12"].append(float(np.nanmean(exp12[j]))); ex["e24"].append(exp24[t]); ex["r24"].append(float(np.nanmean(exp24[j]))); ex["up"].append(float(c[t + 12] > c[t])); ex["blk"].append(f"{F['sym']}|{F['date'][t]}")
        for t in D.first_bars(s["atr"]):
            if not m[t] or not np.isfinite(exp12[t]):
                continue
            lunch["l"].append(float(F["tod"][t] == 2)); lunch["e"].append(exp12[t]); lunch["blk"].append(f"{F['sym']}|{F['date'][t]}")
            # mean rvol inside the run
            e_ = t
            while e_ + 1 < n and s["atr"][e_ + 1]:
                e_ += 1
            rv = np.nanmean(F["rvol"][t:e_ + 1]) if np.isfinite(F["rvol"][t:e_ + 1]).any() else np.nan
            if np.isfinite(rv):
                lowv["low"].append(float(rv < 0.8)); lowv["e"].append(exp12[t]); lowv["blk"].append(f"{F['sym']}|{F['date'][t]}")
        # H5.4 fade: swing breaks inside a squeeze
        br = F.get("breaks")
        if br is not None and len(br):
            for _, e in br.iterrows():
                t = int(e["t"]); dr = int(e["dir"])
                if not m[t] or F["sq"][t] not in (2, 3) or not np.isfinite(F["move"][t]):
                    continue
                p, oc, _, _ = D.sim_trade(F, t, -dr, 0.75 * F["move"][t], F["move"][t], K); fade.append(dict(pnl=p, blk=f"{F['sym']}|{F['date'][t]}", tod=int(F["tod"][t]), hb=int(F["hb"][t])))
    for k, v in ev.items():
        bl = np.array(v["blk"]); d = D.boot_diff(v["real"], v["rnd"], bl) if bl.size >= 30 else None
        out[f"H5.1_{k}"] = dict(n=int(bl.size), expansion_real=round(float(np.mean(v["real"])), 4) if bl.size else None, expansion_random=round(float(np.mean(v["rnd"])), 4) if bl.size else None, lift=d, finds_expansion=bool(d and D.excludes0(d) and d["mean"] > 0), calm_persists=bool(d and D.excludes0(d) and d["mean"] < 0))
    Dd = pd.DataFrame(dur); rates = {}
    for b in range(4):
        x = Dd[Dd.bin == b]; rates[("1-5", "6-12", "13-24", ">24")[b]] = D.boot_mean(x["exp"].to_numpy(), x["blk"].to_numpy()) if len(x) else None
    # slope of expansion on bin index by block bootstrap
    u = Dd["blk"].unique(); rng2 = np.random.default_rng(52); bs = []
    g = Dd.groupby("blk").agg(sx=("bin", "sum"), sy=("exp", "sum"), sxx=("bin", lambda s: (s ** 2).sum()), sxy=("bin", lambda s: 0.0), n=("exp", "size"))
    g["sxy"] = (Dd["bin"] * Dd["exp"]).groupby(Dd["blk"]).sum(); G = g.to_numpy(float)
    def slope(M):
        n_ = M[:, 4].sum(); sx, sy, sxx, sxy = M[:, 0].sum(), M[:, 1].sum(), M[:, 2].sum(), M[:, 3].sum(); return (n_ * sxy - sx * sy) / max(n_ * sxx - sx * sx, 1e-12)
    bs = [slope(G[rng2.integers(0, len(G), len(G))]) for _ in range(1000)]
    out["H5.2_duration"] = dict(rates=rates, slope_per_bin=dict(mean=round(float(slope(G)), 5), lo=round(float(np.percentile(bs, 2.5)), 5), hi=round(float(np.percentile(bs, 97.5)), 5)))
    out["H5.2_duration"]["pass"] = bool(out["H5.2_duration"]["slope_per_bin"]["lo"] > 0 or out["H5.2_duration"]["slope_per_bin"]["hi"] < 0)
    bl = np.array(ex["blk"])
    out["H5.3_exit"] = dict(n=int(bl.size), expansion12_minus_random=D.boot_diff(ex["e12"], ex["r12"], bl) if bl.size else None, expansion24_minus_random=D.boot_diff(ex["e24"], ex["r24"], bl) if bl.size else None, p_up_12=D.boot_mean(np.array(ex["up"]), bl) if bl.size else None)
    e = out["H5.3_exit"]; e["pass_expansion"] = bool(bl.size and D.excludes0(e["expansion12_minus_random"])); e["pass_direction"] = bool(bl.size and (e["p_up_12"]["lo"] > 0.5 or e["p_up_12"]["hi"] < 0.5))
    Fd = pd.DataFrame(fade); out["H5.4_fade"] = dict(n=int(len(Fd)), expectancy=D.boot_mean(Fd["pnl"].to_numpy(), Fd["blk"].to_numpy()) if len(Fd) else None)
    out["H5.4_fade"]["pass_test"] = bool(len(Fd) and out["H5.4_fade"]["expectancy"]["lo"] > 0)
    if daily is not None:
        out["H5.4_fade"]["daily_validation"] = fade_daily(daily)
        out["H5.4_fade"]["pass"] = bool(out["H5.4_fade"]["pass_test"] and out["H5.4_fade"]["daily_validation"].get("expectancy", {}).get("lo", -1) > 0)
    L = pd.DataFrame(lunch); a = L[L.l == 1]; b = L[L.l == 0]
    out["H5.5_lunch"] = dict(lunch=D.boot_mean(a["e"].to_numpy(), a["blk"].to_numpy()), other=D.boot_mean(b["e"].to_numpy(), b["blk"].to_numpy()))
    out["H5.5_lunch"]["diff"] = D.boot_diff(np.r_[a["e"].to_numpy(), b["e"].to_numpy()], np.r_[np.full(len(a), b["e"].mean()), np.full(len(b), b["e"].mean())], np.r_[a["blk"].to_numpy(), b["blk"].to_numpy()]) if len(a) and len(b) else None
    out["H5.5_lunch"]["pass"] = bool(len(a) and len(b) and (out["H5.5_lunch"]["lunch"]["lo"] > out["H5.5_lunch"]["other"]["hi"] or out["H5.5_lunch"]["other"]["lo"] > out["H5.5_lunch"]["lunch"]["hi"]))
    Lv = pd.DataFrame(lowv); a = Lv[Lv.low == 1]; b = Lv[Lv.low == 0]
    out["H5.6_low_rvol"] = dict(low=D.boot_mean(a["e"].to_numpy(), a["blk"].to_numpy()) if len(a) else None, normal=D.boot_mean(b["e"].to_numpy(), b["blk"].to_numpy()) if len(b) else None)
    out["H5.6_low_rvol"]["pass"] = bool(len(a) and len(b) and (out["H5.6_low_rvol"]["low"]["lo"] > out["H5.6_low_rvol"]["normal"]["hi"] or out["H5.6_low_rvol"]["normal"]["lo"] > out["H5.6_low_rvol"]["low"]["hi"]))
    out["_fade"] = Fd.to_dict("list") if len(Fd) else {}
    return out


def fade_daily(daily):
    """daily validation of H5.4: swing-high/low breaks (k=5 strict pivots, close beyond) while the daily squeeze is ongoing, fade with stop 0.75 move, target 1x, 5 days"""
    rows = []
    for F in daily:
        c, h, l, n = F["c"], F["h"], F["l"], F["n"]; k = 5
        for i in range(2 * k + 1, n - 6):
            if not F["valid"][i] or F["sq"][i] not in (2, 3) or not np.isfinite(F["move"][i]):
                continue
            # swing levels formed before i: strict pivots at p = i-k.. earlier; use the most recent unbroken pivot high/low
            p = i - k
            for dr, arr, cmp_ in ((1, h, np.greater), (-1, l, np.less)):
                if cmp_(arr[p], arr[p - k:p]).all() and cmp_(arr[p], arr[p + 1:i]).all() and ((c[i] > arr[p]) if dr > 0 else (c[i] < arr[p])) and not ((c[i - 1] > arr[p]) if dr > 0 else (c[i - 1] < arr[p])):
                    pnl, _, _, _ = D.sim_trade(dict(h=h, l=l, c=c, n=n), i, -dr, 0.75 * F["move"][i], F["move"][i], 5); rows.append(dict(pnl=pnl, blk=f"{F['sym']}|{F['date'][i][:7]}"))
    if not rows:
        return dict(n=0, no_validation_possible=True)
    V = pd.DataFrame(rows); return dict(n=int(len(V)), expectancy=D.boot_mean(V["pnl"].to_numpy(), V["blk"].to_numpy()))


# ====================================================================================
# planted tests (family level)
# ====================================================================================
def run_planted(seeds=range(300, 310)):
    res = {}; t0 = time.time()
    def frames_of(world, n=len(list(seeds))):
        return [D.synth_frame(s, world, sessions=200) for s in list(seeds)[:n]]
    # F1 fat tails: t4 world -> empirical band fixes the Gaussian; gauss world -> both fine
    r = {}
    for w in ("t4", "gauss"):
        h11, h12 = h11_fan(frames_of(w)); r[w] = dict(emp_inner=h11["test"]["empirical"]["inner"]["mean"], gauss_inner=h11["test"]["gaussian"]["inner"]["mean"], pinball=h11["test"]["pinball_emp_minus_gauss"], t_df=h11["train"]["t_df"])
    r["pass"] = bool(abs(r["t4"]["emp_inner"] - 0.683) <= 0.02 and abs(r["t4"]["gauss_inner"] - 0.683) > 0.02 and r["t4"]["pinball"]["hi"] < 0 and abs(r["gauss"]["emp_inner"] - 0.683) <= 0.02 and not (r["gauss"]["pinball"]["hi"] < 0))
    res["F1_fat_tails"] = r; print("F1", r, f"{time.time() - t0:.0f}s", flush=True)
    r = {w: h13_season(frames_of(w))["qlike_seasonal_minus_plain"] for w in ("season", "gauss")}
    r["pass"] = bool(r["season"]["hi"] < 0 and not (r["gauss"]["hi"] < 0)); res["F2_seasonality"] = r; print("F2", r, flush=True)
    r = {w: h3_dayrange([D.synth_frame(s_, w, sessions=500) for s_ in list(seeds)])["H3.1_fuel_1.0"]["lift12"] for w in ("revert", "gauss")}
    r["pass"] = bool(r["revert"]["lo"] > 0 and not D.excludes0(r["gauss"])); res["F3_fuel"] = r; print("F3", r, flush=True)
    r = {}
    for w in ("momo", "gauss"):
        e = h2_exits(frames_of(w)); r[w] = e["H2.1_pooled"]["signed_r12_minus_random"]
    r["pass"] = bool(r["momo"]["lo"] > 0 and not D.excludes0(r["gauss"])); res["F5_exits"] = r; print("F5", r, flush=True)
    r = {}
    for w in ("garch", "gauss"):
        e = h6_heat(frames_of(w)); r[w] = e["H6.2_acceleration"]
    r["pass"] = bool(r["garch"]["lo"] > 0 and not (r["gauss"]["lo"] > 0)); res["F6_heat_acceleration"] = r; print("F6", r, flush=True)
    r = {}
    for w in ("sqz", "gauss"):
        fr = frames_of(w)
        # the fixed real-data threshold (PREREG): the synthetic normal regime sits near 1.0, the planted compression crosses it
        e = h5_squeeze(fr)
        r[w] = dict(atr_lift=e["H5.1_atr"]["lift"], duration_slope=e["H5.2_duration"]["slope_per_bin"], n=e["H5.1_atr"]["n"])
    r["pass"] = bool(r["sqz"]["atr_lift"] and r["sqz"]["atr_lift"]["lo"] > 0 and (r["gauss"]["atr_lift"] is None or not D.excludes0(r["gauss"]["atr_lift"])))
    res["F7_squeeze"] = r; print("F7", r, flush=True)
    r = {}
    for w in ("trendodds", "gauss"):
        fr = [D.synth_frame(s_, w, sessions=1000) for s_ in list(seeds)]
        if w == "gauss":
            for F in fr:
                rng = np.random.default_rng(1); F["st"] = rng.choice([-1, 0, 1], F["n"]); F["conf"] = np.ones(F["n"], bool); F["S0"] = rng.random(F["n"])
        e = h4_ladder(fr); cells = e["H4.3_odds"]["cells"]
        r[w] = dict(pooled_1x=e["H4.3_odds"]["pooled_1x"]["mean"], cells_pass=sum(1 for v in cells.values() if v.get("pass_1x")), cells=len([v for v in cells.values() if "p_1x" in v]), base_exp=e["base_expectancy_test"])
    # a random world pays the costs and nothing else: its expectancy interval must contain -2 x cost
    r["pass"] = bool(r["trendodds"]["base_exp"]["lo"] > 0 and r["trendodds"]["cells_pass"] >= 1 and r["gauss"]["cells_pass"] <= 1 and r["gauss"]["base_exp"]["lo"] <= -2 * D.COST <= r["gauss"]["base_exp"]["hi"])
    res["F4_ladder"] = r; print("F4", r, flush=True)
    res["R_regimes"] = RG.planted()
    res["all_pass"] = all(v.get("pass") for v in res.values() if isinstance(v, dict))
    jdump(res, "planted.json"); print("planted all_pass", res["all_pass"], f"{time.time() - t0:.0f}s")


# ====================================================================================
# regime map
# ====================================================================================
def regime_map(frames, V):
    """primary statistic per tool x regime cell, from the stored per-event tables and the frames"""
    dims = dict(trend=("down", "none", "up"), heat=RG.HEAT_NAMES, squeeze=("none", "inside"), vix=("q0", "q1", "q2", "q3", "q4"), tod=RG.TOD_NAMES, day=("ordinary", "event"))
    def cell_of(dim, F, t):
        if dim == "trend": return ("down", "none", "up")[int(F["st"][t]) + 1]
        if dim == "heat": return RG.HEAT_NAMES[int(F["hb"][t])] if F["hb"][t] >= 0 else None
        if dim == "squeeze": return "inside" if F["sq"][t] in (2, 3) else "none"
        if dim == "vix": return f"q{int(F['vix_q'][t])}" if np.isfinite(F["vix_q"][t]) else None
        if dim == "tod": return RG.TOD_NAMES[int(F["tod"][t])]
        if dim == "day": return "event" if F["event"][t] else "ordinary"
    Q = V["H1.1"]["train"]; out = {}
    # T1: |cov-68.3| empirical minus gaussian per cell; T6: ic(heat, R24) per cell; T2: R24 lift per cell (from stored exits); T5: atr squeeze lift per cell;
    # T3: fuel 1.0 reversal lift per cell (recomputed); T4: base expectancy per cell (stored entries)
    E = pd.DataFrame(V["H2"]["_exits"]); T4 = pd.DataFrame(V["H4"]["_entries"])
    for dim, names in dims.items():
        out[dim] = {}
        for name in names:
            cell = {}
            # T1 and T6 from bars
            ce, cg, blk, hx, hy, hs = [], [], [], [], [], []
            for F in frames:
                m = test_mask(F) & np.isfinite(F["z24"]); idx = np.where(m)[0]
                lab = np.array([cell_of(dim, F, t) for t in idx]); sel = idx[lab == name]
                z = F["z24"][sel]; ce.append(((z >= Q["q16"]) & (z <= Q["q84"])).astype(float)); cg.append((np.abs(z) <= 1).astype(float)); blk.append(blocks_of(F, sel))
                ok = np.isfinite(F["R24"][sel]) & np.isfinite(F["heat"][sel]); hx.append(F["heat"][sel][ok]); hy.append(F["R24"][sel][ok]); hs.append(np.array([F["sym"]] * int(ok.sum())))
            ce, cg, blk, hx, hy, hs = (np.concatenate(v) for v in (ce, cg, blk, hx, hy, hs)); nb = len(np.unique(blk))
            if nb < MIN_BLOCKS:
                cell["T1_fan"] = cell["T6_heat"] = "not enough data"
            else:
                cell["T1_fan"] = dict(cov_emp=round(float(ce.mean()), 4), cov_gauss=round(float(cg.mean()), 4), blocks=int(nb), value="value" if abs(ce.mean() - 0.683) < abs(cg.mean() - 0.683) and abs(ce.mean() - 0.683) <= 0.03 else "no value")
                bl2 = blk[np.isfinite(hx[:len(blk)])] if len(hx) == len(blk) else blk[:len(hx)]
                ic, (lo, hi), nbi = VT.ic_pooled(hx, hy, bl2, hs); cell["T6_heat"] = dict(ic=round(float(ic), 4), lo=round(float(lo), 4), hi=round(float(hi), 4), value="value" if lo > 0 else "no value")
            # T2 exits (range) and T4 entries from the stored tables
            key = {"trend": "st", "heat": "hb", "squeeze": "sq", "vix": "vix_q", "tod": "tod", "day": "event"}[dim]
            def sel_rows(df):
                if dim == "trend": return df[df["st"] == {"down": -1, "none": 0, "up": 1}[name]]
                if dim == "heat": return df[df["hb"] == RG.HEAT_NAMES.index(name)]
                if dim == "squeeze": return df[df["sq"] == (1 if name == "inside" else 0)]
                if dim == "vix": return df[df["vix_q"] == float(name[1])]
                if dim == "tod": return df[df["tod"] == RG.TOD_NAMES.index(name)]
                return df[df["event"] == (name == "event")]
            e = sel_rows(E)
            if e["blk"].nunique() < MIN_BLOCKS:
                cell["T2_exits"] = "not enough data"
            else:
                d = D.boot_diff(e["R24"].to_numpy(), e["QR24"].to_numpy(), e["blk"].to_numpy()); d12 = D.boot_diff(e["r12"].to_numpy(), e["q12"].to_numpy(), e["blk"].to_numpy())
                cell["T2_exits"] = dict(range_lift=d, direction_lift=d12, value="value (range)" if D.excludes0(d) and d["mean"] > 0 else "no value")
            if dim != "trend" or name != "none":
                t4 = sel_rows(T4)
                if len(t4) == 0 or t4["blk"].nunique() < MIN_BLOCKS:
                    cell["T4_ladder"] = "not enough data"
                else:
                    ex = D.boot_mean(t4["pnl_0.75"].to_numpy(), t4["blk"].to_numpy()); cell["T4_ladder"] = dict(expectancy=ex, value="value" if ex["lo"] > 0 else "no value")
            else:
                cell["T4_ladder"] = "no entries by construction"
            out[dim][name] = cell
    # T3 and T5 by cell (recompute cheaply from the stored event tables is not possible: their events were not stored with every dim) -> computed in h3/h5 per cell below
    return out


def regime_t3_t5(frames):
    """fuel-1.0 reversal lift and ATR-squeeze expansion lift per regime cell"""
    rng = np.random.default_rng(35); rows3, rows5 = [], []
    for F in frames:
        m = test_mask(F); c, n = F["c"], F["n"]; pools = D.pools_by_slot(F, m & np.isfinite(F["z24"]))
        R12 = F["R12"]; med12 = VT.slot_baseline(R12, F["sess"], F["slot"]); exp12 = np.where(np.isfinite(R12) & np.isfinite(med12), (R12 > med12).astype(float), np.nan)
        starts = np.where(F["new"])[0]; ends = np.r_[starts[1:], n]
        tags = lambda t: dict(blk=f"{F['sym']}|{F['date'][t]}", st=int(F["st"][t]), hb=int(F["hb"][t]), sq=int(F["sq"][t] in (2, 3)), vix_q=float(F["vix_q"][t]), tod=int(F["tod"][t]), event=bool(F["event"][t]))
        for a, b in zip(starts, ends):
            if not m[a]:
                continue
            for t in range(a + 1, b - 24):
                side = np.sign(c[t] - F["s_open"][t])
                if side != 0 and np.isfinite(F["fuel"][t]) and F["fuel"][t] >= 1.0:
                    j = D.matched_random(F, t, pools, rng)
                    if j is not None:
                        sd = np.sign(c[j] - F["s_open"][j]); rows3.append(dict(rev=float(np.sign(c[t + 12] - c[t]) == -side), rnd=float(np.mean(np.sign(c[j + 12] - c[j]) == -sd)), **tags(t)))
                    break
        for t in np.where(m & (F["sq"] == 1) & np.isfinite(exp12))[0]:
            j = D.matched_random(F, t, pools, rng)
            if j is not None:
                rows5.append(dict(real=exp12[t], rnd=float(np.nanmean(exp12[j])), **tags(t)))
    return pd.DataFrame(rows3), pd.DataFrame(rows5)


# ====================================================================================
def main():
    cmd = sys.argv[1]
    if cmd == "planted":
        run_planted(); return
    if cmd == "frames":
        build_real_frames(); return
    frames, cut = load_frames(); daily = load_daily()
    if cmd == "p1":
        h11, h12 = h11_fan(frames); part = {"H1.1": h11, "H1.2": h12}
        # daily validation of the train band at k=5
        cov, blk = [], []
        for F in daily:
            z = F["z5"]; m = F["valid"] & np.isfinite(z); idx = np.where(m)[0]; cov.append(((z[idx] >= h11["train"]["q16"]) & (z[idx] <= h11["train"]["q84"])).astype(float)); blk.append(np.array([f"{F['sym']}|{F['date'][i][:7]}" for i in idx]))
        cov, blk = np.concatenate(cov), np.concatenate(blk); part["H1.1"]["daily_validation"] = D.boot_mean(cov, blk); part["H1.1"]["daily_validation"]["pass"] = bool(abs(part["H1.1"]["daily_validation"]["mean"] - 0.683) <= 0.03)
        part["H1.3"] = h13_season(frames); part["H1.4"] = h14_horizon(frames); part["H1.5"] = h15_events(frames, h11["train"]); part["H3"] = h3_dayrange(frames)
        merge_verdict(part); print(json.dumps({k: (v.get("pass"), {kk: vv.get("pass") for kk, vv in v.items() if isinstance(vv, dict) and "pass" in vv}) for k, v in part.items()}, indent=1, default=str))
    elif cmd == "p2":
        merge_verdict({"H4": h4_ladder(frames)}); V = json.load(open(os.path.join(OUT, "verdict.json")))["H4"]; print({k: v for k, v in V.items() if k != "_entries" and k != "H4.1_cells"}, {k: v.get("pass") for k, v in V["H4.1_cells"].items()})
    elif cmd == "p3":
        part = {"H2": h2_exits(frames, daily), "H6": h6_heat(frames)}; merge_verdict(part); print({k: v for k, v in part["H2"].items() if not k.startswith("_") and k != "H2.1_cells"}, part["H6"])
    elif cmd == "p4":
        part = {"H5": h5_squeeze(frames, daily)}; merge_verdict(part); print({k: v for k, v in part["H5"].items() if not k.startswith("_")})
    elif cmd == "map":
        V = json.load(open(os.path.join(OUT, "verdict.json"))); M = regime_map(frames, V); r3, r5 = regime_t3_t5(frames)
        dims = dict(trend=("down", "none", "up"), heat=RG.HEAT_NAMES, squeeze=("none", "inside"), vix=("q0", "q1", "q2", "q3", "q4"), tod=RG.TOD_NAMES, day=("ordinary", "event"))
        for dim, names in dims.items():
            for name in names:
                def sel(df):
                    if dim == "trend": return df[df["st"] == {"down": -1, "none": 0, "up": 1}[name]]
                    if dim == "heat": return df[df["hb"] == RG.HEAT_NAMES.index(name)]
                    if dim == "squeeze": return df[df["sq"] == (1 if name == "inside" else 0)]
                    if dim == "vix": return df[df["vix_q"] == float(name[1])]
                    if dim == "tod": return df[df["tod"] == RG.TOD_NAMES.index(name)]
                    return df[df["event"] == (name == "event")]
                a = sel(r3); b = sel(r5)
                M[dim][name]["T3_fuel"] = (lambda d: dict(reversal_lift=d, value="value" if D.excludes0(d) and d["mean"] > 0 else "no value"))(D.boot_diff(a["rev"].to_numpy(), a["rnd"].to_numpy(), a["blk"].to_numpy())) if len(a) and a["blk"].nunique() >= MIN_BLOCKS else "not enough data"
                M[dim][name]["T5_squeeze"] = (lambda d: dict(expansion_lift=d, value="value (calm persists)" if D.excludes0(d) and d["mean"] < 0 else "no value"))(D.boot_diff(b["real"].to_numpy(), b["rnd"].to_numpy(), b["blk"].to_numpy())) if len(b) and b["blk"].nunique() >= MIN_BLOCKS else "not enough data"
        jdump(M, "regime_map.json"); print("map written")


if __name__ == "__main__":
    main()
