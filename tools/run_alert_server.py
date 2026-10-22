"""Runs app.py (with the TradingView webhook) on this machine only: 127.0.0.1:5000.

    pythonw tools/run_alert_server.py           # the AlertServer logon task runs this

TradingView's servers cannot reach 127.0.0.1: a public address (a tunnel such as Cloudflare Tunnel or ngrok)
must forward to http://127.0.0.1:5000 - see the webhook section in app.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("ALERT_PORT", "5000")), debug=False)
