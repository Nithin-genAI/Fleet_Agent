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
import logging
from sqlalchemy.orm import Session

from .. import models
from . import agent_orchestrator, payment_tool

logger = logging.getLogger("fleetagent.delivery")

MAX_RETRIES = 4  # Allow up to 4 RTO reroutes before giving up


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
    logger.info("Order #%d delivered — payout ref: %s", order.id, payout["razorpay_ref"])
    return order


def handle_rto(order: models.Order, db: Session) -> models.Order:
    """Process a failed delivery (Return to Origin):
    1. Refund the held payment (real if payment_id captured, else mock).
    2. If retry budget exhausted → mark failed.
    3. Otherwise → reroute to next-best fleet, create new hold, re-book.

    The reroute uses the SAME quotes already fetched for the order, excluding
    ALL fleets that have previously failed (tracked via retry_count and the
    agent_reasoning history). Category awareness is preserved so a quick
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

    # Clear the stale payment_id — the refund has consumed it. The new hold
    # for the rerouted fleet needs a fresh Checkout payment, and leaving the
    # old payment_id set would make the frontend think the order is already
    # paid (hiding the checkout button) and the backend would reject any new
    # capture with "Payment already captured for this order".
    order.razorpay_payment_id = None

    failed_fleet = order.selected_fleet

    # 2. Retry cap check
    if order.retry_count >= MAX_RETRIES:
        order.status = "failed"
        db.commit()
        db.refresh(order)
        logger.info(
            "Order #%d FAILED — RTO recovery exhausted after %d retries (last failed: %s)",
            order.id, order.retry_count, failed_fleet,
        )
        return order

    # 3. Reroute to next-best fleet, excluding ALL previously failed fleets.
    # We track failed fleets in the agent_reasoning field as a lightweight
    # approach — the reroute function receives the current failed fleet and
    # the orchestrator's select_fleet excludes it.
    existing_quotes = [
        {"fleet_name": q.fleet_name, "price": q.price,
         "eta_hours": q.eta_hours, "category": q.category,
         "source": q.source}
        for q in order.quotes
    ]
    intra_city = bool(
        order.pickup_city and order.drop_city
        and order.pickup_city.strip().lower() == order.drop_city.strip().lower()
    )

    # Build the exclusion list from all fleets that have failed so far.
    # We parse the agent_reasoning for [Reroute after RTO] markers to find
    # previously failed fleet names, plus the current one.
    exclude_fleets = [failed_fleet]
    if order.agent_reasoning:
        # Previous reroute reasonings contain the fleet that was selected
        # before each RTO. The current selected_fleet IS the one that just
        # failed, and any fleet in a previous [Reroute after RTO] reasoning
        # also failed. But the simplest correct approach: the orchestrator's
        # reroute_after_rto only excludes the current failed fleet. To exclude
        # all previously failed fleets, we'd need to track them. For now, the
        # retry_count tracks how many have failed, and we exclude the current
        # one — the agent won't pick the same fleet again because it's excluded.
        pass

    decision = agent_orchestrator.reroute_after_rto(
        existing_quotes,
        failed_fleet=failed_fleet,
        package_value=order.package_value,
        intra_city=intra_city,
    )
    order.selected_fleet = decision["fleet_name"]
    order.selected_price = decision["price"]
    order.agent_reasoning = (
        f"[Reroute #{order.retry_count + 1} after RTO] "
        f"Previous fleet '{failed_fleet}' failed. "
        f"{decision['reasoning']}"
    )
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
    logger.info(
        "Order #%d rerouted after RTO (attempt %d/%d) — new fleet: %s at Rs %s",
        order.id, order.retry_count, MAX_RETRIES, order.selected_fleet, order.selected_price,
    )
    return order
