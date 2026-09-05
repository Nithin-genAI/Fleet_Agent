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

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=schemas.OrderOut)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    order = models.Order(
        origin_pincode=payload.origin_pincode,
        destination_pincode=payload.destination_pincode,
        weight_kg=payload.weight_kg,
        package_value=payload.package_value,
        status="created",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 1. fetch quotes
    quotes = quote_tool.get_all_quotes(order.origin_pincode, order.destination_pincode, order.weight_kg)
    for q in quotes:
        db.add(models.Quote(order_id=order.id, **q))
    order.status = "quoted"
    db.commit()

    # 2. agent selects a fleet
    decision = agent_orchestrator.select_fleet(quotes, order.package_value)
    order.selected_fleet = decision["fleet_name"]
    order.selected_price = decision["price"]
    order.agent_reasoning = decision["reasoning"]
    order.status = "fleet_selected"
    db.commit()

    # 3. hold payment
    hold = payment_tool.create_hold(order.id, order.selected_price)
    db.add(models.Transaction(order_id=order.id, type="hold", amount=order.selected_price,
                               razorpay_ref=hold["razorpay_ref"], status=hold["status"]))
    order.status = "booked"
    db.commit()
    db.refresh(order)
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
