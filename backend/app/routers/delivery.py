"""
Stands in for a webhook a real courier would send on pickup/delivery status
change. In the demo, this is the button that fires "Delivered" or "RTO" —
say that explicitly on screen, it's an honest and reasonable simplification.

This router is deliberately thin: all state-transition logic lives in
services/delivery_service.py. Both this manual endpoint and the autonomous
/webhooks/courier endpoint call the same service functions, so the RTO
recovery loop, retry cap, and refund logic can never diverge.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..services import delivery_service

router = APIRouter(prefix="/orders", tags=["delivery"])


@router.post("/{order_id}/delivery-event", response_model=schemas.OrderOut)
def delivery_event(order_id: int, event: schemas.DeliveryEvent, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "booked":
        raise HTTPException(400, f"Order is in status '{order.status}', not awaiting delivery")

    if event.outcome == "delivered":
        return delivery_service.handle_delivered(order, db)

    if event.outcome == "rto":
        return delivery_service.handle_rto(order, db)

    raise HTTPException(400, "outcome must be 'delivered' or 'rto'")
