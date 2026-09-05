from __future__ import annotations

from .conftest import make_contract

VALID_PAYLOAD = {
    "symbol": "aapl",
    "type": "call",
    "side": "long",
    "strike": 200,
    "entry_premium": 5,
    "current_premium": 7.5,
    "qty": 2,
    "expiry": "2030-01-17",
}


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"<!DOCTYPE html>" in response.data


def test_health(client):
    body = client.get("/api/health").get_json()
    assert body == {"status": "ok", "contracts": 0}


def test_empty_portfolio(client):
    body = client.get("/api/portfolio").get_json()
    assert body["empty"] is True
    assert body["total_pnl"] == 0.0


def test_add_contract_returns_201_with_id(client):
    response = client.post("/api/contracts", json=VALID_PAYLOAD)
    assert response.status_code == 201
    contract = response.get_json()["contract"]
    assert contract["id"] == 1
    assert contract["symbol"] == "AAPL"


def test_add_contract_rejects_invalid_payload(client):
    response = client.post("/api/contracts", json={**VALID_PAYLOAD, "strike": -5})
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_error"


def test_add_contract_rejects_non_json(client):
    response = client.post("/api/contracts", data="oops", content_type="text/plain")
    assert response.status_code == 400


def test_portfolio_reflects_added_contract(client):
    client.post("/api/contracts", json=VALID_PAYLOAD)
    body = client.get("/api/portfolio").get_json()
    assert body["total_contracts"] == 1
    assert body["total_pnl"] == 500.0
    assert body["contracts_detail"][0]["id"] == 1


def test_delete_contract(client):
    contract_id = client.post("/api/contracts", json=VALID_PAYLOAD).get_json()["contract"]["id"]
    response = client.delete(f"/api/contracts/{contract_id}")
    assert response.status_code == 200
    assert response.get_json()["removed"]["id"] == contract_id
    assert client.get("/api/contracts").get_json() == []


def test_delete_missing_contract_returns_404(client):
    response = client.delete("/api/contracts/4242")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


def test_price_endpoint(client):
    body = client.get("/api/price/aapl").get_json()
    assert body == {"symbol": "AAPL", "price": 201.23}


def test_market_endpoint(client):
    body = client.get("/api/market/aapl").get_json()
    assert body["symbol"] == "AAPL"
    assert body["change_pct"] == 10.0


def test_options_endpoint(client):
    body = client.get("/api/options/aapl?expiry=2030-02-21").get_json()
    assert body["expiry"] == "2030-02-21"
    assert body["calls"][0]["strike"] == 200.0
    assert body["all_expiries"] == ["2030-01-17", "2030-02-21"]


def test_invalid_symbol_returns_400(client):
    response = client.get("/api/market/not-a-symbol!!")
    assert response.status_code == 400


def test_chat_uses_configured_model(client, created_clients, repository):
    repository.add(make_contract())
    response = client.post("/api/chat", json={"question": "كيف حال محفظتي؟"})
    assert response.status_code == 200
    assert response.get_json()["response"] == "تحليل تجريبي"
    assert created_clients[0].api_key == "sk-test"
    call = created_clients[0].calls[0]
    assert call["model"] == "claude-opus-5"
    assert "AAPL" in call["system"]


def test_chat_prefers_request_api_key(client, created_clients):
    client.post("/api/chat", json={"question": "س", "api_key": "sk-from-client"})
    assert created_clients[0].api_key == "sk-from-client"


def test_chat_rejects_empty_question(client):
    response = client.post("/api/chat", json={"question": "  "})
    assert response.status_code == 400


def test_unknown_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
