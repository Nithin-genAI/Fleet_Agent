"""
Three tables only. Resist the urge to add more for the demo — every extra
table is a migration you don't have time to debug.

Order.status is the state machine driving the whole agent loop. These are
the ONLY valid values — the orchestrator service is the one place that's
allowed to change this field. If you find yourself setting order.status
from inside a router, that's a bug: routers call services, services own
state transitions.

    created -> quoted -> fleet_selected -> payment_held -> booked
        -> delivered -> payment_released -> completed
                or
        -> rto -> refunded -> rerouted -> booked (retry, capped at 1)
                or -> failed (if reroute also fails)
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    origin_pincode = Column(String, nullable=False)
    destination_pincode = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=False)
    package_value = Column(Float, nullable=False)

    status = Column(String, default="created", nullable=False)
    selected_fleet = Column(String, nullable=True)
    selected_price = Column(Float, nullable=True)
    agent_reasoning = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    quotes = relationship("Quote", back_populates="order", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="order", cascade="all, delete-orphan")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    fleet_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    eta_hours = Column(Float, nullable=True)
    source = Column(String, nullable=False)  # "porter" | "wareiq" | "mock"
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="quotes")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    type = Column(String, nullable=False)  # "hold" | "release" | "refund"
    razorpay_ref = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(String, default="created")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="transactions")
