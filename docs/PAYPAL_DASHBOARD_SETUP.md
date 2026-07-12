# PayPal Dashboard Setup Checklist

Click-by-click steps to register the webhook and confirm a real signed event verifies. Follow top to bottom — **Sandbox** first (matches the current code defaults), with the **Live** equivalent at the end. For the Postman requests referenced here, see [`POSTMAN_AND_WEBHOOKS.md`](./POSTMAN_AND_WEBHOOKS.md). Production/go-live tracking lives in issue #7.

## A. Create the sandbox app + credentials
- [ ] Sign in at **developer.paypal.com/dashboard**. Confirm the toggle (top of the page) is set to **Sandbox**.
- [ ] **Apps & Credentials → Create App**. Name it (e.g. `maestro-cerebro-escrow`), type **Merchant**, Create.
- [ ] Copy the **Client ID** and **Secret** → these become `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`.

## B. Create sandbox test accounts (to actually move money)
- [ ] **Testing Tools → Sandbox Accounts**. Confirm a **Business** account (the merchant) and a **Personal** account (the buyer) exist. Create the personal buyer if missing.
- [ ] Note the buyer's sandbox email/password — used to approve a test order.

## C. Configure the server
- [ ] Set secrets (GCP Secret Manager or `.env`): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE=sandbox`, plus `GLOBAL_API_SECRET`, `ADMIN_PASSWORD_HASH`, and a `DEVICE_S9_SECRET`.
- [ ] Make the endpoint publicly reachable over HTTPS: deploy the branch to Cloud Run, **or** run locally and expose it with `ngrok http 8080`. Note the public base URL.

## D. Register the webhook + get the ID
- [ ] Open your app under **Apps & Credentials**, scroll to the **Sandbox Webhooks** section → **Add Webhook**.
- [ ] Webhook URL: `https://<your-public-host>/paypal-api/webhook`
- [ ] Subscribe to: `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`, `PAYMENT.CAPTURE.REVERSED`, `PAYMENT.CAPTURE.REFUNDED`, and the `PAYMENT.PAYOUTS-ITEM.*` events. Save.
- [ ] Copy the generated **Webhook ID** → set it as the `PAYPAL_WEBHOOK_ID` secret, then restart the service.

## E. Verify (using the Postman collection)
- [ ] **PayPal Sandbox → Get OAuth2 access token** returns `200` (proves credentials).
- [ ] Create + approve (as the sandbox buyer) + capture a sandbox order.
- [ ] Confirm PayPal delivers the event: your endpoint returns `200` and logs `PAYPAL_WEBHOOK_VERIFIED` with `handled=true`.
- [ ] Optional plumbing check: **Testing Tools → Webhooks Simulator** to fire an event at your URL.
- [ ] Optional exact-signature check: copy a real delivered event's transmission headers + body into the **Verify webhook signature** request → expect `verification_status: SUCCESS`.

## F. When going live (tracked in issue #7)
- [ ] Flip the dashboard toggle to **Live**, create a Live app, copy live credentials.
- [ ] Repeat C–E with `PAYPAL_MODE=live`, a **Live Webhook** registered, and the live `PAYPAL_WEBHOOK_ID`.

> Reminder: a hand-crafted POST to `/paypal-api/webhook` cannot pass signature verification and will correctly return `400`. Only genuinely signed PayPal events (a real transaction, or a replayed real event) verify as `SUCCESS`.
