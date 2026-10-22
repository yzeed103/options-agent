"""Do the OI walls (CWOI / PWOI) stay fixed inside a session? Uses the full strike tables GEXRadar keeps in
snap_detail (every ~10 min, last 7 days). Compares with the gamma walls in the same snapshots. Read-only."""
import sqlite3, json, zlib, sys, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, r"C:\project\options-agent")
from vzones.gex_block import oi_walls

NY = ZoneInfo("America/New_York")
c = sqlite3.connect("file:C:/project/gex_radar/data/snapshots.db?mode=ro", uri=True)
days, vint = {}, {}
for sym, ts, blob in c.execute("select symbol, ts, blob from snap_detail where basis='oi' order by symbol, ts"):
    t = datetime.fromisoformat(ts).astimezone(NY)
    if t.weekday() > 4 or not (570 <= t.hour * 60 + t.minute <= 960):
        continue
    p = json.loads(zlib.decompress(blob))
    stks = p.get("strikes")
    lv = p.get("levels") or {}
    if not stks or lv.get("call_wall") is None:
        continue
    spot = (p.get("meta") or {}).get("spot")
    if spot is None:
        continue
    cwoi, pwoi = oi_walls(stks, spot)
    days.setdefault((sym, t.date()), []).append((spot, lv["call_wall"], lv["put_wall"], cwoi, pwoi))
    vint.setdefault((sym, t.date()), []).append((p["meta"].get("oi_as_of"), sum((s.get("call_oi") or 0) + (s.get("put_oi") or 0) for s in stks)))

out = {"CW": [], "PW": [], "CWOI": [], "PWOI": []}
for r in days.values():
    if len(r) < 20:
        continue
    a = np.array([[np.nan if v is None else v for v in x] for x in r], float)
    for j, k in enumerate(out, start=1):
        out[k].append(int((np.diff(a[:, j]) != 0).sum()) == 0)
n = len(out["CW"])
print("symbol-days with >= 20 full strike tables:", n)
for k, v in out.items():
    print(f"{k:5} fixed all session on {100 * np.mean(v):.0f}% of days")

# why do the OI walls move? classify each change: OI data changed (vintage or total OI) vs price crossed the strike
why = {"oi_data_changed": 0, "same_oi_data": 0}
crossed = 0
for key, r in days.items():
    if len(r) < 20:
        continue
    v = vint[key]
    for i in range(1, len(r)):
        for j in (3, 4):
            if r[i][j] != r[i - 1][j]:
                if v[i] != v[i - 1]:
                    why["oi_data_changed"] += 1
                else:
                    why["same_oi_data"] += 1
                    old = r[i - 1][j]
                    if old is not None and (j == 3 and r[i][0] + r[i][0] * 0.006 > old or j == 4 and r[i][0] - r[i][0] * 0.006 < old):
                        crossed += 1
print(why, " of the same-OI moves, old wall now inside the buffer / crossed by price:", crossed)
