import pytest
from fastapi.testclient import TestClient
from main import app, transactions
import os

# Use the same key as in .env
API_KEY = os.getenv("GLOBAL_API_SECRET", "super-secret-global-api-key")
HEADERS = {
    "api-key": API_KEY,
    "device-id": "S9",
    "device-secret": "f7a9d3e8c2b51a09d4f8e6c7a3b1d9c5f2e8d4a6b9c3d1f0e7a2b5c4d8e9f1a0"
}

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_transactions():
    transactions.clear()

# Use a wrapper or modify the client to always include headers
def authenticated_post(url, json=None):
    return client.post(url, json=json, headers=HEADERS)

def authenticated_get(url):
    return client.get(url, headers=HEADERS)

def test_root():
    response = authenticated_get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Maestro Cerebro Escrow Service", "status": "active"}

def test_create_transaction():
    payload = {
        "amount": 1000.0,
        "sender_id": "user_a",
        "receiver_id": "user_b",
        "metadata": {"note": "Test payment"}
    }
    response = authenticated_post("/transactions/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 1000.0
    assert data["status"] == "pending"
    assert "id" in data

def test_escrow_lifecycle():
    # 1. Create
    payload = {"amount": 50.0, "sender_id": "a", "receiver_id": "b"}
    resp = authenticated_post("/transactions/", json=payload)
    tx_id = resp.json()["id"]

    # 2. Hold
    resp = authenticated_post(f"/transactions/{tx_id}/hold")
    assert resp.status_code == 200
    assert resp.json()["transaction"]["status"] == "held"

    # 3. Release
    resp = authenticated_post(f"/transactions/{tx_id}/release")
    assert resp.status_code == 200
    assert resp.json()["transaction"]["status"] == "released"

def test_cancel_transaction():
    payload = {"amount": 100.0, "sender_id": "a", "receiver_id": "b"}
    resp = authenticated_post("/transactions/", json=payload)
    tx_id = resp.json()["id"]

    resp = authenticated_post(f"/transactions/{tx_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["transaction"]["status"] == "cancelled"

def test_invalid_release():
    payload = {"amount": 50.0, "sender_id": "a", "receiver_id": "b"}
    resp = authenticated_post("/transactions/", json=payload)
    tx_id = resp.json()["id"]

    # Try to release without holding first
    resp = authenticated_post(f"/transactions/{tx_id}/release")
    assert resp.status_code == 400 # Should fail
