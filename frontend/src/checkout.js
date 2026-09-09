// Shared Razorpay Checkout.js opener. Used by both the order-create flow
// (auto-opens right after a real hold is created) and the timeline's
// "Collect Payment" button (for booked orders not yet paid).
//
// Returns a Promise that resolves to:
//   { status: "captured", order }   — customer paid, backend captured payment_id
//   { status: "dismissed" }         — customer closed the modal without paying
//   { status: "unavailable" }       — no real Razorpay order / no key -> skip checkout
import { getRazorpayKey, capturePayment } from "./api";

const TEST_CARD_HINT = "Test card: 4111 1111 1111 1111 · any future expiry · any CVV";

function holdRef(order) {
  const hold = order.transactions?.find((t) => t.type === "hold");
  return hold?.razorpay_ref;
}

export function checkoutAvailable(order) {
  // Only real Razorpay orders (id starts with "order_") can be checked out.
  // Mock holds (mock_hold_…) mean no keys were configured -> skip.
  const ref = holdRef(order);
  return !!ref && ref.startsWith("order_");
}

export async function openCheckout(order) {
  if (!checkoutAvailable(order)) return { status: "unavailable" };

  let keyId;
  try {
    ({ key_id: keyId } = await getRazorpayKey());
  } catch {
    return { status: "unavailable" };
  }
  if (!keyId) return { status: "unavailable" };

  const razorpayOrderId = holdRef(order);

  return new Promise((resolve) => {
    const options = {
      key: keyId,
      amount: Math.round(order.selected_price * 100), // paise — must match the hold
      currency: "INR",
      name: "FleetAgent",
      description: `Order #${order.id} — ${order.selected_fleet}`,
      order_id: razorpayOrderId,
      // Pre-filled so the demo card form is one click; still fully editable.
      prefill: { name: "FleetAgent Demo", email: "demo@fleetagent.in", contact: "9999999999" },
      notes: { fleetagent_order_id: String(order.id) },
      theme: { color: "#1f6f5c" },
      handler: async (response) => {
        try {
          const updated = await capturePayment(order.id, {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          resolve({ status: "captured", order: updated });
        } catch (err) {
          // Capture failed (e.g. bad signature) — surface it so the UI can show it.
          resolve({ status: "capture_failed", error: err.message });
        }
      },
      modal: {
        ondismiss: () => resolve({ status: "dismissed" }),
      },
    };

    const rzp = new window.Razorpay(options);
    rzp.on("payment.failed", (resp) => {
      resolve({ status: "payment_failed", error: resp?.error?.description || "Payment failed" });
    });
    rzp.open();
  });
}

export { TEST_CARD_HINT };
