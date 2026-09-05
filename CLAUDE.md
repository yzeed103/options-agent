# CLAUDE.md — دليل العمل على هذا المستودع

تطبيق Flask لتتبّع عقود الخيارات: تخزين SQLite، بيانات سوق من Yahoo Finance،
ومساعد Claude يجيب بالعربية.

## أوامر أساسية

```bash
pytest                      # كل الاختبارات (65)
pytest tests/test_api.py    # ملف واحد
ruff check .                # فحص الأسلوب
ruff format .               # تنسيق
python app.py               # تشغيل محلي على 5000
```

بيئة الجلسات على الويب تُجهَّز تلقائياً عبر `.claude/hooks/session-start.sh`
(يُنشئ `.venv` ويثبّت `requirements-dev.txt`).

## خريطة المشروع

اقرأ هذه الخريطة قبل فتح الملفات؛ لا تُعِد فهرسة المستودع كاملاً لكل طلب.

```
app.py ──> options_agent.create_app()
             │
             ├─ config.Settings      (لا يعتمد على شيء)
             ├─ errors.AppError      (لا يعتمد على شيء)
             ├─ models.Contract      ──> errors
             ├─ analytics            ──> models              [دوال نقيّة]
             ├─ repository           ──> models, errors      [SQLite]
             ├─ market               ──> models, errors      [yfinance]
             ├─ ai.ClaudeAdvisor     ──> config, errors      [anthropic]
             ├─ services.Services    ──> repository, market, ai, config
             └─ api (Blueprint)      ──> services, analytics, models
                    templates/index.html   [واجهة صفحة واحدة]
```

اتجاه الاعتماد أحادي: `api → services → (repository | market | ai) → models → errors`.
لا يستورد أي ملف ما هو أعلى منه في السلسلة.

### أين أعدّل ماذا

| التغيير | الملف |
| --- | --- |
| قاعدة حساب (PnL، Break-Even، تجميع) | `analytics.py` |
| حقل جديد أو قاعدة تحقق | `models.py` + `repository.py` (الجدول) |
| مسار HTTP جديد | `api.py` فقط |
| نوع خطأ أو رمز HTTP | `errors.py` |
| متغيّر بيئة | `config.py` + جدول README |
| مزوّد بيانات سوق | `market.py` |
| موديل أو prompt | `ai.py` |
| الواجهة | `templates/index.html` |

## قواعد الكود

1. **المسارات رفيعة.** `api.py` يتحقق ويفوّض ويُسلسل فقط — لا منطق أعمال فيه.
2. **الاعتماديات محقونة.** كل مزوّد خارجي يمرّ عبر `Services`؛ ممنوع استدعاء
   `yfinance` أو `anthropic` مباشرة خارج `market.py` و`ai.py`.
3. **أنواع صريحة** على كل دالة عامة، مع `from __future__ import annotations`.
4. **ممنوع `except:` العارية.** ارفع نوعاً من `errors.py`؛ الالتقاط العريض
   مسموح فقط عند حدود المزوّد الخارجي وبإعادة تغليف الخطأ.
5. **التحقق عند الحدود.** كل JSON وارد يمرّ عبر `Contract.from_payload` أو
   `normalize_symbol`؛ لا تثق بمدخلات الواجهة.
6. **لا حالة عامة.** لا متغيّرات module-level قابلة للتعديل؛ الحالة في
   `Services` المرتبطة بنسخة التطبيق.
7. **رسائل الخطأ للمستخدم بالعربية**، وسجلّات التشخيص بالإنجليزية.
8. **اختبار مع كل تغيير سلوك.** الاختبارات تعمل بلا شبكة وبلا مفتاح API —
   استخدم الـ fakes في `tests/conftest.py` ولا تضف اتصالاً حقيقياً.

## أسلوب الردود

مختصرة ومنظّمة ومباشرة، بلا مقدّمات أو حشو. جداول ونقاط بدل الفقرات الطويلة.
عند كتابة العربية، ضع كل مصطلح إنجليزي في سطر مستقل.

## محاذير

- **`OPTIONS_DB_PATH`** يجب أن يشير إلى تخزين دائم في الإنتاج، وإلا فُقدت
  البيانات عند إعادة النشر.
- **`migrate_legacy_json`** يعمل مرة واحدة فقط (يتخطّى إن كانت القاعدة غير فارغة).
- **الحذف بالمعرّف `id`** لا بترتيب الصف — لا تُرجِع الفهرسة بالموضع.
- **`analyze_portfolio([])`** يعيد `"empty": true` وليس خطأً.
