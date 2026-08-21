#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وكيل تحليل عقود الخيارات - نسخة Web
يشتغل من أي جهاز: جوال، آيباد، كمبيوتر
"""

from flask import Flask, request, jsonify, render_template_string
import os, json, threading, time
from datetime import datetime
from typing import Optional

# ─── تثبيت المكتبات ───────────────────────────────────────
def install(pkg):
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

try:
    import yfinance as yf
except ImportError:
    install("yfinance"); import yfinance as yf

try:
    import pandas as pd
except ImportError:
    install("pandas"); import pandas as pd

try:
    import anthropic
except ImportError:
    install("anthropic"); import anthropic

try:
    from flask import Flask
except ImportError:
    install("flask"); from flask import Flask

app = Flask(__name__)

DATA_FILE     = "contracts.json"
ALERT_FILE    = "alerts_log.txt"
SETTINGS_FILE = "settings.json"

# ═══════════════════════════════════════════════════════════
# إعدادات مؤشر ADX (قابلة للتعديل من صفحة السوق أو /api/settings)
# ═══════════════════════════════════════════════════════════
DEFAULT_SETTINGS = {
    # طول فترة المؤشر (الافتراضي عند Wilder = 14)
    "adx_period": 14,
    # عدد الشموع المستخدمة في الحساب
    "adx_lookback_days": 180,
    # الوزن: يضرب قيمة ADX. أكبر من 1 = تثقيل المؤشر
    # فيخضّر أبكر مع التحركات الاتجاهية
    "adx_weight": 1.0,
    # عتبة "اتجاه قوي" (أخضر) بعد تطبيق الوزن
    "adx_strong": 25.0,
    # عتبة "اتجاه قوي جداً" (أخضر فاتح)
    "adx_very_strong": 40.0,
    # عتبة "بداية اتجاه" (أصفر)، تحتها = سوق عرضي (رمادي)
    "adx_weak": 20.0,
    # أقل فرق مطلوب بين +DI و -DI لاعتبار الحركة اتجاهية فعلاً
    "adx_min_di_gap": 2.0,
    # false = أخضر لأي اتجاه قوي (صاعد أو هابط)
    # true  = أخضر للصاعد القوي وأحمر للهابط القوي
    "adx_color_by_direction": False,
}

# ═══════════════════════════════════════════════════════════
# إدارة البيانات
# ═══════════════════════════════════════════════════════════
def load_contracts():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_contracts(contracts):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(contracts, f, ensure_ascii=False, indent=2)

def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
        except Exception:
            pass
    return settings

def save_settings(new_values):
    settings = load_settings()
    for key, val in (new_values or {}).items():
        if key not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[key]
        try:
            if isinstance(default, bool):
                settings[key] = val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                settings[key] = int(float(val))
            elif isinstance(default, float):
                settings[key] = float(val)
            else:
                settings[key] = val
        except (TypeError, ValueError):
            continue
    settings["adx_period"]        = max(2,   min(100, settings["adx_period"]))
    settings["adx_lookback_days"] = max(30,  min(730, settings["adx_lookback_days"]))
    settings["adx_weight"]        = max(0.1, min(5.0, settings["adx_weight"]))
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return settings

# ═══════════════════════════════════════════════════════════
# Yahoo Finance
# ═══════════════════════════════════════════════════════════
def get_stock_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        price  = ticker.fast_info.last_price
        return round(float(price), 2) if price else None
    except:
        return None

def get_options_chain(symbol, expiry=None):
    try:
        ticker = yf.Ticker(symbol)
        dates  = ticker.options
        if not dates:
            return {"error": f"لا توجد خيارات لـ {symbol}"}
        target = expiry if expiry and expiry in dates else dates[0]
        chain  = ticker.option_chain(target)
        calls  = chain.calls[["strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"]].head(10)
        puts   = chain.puts[["strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"]].head(10)
        return {
            "symbol": symbol, "expiry": target,
            "calls": calls.to_dict("records"),
            "puts":  puts.to_dict("records"),
            "all_expiries": list(dates)[:8]
        }
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
# مؤشر ADX + DI (طريقة Wilder)
# ═══════════════════════════════════════════════════════════
def _wilder(series, period):
    """تنعيم Wilder: مكافئ لـ EMA بمعامل alpha = 1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()

def compute_adx(hist, period=14):
    """يحسب ADX و +DI و -DI من شموع OHLC. يرجّع None لو البيانات ناقصة."""
    if hist is None or len(hist) < period * 2 + 1:
        return None

    high, low, close = hist["High"], hist["Low"], hist["Close"]
    prev_close, prev_high, prev_low = close.shift(1), high.shift(1), low.shift(1)

    # المدى الحقيقي
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low  - prev_close).abs()], axis=1).max(axis=1)

    # الحركة الاتجاهية
    up_move   = high - prev_high
    down_move = prev_low - low
    plus_dm   = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.clip(lower=0)
    minus_dm  = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.clip(lower=0)

    atr           = _wilder(tr, period)
    safe_atr      = atr.replace(0, float("nan"))
    plus_di       = 100 * _wilder(plus_dm, period) / safe_atr
    minus_di      = 100 * _wilder(minus_dm, period) / safe_atr
    di_sum        = (plus_di + minus_di).replace(0, float("nan"))
    dx            = 100 * (plus_di - minus_di).abs() / di_sum
    adx           = _wilder(dx.fillna(0), period)

    last_adx, last_plus, last_minus = adx.iloc[-1], plus_di.iloc[-1], minus_di.iloc[-1]
    if any(v != v for v in (last_adx, last_plus, last_minus)):   # فحص NaN
        return None

    prev_adx = adx.iloc[-2] if len(adx) > 1 else last_adx
    return {
        "adx":      round(float(last_adx), 2),
        "plus_di":  round(float(last_plus), 2),
        "minus_di": round(float(last_minus), 2),
        "prev_adx": round(float(prev_adx), 2),
        "rising":   bool(last_adx > prev_adx),
        "period":   period,
    }

