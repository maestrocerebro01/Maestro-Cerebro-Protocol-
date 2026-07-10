import os
import logging
from typing import Optional

import httpx

from config import config

logger = logging.getLogger("QuickBooksClient")

QBO_OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QuickBooksClient:
    """
    Records Maestro Cerebro payouts, tax set-aside reserves, and Stripe fees to
    QuickBooks Online (account under maestrocerebro01@gmail.com) for tax/audit.

    Mock-first: with QUICKBOOKS_MOCK=true (default) nothing is sent to QBO; every
    intended record is returned and logged so the flow can be verified safely.

    Live mode requires QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET,
    QUICKBOOKS_REFRESH_TOKEN, QUICKBOOKS_REALM_ID and the chart-of-accounts IDs
    below. Posting fails safe (raises) when required account IDs are missing, so
    incorrect/partial entries are never written to the books.

    CAVEATS (see PR):
      * QBO rotates the refresh token on every use; a durable store must persist
        the new refresh_token or the integration will lock out.
      * The double-entry mapping below is a starting point - confirm accounts,
        posting types, and the tax set-aside rate with a CPA before going live.
    """

    def __init__(self):
        self.mock = os.getenv("QUICKBOOKS_MOCK", "true").lower() == "true"
        self.env = os.getenv("QUICKBOOKS_ENV", "sandbox").lower()
        self.client_id = config.quickbooks_client_id
        self.client_secret = config.quickbooks_client_secret
        self.refresh_token = config.quickbooks_refresh_token
        self.realm_id = config.quickbooks_realm_id

        # Chart-of-accounts references (QBO Account IDs). Required for live posting.
        self.acct_bank = os.getenv("QBO_BANK_ACCOUNT_ID")                  # business checking
        self.acct_stripe_balance = os.getenv("QBO_STRIPE_BALANCE_ACCOUNT_ID")
        self.acct_tax_reserve = os.getenv("QBO_TAX_RESERVE_ACCOUNT_ID")
        self.acct_stripe_fees = os.getenv("QBO_STRIPE_FEES_ACCOUNT_ID")

        if self.env == "production":
            self.base_url = "https://quickbooks.api.intuit.com"
        else:
            self.base_url = "https://sandbox-quickbooks.api.intuit.com"

    # --- auth / transport ---
    def _configured(self) -> bool:
        return all([self.client_id, self.client_secret, self.refresh_token, self.realm_id])

    @staticmethod
    def _require_accounts(accounts) -> None:
        if not all(accounts):
            raise ValueError("QuickBooks account IDs not configured; refusing to post incomplete entries.")

    def _get_access_token(self) -> str:
        resp = httpx.post(
            QBO_OAUTH_TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        new_refresh = body.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            # QBO rotates refresh tokens on use; this MUST be persisted durably.
            logger.warning("QuickBooks issued a new refresh_token; persist it to avoid lockout.")
            self.refresh_token = new_refresh
        return body["access_token"]

    def _post(self, resource: str, payload: dict) -> dict:
        token = self._get_access_token()
        url = f"{self.base_url}/v3/company/{self.realm_id}/{resource}"
        resp = httpx.post(
            url,
            params={"minorversion": "73"},
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # --- recording ---
    def record_payout(self, payout_id, amount, currency, tax_set_aside,
                      idempotency_key, metadata: Optional[dict] = None) -> dict:
        """Record a payout (Stripe balance -> own bank) plus a tax set-aside reserve."""
        record = {
            "kind": "payout",
            "payout_id": payout_id,
            "amount": round(float(amount), 2),
            "currency": currency,
            "tax_set_aside": round(float(tax_set_aside), 2),
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        if self.mock or not self._configured():
            logger.warning("QUICKBOOKS_MOCK/unconfigured - not posting to QBO. Would record: %s", record)
            return {"mock": True, **record}

        self._require_accounts([self.acct_bank, self.acct_stripe_balance, self.acct_tax_reserve])
        amt = record["amount"]
        reserve = record["tax_set_aside"]
        # Payout: move funds Stripe balance -> bank. Tax reserve: set aside from bank.
        # Confirm accounts/posting types with a CPA before going live.
        journal = {
            "PrivateNote": f"Stripe payout {payout_id} (idem {idempotency_key})",
            "Line": [
                {"Description": "Stripe payout to bank", "Amount": amt,
                 "DetailType": "JournalEntryLineDetail",
                 "JournalEntryLineDetail": {"PostingType": "Debit",
                                            "AccountRef": {"value": self.acct_bank}}},
                {"Description": "Stripe payout to bank", "Amount": amt,
                 "DetailType": "JournalEntryLineDetail",
                 "JournalEntryLineDetail": {"PostingType": "Credit",
                                            "AccountRef": {"value": self.acct_stripe_balance}}},
                {"Description": "Tax set-aside reserve", "Amount": reserve,
                 "DetailType": "JournalEntryLineDetail",
                 "JournalEntryLineDetail": {"PostingType": "Debit",
                                            "AccountRef": {"value": self.acct_tax_reserve}}},
                {"Description": "Tax set-aside reserve", "Amount": reserve,
                 "DetailType": "JournalEntryLineDetail",
                 "JournalEntryLineDetail": {"PostingType": "Credit",
                                            "AccountRef": {"value": self.acct_bank}}},
            ],
        }
        result = self._post("journalentry", journal)
        record["qbo_journal_entry_id"] = (result.get("JournalEntry") or {}).get("Id")
        return record

    def record_stripe_fee(self, amount, currency, source_id,
                          description: str = "Stripe processing fee") -> dict:
        """Record a Stripe fee (the cost of the Stripe integration) as an expense."""
        record = {
            "kind": "stripe_fee",
            "amount": round(float(amount), 2),
            "currency": currency,
            "source_id": source_id,
        }
        if self.mock or not self._configured():
            logger.warning("QUICKBOOKS_MOCK/unconfigured - not posting fee to QBO. Would record: %s", record)
            return {"mock": True, **record}

        self._require_accounts([self.acct_stripe_fees, self.acct_stripe_balance])
        purchase = {
            "PaymentType": "Cash",
            "AccountRef": {"value": self.acct_stripe_balance},
            "PrivateNote": f"{description} for {source_id}",
            "Line": [
                {"Amount": record["amount"], "DetailType": "AccountBasedExpenseLineDetail",
                 "AccountBasedExpenseLineDetail": {"AccountRef": {"value": self.acct_stripe_fees}}}
            ],
        }
        result = self._post("purchase", purchase)
        record["qbo_purchase_id"] = (result.get("Purchase") or {}).get("Id")
        return record


# Global instance for the service.
quickbooks = QuickBooksClient()
