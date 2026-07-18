from fastapi import FastAPI, HTTPException, Depends, Header, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import os
import hmac
import uuid
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from protocol import protocol
from payments import paypal
from stripe_client import stripe_client, StripeConfigError
import anyio

# Auth Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
GLOBAL_API_SECRET = os.getenv("GLOBAL_API_SECRET")

# Device node allowlist. Locked to the S8 node after the A14 was reported
# stolen (2026-07-12). Set ALLOWED_DEVICE_IDS (comma-separated) to re-provision
# additional trusted device nodes; defaults to the S8 node only.
ALLOWED_DEVICE_IDS = {
    d.strip().lower()
    for d in os.getenv("ALLOWED_DEVICE_IDS", "s8").split(",")
    if d.strip()
}

# Auth Helpers
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

async def authenticate_global(api_key: str = Header(...)):
    if api_key != GLOBAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

async def authenticate_admin(admin_password: str = Header(...)):
    if not verify_password(admin_password, os.getenv("ADMIN_PASSWORD_HASH")):
        raise HTTPException(status_code=401, detail="Unauthorized Admin")
    return True

async def authenticate_device(
    device_id: str = Header(...),
    device_secret: str = Header(...)
):
    if device_id.strip().lower() not in ALLOWED_DEVICE_IDS:
        raise HTTPException(status_code=403, detail="Device node not authorized")
    env_var_name = f"DEVICE_{device_id.upper()}_SECRET"
    expected_secret = os.getenv(env_var_name)
    if not expected_secret or not hmac.compare_digest(device_secret, expected_secret):
        raise HTTPException(status_code=401, detail="Unauthorized device access")
    return device_id

app = FastAPI(title="Maestro Cerebro Escrow Service")


# Security Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://escrow.maestro-cerebro.com"], # Strictly define allowed domain
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=["escrow.maestro-cerebro.com", "localhost", "127.0.0.1"])

# Mount static files
app.mount("/static", StaticFiles(directory="escrow-service/static"), name="static")

# In-memory storage for demonstration (replace with database in production)
transactions = {}

class Transaction(BaseModel):
    id: Optional[str] = None
    paypal_order_id: Optional[str] = None
    amount: float
    currency: str = "USD"
    status: str = "pending"  # pending, held, released, cancelled
    sender_id: str
    receiver_id: str
    metadata: Optional[dict] = None

class PayoutRequest(BaseModel):
    recipient_email: str
    amount: float
    currency: str = "USD"

class StripePayoutRequest(BaseModel):
    amount: float                 # major units, e.g. dollars
    currency: str = "USD"
    confirm: bool = False         # manual-approval gate — must be true to execute
    note: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "Welcome to the Maestro Cerebro Escrow Service", "status": "active"}

@app.post("/payouts")
async def create_payout(
    payout: PayoutRequest, 
    admin: bool = Depends(authenticate_admin),
    api_key: str = Depends(authenticate_global)
):
    try:
        result = await paypal.create_payout(payout.recipient_email, payout.amount, payout.currency)
        await protocol.register_event("PAYOUT_CREATED", {"recipient": payout.recipient_email, "amount": payout.amount})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payout creation failed: {str(e)}")

@app.get("/paypal-client-token")
async def get_client_token(api_key: str = Depends(authenticate_global)):
    try:
        token = await paypal.generate_client_token()
        return {"client_token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate client token: {str(e)}")

async def check_escrow_conditions(order_id: str) -> bool:
    # TODO: Implement your actual business logic to verify escrow conditions
    # For now, it returns True for demonstration
    return True

