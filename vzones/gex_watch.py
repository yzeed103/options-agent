"""Change detection for the GEX agent (tools/gex_agent.py): when is a new GEXRadar block worth pushing to the chart?

GEXRadar's levels jitter: FLIP / DFLIP move a little on every reprice, and the gamma walls swap with their runner-up
on ~2/3 of their changes (measured on 560 symbol-days). Pushing every jitter would make the bands jump all day.
So a symbol's levels are replaced only when:
  - a strike level (CW, PW, PIN, MAXOI, CWOI, PWOI) changed, or FLIP / DFLIP moved more than `flip_tol` of price, and
  - the SAME new levels were seen on `confirm` consecutive polls (a swap that flips back is never pushed).
A new DATE always replaces everything (new session = new open interest).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gex_block import KEYS, format_block

STRIKE_KEYS = ("CW", "PW", "PIN", "MAXOI", "CWOI", "PWOI")
FLOAT_KEYS = ("FLIP", "DFLIP")


def parse_all(text: str) -> tuple[str, dict[str, dict]]:
    """Whole block -> (date, {symbol: {key: value}})."""
    from .gex_block import parse_block, norm_symbol
    date, out = "", {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("DATE="):
            date = line[5:].strip()
        elif ":" in line:
            sym = norm_symbol(line.split(" ", 1)[0])
            lv = parse_block(line, sym)
            if lv:
                lv.pop("DATE", None)
                out[sym] = lv
    return date, out


def differs(a: dict, b: dict, flip_tol: float) -> bool:
    """True when b is a real change from a (strike levels exact, flips beyond flip_tol of the level)."""
    for k in STRIKE_KEYS:
        if a.get(k) != b.get(k):
            return True
    for k in FLOAT_KEYS:
        x, y = a.get(k), b.get(k)
        if (x is None) != (y is None):
            return True
        if x is not None and abs(x - y) > flip_tol * abs(x):
            return True
    return False


@dataclass
class Watch:
    confirm: int = 2            # consecutive polls a change must survive
    flip_tol: float = 0.0025    # 0.25% of the level
    date: str = ""
    applied: dict = field(default_factory=dict)     # symbol -> levels currently on the chart
    pending: dict = field(default_factory=dict)     # symbol -> (levels, times seen)

    def update(self, text: str) -> tuple[bool, list[str]]:
        """Feed one fresh block. Returns (chart needs a new block, human-readable changes)."""
        date, now = parse_all(text)
        if not now:
            return False, []
        if date != self.date:
            first = not self.date
            self.date, self.applied, self.pending = date, now, {}
            return True, ["first block" if first else f"new session {date}"]
        changes = []
        for sym, lv in now.items():
            old = self.applied.get(sym)
            if old is None:
                self.applied[sym] = lv
                changes.append(f"{sym} added")
                continue
            if not differs(old, lv, self.flip_tol):
                self.pending.pop(sym, None)
                continue
            cand, seen = self.pending.get(sym, (None, 0))
            seen = seen + 1 if cand is not None and not differs(cand, lv, self.flip_tol) else 1
            if seen >= self.confirm:
                moved = [f"{k} {old.get(k):g}->{lv.get(k):g}" for k in KEYS
                         if old.get(k) is not None and lv.get(k) is not None and old.get(k) != lv.get(k)
                         and (k in STRIKE_KEYS or abs(old[k] - lv[k]) > self.flip_tol * abs(old[k]))]
                self.applied[sym] = lv
                self.pending.pop(sym, None)
                changes.append(f"{sym}: " + ", ".join(moved))
            else:
                self.pending[sym] = (lv, seen)
        return bool(changes), changes

    def block(self) -> str:
        return format_block(self.date, self.applied)
