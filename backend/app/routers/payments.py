"""
HTTP surface for the Razorpay checkout step — the piece that was missing
before, which is what makes refunds real instead of mocked.

  GET  /payments/razorpay-key   -> ships the public key_id to the browser
                                   (Checkout.js needs it; the secret never leaves here).
  POST /payments/{order_id}/capture -> verifies the Checkout.js success
                                       signature and stores the payment_id on the order.

Same thin-router discipline as the others: 1-3 lines calling payment_tool.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..services import payment_tool

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/razorpay-key")
def razorpay_key():
    # key_id is public-safe; key_secret stays server-side. None when no keys
    # are configured, which tells the frontend to skip checkout and fall back.
    return {"key_id": payment_tool.get_public_key()}


@router.post("/{order_id}/capture", response_model=schemas.OrderOut)
def capture_payment(order_id: int, payload: schemas.PaymentCapture, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # The order id the browser hands back must match the hold we actually
    # created for this order — guards against capturing payment against the
    # wrong Razorpay order.
    hold = next((t for t in order.transactions if t.type == "hold"), None)
    if not hold or hold.razorpay_ref != payload.razorpay_order_id:
        raise HTTPException(400, "razorpay_order_id does not match this order's hold")

    if not payment_tool.verify_payment(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    ):
        raise HTTPException(400, "Payment signature verification failed")

    order.razorpay_payment_id = payload.razorpay_payment_id
    db.commit()
    db.refresh(order)
    return order
