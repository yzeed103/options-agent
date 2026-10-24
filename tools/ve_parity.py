"""Parity of the indicator's expected move (EWMA variance of session returns, 1 sigma over k bars) against
vzones.vol_engine on TradingView's own bars.

    python tools/ve_parity.py --version 44.0 [--symbol BATS:SPY --tf 5]"""
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
from vzones import vol_engine as VE  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import rvol_parity as RP  # noqa: E402
import tv_pine_test as T  # noqa: E402

TITLES = {"move": "الحركة المتوقّعة (1σ)", "s2": "تباين EWMA"}
JS = RP.JS.replace('if (t && t.startsWith("RVOL")) col = i + 1;', 'const T = __T__; for (const k in T) if (t === T[k]) cols[k] = i + 1;').replace("let col = -1;", "let cols = {};").replace(
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[col] != null) ? r[col] : null]);",
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[cols.move] != null) ? r[cols.move] : null, (r && r[cols.s2] != null) ? r[cols.s2] : null]);").replace("out.rows = rows; out.col = col;", "out.rows = rows; out.cols = cols;")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", required=True); ap.add_argument("--symbol", default="BATS:SPY"); ap.add_argument("--tf", default="5")
    a = ap.parse_args()
    ws = T.page(); ws.settimeout(600)
    js = JS.replace("__T__", json.dumps(TITLES, ensure_ascii=False)) % (json.dumps(T.SCRIPT), json.dumps(a.version), json.dumps(a.symbol), json.dumps(a.tf))
    out = json.loads(T.run(ws, js))
    print("after:", out.get("after"), "| err:", out.get("err"), out.get("restoreErr"), "| cols:", out.get("cols"))
    rows = out["rows"]
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], unit="s", utc=True)).tz_convert("America/New_York")
    d = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}, index=idx)
    tv_move = np.array([np.nan if r[6] is None else r[6] for r in rows], float); tv_s2 = np.array([np.nan if r[7] is None else r[7] for r in rows], float)
    reg = (d.index.time >= dt.time(9, 30)) & (d.index.time < dt.time(16, 0))
    d = d[reg]; tv_move = tv_move[reg]; tv_s2 = tv_s2[reg]
    sess, _ = VT.sessions_slots(d.index, int(a.tf)); r = VE.session_returns(d, sess)
    lam = 0.99 if int(a.tf) <= 5 else 0.97; k = 24 if int(a.tf) <= 5 else 8 if int(a.tf) <= 15 else 2
    s2 = VE.ewma_var(r, lam); move = np.sqrt(k * s2) * d["close"].to_numpy()
    res = {"version": a.version, "symbol": out.get("sym"), "tf": out.get("res"), "bars": len(d)}
    for name, tv, py in (("s2", tv_s2, s2), ("move", tv_move, move)):
        ok = np.isfinite(tv) & np.isfinite(py); ok[:300] = False
        rel = np.abs(tv[ok] - py[ok]) / np.maximum(np.abs(py[ok]), 1e-12)
        res[name] = dict(compared=int(ok.sum()), within_1e6_rel=round(float(np.mean(rel <= 1e-6)), 5), within_1e3_rel=round(float(np.mean(rel <= 1e-3)), 5), max_rel=float(rel.max()))
    print(res)
    json.dump(res, open(os.path.join(ROOT, "reports", "vol_engine", "parity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
