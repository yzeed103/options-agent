"""Change detection for the GEX agent (tools/gex_agent.py): when is a new GEXRadar block worth pushing to the chart?

Measured on GEXRadar's own snapshots (560 symbol-days, reports/oiwall_drift.py, push_freq replay):
  - the gamma levels (CW, PW, FLIP, PIN, DFLIP) partly follow price: PIN and the gamma walls correlate ~0.6 with
    price on the days they move, ~2/3 of wall changes are swaps with the runner-up, and FLIP drifts all day.
    Replaying "push every confirmed change" gave ~67 pushes a day (FLIP alone 4,225 changes in 20 days).
  - the open-interest levels (MAXOI, CWOI, PWOI) hold all day on most days (MAXOI 85%, OI walls ~65%).
So the agent:
  - takes the gamma levels ONCE per session, at the first poll after `snap_at` (09:35 ET: open + 5 min, real
    price, fresh chain) - before that the overnight values; a new DATE replaces everything;
  - updates the open-interest levels during the day, but only when the SAME new value is seen on `confirm`
    consecutive polls (a swap that flips back is never pushed).
`live_gamma=True` brings back intraday gamma updates (FLIP / DFLIP only beyond `flip_tol` of the level).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gex_block import format_block

GAMMA_KEYS = ("CW", "PW", "FLIP", "PIN", "DFLIP")
OI_KEYS = ("MAXOI", "CWOI", "PWOI")
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


def changed_keys(a: dict, b: dict, keys, flip_tol: float) -> list[str]:
    """Keys of b that really changed from a (strike levels exact, flips beyond flip_tol of the level)."""
    out = []
    for k in keys:
        x, y = a.get(k), b.get(k)
        if (x is None) != (y is None):
            out.append(k)
        elif x is not None and (abs(x - y) > flip_tol * abs(x) if k in FLOAT_KEYS else x != y):
            out.append(k)
    return out


def _fmt(v) -> str:
    return "-" if v is None else f"{v:g}"


@dataclass
class Watch:
    confirm: int = 2            # consecutive polls a change must survive
    flip_tol: float = 0.0025    # live_gamma only: FLIP / DFLIP must move more than 0.25% of the level
    snap_at: int = 9 * 60 + 35  # minutes after midnight ET: gamma levels are taken once, at the first poll after this
    live_gamma: bool = False
    min_share: float = 0.8      # a block with fewer symbols than this share of the chart's is ignored
    date: str = ""
    snapped: bool = False       # today's gamma snapshot taken
    applied: dict = field(default_factory=dict)     # symbol -> levels currently on the chart
    pending: dict = field(default_factory=dict)     # symbol -> (levels, times seen)

    def update(self, text: str, minute_et: int | None = None) -> tuple[bool, list[str]]:
        """Feed one fresh block (minute_et = minutes after midnight New York, None = after the snapshot time).
        Returns (chart needs a new block, human-readable changes)."""
        date, now = parse_all(text)
        if not now:
            return False, []
        if self.applied and len(now) < self.min_share * len(self.applied):
            # a partial block (GEXRadar overloaded / restarting) must not wipe symbols off the chart
            return False, [f"incomplete block ({len(now)} of {len(self.applied)} symbols) - skipped"]
        after_snap = minute_et is None or minute_et >= self.snap_at
        if date != self.date:
            first = not self.date
            self.date, self.applied, self.pending = date, now, {}
            self.snapped = after_snap
            return True, ["first block" if first else f"new session {date}"]
        if not self.snapped and after_snap:
            # the once-a-day gamma snapshot: take the gamma levels of every symbol as they are now
            self.snapped = True
            moved = []
            for sym, lv in now.items():
                old = self.applied.setdefault(sym, {})
                ks = changed_keys(old, lv, GAMMA_KEYS, 0.0)
                for k in GAMMA_KEYS:
                    old[k] = lv.get(k)
                if ks:
                    moved.append(sym)
            return True, [f"opening snapshot ({len(moved)} symbols changed)"]
        watched = OI_KEYS + (GAMMA_KEYS if self.live_gamma else ())
        changes = []
        for sym, lv in now.items():
            old = self.applied.get(sym)
            if old is None:
                self.applied[sym] = lv
                changes.append(f"{sym} added")
                continue
            ks = changed_keys(old, lv, watched, self.flip_tol)
            if not ks:
                self.pending.pop(sym, None)
                continue
            cand, seen = self.pending.get(sym, (None, 0))
            seen = seen + 1 if cand is not None and not changed_keys(cand, lv, watched, self.flip_tol) else 1
            if seen >= self.confirm:
                changes.append(f"{sym}: " + ", ".join(f"{k} {_fmt(old.get(k))}->{_fmt(lv.get(k))}" for k in ks))
                for k in watched:
                    old[k] = lv.get(k)
                self.pending.pop(sym, None)
            else:
                self.pending[sym] = (lv, seen)
        return bool(changes), changes

    def block(self) -> str:
        return format_block(self.date, self.applied)

    # state survives an agent restart (reboot at noon must not replace the 09:35 snapshot with noon values)
    def to_json(self) -> dict:
        return {"date": self.date, "snapped": self.snapped, "applied": self.applied}

    def load(self, d: dict) -> None:
        self.date, self.snapped = d.get("date", ""), bool(d.get("snapped"))
        self.applied = {s: dict(v) for s, v in (d.get("applied") or {}).items()}
