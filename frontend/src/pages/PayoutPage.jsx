import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getOrder, sendDeliveryEvent } from "../api";
import { openCheckout, checkoutAvailable, TEST_CARD_HINT } from "../checkout";

const STATUS_LABELS = {
  created: "Created",
  quoted: "Quotes received",
  fleet_selected: "Fleet selected",
  booked: "Booked — awaiting delivery",
  completed: "Delivered — payment released",
  failed: "Failed (retry limit reached)",
};

const TXN_ICONS = { hold: "🔒", release: "💸", refund: "↩️" };
const TXN_LABELS = { hold: "Payment Hold", release: "Payout to Fleet", refund: "Refund" };

export default function PayoutPage({ onUpdated }) {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [payMsg, setPayMsg] = useState(null);

  useEffect(() => {
    getOrder(orderId)
      .then((data) => { setOrder(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [orderId]);

  async function refresh() {
    const data = await getOrder(orderId);
    setOrder(data);
    onUpdated();
  }

  async function fire(outcome) {
    await sendDeliveryEvent(order.id, outcome);
    await refresh();
  }

  async function collectPayment() {
    setPayMsg(null);
    const result = await openCheckout(order);
    if (result.status === "captured") {
      await refresh();
      setPayMsg("Payment captured — refunds will now be real.");
    } else if (result.status === "payment_failed" || result.status === "capture_failed") {
      setPayMsg(result.error || "Payment failed");
    } else if (result.status === "dismissed") {
      setPayMsg("Checkout closed without paying.");
    }
  }

  if (loading) return <p className="empty">Loading order...</p>;
  if (!order) return <p className="empty">Order not found.</p>;

  const canSimulate = order.status === "booked";
  const needsPayment = canSimulate && !order.razorpay_payment_id && checkoutAvailable(order);
  const isTerminal = order.status === "completed" || order.status === "failed";
  const isCompleted = order.status === "completed";
  const releaseTxn = order.transactions?.find((t) => t.type === "release");
  const isMockPayout = releaseTxn && releaseTxn.razorpay_ref?.startsWith("mock_");
  const webhookPayload = '{"order_id": ' + order.id + ', "status": "delivered"}';
  const route = `${order.origin_pincode} → ${order.destination_pincode}`;

  return (
    <div>
      <div className="page-head">
        <h2>Order #{order.id} — Payout & Delivery</h2>
        <p>{route} · {order.selected_fleet} · ₹{order.selected_price}</p>
      </div>

      <span className="status-badge" data-status={order.status}>
        {STATUS_LABELS[order.status] || order.status}
      </span>
      {order.razorpay_payment_id && (
        <span className="tag" style={{ marginLeft: "10px" }}>payment captured · {order.razorpay_payment_id}</span>
      )}
      {order.retry_count > 0 && (
        <span className="tag tag-reroute" style={{ marginLeft: "10px" }}>Rerouted ({order.retry_count})</span>
      )}

      {/* Payout confirmation banner */}
      {isCompleted && releaseTxn && (
        <div className="payout-confirmation">
          <h3>✓ Payment Released to Fleet</h3>
          <p><strong>{order.selected_fleet}</strong> has been paid <strong>₹{releaseTxn.amount}</strong></p>
          <p className="payout-ref">
            Payout ref: <code>{releaseTxn.razorpay_ref}</code> · Status: {releaseTxn.status}
            {isMockPayout && <span className="mock-badge"> (simulated — RazorpayX not configured)</span>}
          </p>
          <p className="payout-note">The autonomous loop is complete: order delivered → payment released to fleet.</p>
        </div>
      )}

      {/* RTO failure banner */}
      {order.status === "failed" && (
        <div className="rto-failed-banner">
          <h3>✗ Delivery Failed</h3>
          <p>RTO recovery exhausted (retry limit reached). Refund has been processed.</p>
        </div>
      )}

      {/* Payment events timeline */}
      <h3 style={{ marginTop: "24px", marginBottom: "8px", fontSize: "0.95rem", color: "var(--muted)" }}>Payment Events</h3>
      <div className="events-timeline">
        {order.transactions.length === 0 && (
          <p className="quick-hint">No transactions yet.</p>
        )}
        {order.transactions.map((t, i) => (
          <div key={i} className="event-row">
            <div className="event-icon">{TXN_ICONS[t.type] || "📋"}</div>
            <div className="event-content">
              <div className="event-title">{TXN_LABELS[t.type] || t.type} — ₹{t.amount}</div>
              <div className="event-detail">
                Status: {t.status} · Ref: <code>{t.razorpay_ref}</code>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Collect payment */}
      {needsPayment && (
        <div style={{ marginTop: "20px" }}>
          <h3 style={{ fontSize: "0.95rem", color: "var(--muted)", marginBottom: "8px" }}>Collect Payment</h3>
          <p className="quick-hint">No payment captured yet — complete a test checkout so an RTO refund is real. {TEST_CARD_HINT}.</p>
          <div className="sim-buttons">
            <button className="btn btn-primary" onClick={collectPayment}>Open Razorpay Checkout</button>
          </div>
          {payMsg && <p className="quick-hint" style={{ marginTop: "10px" }}>{payMsg}</p>}
        </div>
      )}

      {/* Simulate delivery */}
      {canSimulate && (
        <div style={{ marginTop: "24px" }}>
          <h3 style={{ fontSize: "0.95rem", color: "var(--muted)", marginBottom: "8px" }}>
            {needsPayment ? "Simulate Delivery Outcome" : "Simulate Delivery Outcome"}
          </h3>
          {!order.razorpay_payment_id && (
            <p className="quick-hint">
              {checkoutAvailable(order)
                ? "No payment captured — an RTO here will fall back to a mock refund."
                : "Hold is mocked (no Razorpay keys) — refunds will mock."}
            </p>
          )}
          <div className="sim-buttons">
            <button className="btn btn-primary" onClick={() => fire("delivered")}>Simulate Delivered ✓</button>
            <button className="btn btn-danger" onClick={() => fire("rto")}>Simulate RTO ↩️</button>
          </div>
        </div>
      )}

      {/* Webhook info */}
      {canSimulate && (
        <div className="webhook-info">
          <h3>Or trigger via webhook (autonomous mode)</h3>
          <p className="quick-hint">Courier: <code>POST /webhooks/courier</code> — body: <code>{webhookPayload}</code></p>
          <p className="quick-hint">Razorpay: <code>POST /webhooks/razorpay</code> — for payment/payout lifecycle events</p>
        </div>
      )}

      {/* Back to orders */}
      <div style={{ marginTop: "24px" }}>
        <button className="btn btn-outline" onClick={() => navigate("/orders")}>← Back to Orders</button>
      </div>
    </div>
  );
}
