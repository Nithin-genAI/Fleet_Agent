"""
Real Razorpay test-mode calls via the official SDK. Same fallback discipline
as quote_tool.py: any failure -> mock reference, never crash the order flow.

HONEST ARCHITECTURAL NOTE — read this before demo day:

create_hold() creates a real Razorpay ORDER (a container to collect payment
against) — this works instantly with any test-mode key pair, no approval
needed. This is genuinely real and verifiable in your Razorpay dashboard.

The money flow is now end-to-end real on the refund side too, because we
built the missing checkout step:
  1. create_hold()  -> real Razorpay ORDER (status "attempted").
  2. Customer pays that order via Razorpay Checkout.js in the frontend (test
     card 4111 1111 1111 1111, any future expiry / any CVV). Razorpay
     auto-captures (payment_capture: 1) and returns a payment_id + signature.
  3. verify_payment() checks the HMAC signature server-side; if valid, the
     router stores the payment_id on the order.
  4. refund_payment() now has a real payment_id to refund against on RTO, so
     RTO refunds are genuinely real and visible in the dashboard.

release_payment (paying the fleet on successful delivery) is a RazorpayX
Payout, which needs RazorpayX enabled on your account plus a registered
fund_account for the fleet partner — not something you get approved for
same-day. It stays mocked, and that's the one honest remaining gap. Say so
plainly in the README.
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


def get_public_key() -> str | None:
    """The key_id is public-safe to ship to the browser (Checkout.js needs it).
    The key_secret must NEVER leave the server. Returns None if no keys configured."""
    return os.environ.get("RAZORPAY_KEY_ID")


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


def verify_payment(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """Verify the Checkout.js success signature server-side (HMAC-SHA256 of
    order_id|payment_id with key_secret). Returns False if no keys (can't verify)
    or if verification fails — the router treats False as a rejected capture."""
    client = _get_client()
    if not client:
        return False
    try:
        return client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except Exception:
        return False


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
    """Real refund if a payment_id is passed in (i.e. a checkout was actually completed + captured). Else mock."""
    client = _get_client()
    if client and payment_id:
        try:
            refund = client.payment.refund(payment_id, {"amount": int(amount * 100)})
            return {"razorpay_ref": refund["id"], "status": refund["status"]}
        except Exception:
            pass
    return {"razorpay_ref": f"mock_refund_{uuid.uuid4().hex[:8]}", "status": "refunded"}
