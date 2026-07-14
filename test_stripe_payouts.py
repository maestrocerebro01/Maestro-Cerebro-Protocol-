import os
import json
import time
import hmac
import hashlib

# Configure the environment BEFORE importing the app/modules, since the Stripe
# client and ledger read config at import time.
WEBHOOK_SECRET = "whsec_test_secret_for_ci"
os.environ["STRIPE_MOCK"] = "true"
os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
os.environ["PAYOUT_LEDGER_PATH"] = "test_payout_events.jsonl"
os.environ.setdefault("GLOBAL_API_SECRET", "super-secret-global-api-key")

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

# Admin auth is verified against a bcrypt hash; set it up before importing main.
ADMIN_PASSWORD = "test-admin-pass"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
os.environ["ADMIN_PASSWORD_HASH"] = pwd_context.hash(ADMIN_PASSWORD)

from main import app  # noqa: E402
from ledger import LEDGER_PATH  # noqa: E402

client = TestClient(app)

API_KEY = os.environ["GLOBAL_API_SECRET"]
ADMIN_HEADERS = {"api-key": API_KEY, "admin-password": ADMIN_PASSWORD}


@pytest.fixture(autouse=True)
def clean_ledger():
    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)
    yield
    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET, timestamp: int = None) -> str:
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def _payout_event(event_id: str = "evt_test_1", event_type: str = "payout.paid") -> bytes:
    body = {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "livemode": False,
        "data": {"object": {"id": "po_test_1", "amount": 7500, "currency": "usd", "status": "paid"}},
    }
    return json.dumps(body).encode("utf-8")


def test_webhook_rejects_bad_signature():
    payload = _payout_event()
    resp = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": "t=123,v1=deadbeef"},
    )
    assert resp.status_code == 400


def test_webhook_accepts_and_is_idempotent():
    payload = _payout_event(event_id="evt_idem_1")
    sig = _sign(payload)

    first = client.post("/webhooks/stripe", content=payload, headers={"stripe-signature": sig})
    assert first.status_code == 200
    assert first.json().get("received") is True

    # Re-deliver the same event id: must be recognized as a duplicate, not reprocessed.
    second = client.post("/webhooks/stripe", content=payload, headers={"stripe-signature": _sign(payload)})
    assert second.status_code == 200
    assert second.json().get("duplicate") is True

    # The event should be recorded exactly once.
    with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
        matches = [l for l in fh if '"evt_idem_1"' in l]
    assert len(matches) == 1


def test_payout_requires_admin():
    # Missing admin credentials must not create a payout.
    resp = client.post("/payouts/stripe", json={"amount": 50.0}, headers={"api-key": API_KEY})
    assert resp.status_code in (401, 403, 422)


def test_payout_idempotency_key_never_reused():
    key = "payout-key-unique-123"
    body = {"amount": 50.0, "currency": "USD", "idempotency_key": key}

    first = client.post("/payouts/stripe", json=body, headers=ADMIN_HEADERS)
    assert first.status_code == 200
    assert first.json()["idempotency_key"] == key

    # Reusing the same key must be rejected to prevent a double payout.
    second = client.post("/payouts/stripe", json=body, headers=ADMIN_HEADERS)
    assert second.status_code == 409
