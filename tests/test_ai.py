from __future__ import annotations

import dataclasses

import pytest

from options_agent.ai import ClaudeAdvisor
from options_agent.errors import AuthError, ConfigurationError, UpstreamError, ValidationError

from .conftest import FakeAnthropicClient


class AuthenticationError(Exception):
    """Mirrors anthropic.AuthenticationError by name only."""


class RateLimitError(Exception):
    pass


def test_missing_key_raises_configuration_error(settings):
    advisor = ClaudeAdvisor(dataclasses.replace(settings, anthropic_api_key=None),
                            client_factory=FakeAnthropicClient)
    with pytest.raises(ConfigurationError):
        advisor.ask("سؤال", {})


def test_blank_question_rejected(settings):
    advisor = ClaudeAdvisor(settings, client_factory=FakeAnthropicClient)
    with pytest.raises(ValidationError):
        advisor.ask("   ", {})


def test_overlong_question_rejected(settings):
    advisor = ClaudeAdvisor(settings, client_factory=FakeAnthropicClient)
    with pytest.raises(ValidationError):
        advisor.ask("x" * 5000, {})


def _failing_factory(exc: Exception):
    class _Client:
        def __init__(self, api_key: str) -> None:
            self.messages = self

        def create(self, **_kwargs):
            raise exc

    return _Client


def test_authentication_error_becomes_auth_error(settings):
    advisor = ClaudeAdvisor(settings, client_factory=_failing_factory(AuthenticationError()))
    with pytest.raises(AuthError):
        advisor.ask("سؤال", {})


def test_rate_limit_becomes_upstream_error(settings):
    advisor = ClaudeAdvisor(settings, client_factory=_failing_factory(RateLimitError()))
    with pytest.raises(UpstreamError):
        advisor.ask("سؤال", {})


def test_empty_response_becomes_upstream_error(settings):
    class _Empty:
        def __init__(self, api_key: str) -> None:
            self.messages = self

        def create(self, **_kwargs):
            return type("M", (), {"content": []})()

    advisor = ClaudeAdvisor(settings, client_factory=_Empty)
    with pytest.raises(UpstreamError):
        advisor.ask("سؤال", {})
