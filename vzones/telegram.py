"""Telegram sending for the whole pipeline (webhook alerts, GEX agent updates, daily GEX block).

The bot token and chat id are read from, in order:
  1. environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
  2. runtime/telegram.json  {"bot_token": "...", "chat_id": "...", "webhook_key": "..."}  (git-ignored)
Nothing is sent - and nothing fails - while neither is set: send() returns False and says why.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "runtime", "telegram.json")
API = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")   # overridable for tests


def config() -> dict:
    cfg = {}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    cfg["bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("bot_token") or ""
    cfg["chat_id"] = os.environ.get("TELEGRAM_CHAT_ID") or str(cfg.get("chat_id") or "")
    cfg["webhook_key"] = os.environ.get("WEBHOOK_KEY") or cfg.get("webhook_key") or ""
    return cfg


def configured() -> bool:
    c = config()
    return bool(c["bot_token"] and c["chat_id"])


def send(text: str) -> tuple[bool, str]:
    """Send a message. Returns (sent, reason). Never raises."""
    c = config()
    if not (c["bot_token"] and c["chat_id"]):
        return False, "telegram not configured (runtime/telegram.json)"
    body = urllib.parse.urlencode({"chat_id": c["chat_id"], "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"{API}/bot{c['bot_token']}/sendMessage", body, timeout=20) as r:
            ok = json.loads(r.read().decode()).get("ok")
        return bool(ok), "sent" if ok else "telegram refused the message"
    except Exception as e:  # noqa: BLE001
        return False, f"telegram error: {type(e).__name__}"
