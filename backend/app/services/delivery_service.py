"""
Delivery outcome processing — the ONE place that owns the state transitions
for "delivered" and "RTO" outcomes.

Both routers/delivery.py (manual simulate buttons) and routers/webhooks.py
(real courier webhooks) call these functions. This ensures the retry cap,
refund logic, and reroute logic can never diverge between the two entry
points — there is exactly one copy of each.

Architecture rule: routers stay thin, services own state transitions.
This module is the service for delivery outcomes.
"""
from sqlalchemy.orm import Session

from .. import models
from . import agent_orchestrator, payment_tool

MAX_RETRIES = 1


def handle_delivered(order: models.Order, db: Session) -> models.Order:
    """Process a successful delivery: release payment to fleet, mark completed.

    Creates a Transaction record for the payout. If RazorpayX is configured
    (account number + fund account for this fleet), this fires a real payout;
    otherwise it returns a mock_payout_ reference that the frontend labels
    as simulated.
    """
    payout = payment_tool.release_payment(
        order.id, order.selected_price, order.selected_fleet
    )
    db.add(models.Transaction(
        order_id=order.id,
        type="release",
        amount=order.selected_price,
        razorpay_ref=payout["razorpay_ref"],
        status=payout["status"],
    ))
    order.status = "completed"
    db.commit()
    db.refresh(order)
    return order


def handle_rto(order: models.Order, db: Session) -> models.Order:
    """Process a failed delivery (Return to Origin):
    1. Refund the held payment (real if payment_id captured, else mock).
    2. If retry budget exhausted → mark failed.
    3. Otherwise → reroute to next-best fleet, create new hold, re-book.

    The reroute uses the SAME quotes already fetched for the order, excluding
    the fleet that just failed. Category awareness is preserved so a quick
    (intra-city) fleet can't win an inter-city reroute.
    """
    # 1. Refund
    refund = payment_tool.refund_payment(
        order.id, order.selected_price, order.razorpay_payment_id
    )
    db.add(models.Transaction(
        order_id=order.id,
        type="refund",
        amount=order.selected_price,
        razorpay_ref=refund["razorpay_ref"],
        status=refund["status"],
    ))

    # 2. Retry cap check
    if order.retry_count >= MAX_RETRIES:
        order.status = "failed"
        db.commit()
        db.refresh(order)
        return order

    # 3. Reroute to next-best fleet
    existing_quotes = [
        {"fleet_name": q.fleet_name, "price": q.price,
         "eta_hours": q.eta_hours, "category": q.category}
        for q in order.quotes
    ]
    intra_city = bool(
        order.pickup_city and order.drop_city
        and order.pickup_city.strip().lower() == order.drop_city.strip().lower()
    )
    decision = agent_orchestrator.reroute_after_rto(
        existing_quotes,
        failed_fleet=order.selected_fleet,
        package_value=order.package_value,
        intra_city=intra_city,
    )
    order.selected_fleet = decision["fleet_name"]
    order.selected_price = decision["price"]
    order.agent_reasoning = f"[Reroute after RTO] {decision['reasoning']}"
    order.retry_count += 1

    # 4. New hold for the rerouted fleet
    hold = payment_tool.create_hold(order.id, order.selected_price)
    db.add(models.Transaction(
        order_id=order.id,
        type="hold",
        amount=order.selected_price,
        razorpay_ref=hold["razorpay_ref"],
        status=hold["status"],
    ))
    order.status = "booked"
    db.commit()
    db.refresh(order)
    return order
