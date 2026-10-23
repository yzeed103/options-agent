"""Pre-registration B (reports/invention/PREREG_OFI.md): order flow imbalance before first touches of our levels.

    python tools/ofi_levels.py --count       # how many events (no quotes fetched)
    python tools/ofi_levels.py               # fetch (resumable) + analyse
    python tools/ofi_levels.py --analyse     # analyse what is fetched
Always runs on the consolidated SIP feed. Keys read in-process from GEXRadar's config, never printed.
"""
from __future__ import annotations

import os
os.environ["VZ_TAG"] = "sip"

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import timedelta  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, eyes  # noqa: E402

SYMS = ["SPY", "QQQ", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD"]
TYPES = {"cw", "pw", "cwoi", "pwoi", "flip", "whale_poc", "whale_vah", "whale_val"}
DAYS = 60
WINDOW = 60                    # seconds of quotes before the touch
OUT = os.path.join(data.RUNTIME, "ofi_events.jsonl")


def events() -> list[dict]:
    out = []
    for s in SYMS:
        b = data.load_bars(s)
        fr = eyes.build(s, b, tfs=(5,), paths=False)
        d = fr[5]
        days = [x for x in sorted(set(d.session)) if np.isfinite(d.loc[d.session == x, "cw"].iat[0])][-DAYS:]
        ev = eyes.level_events(s, 5, d[d.session.isin(days)], fr["whale"], fr["whale_va"])
        out += [dict(e, key=f"{s}|{e['time'].isoformat()}|{e['type']}|{e['level']:.4f}|{e['real']}") for e in ev if e["type"] in TYPES]
    return out


def ofi(q: pd.DataFrame) -> tuple[float, float, int]:
    pb, qb, pa, qa = (q[k].to_numpy(float) for k in ("bid_price", "bid_size", "ask_price", "ask_size"))
    if len(pb) < 2:
        return np.nan, np.nan, len(pb)
    e = ((pb[1:] >= pb[:-1]) * qb[1:] - (pb[1:] <= pb[:-1]) * qb[:-1]
         - (pa[1:] <= pa[:-1]) * qa[1:] + (pa[1:] >= pa[:-1]) * qa[:-1])
    depth = np.mean((qb + qa) / 2)
    return float(e.sum()), float(e.sum() / depth) if depth > 0 else np.nan, len(pb)


def _j(o):
    """JSON for numpy scalars and timestamps."""
    return o.item() if hasattr(o, "item") else str(o)


def call(fn, *a, tries=6):
    for k in range(tries):
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001 - rate limit or network: wait and retry
            if k == tries - 1:
                raise
            time.sleep(10 * (k + 1))


def fetch(evs: list[dict]) -> None:
    from alpaca.data.requests import StockQuotesRequest, StockTradesRequest
    from alpaca.data.enums import DataFeed
    cl = data._client()
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["key"] for l in open(OUT, encoding="utf-8")}
    todo = [e for e in evs if e["key"] not in done]
    print("to fetch", len(todo), "done", len(done), flush=True)
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8") as f:
        for n, e in enumerate(todo):
            sym, L, a = e["sym"], e["level"], e["approach"]
            bar0 = pd.Timestamp(e["time"]).tz_convert("UTC")
            rec = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in e.items()}
            tr = call(lambda: cl.get_stock_trades(StockTradesRequest(symbol_or_symbols=sym, start=bar0.to_pydatetime(),
                                                                       end=(bar0 + timedelta(minutes=5)).to_pydatetime(), feed=DataFeed.SIP)).df)
            if tr is None or tr.empty:
                rec["skip"] = "no trades"; f.write(json.dumps(rec, default=_j) + "\n"); continue
            tr = tr.reset_index()
            hit = tr[(tr.price >= L) if a > 0 else (tr.price <= L)]
            if hit.empty:
                rec["skip"] = "no trade at the level"; f.write(json.dumps(rec, default=_j) + "\n"); continue
            ts = pd.Timestamp(hit.timestamp.iloc[0])
            q = call(lambda: cl.get_stock_quotes(StockQuotesRequest(symbol_or_symbols=sym, start=(ts - timedelta(seconds=WINDOW)).to_pydatetime(),
                                                                      end=ts.to_pydatetime(), feed=DataFeed.SIP)).df)
            q = q.reset_index() if q is not None and not q.empty else pd.DataFrame()
            if len(q):
                q = q[(q.bid_price > 0) & (q.ask_price > 0) & (q.ask_price >= q.bid_price)]
            raw, norm, nq = ofi(q) if len(q) else (np.nan, np.nan, 0)
            rec.update(touch_ts=ts.isoformat(), ofi=raw, ofi_norm=norm, signed=(norm * a) if np.isfinite(norm) else None, quotes=nq)
            f.write(json.dumps(rec, default=_j) + "\n")
            if n % 50 == 0:
                f.flush()
                print(n, "/", len(todo), f"{time.time() - t0:.0f}s", flush=True)


def analyse() -> dict:
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    d = pd.DataFrame(rows)
    res = {"events": len(d), "skipped": int(d.get("skip", pd.Series(dtype=object)).notna().sum())}
    d = d[d.signed.notna()].copy() if "signed" in d else d.iloc[:0]
    d["date"] = d.time.str[:10]
    d["pos"] = d.signed > 0
    res["used"] = len(d)

    def split(x, label):
        x = x.copy()
        g = pd.factorize(x.sym + x.date)[0]; k = g.max() + 1
        p, a = x.passed.to_numpy(float), x.pos.to_numpy(bool)
        s1, c1 = np.bincount(g, p * a, k), np.bincount(g, a.astype(float), k)
        s0, c0 = np.bincount(g, p * ~a, k), np.bincount(g, (~a).astype(float), k)
        dr = np.random.default_rng(0).integers(0, k, (2000, k))
        bs = s1[dr].sum(1) / np.maximum(c1[dr].sum(1), 1) - s0[dr].sum(1) / np.maximum(c0[dr].sum(1), 1)
        return dict(label=label, n=len(x), n_pos=int(a.sum()), pass_pos=float(p[a].mean()), pass_neg=float(p[~a].mean()),
                    diff=float(p[a].mean() - p[~a].mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))
    real, pseudo = d[d.real == 1], d[d.real == 0]
    res["H1"] = split(real, "real levels")
    res["H2"] = split(pseudo, "pseudo levels")
    q = real.signed.quantile([1 / 3, 2 / 3])
    top, bot = real[real.signed >= q.iloc[1]], real[real.signed <= q.iloc[0]]
    res["H3"] = dict(top_pass=float(top.passed.mean()), bottom_pass=float(bot.passed.mean()), n_each=len(top))
    res["by_type"] = {t: split(g, t) for t, g in real.groupby("type") if len(g) >= 30 and g.pos.nunique() == 2}
    res["H1_success"] = bool(res["H1"]["diff"] >= 0.05 and res["H1"]["lo"] > 0)
    p = os.path.join(data.REPORTS, "invention")
    os.makedirs(p, exist_ok=True)
    json.dump(res, open(os.path.join(p, "ofi_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    if a.analyse:
        analyse(); sys.exit()
    ev = events()
    print("events", len(ev), "real", sum(e["real"] for e in ev), pd.Series([e["type"] for e in ev]).value_counts().to_dict())
    if a.count:
        sys.exit()
    fetch(ev)
    analyse()
