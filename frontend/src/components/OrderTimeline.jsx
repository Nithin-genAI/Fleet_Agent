import { useState } from "react";
import { sendDeliveryEvent } from "../api";
import { openCheckout, checkoutAvailable, TEST_CARD_HINT } from "../checkout";

const STATUS_LABELS = {
  created: "Created",
  quoted: "Quotes received",
  fleet_selected: "Fleet selected",
  booked: "Booked — awaiting delivery",
  completed: "Delivered — payment released",
  failed: "Failed (retry limit reached)",
};

export default function OrderTimeline({ order, onUpdated }) {
  const [payMsg, setPayMsg] = useState(null);
  if (!order) return <p className="empty">Create an order to see the agent work.</p>;

  async function fire(outcome) {
    const updated = await sendDeliveryEvent(order.id, outcome);
    onUpdated(updated);
  }

  async function collectPayment() {
    setPayMsg(null);
    const result = await openCheckout(order);
    if (result.status === "captured") {
      onUpdated(result.order);
      setPayMsg("Payment captured — refunds will now be real.");
    } else if (result.status === "payment_failed" || result.status === "capture_failed") {
      setPayMsg(result.error || "Payment failed");
    } else if (result.status === "dismissed") {
      setPayMsg("Checkout closed without paying.");
    }
  }

  const canSimulate = order.status === "booked";
  const needsPayment = canSimulate && !order.razorpay_payment_id && checkoutAvailable(order);

  return (
    <div className="timeline">
      <h2>Order #{order.id}</h2>
      <p className="status-badge" data-status={order.status}>
        {STATUS_LABELS[order.status] || order.status}
      </p>
      {order.razorpay_payment_id && (
        <p className="tag">payment captured · {order.razorpay_payment_id}</p>
      )}

      <section>
        <h3>1. Quotes fetched</h3>
        <ul className="quote-list">
          {order.quotes.map((q, i) => (
            <li key={i} className={q.fleet_name === order.selected_fleet ? "chosen" : ""}>
              <strong>{q.fleet_name}</strong> — ₹{q.price} · ETA {q.eta_hours}h
              <span className={`cat cat-${q.category || "standard"}`}>
                {(q.category === "quick") ? "same-day" : "long-haul"}
              </span>
              {q.fleet_name === order.selected_fleet && <span className="tag">selected</span>}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>2. Agent decision</h3>
        <p className="reasoning">{order.agent_reasoning}</p>
        {order.retry_count > 0 && <p className="tag">Rerouted after RTO ({order.retry_count})</p>}
      </section>

      <section>
        <h3>3. Payment events</h3>
        <ul className="txn-list">
          {order.transactions.map((t, i) => (
            <li key={i}>
              <strong>{t.type}</strong> — ₹{t.amount} ({t.status}) · {t.razorpay_ref}
            </li>
          ))}
        </ul>
      </section>

      {needsPayment && (
        <section>
          <h3>4. Collect payment</h3>
          <p className="quick-hint">No payment captured yet — complete a test checkout so an RTO refund is real. {TEST_CARD_HINT}.</p>
          <div className="sim-buttons">
            <button className="delivered" onClick={collectPayment}>Open Razorpay Checkout</button>
          </div>
          {payMsg && <p className="quick-hint">{payMsg}</p>}
        </section>
      )}

      {canSimulate && (
        <section>
          <h3>{needsPayment ? "5" : "4"}. Simulate delivery outcome</h3>
          {!order.razorpay_payment_id && (
            <p className="quick-hint">
              {checkoutAvailable(order)
                ? "No payment captured — an RTO here will fall back to a mock refund."
                : "Hold is mocked (no Razorpay keys) — refunds will mock."}
            </p>
          )}
          <div className="sim-buttons">
            <button className="delivered" onClick={() => fire("delivered")}>Simulate Delivered</button>
            <button className="rto" onClick={() => fire("rto")}>Simulate RTO</button>
          </div>
        </section>
      )}
    </div>
  );
}