def classify_adx(raw, settings=None):
    """يطبّق الوزن على ADX ويحدد الحالة واللون.

    رفع adx_weight فوق 1 يثقّل المؤشر: القيمة الموزونة توصل عتبة
    "اتجاه قوي" أبكر، فيصير أخضر مع التحركات الاتجاهية القوية.
    """
    settings = settings or load_settings()
    weight    = float(settings["adx_weight"])
    weighted  = min(100.0, raw["adx"] * weight)
    di_gap    = raw["plus_di"] - raw["minus_di"]
    bullish   = di_gap > 0
    directional = abs(di_gap) >= float(settings["adx_min_di_gap"])

    if weighted >= float(settings["adx_very_strong"]) and directional:
        state, label, color = "very_strong", "اتجاه قوي جداً", "green"
    elif weighted >= float(settings["adx_strong"]) and directional:
        state, label, color = "strong", "اتجاه قوي", "green"
    elif weighted >= float(settings["adx_weak"]):
        state, label, color = "building", "بداية اتجاه", "yellow"
    else:
        state, label, color = "range", "سوق عرضي", "gray"

    # أخضر للصاعد وأحمر للهابط لو المستخدم فعّل التلوين حسب الاتجاه
    if color == "green" and settings.get("adx_color_by_direction") and not bullish:
        color = "red"

    direction = "صاعد" if bullish else "هابط"
    return {
        "adx":          raw["adx"],
        "adx_weighted": round(weighted, 2),
        "weight":       weight,
        "plus_di":      raw["plus_di"],
        "minus_di":     raw["minus_di"],
        "di_gap":       round(di_gap, 2),
        "period":       raw["period"],
        "rising":       raw["rising"],
        "state":        state,
        "label":        label,
        "color":        color,
        "direction":    direction if directional else "بدون اتجاه واضح",
        "is_strong":    state in ("strong", "very_strong"),
        "summary":      f"{label} {direction}" if directional and state != "range" else label,
        "thresholds": {
            "weak":        float(settings["adx_weak"]),
            "strong":      float(settings["adx_strong"]),
            "very_strong": float(settings["adx_very_strong"]),
        },
    }

def get_adx(symbol, settings=None):
    """يجلب الشموع من Yahoo ويرجّع قراءة ADX جاهزة للعرض."""
    settings = settings or load_settings()
    try:
        hist = yf.Ticker(symbol).history(period=f"{int(settings['adx_lookback_days'])}d")
        raw  = compute_adx(hist, int(settings["adx_period"]))
        if not raw:
            return {"error": "بيانات غير كافية لحساب ADX"}
        return classify_adx(raw, settings)
    except Exception as e:
        return {"error": str(e)}

def get_market_summary(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.info
        hist   = ticker.history(period="5d")
        change = 0
        if len(hist) >= 2:
            change = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 2)
        return {
            "symbol":     symbol,
            "price":      info.get("currentPrice") or info.get("regularMarketPrice"),
            "change_pct": change,
            "52w_high":   info.get("fiftyTwoWeekHigh"),
            "52w_low":    info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "pe_ratio":   info.get("trailingPE"),
            "beta":       info.get("beta"),
            "sector":     info.get("sector"),
            "adx":        get_adx(symbol),
        }
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
# تحليل المحفظة
# ═══════════════════════════════════════════════════════════
def calc_pnl(c):
    mult = 1 if c["side"] == "long" else -1
    return round((c["current_premium"] - c["entry_premium"]) * c["qty"] * 100 * mult, 2)

def break_even(c):
    if c["type"] == "call":
        return round(c["strike"] + c["entry_premium"], 2)
    return round(c["strike"] - c["entry_premium"], 2)

def analyze_portfolio(contracts):
    if not contracts:
        return {"error": "لا توجد عقود"}
    total_pnl  = sum(calc_pnl(c) for c in contracts)
    total_cost = sum(c["entry_premium"] * c["qty"] * 100 for c in contracts)
    winners    = [c for c in contracts if calc_pnl(c) > 0]
    return {
        "total_contracts": len(contracts),
        "total_pnl":       total_pnl,
        "total_cost":      total_cost,
        "calls":           len([c for c in contracts if c["type"] == "call"]),
        "puts":            len([c for c in contracts if c["type"] == "put"]),
        "long_positions":  len([c for c in contracts if c["side"] == "long"]),
        "short_positions": len([c for c in contracts if c["side"] == "short"]),
        "win_rate":        round(len(winners) / len(contracts) * 100, 1),
        "contracts_detail": [{
            "symbol":     c["symbol"], "type": c["type"], "side": c["side"],
            "strike":     c["strike"], "entry": c["entry_premium"],
            "current":    c["current_premium"], "pnl": calc_pnl(c),
            "break_even": break_even(c), "expiry": c["expiry"], "qty": c["qty"]
        } for c in contracts]
    }

