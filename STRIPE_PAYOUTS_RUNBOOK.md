# Stripe Payouts — Verification & Go-Live Runbook

End-to-end checklist to verify the Stripe webhook and get **live payouts** working for
Maestro Cerebro LLC. Pairs with the code added in this PR (`stripe_client.py`,
`/stripe/webhook`, `/stripe/payouts`) and the team "Stripe Payouts Design" doc.

Two environments are kept in parallel — **sandbox** (`_test_` keys) and **live**
(`_live_` keys). Do every step once in test, then once in live.

---

## 0. Prerequisites
- [ ] Stripe account owner/admin access (Dashboard).
- [ ] GCP access to project `project-38af5abf-32a0-48ad-9a4` (Secret Manager).
- [ ] Stripe CLI installed: `brew install stripe/stripe-cli/stripe` (or download from stripe.com/docs/stripe-cli).
- [ ] Live Stripe account **fully activated** (business + bank details verified) — payouts are blocked until activation is complete.

## 1. Create restricted, payouts-only API keys (test + live)
Stripe keys can only be created manually — never programmatically.
- [ ] Dashboard -> Developers -> API keys. Toggle **Test mode ON**.
- [ ] Create restricted key -> name `mc-payouts-test`. Permissions:
  - **Payouts: Write**
  - **Balance: Read**
  - (everything else: None)
- [ ] Copy the `rk_test_...` value (shown once).
- [ ] Toggle **Test mode OFF** (live). Repeat -> name `mc-payouts-live` -> copy `rk_live_...`.

## 2. Store secrets in GCP Secret Manager
The webhook signing secret is **per environment** and comes from step 4; do the API keys now, add the webhook secret after step 4.
- [ ] Add the live API key (this is what deployed Cloud Run uses):
  ```bash
  printf '%s' 'rk_live_XXXX' | gcloud secrets versions add STRIPE_API_KEY \
    --project=project-38af5abf-32a0-48ad-9a4 --data-file=-
  ```
- [ ] Keep the `rk_test_...` key for local/sandbox runs (export as env var locally, do **not** put the test key in the live secret).
- [ ] Never commit either key. `deploy.yml` already injects `STRIPE_API_KEY` + `STRIPE_WEBHOOK_SECRET` from Secret Manager, so no CI change is needed.

## 3. Set payout schedule to Manual + connect the payout bank (test + live)
So revenue accumulates in the Stripe balance for on-demand withdrawal instead of auto-sweeping.
- [ ] Dashboard -> Settings -> Payouts -> Payout schedule -> **Manual** (Test mode).
- [ ] Repeat in Live mode.

**Payout destination bank = Wise Business (USD).** Stripe pays out over ACH; Wise provides USD account details (account number + ACH routing number) that Stripe accepts as a standard payout destination (free, ~2 business days).
- [ ] Open a **Wise Business** account in the LLC's name (**Maestro Cerebro LLC**) and get its **USD** account details (Wise -> Home -> USD account details).
- [ ] Stripe Dashboard -> **Settings -> Bank accounts and scheduling -> Add a bank account** -> enter the Wise **USD** account number + routing number.
- [ ] Confirm the name on the Wise USD details **matches** the Stripe account holder (Maestro Cerebro LLC) — mismatched names cause ACH payouts to bounce.
- [ ] (Note: this is Stripe -> Wise, i.e. Wise as the receiving bank. It is separate from the Wise payout bot, which sends money *out* of a Wise balance via the Wise API.)

## 4. Register the webhook endpoint (test + live)
- [ ] Dashboard -> Developers -> Webhooks -> Add endpoint.
- [ ] Endpoint URL: `https://escrow.maestro-cerebro.com/stripe/webhook`
- [ ] Events to send: `payout.created`, `payout.paid`, `payout.failed`, `payout.canceled`.
- [ ] Save, then copy the **Signing secret** (`whsec_...`).
- [ ] Store it:
  ```bash
  printf '%s' 'whsec_XXXX' | gcloud secrets versions add STRIPE_WEBHOOK_SECRET \
    --project=project-38af5abf-32a0-48ad-9a4 --data-file=-
  ```
- [ ] Do this separately for test and live (live endpoint uses the live signing secret in the live Cloud Run env).

## 5. Deploy the service
- [ ] Merge PR #4 to `main` (CI deploys to Cloud Run) — or deploy the branch manually.
- [ ] Set the runtime env on the live service: `STRIPE_MODE=live`, and ensure `STRIPE_MOCK` is **unset or false**.
- [ ] Confirm the service is up: `curl https://escrow.maestro-cerebro.com/` returns `{"status":"active"}`.

