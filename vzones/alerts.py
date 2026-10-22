"""TradingView alert -> Telegram message.

The Volume Zones indicator sends one JSON per signal through alert() (pine/volume_zones.pine, "webhook alerts"):
    {"sym":"INTU","tf":"5","sig":"whale_up","price":355.2,"target":360,"stop":352.1,"level":null,"t":1792700000000}
Plain-text alerts (the alertcondition() messages) are forwarded as they are.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

SIGNALS = {   # sig -> (icon, Arabic name, direction: 1 up / -1 down / 0 none)
    "trend_up": ("📈", "تنبيه اتجاه صاعد", 1),
    "trend_dn": ("📉", "تنبيه اتجاه هابط", -1),
    "whale_up": ("🐋", "ارتداد حوت صعود (تحت الاختبار)", 1),
    "whale_dn": ("🐋", "ارتداد حوت هبوط (تحت الاختبار)", -1),
    "head_hit": ("🎯", "وصل خط الحوت المتجه إليه", 0),
    "st_up": ("🔄", "انكسر الترند الهابط (Supertrend)", 1),
    "st_dn": ("🔄", "انكسر الترند الصاعد (Supertrend)", -1),
    "tl_up": ("✂️", "كسر خط الترند الهابط", 1),
    "tl_dn": ("✂️", "كسر خط الترند الصاعد", -1),
    "gex_cross": ("🧱", "عبور مستوى خيارات", 0),
    "weak_vol": ("💤", "الفوليوم أصبح ضعيفا", 0),
}


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v          # NaN -> None


def _fmt(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:,.2f}"


def parse(body: str) -> dict:
    """Request body -> alert dict. A non-JSON body becomes {"text": body}."""
    body = (body or "").strip()
    try:
        d = json.loads(body)
        if isinstance(d, dict):
            return d
    except ValueError:
        pass
    return {"text": body}


def format_message(a: dict) -> str:
    """Arabic Telegram message: signal, symbol, price, target and stop with distance in %."""
    if "sig" not in a:
        return "🔔 تنبيه TradingView\n" + str(a.get("text", "")).strip()
    icon, name, _ = SIGNALS.get(a["sig"], ("🔔", a["sig"], 0))
    sym, tf = str(a.get("sym", "?")), str(a.get("tf", ""))
    price = _num(a.get("price"))
    lines = [f"{icon} {name}", f"{sym}" + (f" · فريم {tf}" if tf else "")]
    if price is not None:
        lines.append(f"السعر {_fmt(price)}")
    for key, label in (("target", "الهدف"), ("stop", "الوقف"), ("level", "المستوى")):
        v = _num(a.get(key))
        if v is not None:
            pct = f" ({(v / price - 1) * 100:+.2f}%)" if price else ""
            lines.append(f"{label} {_fmt(v)}{pct}")
    t = _num(a.get("t"))
    lines.append(datetime.fromtimestamp(t / 1000 if t and t > 1e11 else t).strftime("%Y-%m-%d %H:%M")
                 if t else datetime.now().strftime("%Y-%m-%d %H:%M"))
    return "\n".join(lines)


class Dedupe:
    """TradingView can deliver the same alert twice; the same (symbol, signal, bar) inside `window` s is dropped."""

    def __init__(self, window: float = 600.0):
        self.window, self.seen = window, {}

    def fresh(self, a: dict) -> bool:
        key = (a.get("sym"), a.get("sig"), a.get("t")) if "sig" in a else ("text", a.get("text"))
        now = time.time()
        self.seen = {k: v for k, v in self.seen.items() if now - v < self.window}
        if key in self.seen:
            return False
        self.seen[key] = now
        return True
