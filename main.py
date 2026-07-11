from fastapi import FastAPI, HTTPException, Depends, Header, status
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
from stripe_payments import stripe_client
import anyio

# Auth Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
GLOBAL_API_SECRET = os.getenv("GLOBAL_API_SECRET")

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

# Mount static files (the static/ directory is copied to the image working dir)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    amount: float
    currency: str = "usd"
    idempotency_key: Optional[str] = None

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

@app.get("/stripe/balance")
async def get_stripe_balance(api_key: str = Depends(authenticate_global)):
    """Report the account's available (settled) and pending Stripe balance."""
    try:
        return stripe_client.get_balance()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve Stripe balance: {str(e)}")

@app.post("/stripe/payouts")
async def create_stripe_payout(
    payout: StripePayoutRequest,
    admin: bool = Depends(authenticate_admin),
    api_key: str = Depends(authenticate_global)
):
    """
    On-demand, manually-approved Stripe payout: withdraws the settled Stripe
    balance to Maestro Cerebro LLC's own business bank account (the default
    external account on the Stripe account).

    Requires BOTH admin and global API auth -- this is the manual-approval
    guardrail; nothing moves money automatically. Every payout carries a unique
    idempotency key and is logged. When STRIPE_MOCK is not "false", the call is
    simulated and no money moves.
    """
    try:
        result = stripe_client.create_payout(
            amount=payout.amount,
            currency=payout.currency,
            idempotency_key=payout.idempotency_key,
        )
        await protocol.register_event("STRIPE_PAYOUT_CREATED", {
            "payout_id": result.get("id"),
            "amount": payout.amount,
            "currency": payout.currency,
            "idempotency_key": result.get("idempotency_key"),
            "mock": result.get("mock"),
        })
        return result
    except ValueError as e:
        # Business-rule violations (e.g. amount exceeds available balance)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe payout failed: {str(e)}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
