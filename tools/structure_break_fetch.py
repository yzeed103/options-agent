"""Daily bars of the pre-registered universe (reports/structure_break/UNIVERSE.md) from Yahoo, 2010 to now,
split-adjusted, not dividend-adjusted; one CSV per symbol in runtime_sip/daily_universe/. Writes fetch.json."""
from __future__ import annotations

import json
import os
import re
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "runtime_sip", "daily_universe")
REP = os.path.join(ROOT, "reports", "structure_break")


def universe():
    txt = open(os.path.join(REP, "UNIVERSE.md"), encoding="utf-8").read()
    syms = []; on = False
    for line in txt.splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("Current") or line.startswith("that left") or line.startswith("2010") or line.startswith("adjusted"):
            on = False; continue
        if ":" in line:
            on = True; line = line.split(":", 1)[1]
        if on:
            syms += re.findall(r"\b[A-Z][A-Z0-9.\-]{0,5}\b", line)
    seen = []
    for s in syms:
        if s not in seen and s not in ("ETF", "ETFS", "SIP"):
            seen.append(s)
    return seen


def main():
    import yfinance as yf
    os.makedirs(OUT, exist_ok=True)
    syms = universe(); t0 = time.time(); got, missing = [], []
    for i in range(0, len(syms), 25):
        part = syms[i:i + 25]
        try:
            df = yf.download(part, start="2010-01-01", auto_adjust=False, actions=False, group_by="ticker", progress=False, threads=True)
        except Exception as e:  # noqa: BLE001
            missing += [(s, type(e).__name__) for s in part]; continue
        for s in part:
            try:
                d = df[s] if len(part) > 1 else df
                d = d[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(d) < 500:
                    missing.append((s, f"only {len(d)} bars")); continue
                d.columns = ["open", "high", "low", "close", "volume"]
                d.index = [x.date().isoformat() for x in d.index]; d.index.name = "date"
                d.to_csv(os.path.join(OUT, f"{s}.csv")); got.append((s, len(d), d.index[0]))
            except Exception as e:  # noqa: BLE001
                missing.append((s, type(e).__name__))
        print(f"{i + len(part)}/{len(syms)} {time.time() - t0:.0f}s", flush=True)
    json.dump({"requested": len(syms), "got": len(got), "missing": missing, "first_dates": {s: f for s, n, f in got}}, open(os.path.join(REP, "fetch.json"), "w"), indent=1)
    print("got", len(got), "missing", missing)


if __name__ == "__main__":
    main()
