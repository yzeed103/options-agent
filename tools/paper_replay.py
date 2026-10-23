"""Phase 2: replay the stored history through the same code path the live agent uses, into runtime/paper.db.

    python tools/paper_replay.py                 # every watchlist symbol, 5m and 15m
    python tools/paper_replay.py --symbols SPY   # one symbol
    python tools/paper_replay.py --fresh         # start a new journal (the old one is kept as paper.db.bak)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, journal, live  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    if a.fresh and os.path.exists(journal.DB):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(journal.DB + ext):
                os.replace(journal.DB + ext, journal.DB + ".bak" + ext)
    syms = a.symbols or sorted(f[:-7] for f in os.listdir(data.BARS) if f.endswith("_5m.csv"))
    c = journal.connect()
    t0 = time.time()
    for s in syms:
        b = data.load_bars(s)
        if len(b) < 2000:
            print(s, "skipped: only", len(b), "bars"); continue
        for tf, cnt in live.process_symbol(c, s, b, mode="replay").items():
            print(f"{s:6} {tf:>2}m  {cnt}  {time.time() - t0:.0f}s", flush=True)
    journal.event(c, "replay", {"symbols": len(syms), "seconds": round(time.time() - t0)})
    c.commit()


if __name__ == "__main__":
    main()
