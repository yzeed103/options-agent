"""Daily options-levels block (GEXRadar -> Volume Zones indicator).

One line per symbol, pasted into the indicator's text area:

    DATE=2026-10-22
    INTU: CW=360 PW=340 FLIP=355 PIN=350
    SPY: CW=770 PW=750 FLIP=774.56 PIN=760 DFLIP=771.36

parse_block() is the Python counterpart of the Pine parser (same rules), format_block() is what
tools/gex_block.py writes.
Rules: a symbol token is the first token without "=" (a trailing ":" and an exchange prefix such as
"NASDAQ:" are dropped, "^" is removed so ^SPX matches SPX); KEY=VALUE tokens may be split by spaces,
tabs or commas; keys are case-insensitive; a value keeps only its first number; unknown keys are ignored;
a line with DATE= and no symbol sets the date for every line.
"""
from __future__ import annotations

import re

KEYS = ("CW", "PW", "FLIP", "PIN", "DFLIP", "MAXOI")
_NUM = re.compile(r"[-+]?[0-9]*\.?[0-9]+")


def norm_symbol(s: str) -> str:
    parts = [p for p in s.split(":") if p]
    return parts[-1].replace("^", "").upper() if parts else ""


def _num(s: str) -> float | None:
    m = _NUM.search(s)
    return float(m.group(0)) if m else None


def parse_block(text: str, ticker: str) -> dict | None:
    """Levels of `ticker` from the block, or None when the block has no line for it."""
    me = norm_symbol(ticker)
    date, found = "", None
    for line in text.replace("\t", " ").split("\n"):
        sym, got, dt = "", dict.fromkeys(KEYS), ""
        for tk in line.replace(",", " ").split(" "):
            if not tk:
                continue
            if "=" in tk:
                k, _, v = tk.partition("=")
                k = k.upper()
                if k == "DATE":
                    dt = v
                elif k in got:
                    got[k] = _num(v)
            elif not sym:
                sym = norm_symbol(tk)
        if not sym and dt:
            date = dt
        if sym and sym == me:
            found = got
            if dt:
                date = dt
    if found is None:
        return None
    found["DATE"] = date
    return found


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def format_block(date: str, rows: dict[str, dict]) -> str:
    """rows: {symbol: {"CW": .., "PW": .., "FLIP": .., "PIN": .., "DFLIP": ..}}; None values are left out."""
    out = [f"DATE={date}"]
    for sym, lv in rows.items():
        parts = [f"{k}={_fmt(lv[k])}" for k in KEYS if lv.get(k) is not None]
        if parts:
            out.append(f"{norm_symbol(sym)}: " + " ".join(parts))
    return "\n".join(out)
