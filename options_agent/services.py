"""Service container wired once per application instance."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, current_app

from .ai import ClaudeAdvisor
from .config import Settings
from .market import MarketDataService
from .repository import ContractRepository

EXTENSION_KEY = "options_agent"


@dataclass(frozen=True)
class Services:
    settings: Settings
    contracts: ContractRepository
    market: MarketDataService
    advisor: ClaudeAdvisor


def bind(app: Flask, services: Services) -> None:
    app.extensions[EXTENSION_KEY] = services


def get_services() -> Services:
    return current_app.extensions[EXTENSION_KEY]
