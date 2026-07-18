import os
import uuid
import logging
from typing import Optional

import stripe

from config import config


class StripeConfigError(RuntimeError):
    """Raised when the Stripe environment/config is missing or unsafe."""


class StripeClient:
    """
    Thin wrapper around the Stripe SDK for Maestro Cerebro LLC on-demand payouts
    and webhook signature verification.

    Guardrails (see the team "Stripe Payouts Design" doc):
      - Two environments in parallel: sandbox ('_test_' keys) and live ('_live_'
        keys). The environment is chosen explicitly via STRIPE_MODE and is
        cross-checked against the loaded key, so a test key can never run in live
        and a live key can never run in sandbox.
      - Payouts-only restricted key per environment, referenced by name and loaded
        from GCP Secret Manager (never committed).
      - Every payout carries a unique idempotency key, requires manual approval
        (enforced at the API layer), is logged, and pays out to the LLC's own
        default external (bank) account.
      - STRIPE_MOCK=true short-circuits network calls for safe dry runs.
    """

    def __init__(self):
        self.logger = logging.getLogger("StripeClient")
        self.mode = os.getenv("STRIPE_MODE", "sandbox").lower()
        self.mock = os.getenv("STRIPE_MOCK", "false").lower() == "true"
        self._configured = False

    def _ensure_configured(self):
        """Validate key/mode agreement and set the SDK key. Lazy so importing the
        module never crashes an environment that has no Stripe keys yet."""
        if self.mock or self._configured:
            return
        api_key = config.stripe_api_key
        if not api_key:
            raise StripeConfigError("STRIPE_API_KEY is not set")
        self._assert_key_matches_mode(api_key, self.mode)
        stripe.api_key = api_key
        self._configured = True

    @staticmethod
    def _assert_key_matches_mode(key: str, mode: str):
        is_live_key = "_live_" in key
        is_test_key = "_test_" in key
        if mode == "live" and not is_live_key:
            raise StripeConfigError(
                "STRIPE_MODE=live but the loaded STRIPE_API_KEY is not a live key "
                "(expected a key containing '_live_')."
            )
        if mode in ("sandbox", "test") and not is_test_key:
            raise StripeConfigError(
                "STRIPE_MODE=sandbox but the loaded STRIPE_API_KEY is not a test key "
                "(expected a key containing '_test_')."
            )

    # ------------------------------------------------------------------ webhook
    def verify_webhook(self, payload: bytes, sig_header: str):
        """Verify the Stripe-Signature header against the raw body using the
        environment's signing secret. Returns the verified Event, or raises
        stripe.error.SignatureVerificationError / StripeConfigError."""
        webhook_secret = config.stripe_webhook_secret
        if not webhook_secret:
            raise StripeConfigError("STRIPE_WEBHOOK_SECRET is not set")
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )

    # ------------------------------------------------------------------ balance
    def get_available_balance(self, currency: str = "usd") -> int:
        """Return the available (settled) balance for the currency, in the
        smallest currency unit (e.g. cents)."""
        if self.mock:
            return 0
        self._ensure_configured()
        balance = stripe.Balance.retrieve()
        for entry in balance.get("available", []):
            if entry.get("currency") == currency.lower():
                return entry.get("amount", 0)
        return 0

    # ------------------------------------------------------------------- payout
    def create_payout(
        self,
        amount_cents: int,
        currency: str = "usd",
        idempotency_key: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Create an on-demand payout from the Stripe balance to the default
        external (bank) account. `amount_cents` is in the smallest currency unit.
        A unique idempotency key is required (generated if not supplied)."""
        if amount_cents <= 0:
            raise ValueError("amount_cents must be positive")
        idempotency_key = idempotency_key or f"mc_payout_{uuid.uuid4()}"

        if self.mock:
            return {
                "id": f"po_mock_{uuid.uuid4().hex[:16]}",
                "object": "payout",
                "amount": amount_cents,
                "currency": currency.lower(),
                "status": "pending",
                "livemode": self.mode == "live",
                "metadata": metadata or {},
                "idempotency_key": idempotency_key,
                "mock": True,
            }

        self._ensure_configured()
        return stripe.Payout.create(
            amount=amount_cents,
            currency=currency.lower(),
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )


stripe_client = StripeClient()
