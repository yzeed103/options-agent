import json
import pytest

from vzones import alerts, telegram


def test_format_whale_with_target_and_stop():
    a = alerts.parse(json.dumps({"sym": "INTU", "tf": "5", "sig": "whale_up", "price": 355.2,
                                 "target": 360, "stop": 352.1, "t": 1792700000000}))
    m = alerts.format_message(a)
    assert "ارتداد حوت صعود" in m and "INTU · فريم 5" in m
    assert "الهدف 360 (+1.35%)" in m and "الوقف 352.1 (-0.87%)" in m


def test_exact_pine_payload():
    # the string pine/volume_zones.pine's hook() builds: jnum() writes null for na, time is epoch ms
    body = ('{"sym":"SPX","tf":"15","sig":"gex_cross","price":7744.47,"target":null,"stop":null,'
            '"level":7741.96,"t":1792700000000}')
    m = alerts.format_message(alerts.parse(body))
    assert "عبور مستوى خيارات" in m and "المستوى 7,741.96 (-0.03%)" in m and "الهدف" not in m


def test_pine_hook_signals_are_all_known():
    import re, pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "pine" / "volume_zones.pine").read_text(encoding="utf-8")
    sigs = set(re.findall(r'hook\("([a-z_]+)"', src)) | set(re.findall(r'"(st_up|st_dn)"', src))
    assert sigs and sigs <= set(alerts.SIGNALS), sigs - set(alerts.SIGNALS)


def test_nan_and_missing_fields_are_skipped():
    m = alerts.format_message({"sym": "SPY", "sig": "trend_up", "price": 700, "target": "NaN"})
    assert "الهدف" not in m and "السعر 700" in m


def test_plain_text_is_forwarded():
    assert "ثبات السعر" in alerts.format_message(alerts.parse("ثبات السعر خارج منطقة قيمة الأمس"))


def test_dedupe():
    d = alerts.Dedupe()
    a = {"sym": "SPY", "sig": "st_up", "t": 1}
    assert d.fresh(a) and not d.fresh(dict(a)) and d.fresh({**a, "t": 2})


def test_send_without_config_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram, "CONFIG", str(tmp_path / "none.json"))
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert telegram.send("x") == (False, "telegram not configured (runtime/telegram.json)")


def test_webhook_route(monkeypatch, tmp_path):
    flask = pytest.importorskip("flask")
    import app as webapp
    cfg = tmp_path / "telegram.json"
    cfg.write_text(json.dumps({"bot_token": "T", "chat_id": "1", "webhook_key": "k"}), encoding="utf-8")
    monkeypatch.setattr(telegram, "CONFIG", str(cfg))
    monkeypatch.setattr(webapp, "_ALERT_LOG", str(tmp_path / "alerts.log"))
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text: (sent.append(text) or (True, "sent")))
    c = webapp.app.test_client()
    body = json.dumps({"sym": "INTU", "sig": "trend_dn", "price": 350, "stop": 356, "t": 5})
    assert c.post("/webhook/tradingview?key=bad", data=body).status_code == 403
    r = c.post("/webhook/tradingview?key=k", data=body).get_json()
    assert r["sent"] and "تنبيه اتجاه هابط" in sent[0]
    assert c.post("/webhook/tradingview?key=k", data=body).get_json()["duplicate"]
    assert (tmp_path / "alerts.log").read_text(encoding="utf-8").count("trend_dn") == 1
