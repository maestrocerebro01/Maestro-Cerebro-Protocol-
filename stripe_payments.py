"""
Stripe payout client for Maestro Cerebro LLC.

Implements on-demand, manually-approved payouts that withdraw the settled Stripe
balance to Maestro Cerebro LLC's own business bank account (the default external
account configured on the Stripe account).

Design guardrails (see "Maestro Cerebro - Stripe Payouts Design"):
  1. Unique idempotency key per payout (never reused) to prevent double payouts.
  2. Every payout is logged.
  3. On-demand trigger with manual approval (enforced at the API layer in main.py
     via admin + global API auth).
  4. Destination: the account's own default external (bank) account only.
  6. Revenue is held in Stripe (payout schedule = Manual, a Dashboard setting);
     only the available (settled) balance can be withdrawn.

Environment isolation is by key: an sk_live_/rk_live_ key only works in live and
an sk_test_/rk_test_ key only works in test. The key is read from GCP Secret
Manager (STRIPE_API_KEY) via config; it is never committed to the repo or logged.

STRIPE_MOCK gates real money movement. It defaults to "true" (safe) and must be
explicitly set to "false" in the live Cloud Run environment only after the Stripe
account's payout method is verified and the live restricted key is in Secret
Manager.
"""

import os
import uuid
import logging
from typing import Optional

import stripe

from config import config

logger = logging.getLogger("StripePayouts")


class StripeClient:
    def __init__(self):
        # Mock is ON unless explicitly disabled, so we never move real money by
        # accident before the account is verified and ready.
        self.mock = os.getenv("STRIPE_MOCK", "true").strip().lower() != "false"
        self.api_key = config.stripe_api_key
        if self.api_key:
            stripe.api_key = self.api_key
        self.live = bool(self.api_key and self.api_key.startswith(("sk_live_", "rk_live_")))

    def _require_key(self):
        if not self.api_key:
            raise RuntimeError(
                "STRIPE_API_KEY is not configured. Store the live restricted key "
                "in GCP Secret Manager (referenced as STRIPE_API_KEY) before "
                "attempting a live payout."
            )

    def get_balance(self):
        """Return available and pending balance in major USD units."""
        if self.mock:
            return {"available_usd": 0.0, "pending_usd": 0.0, "mock": True}
        self._require_key()
        balance = stripe.Balance.retrieve()

        def _sum(entries, currency="usd"):
            return sum(e["amount"] for e in entries if e["currency"] == currency) / 100.0

        return {
            "available_usd": _sum(balance.get("available", [])),
            "pending_usd": _sum(balance.get("pending", [])),
            "mock": False,
        }

    def create_payout(
        self,
        amount: float,
        currency: str = "usd",
        idempotency_key: Optional[str] = None,
    ):
        """
        Withdraw `amount` (major units, e.g. 10.50) from the settled Stripe
        balance to the account's own default external bank account.

        Enforces:
          - a unique idempotency key per payout (guardrail 1),
          - withdrawal only up to the available/settled balance (guardrail 6),
          - structured logging of the payout (guardrail 2).
        """
        currency = currency.lower()
        idempotency_key = idempotency_key or f"payout_{uuid.uuid4()}"
        amount_minor = int(round(amount * 100))

        if amount <= 0:
            raise ValueError("Payout amount must be greater than zero.")

        if self.mock:
            logger.info(
                "MOCK payout (no money moved): amount=%.2f %s idempotency_key=%s",
                amount, currency.upper(), idempotency_key,
            )
            return {
                "id": f"po_mock_{idempotency_key}",
                "object": "payout",
                "status": "mock",
                "amount": amount_minor,
                "currency": currency,
                "amount_usd": amount,
                "idempotency_key": idempotency_key,
                "mock": True,
            }

        self._require_key()

        # Guardrail 6: only the available (settled) balance can be withdrawn.
        available = self.get_balance()["available_usd"]
        if amount > available:
            raise ValueError(
                f"Requested payout {amount:.2f} {currency.upper()} exceeds the "
                f"available (settled) balance {available:.2f} USD."
            )

        payout = stripe.Payout.create(
            amount=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
            metadata={
                "source": "maestro-cerebro-escrow",
                "idempotency_key": idempotency_key,
            },
        )

        # Guardrail 6 / currency normalization: retain the settling balance
        # transaction (original amount, currency and exchange rate) for audit.
        fx = {"exchange_rate": None, "settled_amount_usd": amount, "settled_currency": currency}
        try:
            bt_id = payout.get("balance_transaction")
            if bt_id:
                bt = stripe.BalanceTransaction.retrieve(bt_id)
                fx = {
                    "exchange_rate": bt.get("exchange_rate"),
                    "settled_amount_usd": bt.get("amount", amount_minor) / 100.0,
                    "settled_currency": bt.get("currency", currency),
                }
        except Exception as e:  # non-fatal: audit enrichment only
            logger.warning(
                "Could not retrieve balance transaction for payout %s: %s",
                payout.get("id"), e,
            )

        logger.info(
            "LIVE payout created: id=%s amount=%.2f %s status=%s idempotency_key=%s",
            payout.get("id"), amount, currency.upper(), payout.get("status"), idempotency_key,
        )

        return {
            "id": payout.get("id"),
            "object": "payout",
            "status": payout.get("status"),
            "amount": payout.get("amount"),
            "currency": payout.get("currency"),
            "idempotency_key": idempotency_key,
            "arrival_date": payout.get("arrival_date"),
            "fx": fx,
            "mock": False,
        }


stripe_client = StripeClient()
