import os
import json

# Configure environment BEFORE importing the app/modules (singletons read config
# at import time). Match test_stripe_payouts so the shared singletons are happy
# regardless of test file import order.
os.environ["STRIPE_MOCK"] = "true"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret_for_ci"
os.environ["QUICKBOOKS_MOCK"] = "true"
os.environ["PAYOUT_LEDGER_PATH"] = "test_payout_events.jsonl"
os.environ["TAX_SET_ASIDE_RATE"] = "0.25"
os.environ.setdefault("GLOBAL_API_SECRET", "super-secret-global-api-key")

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

ADMIN_PASSWORD = "test-admin-pass"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
os.environ["ADMIN_PASSWORD_HASH"] = pwd_context.hash(ADMIN_PASSWORD)

from main import app  # noqa: E402
from ledger import LEDGER_PATH  # noqa: E402
from quickbooks_client import quickbooks  # noqa: E402

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


def _ledger_entries():
    if not os.path.exists(LEDGER_PATH):
        return []
    with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def test_quickbooks_client_mock_record_payout():
    res = quickbooks.record_payout(
        payout_id="po_test", amount=100.0, currency="usd",
        tax_set_aside=25.0, idempotency_key="k1",
    )
    assert res["mock"] is True
    assert res["tax_set_aside"] == 25.0


def test_payout_endpoint_records_quickbooks_with_tax_set_aside():
    body = {"amount": 200.0, "currency": "USD", "idempotency_key": "qbo-key-1"}
    resp = client.post("/payouts/stripe", json=body, headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # 0.25 rate -> 50.00 reserve.
    assert data["tax_set_aside"] == 50.0

    types = [e.get("type") for e in _ledger_entries()]
    assert "payout.create" in types
    assert "quickbooks.payout.recorded" in types
