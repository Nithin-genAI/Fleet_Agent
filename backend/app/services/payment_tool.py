"""
Three operations, matching what the agent actually needs to do:
  hold    -> money reserved when a fleet is booked (Razorpay Order, test mode)
  release -> money paid out to the fleet on successful delivery (RazorpayX Payout)
  refund  -> money returned to the brand on RTO (Razorpay Refund)

We're using Orders + Payouts + Refunds (RazorpayX), NOT UPI Reserve Pay —
Reserve Pay is a consumer spending-mandate mechanism (person authorizes an
agent to pay a merchant). This is brand-to-vendor settlement, a different
primitive. See BlackBuck's own use of RazorpayX payouts for driver
disbursement as the precedent.

Mocked here so the full order lifecycle runs before Razorpay test keys are
even wired in. Swap each function's body for the real SDK call independently
— they don't need to change together.
"""
import uuid


def create_hold(order_id: int, amount: float) -> dict:
    """
    TODO (real): razorpay_client.order.create({"amount": amount*100, "currency": "INR", ...})
    amount is in paise for the real API — multiply by 100 there, not here.
    """
    return {"razorpay_ref": f"mock_hold_{uuid.uuid4().hex[:8]}", "status": "held"}


def release_payment(order_id: int, amount: float, fleet_name: str) -> dict:
    """TODO (real): RazorpayX payout to the fleet partner's linked account."""
    return {"razorpay_ref": f"mock_payout_{uuid.uuid4().hex[:8]}", "status": "released"}


def refund_payment(order_id: int, amount: float) -> dict:
    """TODO (real): razorpay_client.refund.create({"payment_id": ..., "amount": amount*100})"""
    return {"razorpay_ref": f"mock_refund_{uuid.uuid4().hex[:8]}", "status": "refunded"}
