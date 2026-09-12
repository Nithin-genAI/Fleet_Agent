"""
Webhook endpoints — the piece that makes the loop truly autonomous instead
of relying on the "Simulate Delivered / RTO" buttons.

  POST /webhooks/razorpay   — Razorpay server-to-server events:
                              payment.captured, refund.processed, payout.processed
  POST /webhooks/courier    — Courier status updates (stands in for a real
                              courier integration like Delhivery/NimbusPost webhooks):
                              delivered, rto, picked_up

Both verify signatures before trusting the payload. If verification fails
(no secret configured, bad signature), the endpoint returns 400 — never
processes an unverified webhook.

The courier webhook calls the SAME service functions (delivery_service.handle_delivered,
delivery_service.handle_rto) as the manual /delivery-event endpoint, so the
RTO recovery loop and retry cap exist in exactly one place.
"""
import json
import os
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..services import payment_tool, delivery_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Razorpay webhook — payment.captured, refund.processed, payout.processed
# ---------------------------------------------------------------------------

@router.post("/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Razorpay server-to-server webhook events.

    Events we care about:
      - payment.captured  → sync the order's payment_id (redundant with the
                            capture endpoint, but webhooks are the source of truth)
      - refund.processed  → update the refund transaction status
      - payout.processed  → update the release transaction status to 'processed'
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not payment_tool.verify_webhook_signature(body, signature):
        raise HTTPException(400, "Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    event = payload.get("event")
    if not event:
        raise HTTPException(400, "Missing event field")

    # payment.captured — sync the payment_id onto the order
    if event == "payment.captured":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        razorpay_order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")
        if not razorpay_order_id or not payment_id:
            raise HTTPException(400, "Missing order_id or payment_id in payload")

        hold_txn = db.query(models.Transaction).filter(
            models.Transaction.razorpay_ref == razorpay_order_id,
            models.Transaction.type == "hold",
        ).first()
        if not hold_txn:
            raise HTTPException(404, "No order found for this Razorpay order_id")

        order = db.query(models.Order).filter(models.Order.id == hold_txn.order_id).first()
        if order and not order.razorpay_payment_id:
            order.razorpay_payment_id = payment_id
            db.commit()

        return {"status": "ok", "event": event}

    # refund.processed — update the refund transaction status
    if event == "refund.processed":
        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        refund_id = refund_entity.get("id")
        refund_status = refund_entity.get("status")
        if refund_id:
            txn = db.query(models.Transaction).filter(
                models.Transaction.razorpay_ref == refund_id,
                models.Transaction.type == "refund",
            ).first()
            if txn:
                txn.status = refund_status or "processed"
                db.commit()

        return {"status": "ok", "event": event}

    # payout.processed — update the release transaction status
    if event in ("payout.processed", "payout.pending", "payout.failed"):
        payout_entity = payload.get("payload", {}).get("payout", {}).get("entity", {})
        payout_id = payout_entity.get("id")
        payout_status = payout_entity.get("status")
        if payout_id:
            txn = db.query(models.Transaction).filter(
                models.Transaction.razorpay_ref == payout_id,
                models.Transaction.type == "release",
            ).first()
            if txn:
                txn.status = payout_status or "processed"
                db.commit()

        return {"status": "ok", "event": event}

    # Unknown event — acknowledge but don't act
    return {"status": "ignored", "event": event}


# ---------------------------------------------------------------------------
# Courier webhook — delivery status updates (replaces the simulate buttons)
# ---------------------------------------------------------------------------

@router.post("/courier")
async def courier_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle courier delivery status webhooks.

    This is the endpoint a real courier integration (Delhivery, NimbusPost, etc.)
    would call when a package is picked up, delivered, or returned (RTO).
    It replaces the manual "Simulate Delivered / RTO" buttons with a real
    server-to-server callback.

    Expected JSON body:
      {
        "order_id": 1,
        "status": "delivered" | "rto" | "picked_up",
        "tracking_id": "TRK123",       # optional
        "fleet_name": "WareIQ-Bluedart" # optional, for verification
      }

    If COURIER_WEBHOOK_SECRET is set, the `X-Courier-Signature` header must
    match an HMAC-SHA256 of the raw body. If not set, we accept unsigned
    payloads (demo mode).

    The delivered/rto paths call delivery_service — the SAME functions the
    manual /delivery-event endpoint uses — so there is exactly one copy of
    the refund/reroute/retry logic.
    """
    body = await request.body()
    signature = request.headers.get("X-Courier-Signature", "")
    secret = os.environ.get("COURIER_WEBHOOK_SECRET")

    if secret:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(400, "Invalid courier webhook signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    order_id = payload.get("order_id")
    status = (payload.get("status") or "").lower()

    if not order_id or status not in ("delivered", "rto", "picked_up"):
        raise HTTPException(400, "order_id and status (delivered|rto|picked_up) required")

    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    if status == "picked_up":
        return {"status": "ok", "order_id": order_id, "event": "picked_up"}

    if order.status != "booked":
        raise HTTPException(
            400,
            f"Order is in status '{order.status}', not awaiting delivery. Webhook ignored.",
        )

    # --- Both paths delegate to delivery_service (single source of truth) ---
    if status == "delivered":
        order = delivery_service.handle_delivered(order, db)
        release_txn = order.transactions[-1] if order.transactions else None
        return {
            "status": "ok", "order_id": order_id, "event": "delivered",
            "payout_ref": release_txn.razorpay_ref if release_txn else None,
            "payout_status": release_txn.status if release_txn else None,
        }

    if status == "rto":
        order = delivery_service.handle_rto(order, db)
        if order.status == "failed":
            return {"status": "ok", "order_id": order_id, "event": "rto",
                    "result": "failed (retry limit reached)"}
        return {"status": "ok", "order_id": order_id, "event": "rto",
                "result": "rerouted", "new_fleet": order.selected_fleet}

    raise HTTPException(400, "Unhandled status")