## 6. Verify the webhook (Stripe CLI, test mode)
Fastest way to prove signature verification works, no real money.
- [ ] `stripe login`
- [ ] In one terminal, forward events to a locally-running service (starts with `STRIPE_MODE=sandbox`, test key exported):
  ```bash
  stripe listen --forward-to localhost:8080/stripe/webhook
  ```
  Copy the `whsec_...` it prints and export it as `STRIPE_WEBHOOK_SECRET` for the local run.
- [ ] In another terminal, fire test events:
  ```bash
  stripe trigger payout.paid
  stripe trigger payout.failed
  ```
- [ ] **Pass criteria:** endpoint returns HTTP 200; logs show `STRIPE_WEBHOOK_VERIFIED` and a `STRIPE_PAYOUT_PAID` / `STRIPE_PAYOUT_FAILED` event.
- [ ] **Negative test:** send a bad signature and confirm you get **HTTP 400** (rejected):
  ```bash
  curl -i -X POST localhost:8080/stripe/webhook \
    -H 'Stripe-Signature: t=1,v1=deadbeef' -d '{}'
  ```

## 7. Verify payouts — sandbox dry run
Uses the test key (or `STRIPE_MOCK=true`); no real money.
Note: FastAPI turns header params into hyphenated names, so send `admin-password` and `api-key`.
- [ ] Confirm the manual-approval gate rejects an unconfirmed call:
  ```bash
  curl -i -X POST https://<sandbox-host>/stripe/payouts \
    -H 'admin-password: <ADMIN_PASSWORD>' -H 'api-key: <GLOBAL_API_SECRET>' \
    -H 'Content-Type: application/json' \
    -d '{"amount": 5.00, "currency": "USD"}'
  # expect 400: "Payout requires explicit manual approval (confirm=true)."
  ```
- [ ] Confirm a confirmed call succeeds and is logged:
  ```bash
  curl -s -X POST https://<sandbox-host>/stripe/payouts \
    -H 'admin-password: <ADMIN_PASSWORD>' -H 'api-key: <GLOBAL_API_SECRET>' \
    -H 'Content-Type: application/json' \
    -d '{"amount": 5.00, "currency": "USD", "confirm": true, "note": "sandbox test"}'
  # expect {"status":"created", ...} with a unique idempotency_key
  ```
- [ ] Verify a unique `idempotency_key` (`mc_payout_...`) is returned and a `STRIPE_PAYOUT_CREATED` event was logged.

## 8. Go live — first real payout
- [ ] Confirm live env: `STRIPE_MODE=live`, live `STRIPE_API_KEY` loaded, `STRIPE_MOCK` off.
- [ ] Check the **available (settled)** balance is >= the amount (pending funds must clear first).
- [ ] Start small (e.g. $1.00). Call `/stripe/payouts` with `confirm=true`.
- [ ] **Pass criteria:** response `status: created`; within a few minutes the live webhook fires `payout.paid` and your log shows `STRIPE_PAYOUT_PAID`; funds land in the LLC Wise account per Stripe's payout timing.
- [ ] Confirm in Dashboard -> Payments -> Payouts that the payout shows and is destined for the LLC Wise account.

## 9. Record-keeping (every payout, no exceptions)
- [ ] Record the payout in **QuickBooks** (account under maestrocerebro01@gmail.com), including a **tax set-aside reserve** amount. Set the reserve rate with a CPA (`tax_set_aside_rate` is `null` in the config profiles until then).
- [ ] Retain the full currency trail: original amount, currency, USD amount, FX rate, and rate source/date (prefer Stripe's balance-transaction `exchange_rate`).
- [ ] Confirm the "Maestro Cerebro — Account & Payout Status Log" sheet captured the entry (Environment + currency columns).

---

## Final verification checklist (what "verified & working" means)
- [ ] Restricted payouts-only keys exist for test **and** live, stored in Secret Manager.
- [ ] Payout schedule = Manual in both modes; live destination = LLC Wise Business USD account (name matches Stripe account holder).
- [ ] Webhook endpoint registered in both modes; signing secrets in Secret Manager.
- [ ] Webhook signature verification passes on valid events (200) and rejects forged ones (400).
- [ ] Manual-approval gate blocks payouts without `confirm=true`.
- [ ] Each payout carries a unique idempotency key and is logged.
- [ ] A real $1 live payout completed and `payout.paid` was received.
- [ ] Payout recorded in QuickBooks with tax set-aside + full currency trail.
