"""Claude-backed portfolio advisor."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping

from .config import Settings
from .errors import AuthError, ConfigurationError, UpstreamError, ValidationError

logger = logging.getLogger(__name__)

MAX_QUESTION_LEN = 4000

SYSTEM_PROMPT = """أنت وكيل ذكي متخصص في تحليل عقود الخيارات (Options). تجاوب بالعربي دائماً.
تعرف الفرق بين Call وPut، وبين Long وShort، وتفهم Strike Price وPremium وBreak-Even.

== بيانات المحفظة الحالية ==
{analysis}

قواعد: إجاباتك مباشرة ومفيدة بالعربي. اذكر الأرقام الدقيقة من البيانات.
لا تقدّم نصيحة استثمارية قاطعة؛ اشرح المخاطر عند الاقتضاء."""

ClientFactory = Callable[[str], Any]


def _default_client_factory(api_key: str) -> Any:
    import anthropic  # imported lazily to keep test startup cheap

    return anthropic.Anthropic(api_key=api_key)


class ClaudeAdvisor:
    """Wraps the Anthropic client with validation and typed errors."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: ClientFactory = _default_client_factory,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory

    def _resolve_key(self, request_api_key: str | None) -> str:
        key = (request_api_key or "").strip() or self._settings.anthropic_api_key
        if not key:
            raise ConfigurationError("مفتاح API غير متوفر. أدخله في التطبيق أو عيّن ANTHROPIC_API_KEY")
        return key

    def ask(
        self,
        question: str,
        analysis: Mapping[str, Any],
        *,
        api_key: str | None = None,
    ) -> str:
        if not isinstance(question, str) or not question.strip():
            raise ValidationError("السؤال مطلوب")
        if len(question) > MAX_QUESTION_LEN:
            raise ValidationError(f"السؤال طويل جداً (الحد {MAX_QUESTION_LEN} حرف)")

        client = self._client_factory(self._resolve_key(api_key))
        system = SYSTEM_PROMPT.format(analysis=json.dumps(analysis, ensure_ascii=False, indent=2))
        try:
            message = client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=system,
                messages=[{"role": "user", "content": question.strip()}],
            )
        except Exception as exc:  # noqa: BLE001 - narrowed below
            raise _translate(exc) from exc

        blocks = getattr(message, "content", None) or []
        text = "".join(getattr(block, "text", "") for block in blocks).strip()
        if not text:
            raise UpstreamError("لم يصل رد من النموذج")
        return text


def _translate(exc: Exception) -> Exception:
    """Map provider exceptions onto application errors without importing
    anthropic at module import time."""
    name = type(exc).__name__
    if name == "AuthenticationError":
        return AuthError("مفتاح API غير صالح")
    if name in {"PermissionDeniedError", "NotFoundError"}:
        return UpstreamError("النموذج المطلوب غير متاح لهذا المفتاح")
    if name in {"RateLimitError", "APIStatusError", "APIConnectionError", "APITimeoutError"}:
        return UpstreamError("تعذّر الوصول لخدمة النموذج، حاول مرة أخرى")
    logger.exception("unexpected model error")
    return UpstreamError("خطأ غير متوقع أثناء الاتصال بالنموذج")
