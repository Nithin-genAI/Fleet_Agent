"""
Stands in for a webhook a real courier would send on pickup/delivery status
change. In the demo, this is the button that fires "Delivered" or "RTO" —
say that explicitly on screen, it's an honest and reasonable simplification.

The RTO branch is the interesting one: refund -> reroute -> rebook, capped
at one retry so a demo can't loop forever if every fleet "fails".
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..services import agent_orchestrator, payment_tool

router = APIRouter(prefix="/orders", tags=["delivery"])

MAX_RETRIES = 1


@router.post("/{order_id}/delivery-event", response_model=schemas.OrderOut)
def delivery_event(order_id: int, event: schemas.DeliveryEvent, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "booked":
        raise HTTPException(400, f"Order is in status '{order.status}', not awaiting delivery")

    if event.outcome == "delivered":
        payout = payment_tool.release_payment(order.id, order.selected_price, order.selected_fleet)
        db.add(models.Transaction(order_id=order.id, type="release", amount=order.selected_price,
                                   razorpay_ref=payout["razorpay_ref"], status=payout["status"]))
        order.status = "completed"
        db.commit()
        db.refresh(order)
        return order

    if event.outcome == "rto":
        refund = payment_tool.refund_payment(order.id, order.selected_price)
        db.add(models.Transaction(order_id=order.id, type="refund", amount=order.selected_price,
                                   razorpay_ref=refund["razorpay_ref"], status=refund["status"]))

        if order.retry_count >= MAX_RETRIES:
            order.status = "failed"
            db.commit()
            db.refresh(order)
            return order

        # reroute: pick the next-best fleet from the SAME quotes we already fetched
        existing_quotes = [
            {"fleet_name": q.fleet_name, "price": q.price, "eta_hours": q.eta_hours}
            for q in order.quotes
        ]
        decision = agent_orchestrator.reroute_after_rto(
            existing_quotes, failed_fleet=order.selected_fleet, package_value=order.package_value
        )
        order.selected_fleet = decision["fleet_name"]
        order.selected_price = decision["price"]
        order.agent_reasoning = f"[Reroute after RTO] {decision['reasoning']}"
        order.retry_count += 1

        hold = payment_tool.create_hold(order.id, order.selected_price)
        db.add(models.Transaction(order_id=order.id, type="hold", amount=order.selected_price,
                                   razorpay_ref=hold["razorpay_ref"], status=hold["status"]))
        order.status = "booked"
        db.commit()
        db.refresh(order)
        return order

    raise HTTPException(400, "outcome must be 'delivered' or 'rto'")
