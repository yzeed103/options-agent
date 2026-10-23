"""Eyes round, phase 2: run every test of reports/eyes/DEFINITIONS.md on the stored history, write
reports/eyes/HISTORY.md, reports/eyes/history.json and the pictures.

    python tools/eyes_history.py              # all symbols (about 2 minutes)
    python tools/eyes_history.py --report     # re-analyse the saved events only
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, eyes, eyes_live, eyes_report  # noqa: E402

EVENTS = os.path.join(data.RUNTIME, "eyes", "events.pkl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--symbols", nargs="*")
    a = ap.parse_args()
    if not a.report:
        syms = a.symbols or sorted(f[:-7] for f in os.listdir(data.BARS) if f.endswith("_5m.csv"))
        allev = {k: [] for k in ("trend", "wall", "magnet", "level", "flip")}
        days = set()
        t0 = time.time()
        for s in syms:
            b = data.load_bars(s)
            if len(b) < 2000:
                continue
            days |= set(b.index.date)
            r = eyes.run_symbol(s, b)
            for k, v in r.items():
                allev[k] += v
            print(f"{s:6} " + " ".join(f"{k} {len(v)}" for k, v in r.items()) + f"  {time.time() - t0:.0f}s", flush=True)
        allev["days"] = sorted(days)
        os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
        pickle.dump(allev, open(EVENTS, "wb"))
    ev = pickle.load(open(EVENTS, "rb"))
    res = eyes_report.analyse(ev)
    eyes_report.write_history(res)
    eyes_report.pictures(res, ev)
    from datetime import date
    eyes_live.seed_observations(res, date.today().isoformat())
    print(eyes_report.verdict_lines(res))


if __name__ == "__main__":
    main()
