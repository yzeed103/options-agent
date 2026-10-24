"""Parity of the indicator's trend-model section (strength S0, state, inertia, break markers) against
vzones.trend_volume_model on TradingView's own bars.

    python tools/tvm_parity.py --version 42.0 [--symbol BATS:SPY --tf 5]

Switches the visible chart to the symbol / timeframe, loads ~60 sessions, adds a temporary copy, reads the four
data-window plots and the bars, restores the chart, compares per bar. Writes reports/trend_volume_model/parity.json."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import trend_volume_model as TM  # noqa: E402
import rvol_parity as RP  # noqa: E402
import tv_pine_test as T  # noqa: E402

TITLES = {"S0": "قوة الاتجاه S0", "state": "حالة الاتجاه", "I": "القصور الذاتي", "brk": "اختراق"}
JS = RP.JS.replace('if (t && t.startsWith("RVOL")) col = i + 1;', 'const T = %s; for (const k in T) if (t === T[k]) cols[k] = i + 1;').replace("let col = -1;", "let cols = {};").replace(
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[col] != null) ? r[col] : null]);",
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[cols.S0] != null) ? r[cols.S0] : null, (r && r[cols.state] != null) ? r[cols.state] : null, (r && r[cols.I] != null) ? r[cols.I] : null, (r && r[cols.brk] != null) ? r[cols.brk] : null]);").replace(
    "out.rows = rows; out.col = col;", "out.rows = rows; out.cols = cols;")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True); ap.add_argument("--symbol", default="BATS:SPY"); ap.add_argument("--tf", default="5")
    a = ap.parse_args()
    ws = T.page(); ws.settimeout(600)
    js = JS.replace("const T = %s;", "const T = " + json.dumps(TITLES, ensure_ascii=False) + ";")
    js = js % (json.dumps(T.SCRIPT), json.dumps(a.version), json.dumps(a.symbol), json.dumps(a.tf))
    out = json.loads(T.run(ws, js))
    print("after:", out.get("after"), "| err:", out.get("err"), out.get("restoreErr"), "| cols:", out.get("cols"))
    rows = out["rows"]
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], unit="s", utc=True)).tz_convert("America/New_York")
    d = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}, index=idx)
    tv = {k: np.array([np.nan if r[6 + i] is None else r[6 + i] for r in rows], float) for i, k in enumerate(("S0", "state", "I", "brk"))}
    reg = (d.index.time >= dt.time(9, 30)) & (d.index.time < dt.time(16, 0))
    d = d[reg]; tv = {k: v[reg] for k, v in tv.items()}
    res = TM.run(d, int(a.tf)); bars = res["bars"]; br = res["breaks"]
    py = {"S0": bars["S0"].to_numpy(), "state": bars["state"].to_numpy(float), "I": bars["I"].to_numpy()}
    pyb = np.zeros(len(d));
    for t, dr in zip(br["t"], br["dir"]):
        pyb[int(t)] = dr
    out_ = {"version": a.version, "symbol": out.get("sym"), "tf": out.get("res"), "bars": len(d), "sessions": len(set(d.index.date))}
    warm = 300
    for k in ("S0", "I"):
        ok = np.isfinite(tv[k]) & np.isfinite(py[k]); ok[:warm] = False
        diff = np.abs(tv[k][ok] - py[k][ok])
        out_[k] = dict(compared=int(ok.sum()), within_1e6=round(float(np.mean(diff <= 1e-6)), 5), within_1e3=round(float(np.mean(diff <= 1e-3)), 5), max_abs_diff=float(diff.max()))
    ok = np.isfinite(tv["state"]); ok[:warm] = False
    out_["state"] = dict(compared=int(ok.sum()), agree=round(float(np.mean(tv["state"][ok] == py["state"][ok])), 5))
    okb = np.isfinite(tv["brk"]); okb[:warm] = False
    tvb = np.nan_to_num(tv["brk"])
    both = (tvb != 0) & (pyb != 0) & okb; either = ((tvb != 0) | (pyb != 0)) & okb
    out_["breaks"] = dict(tv=int((tvb[okb] != 0).sum()), py=int((pyb[okb] != 0).sum()), same_bar_same_dir=int((both & (tvb == pyb)).sum()), jaccard=round(float((both & (tvb == pyb)).sum() / max(either.sum(), 1)), 4))
    only_tv = np.where((tvb != 0) & (pyb == 0) & okb)[0]; only_py = np.where((pyb != 0) & (tvb == 0) & okb)[0]
    sess = np.array([x.date() for x in d.index]); pos = np.array([int(np.sum(sess[:i] == sess[i])) for i in range(len(d))]) if len(d) < 20000 else None
    out_["mismatch"] = {"only_tv": [[str(d.index[i]), int(pos[i]) if pos is not None else -1, float(tvb[i])] for i in only_tv[:20]],
                        "only_py": [[str(d.index[i]), int(pos[i]) if pos is not None else -1, float(pyb[i])] for i in only_py[:20]]}
    print(out_)
    json.dump(out_, open(os.path.join(ROOT, "reports", "trend_volume_model", "parity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
