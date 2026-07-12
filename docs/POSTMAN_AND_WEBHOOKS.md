# Verifying PayPal via Postman and Webhooks

This guide makes the Maestro Cerebro escrow service verifiable end to end: exercising the REST endpoints in Postman, and receiving + verifying real PayPal webhook events. It assumes **PayPal Sandbox** (matches the current code defaults).

Files referenced here live in `postman/`:
- `Maestro-Cerebro-Escrow.postman_collection.json`
- `Maestro-Cerebro-Escrow.postman_environment.json`

---

## 1. Get PayPal Sandbox credentials

1. Sign in at https://developer.paypal.com/dashboard and switch to **Sandbox**.
2. **Apps & Credentials → Create App** (type: Merchant). Copy the **Client ID** and **Secret**.
3. You'll use these as `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`.

> The code runs in **mock mode** only when `PAYPAL_CLIENT_ID == "your_paypal_client_id_here"`. With real sandbox values it calls the live sandbox API, which is what you want for verification.

---

## 2. Configure the service

Set these as environment variables (local `.env`) or GCP Secret Manager secrets. See `.env.example` for the full list.

| Variable | Purpose |
| --- | --- |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | Sandbox app credentials |
| `PAYPAL_MODE` | `sandbox` (default) or `live` |
| `PAYPAL_WEBHOOK_ID` | Webhook ID from step 4 — **required** for webhook signature verification |
| `GLOBAL_API_SECRET` | Value for the `api-key` header on every protected route |
| `ADMIN_PASSWORD_HASH` | bcrypt hash checked by the `admin-password` header (payouts) |
| `DEVICE_S9_SECRET` (etc.) | Secret for device id `s9`; sent as the `device-secret` header with `device-id: s9` |

> Header naming: FastAPI maps header params with underscores to hyphenated header names, so `api_key` → **`api-key`**, `device_id` → **`device-id`**, `device_secret` → **`device-secret`**, `admin_password` → **`admin-password`**.

Run it:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

Confirm `GET /` returns `{"message": "...", "status": "active"}`.

---

## 3. Exercise the REST API in Postman

1. **Import** both files in `postman/` (collection + environment) and select the environment.
2. Fill the environment secrets: `global_api_secret`, `device_secret`, `admin_password`, `paypal_client_id`, `paypal_client_secret`. Set `base_url` to your running URL (e.g. `http://localhost:8080` or your Cloud Run URL).
3. Run requests in the **Escrow Service** folder:
   - **Health check** → 200.
   - **Get PayPal client token** → 200 with a token (proves creds work).
   - **Create transaction** → saves `transaction_id` + `order_id`, then **Hold**, **Release**, or **Cancel**.
   - **Hold funds (simple)** / **Capture funds (simple)** for the non-escrow flow.
   - **Create payout** for outbound payouts.
4. Use the **PayPal Sandbox API (direct)** folder to validate PayPal itself:
   - **Get OAuth2 access token** (saves `paypal_access_token`) — confirms client ID/secret.
   - **Create order**, **List registered webhooks**, **Verify webhook signature**.

> `Create transaction` also runs the Sentient Protocol integrity check (`protocol.verify_integrity`). If GCP AI credentials aren't set up it may fail there before reaching PayPal — that's a protocol dependency, not a PayPal issue.

---

## 4. Register the webhook and get `PAYPAL_WEBHOOK_ID`

Your endpoint must be reachable over **public HTTPS** for PayPal to deliver events.
- Deployed: use your Cloud Run URL, e.g. `https://<service>/paypal-api/webhook`.
- Local: expose it with a tunnel, e.g. `ngrok http 8080`, then use the https tunnel URL.

Register it (either method):
- **Dashboard:** your Sandbox App → **Webhooks → Add Webhook** → URL `https://<host>/paypal-api/webhook` → subscribe to at least `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`. Copy the generated **Webhook ID**.
- **API/Postman:** POST to `/v1/notifications/webhooks`, then run **List registered webhooks** to read the `id`.

Set that id as the `PAYPAL_WEBHOOK_ID` secret **and** in the Postman `paypal_webhook_id` variable.

---

## 5. Verify webhooks (the important nuance)

The endpoint calls PayPal's `/v1/notifications/verify-webhook-signature` and only acts on events that return `SUCCESS`. It **fails closed**:
- Missing `PAYPAL_WEBHOOK_ID` → `500`.
- Missing signature headers → `400`.
- Signature not `SUCCESS` → `400`.
- Verified event → `200`, logs a `PAYPAL_WEBHOOK_VERIFIED` protocol event, and marks a held transaction `released` on `PAYMENT.CAPTURE.COMPLETED`.

**You cannot fully verify a webhook by hand-crafting a POST in Postman.** PayPal signs each event; a forged body/headers will (correctly) return `400`. The collection's *"Webhook - plumbing test (unsigned, expect 400)"* request exists to confirm exactly that rejection.

To verify a **genuine** signed event, use one of:

1. **Real sandbox transaction (most reliable):** create + approve + capture a sandbox order (via the PayPal direct requests or the checkout page). PayPal delivers a genuinely signed event to your public URL. Confirm your endpoint returns `200` and logs `PAYPAL_WEBHOOK_VERIFIED`.
2. **Webhook Simulator:** Dashboard → **Webhooks Simulator** → pick your URL + event type → **Send Test**. Good for checking delivery/plumbing; note the simulator's events do not always pass strict signature verification.
3. **Replay a real event in Postman:** from the dashboard **event logs**, copy a delivered event's transmission headers + raw body into the **Verify webhook signature** request. A real event returns `verification_status = SUCCESS`.

---

## Troubleshooting

- **App won't start (`RuntimeError: Directory 'static' does not exist`)** — run from the repo root so `static/` resolves.
- **401 Unauthorized device access** — check `device-id`/`device-secret` headers match a configured `DEVICE_<ID>_SECRET`.
- **403 Invalid API Key** — the `api-key` header must equal `GLOBAL_API_SECRET`.
- **PayPal 401 on token request** — wrong client ID/secret, or hitting live vs sandbox base URL.
- **Webhook 500 `PAYPAL_WEBHOOK_ID is not configured`** — set the secret from step 4.
- **Transactions don't persist** — storage is in-memory (`transactions = {}`); a restart clears them, so webhook status updates won't correlate after a restart until persistence is added.
