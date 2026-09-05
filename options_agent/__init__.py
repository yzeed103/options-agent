"""Options portfolio agent — application factory."""

from __future__ import annotations

import logging

from flask import Flask, render_template

from .ai import ClaudeAdvisor
from .api import api
from .config import Settings
from .errors import register_error_handlers
from .market import MarketDataService
from .repository import ContractRepository
from .services import Services, bind

__all__ = ["create_app", "Settings"]

__version__ = "2.0.0"


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> Flask:
    """Build a fully wired application.

    Passing `services` lets tests substitute fakes for the market data and
    model providers without monkeypatching module globals.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = settings or Settings.from_env()
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["SETTINGS"] = settings

    if services is None:
        repository = ContractRepository(settings.database_path)
        repository.initialize()
        repository.migrate_legacy_json(settings.legacy_data_file)
        services = Services(
            settings=settings,
            contracts=repository,
            market=MarketDataService(cache_ttl=settings.market_cache_ttl),
            advisor=ClaudeAdvisor(settings),
        )

    bind(app, services)
    register_error_handlers(app)
    app.register_blueprint(api)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    return app