# ═══════════════════════════════════════════════════════════
# Claude AI
# ═══════════════════════════════════════════════════════════
def ask_claude(question, contracts, api_key):
    try:
        client  = anthropic.Anthropic(api_key=api_key)
        analysis = analyze_portfolio(contracts)
        system  = f"""أنت وكيل ذكي متخصص في تحليل عقود الخيارات (Options). تجاوب بالعربي دائماً.
تعرف الفرق بين Call وPut، وبين Long وShort، وتفهم Strike Price وPremium وBreak-Even.

== بيانات المحفظة الحالية ==
{json.dumps(analysis, ensure_ascii=False, indent=2)}

قواعد: إجاباتك مباشرة ومفيدة بالعربي. اذكر الأرقام الدقيقة من البيانات."""
        message = client.messages.create(
            model="claude-opus-4-6", max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        return message.content[0].text
    except anthropic.AuthenticationError:
        return "❌ مفتاح API غلط."
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

# ═══════════════════════════════════════════════════════════
# API Routes
# ═══════════════════════════════════════════════════════════
@app.route("/api/portfolio")
def api_portfolio():
    contracts = load_contracts()
    return jsonify(analyze_portfolio(contracts))

@app.route("/api/contracts", methods=["GET"])
def api_get_contracts():
    return jsonify(load_contracts())

@app.route("/api/contracts", methods=["POST"])
def api_add_contract():
    data = request.json
    contracts = load_contracts()
    data["added_at"] = datetime.now().isoformat()
    contracts.append(data)
    save_contracts(contracts)
    return jsonify({"success": True})

@app.route("/api/contracts/<int:idx>", methods=["DELETE"])
def api_delete_contract(idx):
    contracts = load_contracts()
    if 0 <= idx < len(contracts):
        removed = contracts.pop(idx)
        save_contracts(contracts)
        return jsonify({"success": True, "removed": removed})
    return jsonify({"error": "رقم غير صحيح"}), 400

@app.route("/api/price/<symbol>")
def api_price(symbol):
    price = get_stock_price(symbol.upper())
    return jsonify({"symbol": symbol.upper(), "price": price})

@app.route("/api/market/<symbol>")
def api_market(symbol):
    return jsonify(get_market_summary(symbol.upper()))

@app.route("/api/adx/<symbol>")
def api_adx(symbol):
    """قراءة ADX. يقبل تجاوز مؤقت للإعدادات عبر الرابط:
    /api/adx/AAPL?adx_weight=1.4&adx_strong=22"""
    settings = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in request.args:
            settings = {**settings, **{key: request.args[key]}}
    # تطبيع القيم القادمة من الرابط بنفس قواعد الحفظ
    normalized = dict(DEFAULT_SETTINGS)
    for key, val in settings.items():
        default = DEFAULT_SETTINGS[key]
        try:
            if isinstance(default, bool):
                normalized[key] = val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                normalized[key] = int(float(val))
            else:
                normalized[key] = float(val)
        except (TypeError, ValueError):
            normalized[key] = default
    return jsonify(get_adx(symbol.upper(), normalized))

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    return jsonify(save_settings(request.json or {}))

@app.route("/api/settings/reset", methods=["POST"])
def api_reset_settings():
    return jsonify(save_settings(DEFAULT_SETTINGS))

@app.route("/api/options/<symbol>")
def api_options(symbol):
    expiry = request.args.get("expiry")
    return jsonify(get_options_chain(symbol.upper(), expiry))

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data      = request.json
    question  = data.get("question", "")
    api_key   = data.get("api_key", "")
    contracts = load_contracts()
    if not api_key:
        return jsonify({"error": "أدخل مفتاح API أولاً"})
    response = ask_claude(question, contracts, api_key)
    return jsonify({"response": response})

# ═══════════════════════════════════════════════════════════
# الصفحة الرئيسية
# ═══════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>وكيل عقود الخيارات</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1a2236;
    --border: #1e2d45;
    --accent: #00d4aa;
    --accent2: #3b82f6;
    --red: #ef4444;
    --green: #10b981;
    --yellow: #f59e0b;
    --text: #e2e8f0;
    --muted: #64748b;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  /* Header */
  header {
    background: linear-gradient(135deg, #0f172a 0%, #1a2236 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(10px);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo-icon {
    width: 38px; height: 38px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
  }
  .logo-text { font-size: 18px; font-weight: 700; }
  .logo-sub  { font-size: 11px; color: var(--muted); }

  /* Nav Tabs */
  .tabs {
    display: flex;
    gap: 4px;
    background: var(--surface);
    padding: 4px;
    border-radius: 12px;
    border: 1px solid var(--border);
  }
  .tab {
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    color: var(--muted);
    transition: all 0.2s;
    border: none;
    background: none;
    font-family: inherit;
  }
  .tab.active {
    background: var(--accent);
    color: #0a0e1a;
  }
  .tab:hover:not(.active) { color: var(--text); background: var(--surface2); }

  /* API Key bar */
  .api-bar {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .api-bar label { font-size: 13px; color: var(--muted); white-space: nowrap; }
  .api-bar input {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    color: var(--text);
    font-size: 13px;
    font-family: monospace;
    direction: ltr;
  }
  .api-bar input:focus { outline: none; border-color: var(--accent); }
  .btn-save {
    background: var(--accent);
    color: #0a0e1a;
    border: none;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    font-size: 13px;
    font-family: inherit;
  }

  /* Main content */
  main { padding: 24px; max-width: 1200px; margin: 0 auto; }

  /* Panels */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 20px;
  }
  .panel-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  /* Stats grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .stat {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
  }
  .stat-value { font-size: 24px; font-weight: 700; }
  .stat-label { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .positive { color: var(--green); }
  .negative { color: var(--red); }

  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th {
    text-align: right;
    padding: 10px 12px;
    background: var(--surface2);
    color: var(--muted);
    font-weight: 500;
    font-size: 12px;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-call  { background: rgba(16,185,129,0.15); color: var(--green); }
  .badge-put   { background: rgba(239,68,68,0.15);  color: var(--red); }
  .badge-long  { background: rgba(59,130,246,0.15); color: var(--accent2); }
  .badge-short { background: rgba(245,158,11,0.15); color: var(--yellow); }

  /* Forms */
  .form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
  }
  .form-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
  .form-group input,
  .form-group select {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }
  .form-group input:focus,
  .form-group select:focus { outline: none; border-color: var(--accent); }
  .form-group select option { background: var(--surface2); }

  /* Buttons */
  .btn {
    padding: 10px 20px;
    border-radius: 10px;
    border: none;
    cursor: pointer;
    font-weight: 600;
    font-size: 14px;
    font-family: inherit;
    transition: all 0.2s;
  }
  .btn-primary { background: var(--accent); color: #0a0e1a; }
  .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
  .btn-danger  { background: rgba(239,68,68,0.15); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }
  .btn-danger:hover { background: rgba(239,68,68,0.25); }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }

  /* Search bar */
  .search-row {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
  }
  .search-row input {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 14px;
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
    direction: ltr;
  }
  .search-row input:focus { outline: none; border-color: var(--accent); }

  /* Chat */
  .chat-messages {
    height: 380px;
    overflow-y: auto;
    padding: 16px;
    background: var(--surface2);
    border-radius: 12px;
    margin-bottom: 14px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .msg {
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 14px;
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
  }
  .msg-user {
    background: var(--accent);
    color: #0a0e1a;
    align-self: flex-end;
    border-radius: 14px 14px 4px 14px;
  }
  .msg-bot {
    background: var(--surface);
    border: 1px solid var(--border);
    align-self: flex-start;
    border-radius: 14px 14px 14px 4px;
  }
  .msg-system {
    color: var(--muted);
    font-size: 12px;
    align-self: center;
    font-style: italic;
  }
  .chat-input-row {
    display: flex;
    gap: 10px;
  }
  .chat-input-row input {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }
  .chat-input-row input:focus { outline: none; border-color: var(--accent); }

  /* Market info card */
  .market-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-top: 14px;
  }
  .market-price { font-size: 32px; font-weight: 700; }
  .market-change { font-size: 14px; margin-top: 4px; }
  .market-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 14px;
  }
  .market-item { font-size: 13px; }
  .market-item span { color: var(--muted); display: block; font-size: 11px; }

  /* ADX indicator */
  .adx-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-right: 4px solid var(--muted);
    border-radius: 12px;
    padding: 16px;
    margin-top: 14px;
  }
  .adx-card.adx-green  { border-right-color: var(--green);  background: rgba(16,185,129,0.07); }
  .adx-card.adx-red    { border-right-color: var(--red);    background: rgba(239,68,68,0.07); }
  .adx-card.adx-yellow { border-right-color: var(--yellow); background: rgba(245,158,11,0.06); }
  .adx-card.adx-gray   { border-right-color: var(--muted); }
  .adx-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .adx-value { font-size: 28px; font-weight: 700; }
  .adx-green  .adx-value { color: var(--green); }
  .adx-red    .adx-value { color: var(--red); }
  .adx-yellow .adx-value { color: var(--yellow); }
  .adx-gray   .adx-value { color: var(--muted); }
  .adx-label { font-size: 13px; font-weight: 600; }
  .adx-raw { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .adx-bar {
    position: relative;
    height: 8px;
    background: var(--bg);
    border-radius: 6px;
    margin: 14px 0 6px;
    overflow: hidden;
  }
  .adx-bar-fill { height: 100%; border-radius: 6px; transition: width .3s ease; }
  .adx-green  .adx-bar-fill { background: var(--green); }
  .adx-red    .adx-bar-fill { background: var(--red); }
  .adx-yellow .adx-bar-fill { background: var(--yellow); }
  .adx-gray   .adx-bar-fill { background: var(--muted); }
  .adx-tick {
    position: absolute; top: -3px; width: 2px; height: 14px;
    background: var(--border);
  }
  .adx-di { display: flex; gap: 18px; font-size: 12px; margin-top: 10px; flex-wrap: wrap; }
  .adx-di b { font-weight: 600; }

  /* Options table */
  .options-tabs {
    display: flex; gap: 8px; margin-bottom: 14px;
  }
  .opt-tab {
    padding: 6px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--muted);
    font-family: inherit;
  }
  .opt-tab.active-call { background: rgba(16,185,129,0.2); color: var(--green); border-color: rgba(16,185,129,0.4); }
  .opt-tab.active-put  { background: rgba(239,68,68,0.2);  color: var(--red);   border-color: rgba(239,68,68,0.4); }

  /* Loading spinner */
  .spinner {
    display: inline-block;
    width: 16px; height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Toast */
  #toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(80px);
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 24px;
    font-size: 14px;
    transition: transform 0.3s;
    z-index: 999;
  }
  #toast.show { transform: translateX(-50%) translateY(0); }

  /* Page sections */
  .page { display: none; }
  .page.active { display: block; }

  /* Delete btn in table */
  .del-btn {
    background: none;
    border: none;
    color: var(--red);
    cursor: pointer;
    font-size: 16px;
    padding: 4px 8px;
    border-radius: 6px;
    opacity: 0.6;
    transition: opacity 0.2s;
  }
  .del-btn:hover { opacity: 1; background: rgba(239,68,68,0.1); }

  @media (max-width: 600px) {
    header { flex-direction: column; gap: 12px; align-items: flex-start; }
    .tabs { width: 100%; overflow-x: auto; }
    main { padding: 16px; }
    .stats-grid { grid-template-columns: 1fr 1fr; }
    .form-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">📊</div>
    <div>
      <div class="logo-text">وكيل الخيارات</div>
      <div class="logo-sub">Claude AI + Yahoo Finance</div>
    </div>
  </div>
  <div class="tabs">
    <button class="tab active" onclick="showPage('portfolio')">المحفظة</button>
    <button class="tab" onclick="showPage('add')">+ إضافة عقد</button>
    <button class="tab" onclick="showPage('market')">السوق</button>
    <button class="tab" onclick="showPage('options')">الخيارات</button>
    <button class="tab" onclick="showPage('chat')">🤖 الوكيل</button>
  </div>
</header>

<div class="api-bar">
  <label>🔑 مفتاح API:</label>
  <input type="password" id="apiKey" placeholder="sk-ant-api03-..." />
  <button class="btn-save" onclick="saveKey()">حفظ</button>
</div>

<main>

  <!-- ───── المحفظة ───── -->
  <div id="page-portfolio" class="page active">
    <div id="statsArea"></div>
    <div class="panel">
      <div class="panel-title">📋 عقوداتي</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>الأصل</th><th>النوع</th><th>الاتجاه</th>
              <th>Strike</th><th>دخول</th><th>حالي</th><th>P&L</th>
              <th>Break-Even</th><th>انتهاء</th><th>حذف</th>
            </tr>
          </thead>
          <tbody id="contractsTable"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ───── إضافة عقد ───── -->
  <div id="page-add" class="page">
    <div class="panel">
      <div class="panel-title">➕ إضافة عقد جديد</div>
      <div class="form-grid">
        <div class="form-group">
          <label>رمز السهم</label>
          <input id="f-symbol" placeholder="AAPL" style="direction:ltr" />
        </div>
        <div class="form-group">
          <label>نوع العقد</label>
          <select id="f-type">
            <option value="call">Call 📈</option>
            <option value="put">Put 📉</option>
          </select>
        </div>
        <div class="form-group">
          <label>الاتجاه</label>
          <select id="f-side">
            <option value="long">Long</option>
            <option value="short">Short</option>
          </select>
        </div>
        <div class="form-group">
          <label>Strike Price ($)</label>
          <input id="f-strike" type="number" placeholder="150.00" style="direction:ltr" />
        </div>
        <div class="form-group">
          <label>Premium عند الدخول ($)</label>
          <input id="f-entry" type="number" step="0.01" placeholder="3.50" style="direction:ltr" />
        </div>
        <div class="form-group">
          <label>Premium الحالي ($)</label>
          <input id="f-current" type="number" step="0.01" placeholder="4.20" style="direction:ltr" />
        </div>
        <div class="form-group">
          <label>عدد العقود</label>
          <input id="f-qty" type="number" value="1" style="direction:ltr" />
        </div>
        <div class="form-group">
          <label>تاريخ الانتهاء</label>
          <input id="f-expiry" type="date" style="direction:ltr" />
        </div>
      </div>
      <div style="margin-top:20px">
        <button class="btn btn-primary" onclick="addContract()">✅ إضافة العقد</button>
      </div>
    </div>
  </div>

  <!-- ───── السوق ───── -->
  <div id="page-market" class="page">
    <div class="panel">
      <div class="panel-title">📈 بيانات السوق</div>
      <div class="search-row">
        <input id="marketSymbol" placeholder="AAPL, TSLA, MSFT..." onkeydown="if(event.key==='Enter') fetchMarket()" />
        <button class="btn btn-primary" onclick="fetchMarket()">بحث</button>
      </div>
      <div id="marketResult"></div>
    </div>

    <div class="panel">
      <div class="panel-title">⚙️ إعدادات مؤشر ADX</div>
      <div class="form-grid">
        <div class="form-group">
          <label>الفترة (Period)</label>
          <input id="setPeriod" type="number" min="2" max="100" step="1" />
        </div>
        <div class="form-group">
          <label>وزن المؤشر (تثقيل)</label>
          <input id="setWeight" type="number" min="0.1" max="5" step="0.1" />
        </div>
        <div class="form-group">
          <label>عتبة الاتجاه القوي (أخضر)</label>
          <input id="setStrong" type="number" min="1" max="100" step="1" />
        </div>
        <div class="form-group">
          <label>عتبة الاتجاه القوي جداً</label>
          <input id="setVeryStrong" type="number" min="1" max="100" step="1" />
        </div>
        <div class="form-group">
          <label>عتبة بداية الاتجاه (أصفر)</label>
          <input id="setWeak" type="number" min="1" max="100" step="1" />
        </div>
        <div class="form-group">
          <label>أقل فرق بين ‎+DI و ‎-DI</label>
          <input id="setGap" type="number" min="0" max="50" step="0.5" />
        </div>
        <div class="form-group">
          <label>التلوين</label>
          <select id="setColorMode">
            <option value="false">أخضر لأي اتجاه قوي</option>
            <option value="true">أخضر للصاعد / أحمر للهابط</option>
          </select>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="saveAdxSettings()">حفظ الإعدادات</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="resetAdxSettings()">استرجاع الافتراضي</button>
        <span id="settingsMsg" style="align-self:center;font-size:12px;color:var(--muted)"></span>
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:12px;line-height:1.7">
        الوزن يضرب قيمة ADX قبل مقارنتها بالعتبات. وزن أكبر من 1 يثقّل المؤشر
        فيخضّر أبكر مع التحركات الاتجاهية القوية، ووزن أقل من 1 يشدّده.
      </div>
    </div>
  </div>

  <!-- ───── الخيارات ───── -->
  <div id="page-options" class="page">
    <div class="panel">
      <div class="panel-title">🔗 سلسلة الخيارات (Options Chain)</div>
      <div class="search-row">
        <input id="optionsSymbol" placeholder="AAPL, TSLA, SPY..." onkeydown="if(event.key==='Enter') fetchOptions()" />
        <button class="btn btn-primary" onclick="fetchOptions()">جلب الخيارات</button>
      </div>
      <div id="optionsResult"></div>
    </div>
  </div>

  <!-- ───── الوكيل الذكي ───── -->
  <div id="page-chat" class="page">
    <div class="panel">
      <div class="panel-title">🤖 الوكيل الذكي</div>
      <div class="chat-messages" id="chatMessages">
        <div class="msg msg-system">مرحباً! اسألني عن محفظتك أو عقوداتك أو السوق 📊</div>
      </div>
      <div class="chat-input-row">
        <input id="chatInput" placeholder="اكتب سؤالك هنا..." onkeydown="if(event.key==='Enter') sendChat()" />
        <button class="btn btn-primary" onclick="sendChat()">إرسال ↗</button>
      </div>
    </div>
  </div>

</main>

<div id="toast"></div>

<script>
let API_KEY = localStorage.getItem('apiKey') || '';
document.getElementById('apiKey').value = API_KEY;

function saveKey() {
  API_KEY = document.getElementById('apiKey').value.trim();
  localStorage.setItem('apiKey', API_KEY);
  toast('✅ تم حفظ المفتاح');
}

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'portfolio') loadPortfolio();
}

