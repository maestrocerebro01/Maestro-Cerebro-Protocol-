import os
import uuid
import json
import logging
from typing import Optional

from config import config

try:  # The stripe SDK is optional at import time (mock mode works without it).
    import stripe
except ImportError:  # pragma: no cover
    stripe = None

logger = logging.getLogger("StripeClient")


class StripeClient:
    """
    Thin wrapper around the Stripe SDK for Maestro Cerebro payouts + webhooks.

    Non-negotiable design constraints (see project preferences):
      * Payouts move funds from the Maestro Cerebro Stripe balance to the
        business's OWN default external bank account (stripe.Payout.create).
        They are NOT third-party transfers.
      * Every payout MUST carry a unique idempotency key that is never reused
        (double-payout protection).
      * Every payout and every payout webhook event MUST be logged (ledger.py).
      * Use ONE restricted, payouts-only API key (STRIPE_API_KEY). Start in test
        mode (sk_test_...), then rotate to live (sk_live_...) in the dashboard.
        Stripe cannot create/disable API keys programmatically, so key rotation
        is an operational step, not code.
    """

    # payout.* webhook events we act on.
    PAYOUT_EVENTS = {
        "payout.created",
        "payout.updated",
        "payout.paid",
        "payout.failed",
        "payout.canceled",
        "payout.reconciliation_completed",
    }

    def __init__(self):
        self.api_key = config.stripe_api_key
        self.webhook_secret = config.stripe_webhook_secret
        self.mock = os.getenv("STRIPE_MOCK", "true").lower() == "true"
        if stripe and self.api_key:
            stripe.api_key = self.api_key
        self.live = bool(self.api_key and self.api_key.startswith("sk_live_"))
        if self.live and self.mock:
            logger.warning("Live Stripe key detected but STRIPE_MOCK=true; no real payouts will be sent.")

    def construct_event(self, payload, sig_header: str):
        """
        Verify the Stripe-Signature header and return the parsed event.

        Raises ValueError for a missing/invalid signature or an unparseable
        payload so the caller can respond with HTTP 400. Signature verification
        is the ONLY authentication for the webhook (Stripe cannot send our
        custom auth headers), so it must never be skipped in production.
        """
        if not sig_header:
            raise ValueError("Missing Stripe-Signature header")

        if not self.webhook_secret:
            # No signing secret configured. In mock/dev only, allow an UNVERIFIED
            # parse so local testing works, but log loudly. In production the
            # secret is always mapped from Secret Manager (deploy.yml), so this
            # branch must never run in a live deployment.
            if self.mock:
                logger.warning(
                    "STRIPE_WEBHOOK_SECRET not set; parsing webhook WITHOUT "
                    "signature verification (mock mode only)."
                )
                raw = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
                return json.loads(raw)
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")

        if not stripe:
            raise ValueError("stripe package is not installed")

        try:
            return stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception as exc:  # ValueError (bad payload) or SignatureVerificationError
            raise ValueError(f"Webhook signature verification failed: {exc}") from exc

    def create_payout(self, amount: float, currency: str, idempotency_key: str,
                      metadata: Optional[dict] = None):
        """
        Create a payout from the Stripe balance to the business's default
        external bank account.

        `amount` is in major currency units (dollars); Stripe expects the
        smallest unit (cents), so we convert here.
        """
        if not idempotency_key:
            raise ValueError("idempotency_key is required for every payout")
        if amount is None or amount <= 0:
            raise ValueError("Payout amount must be positive")

        amount_minor = int(round(amount * 100))
        meta = dict(metadata or {})

        if self.mock or not stripe or not self.api_key:
            logger.warning("STRIPE_MOCK active - returning simulated payout (no funds moved).")
            return {
                "id": f"po_mock_{uuid.uuid4().hex[:16]}",
                "object": "payout",
                "amount": amount_minor,
                "currency": currency.lower(),
                "status": "pending",
                "livemode": False,
                "metadata": meta,
                "mock": True,
            }

        payout = stripe.Payout.create(
            amount=amount_minor,
            currency=currency.lower(),
            metadata=meta,
            idempotency_key=idempotency_key,
        )
        return payout.to_dict() if hasattr(payout, "to_dict") else dict(payout)


# Global instance for the service.
stripe_client = StripeClient()
