"""Replay the NEW policy (gamma snapshot at 09:35 ET + confirmed OI changes) on recorded snapshots, 5-min polls
from 04:00 to 16:00 ET. CWOI / PWOI are not in the snapshots table: only MAXOI stands for the OI levels here."""
import sqlite3, sys, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, r"C:\project\options-agent")
from vzones.gex_watch import Watch
from vzones.gex_block import format_block
NY = ZoneInfo("America/New_York")
c = sqlite3.connect("file:C:/project/gex_radar/data/snapshots.db?mode=ro", uri=True)
polls = {}
for sym, ts, cw, pw, fl, pin, df, mo in c.execute("select symbol, ts, call_wall, put_wall, gamma_flip, pin, delta_flip, max_oi_strike from snapshots where basis='oi' and engine_version=2 order by ts"):
    t = datetime.fromisoformat(ts).astimezone(NY); m = t.hour * 60 + t.minute
    if t.weekday() > 4 or not (240 <= m < 960):
        continue
    polls.setdefault((t.date(), m // 5), {})[sym] = {"CW": cw, "PW": pw, "FLIP": fl, "PIN": pin, "DFLIP": df, "MAXOI": mo}
w, per_day, kinds = Watch(confirm=2), {}, {}
for (d, slot) in sorted(polls):
    ok, what = w.update(format_block(d.isoformat(), polls[(d, slot)]), slot * 5)
    if ok:
        per_day[d] = per_day.get(d, 0) + 1
        k = what[0].split(" ")[0] if what[0].startswith(("first", "new", "opening")) else "oi change"
        kinds[k] = kinds.get(k, 0) + 1
days = sorted({d for d, _ in polls})
print("days", len(days), "pushes/day median", st.median([per_day.get(d, 0) for d in days]),
      "max", max(per_day.get(d, 0) for d in days), "by kind", kinds)
