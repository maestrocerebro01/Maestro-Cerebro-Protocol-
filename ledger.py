import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("PayoutLedger")

# Append-only ledger of payouts + payout webhook events.
# NOTE: on Cloud Run the container filesystem is EPHEMERAL, so this file does
# not survive restarts. It satisfies the "log every payout" requirement at the
# application level and mirrors the existing protocol_events.jsonl pattern, but
# for durable audit records point PAYOUT_LEDGER_PATH at a mounted volume or ship
# these records to GCS / a database. See the PR description.
LEDGER_PATH = os.getenv("PAYOUT_LEDGER_PATH", "payout_events.jsonl")


def record_payout_event(record: dict) -> dict:
    """
    Append a payout or payout-webhook event to the ledger.

    Non-negotiable: every payout / payout event MUST be recorded. A write
    failure is raised (never silently swallowed) so the caller can react.
    """
    entry = dict(record)
    entry.setdefault("recorded_at", datetime.utcnow().isoformat() + "Z")
    line = json.dumps(entry, default=str)
    try:
        with open(LEDGER_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:
        logger.error("FAILED to write payout ledger entry: %s | entry=%s", exc, line)
        raise
    logger.info("payout-ledger %s", line)
    return entry


def _scan_ledger(field: str, value: str) -> bool:
    """Return True if any ledger entry has entry[field] == value."""
    if not value or not os.path.exists(LEDGER_PATH):
        return False
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if rec.get(field) == value:
                    return True
    except Exception as exc:  # pragma: no cover
        logger.error("Failed reading payout ledger: %s", exc)
    return False


def idempotency_key_used(idempotency_key: str) -> bool:
    """True if this idempotency key has already been used for a payout."""
    return _scan_ledger("idempotency_key", idempotency_key)


def event_already_processed(event_id: str) -> bool:
    """True if this Stripe webhook event id was already recorded (dedupe)."""
    return _scan_ledger("stripe_event_id", event_id)
