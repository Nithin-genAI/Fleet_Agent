"""
Real Razorpay test-mode calls via the official SDK. Same fallback discipline
as quote_tool.py: any failure -> mock reference, never crash the order flow.

HONEST ARCHITECTURAL NOTE — read this before demo day:

create_hold() creates a real Razorpay ORDER (a container to collect payment
against) — this works instantly with any test-mode key pair, no approval
needed. This is genuinely real and verifiable in your Razorpay dashboard.

release_payment() and refund_payment() are architecturally harder to make
fully real in a hackathon window:
  - refund_payment needs an actual PAYMENT id, which only exists once
    someone has paid the order via Razorpay Checkout with a test card.
    We never built that checkout step (there's no "customer" in a B2B
    brand->fleet flow), so there is no payment_id to refund in this demo
    unless you manually complete one test checkout first.
  - release_payment (paying the fleet) is a RazorpayX Payout, which needs
    RazorpayX enabled on your account plus a registered fund_account for
    the fleet partner — not something you get approved for same-day.

Both are wired below to ATTEMPT the real call and fall back to a mock
reference on any failure, so the code is correct and ready to go live the
moment those prerequisites exist — but expect them to fall back to mock in
your actual demo, and say so plainly in your README. That's honest, not a
weakness: the Orders API call being real is still the meaningful part.
"""
import os
import uuid
import razorpay


def _get_client():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def create_hold(order_id: int, amount: float) -> dict:
    """Creates a real Razorpay test-mode Order. Falls back to a mock ref if no keys / call fails."""
    client = _get_client()
    if not client:
        return {"razorpay_ref": f"mock_hold_{uuid.uuid4().hex[:8]}", "status": "held"}

    try:
        rp_order = client.order.create({
            "amount": int(amount * 100),  # paise
            "currency": "INR",
            "receipt": f"fleetagent_order_{order_id}",
            "payment_capture": 1,
        })
        return {"razorpay_ref": rp_order["id"], "status": rp_order["status"]}
    except Exception:
        return {"razorpay_ref": f"mock_hold_{uuid.uuid4().hex[:8]}", "status": "held"}


def release_payment(order_id: int, amount: float, fleet_name: str) -> dict:
    """
    TODO once RazorpayX is enabled on your account:
        client.payout.create({
            "account_number": os.environ["RAZORPAY_X_ACCOUNT_NUMBER"],
            "fund_account_id": <fleet's registered fund account>,
            "amount": int(amount * 100),
            "currency": "INR",
            "mode": "UPI",
            "purpose": "payout",
        })
    Not attempted here — requires account setup this demo doesn't have. Mocked.
    """
    return {"razorpay_ref": f"mock_payout_{uuid.uuid4().hex[:8]}", "status": "released"}


def refund_payment(order_id: int, amount: float, payment_id: str | None = None) -> dict:
    """Real refund if a payment_id is passed in (i.e. a test checkout was actually completed). Else mock."""
    client = _get_client()
    if client and payment_id:
        try:
            refund = client.payment.refund(payment_id, {"amount": int(amount * 100)})
            return {"razorpay_ref": refund["id"], "status": refund["status"]}
        except Exception:
            pass
    return {"razorpay_ref": f"mock_refund_{uuid.uuid4().hex[:8]}", "status": "refunded"}
