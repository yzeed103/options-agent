"""Typed application errors mapped onto HTTP responses."""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    """Base class for every error the application raises deliberately."""

    status_code: int = 500
    code: str = "internal_error"
    log_level: int = logging.ERROR

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
    log_level = logging.INFO


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    log_level = logging.INFO


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"
    log_level = logging.WARNING


class ConfigurationError(AppError):
    status_code = 503
    code = "not_configured"
    log_level = logging.WARNING


class UpstreamError(AppError):
    """A third-party dependency (market data, model provider) failed."""

    status_code = 502
    code = "upstream_error"
    log_level = logging.WARNING


def register_error_handlers(app: Flask) -> None:
    """Render every error as JSON so the SPA never has to parse HTML."""

    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError):
        app.logger.log(
            exc.log_level,
            "%s: %s",
            exc.code,
            exc.message,
            exc_info=exc if exc.log_level >= logging.ERROR else None,
        )
        return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc: HTTPException):
        return (
            jsonify({"error": exc.description, "code": exc.name.lower().replace(" ", "_")}),
            exc.code or 500,
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        app.logger.exception("unhandled error", exc_info=exc)
        return jsonify({"error": "حدث خطأ غير متوقع", "code": "internal_error"}), 500
