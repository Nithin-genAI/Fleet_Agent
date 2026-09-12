"""
This router is deliberately thin: every function body is 1-3 lines calling
a service. If logic starts creeping in here (a for-loop doing real work, an
if/else deciding business rules), that's a sign it belongs in a service
instead. Keeping this boundary sharp is what lets you test agent_orchestrator
or payment_tool in isolation without spinning up the whole HTTP app.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..services import quote_tool, agent_orchestrator, payment_tool

import time
import logging

logger = logging.getLogger("fleetagent.orders")

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=schemas.OrderOut)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    t0 = time.time()
    order = models.Order(
        origin_pincode=payload.origin_pincode,
        destination_pincode=payload.destination_pincode,
        weight_kg=payload.weight_kg,
        package_value=payload.package_value,
        pickup_area=payload.pickup_area,
        pickup_city=payload.pickup_city,
        drop_area=payload.drop_area,
        drop_city=payload.drop_city,
        status="created",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    t_order = time.time()

    # 1. fetch quotes. Quick-commerce quotes are only fetched when the user
    # supplied a pickup_city (the Quick Fleets section); otherwise long-haul only.
    quick = None
    if order.pickup_city:
        quick = {
            "pickup_area": order.pickup_area,
            "pickup_city": order.pickup_city,
            "drop_area": order.drop_area,
            "drop_city": order.drop_city,
        }
    quotes = quote_tool.get_all_quotes(
        order.origin_pincode, order.destination_pincode, order.weight_kg, quick=quick
    )
    for q in quotes:
        db.add(models.Quote(order_id=order.id, **q))
    order.status = "quoted"
    db.commit()
    t_quotes = time.time()

    # 2. agent selects a fleet. "quick" fleets are intra-city only, so they're
    # valid candidates only when the user filled the same pickup and drop city.
    intra_city = bool(
        order.pickup_city and order.drop_city
        and order.pickup_city.strip().lower() == order.drop_city.strip().lower()
    )
    decision = agent_orchestrator.select_fleet(quotes, order.package_value, intra_city=intra_city)
    order.selected_fleet = decision["fleet_name"]
    order.selected_price = decision["price"]
    order.agent_reasoning = decision["reasoning"]
    order.status = "fleet_selected"
    db.commit()
    t_select = time.time()

    # 3. hold payment
    hold = payment_tool.create_hold(order.id, order.selected_price)
    db.add(models.Transaction(order_id=order.id, type="hold", amount=order.selected_price,
                               razorpay_ref=hold["razorpay_ref"], status=hold["status"]))
    order.status = "booked"
    db.commit()
    db.refresh(order)
    t_hold = time.time()

    logger.info(
        "Order #%d created in %.1fs | quotes: %.1fs | fleet_select: %.1fs | hold: %.1fs",
        order.id,
        t_hold - t0,
        t_quotes - t_order,
        t_select - t_quotes,
        t_hold - t_select,
    )
    return order


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.get("/", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.id.desc()).all()
