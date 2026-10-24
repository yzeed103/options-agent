"""Parity of the v2 volatility plots (seasonal expected move, same-slot heat rank, remaining move to the close)
against the Python reference on TradingView's own bars.

    python tools/ve2_parity.py --version 49.0 [--symbol BATS:SPY --tf 5]"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import vol_engine as VE  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
from vzones import vol_engine_dev as D  # noqa: E402
import rvol_parity as RP  # noqa: E402
import tv_pine_test as T  # noqa: E402
import vol_engine_dev_eval as EV  # noqa: E402

TITLES = {"move": "الحركة المتوقّعة (1σ)", "heat": "حرارة التذبذب (ترتيب وقت اليوم)", "rem": "المتبقّي حتى الإغلاق (1σ)"}
JS = RP.JS.replace('if (t && t.startsWith("RVOL")) col = i + 1;', 'const T = __T__; for (const k in T) if (t === T[k]) cols[k] = i + 1;').replace("let col = -1;", "let cols = {};").replace(
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[col] != null) ? r[col] : null]);",
    "rows.push([v[0], v[1], v[2], v[3], v[4], v[5], (r && r[cols.move] != null) ? r[cols.move] : null, (r && r[cols.heat] != null) ? r[cols.heat] : null, (r && r[cols.rem] != null) ? r[cols.rem] : null]);").replace("out.rows = rows; out.col = col;", "out.rows = rows; out.cols = cols;")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", required=True); ap.add_argument("--symbol", default="BATS:SPY"); ap.add_argument("--tf", default="5")
    a = ap.parse_args(); ship = json.load(open(os.path.join(ROOT, "reports", "vol_engine_dev", "ship.json")))
    ws = T.page(); ws.settimeout(600)
    js = JS.replace("__T__", json.dumps(TITLES, ensure_ascii=False)) % (json.dumps(T.SCRIPT), json.dumps(a.version), json.dumps(a.symbol), json.dumps(a.tf))
    out = json.loads(T.run(ws, js))
    print("after:", out.get("after"), "| err:", out.get("err"), out.get("restoreErr"), "| cols:", out.get("cols"))
    rows = out["rows"]
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], unit="s", utc=True)).tz_convert("America/New_York")
    d = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}, index=idx)
    tv = {k: np.array([np.nan if r[6 + i] is None else r[6 + i] for r in rows], float) for i, k in enumerate(("move", "heat", "rem"))}
    reg = (d.index.time >= dt.time(9, 30)) & (d.index.time < dt.time(16, 0)); d = d[reg]; tv = {k: v[reg] for k, v in tv.items()}
    sess, slot = VT.sessions_slots(d.index, int(a.tf)); r = VE.session_returns(d, sess); c = d["close"].to_numpy()
    prof = np.array(ship["slot_profile_5m"]); g = np.array(ship["remaining_g_by_slot"])
    F = dict(r=r, slot=slot, train=np.ones(len(c), bool))
    s2s, _ = D.seasonal_var(F, prof); move = np.sqrt(24 * s2s) * c
    s2 = VE.ewma_var(r, 0.99); rem = g[np.clip(slot, 0, 77)] * np.sqrt(s2) * c
    heat = EV.slot_rank(move / c, sess, slot)
    res = {"version": a.version, "symbol": out.get("sym"), "tf": out.get("res"), "bars": int(len(c))}
    for name, py in (("move", move), ("heat", heat), ("rem", rem)):
        x = tv[name]; ok = np.isfinite(x) & np.isfinite(py); ok[:400] = False
        rel = np.abs(x[ok] - py[ok]) / np.maximum(np.abs(py[ok]), 1e-9)
        res[name] = dict(compared=int(ok.sum()), within_1e6_rel=round(float(np.mean(rel <= 1e-6)), 5) if ok.any() else None, within_1e3_rel=round(float(np.mean(rel <= 1e-3)), 5) if ok.any() else None, max_abs=float(np.max(np.abs(x[ok] - py[ok]))) if ok.any() else None)
    print(res); json.dump(res, open(os.path.join(ROOT, "reports", "vol_engine_dev", "parity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
