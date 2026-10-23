"""Trendline settings backtest: which combination of pivot size, hold-until-broken and required touches gives
breaks that actually pay - on 5m and 15m, 7 stocks, with a held-out test.

Trade: at the close of the bar that closes through the line, go in the break's direction; exit after H bars
(5m: 12 = 1 h, 15m: 8 = 2 h), never past the session close. Result per trade in ATR(14) units, minus a cost of
0.02% of price for the round trip. Edge = mean result minus the mean of ALL bars in the same direction over the
same horizon (the drift any entry would have caught).
Selection: the best combination on the FIRST 60% of each symbol's dates (min 150 trades); its result on the LAST
40% is the honest number. Significance on the test part: 2,000 random-entry draws with the same number of
up / down trades per symbol (one-sided p).
Data: data/intraday/<SYM>_15m.csv and <SYM>_5m_alpaca.csv (Alpaca IEX, 2025-04-01 .. 2026-10-22).
"""
import sys, pathlib, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
FILES = {"15m": "{s}_15m.csv", "5m": "{s}_5m_alpaca.csv"}
HORIZON = {"15m": 8, "5m": 12}
COST = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0002
GRID = list(itertools.product((2, 3, 4, 5, 7, 10), (False, True), (0, 1, 2)))
rng = np.random.default_rng(7)


def load(tf, s):
    d = pd.read_csv(ROOT / "data/intraday" / FILES[tf].format(s=s))
    t = pd.to_datetime(d["time"], utc=True).dt.tz_convert("America/New_York")
    h, l, c = (d[x].to_numpy(float) for x in ("high", "low", "close"))
    prev = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    day = t.dt.date.to_numpy()
    # last bar index of each bar's session -> exits never cross the close
    last = pd.Series(np.arange(len(d))).groupby(day).transform("max").to_numpy()
    return h, l, c, atr, day, last


def breaks(h, l, c, atr, k, hold, need):
    """+1 / -1 at bars that close through the current red / green line (Pine logic, see vzones/ranges.py),
    counted only if the line had been touched `need` times (within 0.1 ATR without closing through)."""
    n = len(c); out = np.zeros(n, int)
    for side, x in ((1, h), (-1, l)):
        last = None; line = None; broke = True; touch = 0
        for i in range(2 * k, n):
            p = i - k
            w = x[p - k:p + k + 1]
            if side == 1:
                piv = x[p] == w.max() and (x[p - k:p] < x[p]).all()
            else:
                piv = x[p] == w.min() and (x[p - k:p] > x[p]).all()
            if piv:
                ok = last is not None and (x[p] < last[1] if side == 1 else x[p] > last[1])
                if ok and (not hold or broke or line is None):
                    line = (last[0], last[1], (x[p] - last[1]) / (p - last[0])); broke = False; touch = 0
                last = (p, x[p])
            if line is not None and not broke:
                y = line[1] + line[2] * (i - line[0])
                if (side == 1 and c[i] > y) or (side == -1 and c[i] < y):
                    broke = True
                    if touch >= need:
                        out[i] = side
                elif abs((h[i] if side == 1 else l[i]) - y) <= 0.1 * atr[i]:
                    touch += 1
    return out


def outcomes(c, atr, last, H):
    j = np.minimum(np.arange(len(c)) + H, last)
    move = (c[j] - c) / atr
    cost = COST * c / atr
    valid = j > np.arange(len(c))
    return move, cost, valid


def evaluate(tf):
    data = {s: load(tf, s) for s in SYMS}
    H = HORIZON[tf]
    pre = {}
    for s, (h, l, c, atr, day, last) in data.items():
        move, cost, valid = outcomes(c, atr, last, H)
        days = np.array(sorted(set(day)))
        cut = days[int(len(days) * 0.6)]
        pre[s] = (move, cost, valid, day < cut)
    rows = []
    sigs = {}
    for k, hold, need in GRID:
        res = {"train": [], "test": []}
        base = {"train": [], "test": []}
        for s, (h, l, c, atr, day, last) in data.items():
            b = breaks(h, l, c, atr, k, hold, need)
            sigs[(k, hold, need, s)] = b
            move, cost, valid, is_train = pre[s]
            for part, mask in (("train", is_train), ("test", ~is_train)):
                for sgn in (1, -1):
                    idx = np.where((b == sgn) & valid & mask)[0]
                    res[part] += list(sgn * move[idx] - cost[idx])
                    allx = np.where(valid & mask)[0]
                    base[part].append((len(idx), np.mean(sgn * move[allx])))
        row = {"k": k, "hold": hold, "touches": need}
        for part in ("train", "test"):
            r = np.array(res[part]); n = len(r)
            b = sum(cnt * m for cnt, m in base[part]) / max(n, 1)       # drift expected for this trade mix
            row[f"{part}_n"] = n
            row[f"{part}_edge"] = (r.mean() - b) if n else np.nan
            row[f"{part}_hit"] = (r > 0).mean() * 100 if n else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    elig = df[df.train_n >= 150]
    best = elig.sort_values("train_edge", ascending=False).iloc[0]
    # permutation test of the chosen combination on the test part
    k, hold, need = int(best.k), bool(best.hold), int(best.touches)
    obs, draws = [], []
    per_sym = []
    for s, (h, l, c, atr, day, last) in data.items():
        move, cost, valid, is_train = pre[s]
        b = sigs[(k, hold, need, s)]
        test = valid & ~is_train
        pool = np.where(test)[0]
        for sgn in (1, -1):
            idx = np.where((b == sgn) & test)[0]
            obs += list(sgn * move[idx] - cost[idx])
            per_sym.append((sgn, idx.size, pool, move, cost))
    obs_mean = np.mean(obs)
    for _ in range(2000):
        rr = []
        for sgn, m, pool, move, cost in per_sym:
            if m:
                pick = rng.choice(pool, m, replace=False)
                rr.append(sgn * move[pick] - cost[pick])
        draws.append(np.mean(np.concatenate(rr)))
    p = (np.sum(np.array(draws) >= obs_mean) + 1) / (len(draws) + 1)
    return df, best, p


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for tf in ("15m", "5m"):
        df, best, p = evaluate(tf)
        print(f"\n===== {tf}: exit after {HORIZON[tf]} bars, edge in ATR per trade (after cost, above drift) =====")
        show = df.sort_values("train_edge", ascending=False)
        print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        cur = df[(df.k == 5) & (df.hold) & (df.touches == 0)].iloc[0]
        old = df[(df.k == 2) & (~df.hold) & (df.touches == 0)].iloc[0]
        print(f"\nBEST on train: k={int(best.k)} hold={bool(best.hold)} touches={int(best.touches)} -> "
              f"TEST edge {best.test_edge:.3f} ATR, hit {best.test_hit:.1f}%, n={int(best.test_n)}, permutation p={p:.3f}")
        print(f"current default (k=5 hold, 0 touches): TEST edge {cur.test_edge:.3f}, hit {cur.test_hit:.1f}%, n={int(cur.test_n)}")
        print(f"original (k=2 latest, 0 touches):       TEST edge {old.test_edge:.3f}, hit {old.test_hit:.1f}%, n={int(old.test_n)}")