function toast(msg, color='') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = color || '';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── المحفظة ──
async function loadPortfolio() {
  const res  = await fetch('/api/portfolio');
  const data = await res.json();
  if (data.error) {
    document.getElementById('statsArea').innerHTML = `<div class="panel" style="color:var(--muted);text-align:center;padding:40px">📭 المحفظة فارغة. أضف عقوداً من تبويب "إضافة عقد"</div>`;
    document.getElementById('contractsTable').innerHTML = '';
    return;
  }
  const pnlColor = data.total_pnl >= 0 ? 'positive' : 'negative';
  const pnlSign  = data.total_pnl >= 0 ? '+' : '';
  document.getElementById('statsArea').innerHTML = `
    <div class="stats-grid">
      <div class="stat"><div class="stat-value">${data.total_contracts}</div><div class="stat-label">إجمالي العقود</div></div>
      <div class="stat"><div class="stat-value ${pnlColor}">${pnlSign}$${data.total_pnl}</div><div class="stat-label">إجمالي P&L</div></div>
      <div class="stat"><div class="stat-value">${data.win_rate}%</div><div class="stat-label">نسبة الفوز</div></div>
      <div class="stat"><div class="stat-value" style="color:var(--green)">${data.calls}</div><div class="stat-label">Calls</div></div>
      <div class="stat"><div class="stat-value" style="color:var(--red)">${data.puts}</div><div class="stat-label">Puts</div></div>
      <div class="stat"><div class="stat-value">$${data.total_cost.toFixed(0)}</div><div class="stat-label">إجمالي التكلفة</div></div>
    </div>`;
  let rows = '';
  data.contracts_detail.forEach((c, i) => {
    const pnlC = c.pnl >= 0 ? 'positive' : 'negative';
    const pnlS = c.pnl >= 0 ? '+' : '';
    rows += `<tr>
      <td style="color:var(--muted)">${i+1}</td>
      <td style="font-weight:600">${c.symbol}</td>
      <td><span class="badge badge-${c.type}">${c.type.toUpperCase()}</span></td>
      <td><span class="badge badge-${c.side}">${c.side.toUpperCase()}</span></td>
      <td>$${c.strike}</td>
      <td>$${c.entry}</td>
      <td>$${c.current}</td>
      <td class="${pnlC}" style="font-weight:600">${pnlS}$${c.pnl}</td>
      <td>$${c.break_even}</td>
      <td style="color:var(--muted);font-size:12px">${c.expiry}</td>
      <td><button class="del-btn" onclick="deleteContract(${i})">🗑</button></td>
    </tr>`;
  });
  document.getElementById('contractsTable').innerHTML = rows || '<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:24px">لا توجد عقود</td></tr>';
}

