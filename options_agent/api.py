"""HTTP API. Routes stay thin: validate, delegate, serialise."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from .analytics import analyze_portfolio
from .errors import ValidationError
from .models import Contract
from .services import get_services

api = Blueprint("api", __name__, url_prefix="/api")


def _json_body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("الطلب يجب أن يكون كائن JSON")
    return body


@api.get("/health")
def health():
    services = get_services()
    return jsonify({"status": "ok", "contracts": services.contracts.count()})


@api.get("/portfolio")
def get_portfolio():
    contracts = get_services().contracts.list_all()
    return jsonify(analyze_portfolio(contracts))


@api.get("/contracts")
def list_contracts():
    contracts = get_services().contracts.list_all()
    return jsonify([c.to_dict() for c in contracts])


@api.post("/contracts")
def add_contract():
    contract = Contract.from_payload(_json_body())
    stored = get_services().contracts.add(contract)
    return jsonify({"success": True, "contract": stored.to_dict()}), 201


@api.delete("/contracts/<int:contract_id>")
def delete_contract(contract_id: int):
    removed = get_services().contracts.delete(contract_id)
    return jsonify({"success": True, "removed": removed.to_dict()})


@api.get("/price/<symbol>")
def get_price(symbol: str):
    price = get_services().market.get_price(symbol)
    return jsonify({"symbol": symbol.upper(), "price": price})


@api.get("/market/<symbol>")
def get_market(symbol: str):
    return jsonify(get_services().market.get_summary(symbol))


@api.get("/options/<symbol>")
def get_options(symbol: str):
    expiry = request.args.get("expiry") or None
    return jsonify(get_services().market.get_options_chain(symbol, expiry))


@api.post("/chat")
def chat():
    body = _json_body()
    services = get_services()
    analysis = analyze_portfolio(services.contracts.list_all())
    answer = services.advisor.ask(
        body.get("question", ""),
        analysis,
        api_key=body.get("api_key"),
    )
    return jsonify({"response": answer})
