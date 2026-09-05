# وكيل عقود الخيارات — Options Portfolio Agent

تطبيق ويب لتتبّع وتحليل عقود الخيارات، مع بيانات سوق حيّة ومساعد ذكي يجيب بالعربية.

## البنية

```
app.py                      # WSGI entrypoint فقط (gunicorn app:app)
options_agent/
├── __init__.py             # create_app() — application factory
├── config.py               # Settings المقروءة من البيئة
├── errors.py               # أخطاء مصنّفة + معالجات JSON موحّدة
├── models.py               # Contract + التحقق الصارم من المدخلات
├── analytics.py            # حسابات PnL / Break-Even (دوال نقيّة)
├── repository.py           # تخزين SQLite آمن للتزامن + ترحيل contracts.json
├── market.py               # Yahoo Finance خلف واجهة قابلة للحقن والاختبار
├── ai.py                   # عميل Claude مع أخطاء مترجمة
├── services.py             # حاوية الاعتماديات
├── api.py                  # Blueprint للمسارات
└── templates/index.html    # الواجهة
tests/                      # 65 اختبار pytest
```

طبقات واضحة: المسارات تتحقق وتفوّض فقط، والمنطق في `analytics`/`models`، والـ I/O
في `repository`/`market`/`ai`. كل اعتماد خارجي يُحقن عبر `Services`، لذا تعمل
الاختبارات دون شبكة ودون مفاتيح.

## التشغيل

يتطلب Python 3.11 أو أحدث.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                       # تطوير
gunicorn app:app --bind 0.0.0.0:$PORT   # إنتاج
```

## متغيّرات البيئة

| المتغيّر | الافتراضي | الوصف |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | مفتاح النموذج على الخادم (يبقى إدخاله من الواجهة مدعوماً) |
| `ANTHROPIC_MODEL` | `claude-opus-5` | معرّف النموذج |
| `ANTHROPIC_MAX_TOKENS` | `1024` | حد الرد |
| `OPTIONS_DB_PATH` | `contracts.db` | مسار قاعدة البيانات |
| `OPTIONS_LEGACY_JSON` | `contracts.json` | ملف يُرحَّل مرة واحدة ثم يُعاد تسميته |
| `MARKET_CACHE_TTL` | `30` | ثوانٍ تخزين بيانات السوق مؤقتاً |
| `PORT` | `5000` | منفذ التطوير |

> على منصات النشر ذات القرص المؤقت، وجّه `OPTIONS_DB_PATH` إلى وحدة تخزين دائمة
> وإلا فُقدت العقود عند إعادة النشر.

## الاختبارات والفحص

```bash
pip install -r requirements-dev.txt
pytest          # 65 اختباراً، بلا شبكة وبلا مفتاح API
ruff check .    # فحص الأسلوب
ruff format .   # تنسيق
```

في جلسات Claude Code على الويب تُجهَّز البيئة تلقائياً عبر
`.claude/hooks/session-start.sh`، وقواعد المشروع موثّقة في `CLAUDE.md`.

## واجهة API

| المسار | الطريقة | الوصف |
| --- | --- | --- |
| `/api/health` | GET | فحص الجاهزية |
| `/api/portfolio` | GET | تحليل المحفظة المجمّع |
| `/api/contracts` | GET / POST | عرض العقود / إضافة عقد (201) |
| `/api/contracts/<id>` | DELETE | حذف عقد بالمعرّف |
| `/api/price/<symbol>` | GET | السعر الحالي |
| `/api/market/<symbol>` | GET | ملخّص السهم |
| `/api/options/<symbol>` | GET | سلسلة الخيارات (`?expiry=`) |
| `/api/chat` | POST | سؤال الوكيل الذكي |

الأخطاء تعود دائماً كـ JSON بالشكل `{"error": "...", "code": "..."}` مع رمز
HTTP مناسب: 400 للتحقق، 404 لغير الموجود، 401 للمفتاح غير الصالح، 502 لفشل
مزوّد خارجي، 503 لغياب الإعداد.

## ملاحظات الترحيل من النسخة السابقة

- الحذف صار بالمعرّف `id` بدل ترتيب العنصر في القائمة (كان عرضة لحذف الصف الخطأ
  عند تعديل متزامن).
- `/api/portfolio` لم يعد يعيد `{"error": "لا توجد عقود"}` لمحفظة فارغة، بل
  تحليلاً كاملاً بأصفار مع `"empty": true`.
- `contracts.json` يُرحَّل تلقائياً إلى SQLite عند أول تشغيل.
