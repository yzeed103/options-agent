"""Build today's options-levels block from the local GEXRadar server and print it (optionally send it to Telegram).

    python tools/gex_block.py                      # every symbol GEXRadar serves
    python tools/gex_block.py --symbols SPY,QQQ,HOOD
    python tools/gex_block.py --out gex_block.txt --telegram
    python tools/gex_block.py --out gex_block.txt --clip --notify   # what the morning task runs

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
from vzones.gex_block import format_block, oi_walls  # noqa: E402

NY = ZoneInfo("America/New_York")
FIELDS = {"CW": "call_wall", "PW": "put_wall", "FLIP": "gamma_flip", "PIN": "pin", "DFLIP": "delta_flip", "MAXOI": "max_oi_strike"}


def get(url: str, timeout: float = 20, tries: int = 4):
    """GET JSON. GEXRadar answers 429 (240 requests a minute per address) or 503 (still loading) under load:
    wait and retry instead of dropping the symbol from the block."""
    import time
    import urllib.error
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or i == tries - 1:
                raise
            time.sleep(10 * (i + 1))      # 10 + 20 + 30 s: spans the limiter's one-minute window


def build(base: str, symbols: list[str] | None, basis: str) -> tuple[str, list[str]]:
    if not symbols:
        symbols = [s["symbol"] for s in get(f"{base}/api/symbols")["symbols"] if s.get("ok")]
    rows, notes, dates = {}, [], set()
    for sym in symbols:
        try:
            # 200 = the most the API returns (strikes with the largest |GEX|); enough for the OI walls, checked below
            d = get(f"{base}/api/gex/{urllib.parse.quote(sym)}?basis={basis}&strikes=200")
        except Exception as e:  # noqa: BLE001 - one bad symbol must not stop the block
            notes.append(f"{sym}: failed ({type(e).__name__})")
            continue
        lv = d.get("levels") or {}
        rows[sym] = {k: lv.get(f) for k, f in FIELDS.items()}
        st = d.get("strikes") or []
        rows[sym]["CWOI"], rows[sym]["PWOI"] = oi_walls(st, d.get("spot") or 0.0)
        # coverage check: the highest-OI strike GEXRadar reports must be among the strikes we received
        best = max(st, key=lambda s: (s.get("call_oi") or 0) + (s.get("put_oi") or 0), default=None)
        if lv.get("max_oi_strike") is not None and (best is None or best["strike"] != lv["max_oi_strike"]):
            notes.append(f"{sym}: the 200 strikes returned miss the max-OI strike, OI walls may be off")
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


def copy_to_clipboard(text: str) -> None:
    """Windows clipboard via clip.exe (the block is plain ASCII)."""
    import subprocess
    subprocess.run(["clip"], input=text.encode("ascii", "replace"), check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def notify(title: str, body: str) -> None:
    """Windows toast through PowerShell's own app id (no extra modules). Text goes in -EncodedCommand so Arabic survives."""
    import base64, subprocess
    esc = lambda s: s.replace("'", "''")
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
          "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
          f"$x.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{esc(title)}')) > $null;"
          f"$x.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{esc(body)}')) > $null;"
          "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($x))")
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="GEXRadar address")
    ap.add_argument("--symbols", default="", help="comma list; empty = every symbol GEXRadar serves")
    ap.add_argument("--basis", default="oi", choices=["oi", "volume"])
    ap.add_argument("--out", help="also write the block to this file")
    ap.add_argument("--telegram", action="store_true", help="send the block to Telegram")
    ap.add_argument("--clip", action="store_true", help="copy the block to the Windows clipboard")
    ap.add_argument("--notify", action="store_true", help="show a Windows notification when done")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    text, notes = build(a.url.rstrip("/"), syms, a.basis)
    print(text)
    for n in notes:
        print("# " + n, file=sys.stderr)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if a.clip:
        copy_to_clipboard(text)
    if a.telegram:
        send_telegram(text)
    if a.notify:
        n = text.count("\n")
        notify("كتلة GEX جاهزة " + text.splitlines()[0].replace("DATE=", ""),
               f"{n} سهم" + (" · منسوخة، الصقها في المؤشر بـ Ctrl+V" if a.clip else "")
               + (f" · {len(notes)} ملاحظة" if notes else ""))


if __name__ == "__main__":
    main()
