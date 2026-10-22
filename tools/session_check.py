"""After each session: did the pipeline behave? Writes runtime/session_check.txt and shows a Windows notification.

Checks, for the last finished New York session (and the 3 before it, as a baseline):
  - GEXRadar "database is locked" errors (the DB was switched to WAL on 2026-10-23: expect 0 from then on)
  - GEXRadar self-check (all checks green)
  - the GEX agent: polls, pushes, errors, and whether today's 09:35 ET gamma snapshot was taken

    python tools/session_check.py            # the GEXCheck task runs it every morning at 05:30
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gex_block  # noqa: E402  (notify)

NY = ZoneInfo("America/New_York")
LOCAL = datetime.now().astimezone().tzinfo
GEX_LOGS = [r"C:\project\gex_radar\data\app.log", r"C:\project\gex_radar\data\app.log.1"]
AGENT_LOG = os.path.join(ROOT, "runtime", "gex_agent.log")
OUT = os.path.join(ROOT, "runtime", "session_check.txt")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def ny_day(local_stamp: str) -> str | None:
    """Session day (New York) of a local log time stamp; the day starts at 04:00 ET like GEXRadar's window."""
    try:
        t = datetime.strptime(local_stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL)
    except ValueError:
        return None
    return (t.astimezone(NY) - timedelta(hours=4)).date().isoformat()


def scan(paths: list[str], patterns: dict[str, str]) -> dict[str, Counter]:
    out = {k: Counter() for k in patterns}
    for p in paths:
        try:
            f = open(p, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                m = STAMP.match(line)
                if not m:
                    continue
                for k, pat in patterns.items():
                    if pat in line:
                        d = ny_day(m.group(1))
                        if d:
                            out[k][d] += 1
    return out


def last_sessions(n: int) -> list[str]:
    d = (datetime.now(NY) - timedelta(hours=20)).date()      # a session is finished after 20:00 ET
    days = []
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return days


def main() -> None:
    days = last_sessions(4)
    gex = scan(GEX_LOGS, {"locked": "database is locked", "traceback": "Traceback"})
    agent = scan([AGENT_LOG], {"poll": "INFO poll:", "push": "set ", "snapshot": "opening snapshot",
                               "warn": "WARNING", "error": "ERROR"})
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/selfcheck", timeout=20) as r:
            sc = json.loads(r.read().decode("utf-8"))
        sc_ok, sc_failed = sc.get("ok"), sc.get("failed") or []
    except Exception as e:  # noqa: BLE001
        sc_ok, sc_failed = False, [f"unreachable ({type(e).__name__})"]

    d0 = days[0]
    lines = [f"Session check {datetime.now().strftime('%Y-%m-%d %H:%M')} (local) - last session {d0} (New York)", ""]
    lines.append("GEXRadar 'database is locked' per session (WAL since 2026-10-23):")
    for d in days:
        lines.append(f"  {d}: {gex['locked'][d]}")
    lines.append(f"GEXRadar tracebacks in {d0}: {gex['traceback'][d0]}")
    lines.append(f"GEXRadar self-check now: {'all green' if sc_ok else 'FAILED: ' + ', '.join(sc_failed)}")
    lines.append("")
    snap = agent["snapshot"][d0] > 0
    lines.append(f"GEX agent in {d0}: polls {agent['poll'][d0]}, opening snapshot {'yes' if snap else 'NO'}, "
                 f"warnings {agent['warn'][d0]}, errors {agent['error'][d0]}")
    report = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)

    problems = []
    if gex["locked"][d0]:
        problems.append(f"أخطاء قفل القاعدة {gex['locked'][d0]}")
    if not sc_ok:
        problems.append("فحص GEXRadar الذاتي فشل")
    if agent["poll"][d0] and not snap:
        problems.append("الوكيل ما أخذ لقطة الافتتاح")
    if agent["error"][d0]:
        problems.append(f"أخطاء الوكيل {agent['error'][d0]}")
    gex_block.notify("فحص الجلسة " + d0, "كل شيء سليم" if not problems else "؛ ".join(problems))


if __name__ == "__main__":
    main()
