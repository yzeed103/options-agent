#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WSGI entrypoint — `gunicorn app:app`.

The application itself lives in the `options_agent` package.
"""

from __future__ import annotations

import os

from options_agent import create_app

app = create_app()


def _main() -> None:
    import socket

    port = int(os.environ.get("PORT", "5000"))
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        local_ip = "127.0.0.1"

    print("\n" + "=" * 55)
    print("  🚀 وكيل الخيارات - Web App")
    print("=" * 55)
    print(f"  💻 على جهازك:   http://localhost:{port}")
    print(f"  📱 من الجوال:   http://{local_ip}:{port}")
    print("=" * 55)
    print("  (تأكد أن الجوال والكمبيوتر على نفس الـ WiFi)")
    print("=" * 55 + "\n")

    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    _main()