async function deleteContract(idx) {
  if (!confirm('حذف هذا العقد؟')) return;
  await fetch('/api/contracts/' + idx, {method:'DELETE'});
  toast('🗑 تم الحذف', 'var(--red)');
  loadPortfolio();
}

// ── إضافة عقد ──
async function addContract() {
  const data = {
    symbol:          document.getElementById('f-symbol').value.toUpperCase().trim(),
    type:            document.getElementById('f-type').value,
    side:            document.getElementById('f-side').value,
    strike:          parseFloat(document.getElementById('f-strike').value),
    entry_premium:   parseFloat(document.getElementById('f-entry').value),
    current_premium: parseFloat(document.getElementById('f-current').value),
    qty:             parseInt(document.getElementById('f-qty').value),
    expiry:          document.getElementById('f-expiry').value,
  };
  if (!data.symbol || !data.strike || !data.entry_premium || !data.expiry) {
    toast('⚠️ أكمل جميع الحقول', 'var(--yellow)'); return;
  }
  await fetch('/api/contracts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  toast('✅ تمت الإضافة بنجاح');
  // clear form
  ['f-symbol','f-strike','f-entry','f-current','f-expiry'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('f-qty').value = '1';
}

// ── السوق ──
async function fetchMarket() {
  const sym = document.getElementById('marketSymbol').value.toUpperCase().trim();
  if (!sym) return;
  document.getElementById('marketResult').innerHTML = '<div style="color:var(--muted)"><span class="spinner"></span> جاري الجلب...</div>';
  const res  = await fetch('/api/market/' + sym);
  const data = await res.json();
  if (data.error) {
    document.getElementById('marketResult').innerHTML = `<div style="color:var(--red)">❌ ${data.error}</div>`;
    return;
  }
  const chC = (data.change_pct || 0) >= 0 ? 'positive' : 'negative';
  const chS = (data.change_pct || 0) >= 0 ? '▲' : '▼';
  document.getElementById('marketResult').innerHTML = `
    <div class="market-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="color:var(--muted);font-size:13px;margin-bottom:4px">${data.symbol}</div>
          <div class="market-price">$${data.price || 'N/A'}</div>
          <div class="market-change ${chC}">${chS} ${data.change_pct}% اليوم</div>
        </div>
        <div style="text-align:left;color:var(--muted);font-size:12px">${data.sector || ''}</div>
      </div>
      <div class="market-grid">
        <div class="market-item"><span>أعلى 52 أسبوع</span>$${data['52w_high'] || 'N/A'}</div>
        <div class="market-item"><span>أدنى 52 أسبوع</span>$${data['52w_low'] || 'N/A'}</div>
        <div class="market-item"><span>P/E Ratio</span>${data.pe_ratio ? data.pe_ratio.toFixed(2) : 'N/A'}</div>
        <div class="market-item"><span>Beta</span>${data.beta ? data.beta.toFixed(2) : 'N/A'}</div>
        <div class="market-item"><span>Market Cap</span>${data.market_cap ? '$' + (data.market_cap/1e9).toFixed(1) + 'B' : 'N/A'}</div>
      </div>
    </div>
    ${renderAdx(data.adx)}`;
}

// ── مؤشر ADX ──
function renderAdx(adx) {
  if (!adx) return '';
  if (adx.error) {
    return `<div class="adx-card adx-gray">
      <div class="adx-label">مؤشر ADX</div>
      <div class="adx-raw">❌ ${adx.error}</div>
    </div>`;
  }
  const arrow  = adx.direction === 'صاعد' ? '▲' : (adx.direction === 'هابط' ? '▼' : '◆');
  const trend  = adx.rising ? 'يتصاعد' : 'يتراجع';
  const fill   = Math.min(100, adx.adx_weighted);
  const ticks  = [adx.thresholds.weak, adx.thresholds.strong, adx.thresholds.very_strong]
    .map(t => `<div class="adx-tick" style="right:${Math.min(100, t)}%"></div>`).join('');
  return `
    <div class="adx-card adx-${adx.color}">
      <div class="adx-head">
        <div>
          <div class="adx-value">${adx.adx_weighted.toFixed(1)}</div>
          <div class="adx-raw">ADX(${adx.period}) الخام ${adx.adx.toFixed(1)} × وزن ${adx.weight} — ${trend}</div>
        </div>
        <div style="text-align:left">
          <div class="adx-label">${arrow} ${adx.label}</div>
          <div class="adx-raw">${adx.direction}</div>
        </div>
      </div>
      <div class="adx-bar">
        <div class="adx-bar-fill" style="width:${fill}%"></div>
        ${ticks}
      </div>
      <div class="adx-di">
        <div><b style="color:var(--green)">+DI</b> ${adx.plus_di.toFixed(1)}</div>
        <div><b style="color:var(--red)">−DI</b> ${adx.minus_di.toFixed(1)}</div>
        <div style="color:var(--muted)">الفرق ${Math.abs(adx.di_gap).toFixed(1)}</div>
        <div style="color:var(--muted)">عتبة الأخضر ${adx.thresholds.strong}</div>
      </div>
    </div>`;
}

// ── إعدادات ADX ──
const ADX_FIELDS = {
  setPeriod:     'adx_period',
  setWeight:     'adx_weight',
  setStrong:     'adx_strong',
  setVeryStrong: 'adx_very_strong',
  setWeak:       'adx_weak',
  setGap:        'adx_min_di_gap',
};

async function loadAdxSettings() {
  try {
    const s = await (await fetch('/api/settings')).json();
    for (const [id, key] of Object.entries(ADX_FIELDS)) {
      document.getElementById(id).value = s[key];
    }
    document.getElementById('setColorMode').value = s.adx_color_by_direction ? 'true' : 'false';
  } catch (e) { /* الصفحة تشتغل حتى لو فشل التحميل */ }
}

async function saveAdxSettings() {
  const payload = {};
  for (const [id, key] of Object.entries(ADX_FIELDS)) {
    payload[key] = document.getElementById(id).value;
  }
  payload.adx_color_by_direction = document.getElementById('setColorMode').value === 'true';
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const saved = await res.json();
  for (const [id, key] of Object.entries(ADX_FIELDS)) {
    document.getElementById(id).value = saved[key];
  }
  showSettingsMsg('✅ تم الحفظ');
  if (document.getElementById('marketSymbol').value.trim()) fetchMarket();
}

async function resetAdxSettings() {
  await fetch('/api/settings/reset', { method: 'POST' });
  await loadAdxSettings();
  showSettingsMsg('↺ رجعت الافتراضية');
  if (document.getElementById('marketSymbol').value.trim()) fetchMarket();
}

function showSettingsMsg(text) {
  const el = document.getElementById('settingsMsg');
  el.textContent = text;
  setTimeout(() => { el.textContent = ''; }, 2500);
}

// ── الخيارات ──
let optionsData = null;
async function fetchOptions() {
  const sym = document.getElementById('optionsSymbol').value.toUpperCase().trim();
  if (!sym) return;
  document.getElementById('optionsResult').innerHTML = '<div style="color:var(--muted)"><span class="spinner"></span> جاري الجلب...</div>';
  const res  = await fetch('/api/options/' + sym);
  optionsData = await res.json();
  if (optionsData.error) {
    document.getElementById('optionsResult').innerHTML = `<div style="color:var(--red)">❌ ${optionsData.error}</div>`;
    return;
  }
  renderOptions('calls');
}

function renderOptions(type) {
  if (!optionsData) return;
  const data = optionsData;
  const rows = data[type].map(r => `<tr>
    <td>$${r.strike}</td>
    <td>$${r.lastPrice?.toFixed(2)||'-'}</td>
    <td>$${r.bid?.toFixed(2)||'-'}</td>
    <td>$${r.ask?.toFixed(2)||'-'}</td>
    <td>${r.volume||0}</td>
    <td>${r.openInterest||0}</td>
    <td>${r.impliedVolatility?(r.impliedVolatility*100).toFixed(1)+'%':'-'}</td>
  </tr>`).join('');
  const callActive = type==='calls' ? 'active-call' : '';
  const putActive  = type==='puts'  ? 'active-put'  : '';
  document.getElementById('optionsResult').innerHTML = `
    <div style="margin-bottom:10px;color:var(--muted);font-size:13px">
      ${data.symbol} | تاريخ: ${data.expiry} | 
      <span style="font-size:11px">تواريخ: ${data.all_expiries.join(', ')}</span>
    </div>
    <div class="options-tabs">
      <button class="opt-tab ${callActive}" onclick="renderOptions('calls')">📈 Calls</button>
      <button class="opt-tab ${putActive}"  onclick="renderOptions('puts')">📉 Puts</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Strike</th><th>آخر سعر</th><th>Bid</th><th>Ask</th><th>Volume</th><th>Open Int.</th><th>IV%</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── الوكيل الذكي ──
async function sendChat() {
  const input = document.getElementById('chatInput');
  const q = input.value.trim();
  if (!q) return;
  if (!API_KEY) { toast('⚠️ أدخل مفتاح API أولاً', 'var(--yellow)'); return; }
  addMsg(q, 'user');
  input.value = '';
  const typing = addMsg('...', 'bot');
  const res  = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: q, api_key: API_KEY})
  });
  const data = await res.json();
  typing.textContent = data.response || data.error;
  scrollChat();
}

function addMsg(text, type) {
  const div = document.createElement('div');
  div.className = `msg msg-${type}`;
  div.textContent = text;
  document.getElementById('chatMessages').appendChild(div);
  scrollChat();
  return div;
}

function scrollChat() {
  const c = document.getElementById('chatMessages');
  c.scrollTop = c.scrollHeight;
}

// تحميل أولي
loadPortfolio();
loadAdxSettings();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print("\n" + "="*55)
    print("  🚀 وكيل الخيارات - Web App")
    print("="*55)
    print(f"  💻 على جهازك:   http://localhost:5000")
    print(f"  📱 من الجوال:   http://{local_ip}:5000")
    print("="*55)
    print("  (تأكد أن الجوال والكمبيوتر على نفس الـ WiFi)")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)