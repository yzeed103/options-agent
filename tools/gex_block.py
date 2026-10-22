"""Build today's options-levels block from the local GEXRadar server and print it (optionally send it to Telegram).

    python tools/gex_block.py                      # every symbol GEXRadar serves
    python tools/gex_block.py --symbols SPY,QQQ,HOOD
    python tools/gex_block.py --out gex_block.txt --telegram

Read-only on GEXRadar: it only calls GET /api/symbols and GET /api/gex/{symbol}.
Telegram needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment (never written to the repo).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vzones.gex_block import format_block  # noqa: E402

NY = ZoneInfo("America/New_York")
FIELDS = {"CW": "call_wall", "PW": "put_wall", "FLIP": "gamma_flip", "PIN": "pin", "DFLIP": "delta_flip", "MAXOI": "max_oi_strike"}


def get(url: str, timeout: float = 20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def build(base: str, symbols: list[str] | None, basis: str) -> tuple[str, list[str]]:
    if not symbols:
        symbols = [s["symbol"] for s in get(f"{base}/api/symbols")["symbols"] if s.get("ok")]
    rows, notes, dates = {}, [], set()
    for sym in symbols:
        try:
            d = get(f"{base}/api/gex/{urllib.parse.quote(sym)}?basis={basis}&strikes=1")
        except Exception as e:  # noqa: BLE001 - one bad symbol must not stop the block
            notes.append(f"{sym}: failed ({type(e).__name__})")
            continue
        lv = d.get("levels") or {}
        rows[sym] = {k: lv.get(f) for k, f in FIELDS.items()}
        if d.get("updated_at"):
            dates.add(datetime.fromisoformat(d["updated_at"]).astimezone(NY).date().isoformat())
        if d.get("oi_stale"):
            notes.append(f"{sym}: open interest is stale (as of {d.get('oi_as_of')})")
    date = max(dates) if dates else datetime.now(NY).date().isoformat()
    return format_block(date, rows), notes


def send_telegram(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set")
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout=20) as r:
        if not json.loads(r.read().decode()).get("ok"):
            raise SystemExit("Telegram refused the message")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="GEXRadar address")
    ap.add_argument("--symbols", default="", help="comma list; empty = every symbol GEXRadar serves")
    ap.add_argument("--basis", default="oi", choices=["oi", "volume"])
    ap.add_argument("--out", help="also write the block to this file")
    ap.add_argument("--telegram", action="store_true", help="send the block to Telegram")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    text, notes = build(a.url.rstrip("/"), syms, a.basis)
    print(text)
    for n in notes:
        print("# " + n, file=sys.stderr)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if a.telegram:
        send_telegram(text)


if __name__ == "__main__":
    main()