@app.post("/hold/{amount}")
async def hold_funds(amount: float, api_key: str = Header(...)):
    if api_key != GLOBAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    # 1. Call PayPal to create order
    try:
        order = await paypal.create_order(amount)
        # 2. Save PayPal's order_id to your database alongside your Escrow ID
        return {"order_id": order.id, "status": "HELD"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to hold funds: {str(e)}")

@app.post("/capture/{order_id}")
async def capture_funds(order_id: str, api_key: str = Header(...)):
    if api_key != GLOBAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    # 1. Verify Escrow status in DB (using check_escrow_conditions)
    if not await check_escrow_conditions(order_id):
        raise HTTPException(status_code=403, detail="Conditions not met for capture.")
        
    # 2. Call PayPal Capture API
    try:
        result = await paypal.capture_order(order_id)
        # 3. Update DB to "RELEASED"
        await protocol.register_event("ESCROW_RELEASED", {"order_id": order_id})
        return {"status": "SUCCESS", "capture_id": result.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Capture failed: {str(e)}")

@app.get("/login/paypal")
async def login_paypal():
    # Use the public Cloud Shell URL for mobile testing
    redirect_uri = "https://8080-cs-005fad4b-3ffb-4145-8f13-d9f3dea5e9fa.cs-us-east1-pkhd.cloudshell.dev/login/callback"
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    scope = "openid profile email"
    auth_url = f"https://www.sandbox.paypal.com/signin/authorize?client_id={client_id}&response_type=code&scope={scope}&redirect_uri={redirect_uri}"
    raise HTTPException(status_code=302, headers={"Location": auth_url})

@app.get("/login/callback")
async def login_callback(code: str):
    try:
        user_info = await paypal.get_user_info(code)
        # Here you would link this user info to your local system
        return {"message": "Successfully logged in", "user": user_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@app.post("/paypal-api/checkout/orders/create", response_model=Transaction)
@app.post("/transactions/", response_model=Transaction)
async def create_transaction(
    transaction: Transaction, 
    device: str = Depends(authenticate_device),
    api_key: str = Depends(authenticate_global)
):
    transaction.id = str(uuid.uuid4())
    
    # Link to Sentient Protocol (Gemma + Imagen)
    integrity_res = await protocol.verify_integrity(transaction.id, transaction.model_dump())
    if not integrity_res.get("is_integral"):
        raise HTTPException(status_code=400, detail=f"Sentient Protocol integrity check failed: {integrity_res.get('rationale')}")
    
    # Store AI rationale and visual proof URL in metadata
    transaction.metadata = transaction.metadata or {}
    transaction.metadata["ai_rationale"] = integrity_res.get("rationale")
    transaction.metadata["proof_url"] = integrity_res.get("proof_url")
    
    # Create PayPal Order
    try:
        paypal_order = await paypal.create_order(transaction.amount, transaction.currency)
        transaction.paypal_order_id = paypal_order.id
        transaction.metadata = transaction.metadata or {}
        # Store approval link for the user
        for link in paypal_order.links:
            if link.rel == "approve":
                transaction.metadata["approval_url"] = link.href
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal order creation failed: {str(e)}")

    transactions[transaction.id] = transaction
    await protocol.register_event("TRANSACTION_CREATED", {"id": transaction.id, "paypal_id": transaction.paypal_order_id})
    return transaction

@app.post("/transactions/{transaction_id}/hold")
async def hold_funds(
    transaction_id: str, 
    device: str = Depends(authenticate_device),
    api_key: str = Depends(authenticate_global)
):
    if transaction_id not in transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    tx = transactions[transaction_id]
    if tx.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot hold funds for transaction in status {tx.status}")
    
    tx.status = "held"
    await protocol.register_event("FUNDS_HELD", {"id": transaction_id})
    return {"message": "Funds held successfully", "transaction": tx}

@app.post("/transactions/{transaction_id}/release")
@app.post("/release-escrow/{transaction_id}")
async def release_funds(
    transaction_id: str, 
    device: str = Depends(authenticate_device),
    api_key: str = Depends(authenticate_global)
):
    if transaction_id not in transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    tx = transactions[transaction_id]
    if tx.status != "held":
        raise HTTPException(status_code=400, detail="Only held funds can be released")
    
    # Capture PayPal Payment
    try:
        capture = await paypal.capture_order(tx.paypal_order_id)
        # Robust capture ID extraction
        tx.metadata["capture_id"] = getattr(capture, 'id', 'captured')
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PayPal capture failed: {str(e)}")

    tx.status = "released"
    await protocol.register_event("FUNDS_RELEASED", {"id": transaction_id})
    return {"message": "Funds released successfully", "transaction": tx}

@app.post("/transactions/{transaction_id}/cancel")
async def cancel_transaction(
    transaction_id: str, 
    device: str = Depends(authenticate_device),
    api_key: str = Depends(authenticate_global)
):
    if transaction_id not in transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    tx = transactions[transaction_id]
    if tx.status not in ["pending", "held"]:
        raise HTTPException(status_code=400, detail="Cannot cancel a finalized transaction")
    
    tx.status = "cancelled"
    await protocol.register_event("TRANSACTION_CANCELLED", {"id": transaction_id})
    return {"message": "Transaction cancelled successfully", "transaction": tx}

# ---------------------------------------------------------------------------
# Stripe: webhook verification + on-demand live payouts
# ---------------------------------------------------------------------------

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Receive Stripe events. The raw request body and the Stripe-Signature header
    are verified against STRIPE_WEBHOOK_SECRET before any processing, so forged
    or tampered events are rejected with 400.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        event = stripe_client.verify_webhook(payload, sig_header)
    except StripeConfigError as e:
        raise HTTPException(status_code=500, detail=f"Stripe not configured: {str(e)}")
    except Exception as e:
        # stripe.error.SignatureVerificationError or malformed payload
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {str(e)}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    # Audit: log every verified event
    await protocol.register_event("STRIPE_WEBHOOK_VERIFIED", {
        "event_id": event.get("id"),
        "type": event_type,
        "livemode": event.get("livemode"),
    })

    # Dispatch on payout lifecycle events
    if event_type in ("payout.created", "payout.paid", "payout.failed", "payout.canceled"):
        await protocol.register_event("STRIPE_" + event_type.upper().replace(".", "_"), {
            "payout_id": data_object.get("id"),
            "amount": data_object.get("amount"),
            "currency": data_object.get("currency"),
            "status": data_object.get("status"),
        })

    return {"received": True, "type": event_type}


@app.post("/stripe/payouts")
async def create_stripe_payout(
    payout: StripePayoutRequest,
    admin: bool = Depends(authenticate_admin),
    api_key: str = Depends(authenticate_global),
):
    """
    On-demand payout from the Stripe balance to Maestro Cerebro LLC's own default
    external (bank) account. Guardrails enforced here:
      - manual approval on every payout (confirm=true required; never scheduled)
      - unique idempotency key per payout (never reused -> no double payouts)
      - withdraw only up to the available (settled) balance
      - every payout is logged for audit
    """
    # Guardrail: manual approval on every payout
    if not payout.confirm:
        raise HTTPException(status_code=400, detail="Payout requires explicit manual approval (confirm=true).")

    amount_cents = int(round(payout.amount * 100))
    if amount_cents <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    # Guardrail: unique idempotency key per payout
    idempotency_key = f"mc_payout_{uuid.uuid4()}"

    try:
        # Guardrail: only the available (settled) balance may be withdrawn
        available = stripe_client.get_available_balance(payout.currency)
        if not stripe_client.mock and amount_cents > available:
            raise HTTPException(
                status_code=400,
                detail=f"Requested {amount_cents} exceeds available balance {available} ({payout.currency.lower()}).",
            )

        result = stripe_client.create_payout(
            amount_cents=amount_cents,
            currency=payout.currency,
            idempotency_key=idempotency_key,
            metadata={"note": payout.note or "", "source": "maestro-cerebro-escrow"},
        )
    except HTTPException:
        raise
    except StripeConfigError as e:
        raise HTTPException(status_code=500, detail=f"Stripe not configured: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe payout failed: {str(e)}")

    payout_id = result.get("id") if hasattr(result, "get") else result["id"]

    # Guardrail: every payout is logged (audit + currency trail)
    await protocol.register_event("STRIPE_PAYOUT_CREATED", {
        "payout_id": payout_id,
        "amount_cents": amount_cents,
        "currency": payout.currency.lower(),
        "idempotency_key": idempotency_key,
        "mode": stripe_client.mode,
    })

    return {"status": "created", "payout": result, "idempotency_key": idempotency_key}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
