"""
Pydantic models = what crosses the HTTP boundary. SQLAlchemy models
(models.py) = what's actually stored. They look similar right now, but
keeping them separate means when you add a field like `internal_notes`
to Order later, it doesn't automatically leak into an API response —
you have to deliberately add it here too.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OrderCreate(BaseModel):
    origin_pincode: str
    destination_pincode: str
    weight_kg: float
    package_value: float


class QuoteOut(BaseModel):
    fleet_name: str
    price: float
    eta_hours: Optional[float] = None
    source: str

    class Config:
        from_attributes = True


class TransactionOut(BaseModel):
    type: str
    amount: float
    status: str
    razorpay_ref: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    origin_pincode: str
    destination_pincode: str
    weight_kg: float
    package_value: float
    status: str
    selected_fleet: Optional[str] = None
    selected_price: Optional[float] = None
    agent_reasoning: Optional[str] = None
    retry_count: int
    created_at: datetime
    quotes: list[QuoteOut] = []
    transactions: list[TransactionOut] = []

    class Config:
        from_attributes = True


class DeliveryEvent(BaseModel):
    outcome: str  # "delivered" | "rto"
