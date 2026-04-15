# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Stripe webhook handling utilities with signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

_logger = logging.getLogger(__name__)
_processed_event_ids = set()
_processed_lock = threading.Lock()
_DEFAULT_TOLERANCE_SECONDS = 300


def _parse_signature_header(signature_header: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for part in signature_header.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            parsed[key.strip()] = value.strip()
    return parsed


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: Optional[str] = None,
    tolerance_seconds: int = _DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """Verify Stripe webhook signature using STRIPE_WEBHOOK_SECRET."""
    secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return False

    parts = _parse_signature_header(signature_header)
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False

    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _already_processed(event_id: str) -> bool:
    with _processed_lock:
        if event_id in _processed_event_ids:
            return True
        _processed_event_ids.add(event_id)
        return False


def handle_stripe_event(
    event: Dict[str, Any],
    on_checkout_completed: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_subscription_updated: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_subscription_deleted: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_invoice_payment_failed: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Handle Stripe event payload and dispatch to relevant callback."""
    event_id = event.get("id")
    event_type = event.get("type", "")
    event_object = event.get("data", {}).get("object", {})

    if not event_id:
        return 400, {"error": "Missing event id"}

    if _already_processed(str(event_id)):
        return 200, {"status": "duplicate_ignored"}

    try:
        if event_type == "checkout.session.completed":
            if on_checkout_completed:
                on_checkout_completed(event_object)
        elif event_type == "customer.subscription.updated":
            if on_subscription_updated:
                on_subscription_updated(event_object)
        elif event_type == "customer.subscription.deleted":
            if on_subscription_deleted:
                on_subscription_deleted(event_object)
        elif event_type == "invoice.payment_failed":
            if on_invoice_payment_failed:
                on_invoice_payment_failed(event_object)
        else:
            _logger.info("Unhandled Stripe event type: %s", event_type)
        return 200, {"status": "ok"}
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        _logger.exception("Failed processing Stripe event %s: %s", event_type, exc)
        return 500, {"error": "Webhook processing failed"}


def handle_stripe_webhook(
    payload: bytes,
    signature_header: str,
    webhook_secret: Optional[str] = None,
    on_checkout_completed: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_subscription_updated: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_subscription_deleted: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_invoice_payment_failed: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Validate request signature and process Stripe webhook event."""
    if not verify_stripe_signature(payload, signature_header, webhook_secret=webhook_secret):
        return 400, {"error": "Invalid signature"}

    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return 400, {"error": "Invalid JSON payload"}

    return handle_stripe_event(
        event,
        on_checkout_completed=on_checkout_completed,
        on_subscription_updated=on_subscription_updated,
        on_subscription_deleted=on_subscription_deleted,
        on_invoice_payment_failed=on_invoice_payment_failed,
    )
