import pytest
from fastapi.testclient import TestClient
from main import app
import os
import time

client = TestClient(app)

def test_rate_limiting():
    # Headers for authentication
    API_KEY = os.getenv("GLOBAL_API_SECRET", "super-secret-global-api-key")
    HEADERS = {
        "api-key": API_KEY,
        "device-id": "S9",
        "device-secret": "f7a9d3e8c2b51a09d4f8e6c7a3b1d9c5f2e8d4a6b9c3d1f0e7a2b5c4d8e9f1a0"
    }
    
    # We set the limit to 5/minute for /transactions/
    payload = {"amount": 10.0, "sender_id": "x", "receiver_id": "y"}
    
    # First 5 should succeed (or at least not be 429)
    for i in range(5):
        response = client.post("/transactions/", json=payload, headers=HEADERS)
        # It might fail with 400 if Gemma fails, but it shouldn't be 429
        assert response.status_code != 429
        
    # The 6th should be rate limited
    response = client.post("/transactions/", json=payload, headers=HEADERS)
    assert response.status_code == 429
    assert "per 1 minute" in response.text
