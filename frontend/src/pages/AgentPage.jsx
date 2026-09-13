import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getOrder } from "../api";
import { openCheckout, checkoutAvailable, TEST_CARD_HINT } from "../checkout";
import Typewriter from "../components/Typewriter";
import StepCard from "../components/StepCard";

const STEP_DELAY = 1500; // ms between step card reveals — slower so users can read each step

export default function AgentPage({ onUpdated }) {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [typingDone, setTypingDone] = useState({});
  const [payMsg, setPayMsg] = useState(null);

  // Fetch order whenever orderId changes (handles navigation between orders)
  useEffect(() => {
    setLoading(true);
    setError(null);
    setOrder(null);
    setVisibleSteps(0);
    setTypingDone({});
    getOrder(orderId)
      .then((data) => { setOrder(data); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [orderId]);

  // Reveal step cards sequentially as their typing completes
  function markTypingDone(stepKey) {
    setTypingDone((prev) => ({ ...prev, [stepKey]: true }));
    // Reveal next step after a short delay
    setTimeout(() => {
      setVisibleSteps((s) => Math.min(s + 1, 4));
    }, STEP_DELAY);
  }

  // Open Razorpay checkout for this order
  async function handleCheckout() {
    setPayMsg(null);
    const result = await openCheckout(order);
    if (result.status === "captured") {
      const updated = await getOrder(orderId);
      setOrder(updated);
      onUpdated();
      setPayMsg("Payment captured — refunds will now be real.");
    } else if (result.status === "payment_failed" || result.status === "capture_failed") {
      setPayMsg(result.error || "Payment failed");
    } else if (result.status === "dismissed") {
      setPayMsg("Checkout closed without paying.");
    }
  }

  if (loading) return <p className="empty">Loading order...</p>;
  if (error) return <p className="empty">Error: {error}</p>;
  if (!order) return <p className="empty">Order not found.</p>;

  const holdTxn = order.transactions?.find((t) => t.type === "hold");
  const isPaid = !!order.razorpay_payment_id;
  const canCheckout = checkoutAvailable(order) && !isPaid;
  const route = `${order.origin_pincode} → ${order.destination_pincode}`;

  // Build the quote table rows
  const quoteRows = order.quotes.map((q, i) => (
    <tr key={i} className={q.fleet_name === order.selected_fleet ? "chosen" : ""}>
      <td>{q.fleet_name}</td>
      <td>₹{q.price}</td>
      <td>{q.eta_hours != null ? `${q.eta_hours}h` : "—"}</td>
      <td><span className={`cat cat-${q.category || "standard"}`}>{q.category === "quick" ? "same-day" : "long-haul"}</span></td>
      <td>{q.source}</td>
    </tr>
  ));

  return (
    <div className="agent-container">
      <div className="agent-header">
        <h2>Agent Working on Order #{order.id}</h2>
        <p className="order-meta">{route} · {order.weight_kg}kg · ₹{order.package_value} package value</p>
        {order.retry_count > 0 && <span className="tag tag-reroute">Rerouted after RTO ({order.retry_count})</span>}
      </div>

      {/* Step 1: Fetching quotes */}
      {visibleSteps >= 0 && (
        <StepCard icon="🔍" title="Fetching live fleet quotes..." delay={0} complete={typingDone.quotes}>
          <Typewriter
            text={`Querying WareIQ, NimbusPost${order.pickup_city ? ", Borzo, Porter" : ""} for ${route}...`}
            onDone={() => markTypingDone("quotes")}
          />
          {typingDone.quotes && (
            <table className="quote-table">
              <thead><tr><th>Fleet</th><th>Price</th><th>ETA</th><th>Type</th><th>Source</th></tr></thead>
              <tbody>{quoteRows}</tbody>
            </table>
          )}
        </StepCard>
      )}

      {/* Step 2: Agent decision */}
      {visibleSteps >= 1 && (
        <StepCard icon="🤖" title="Analyzing cost + time efficiency..." delay={0} complete={typingDone.decision}>
          <Typewriter
            text={order.agent_reasoning || "Selecting best fleet based on composite score (cost 60% + time 40%)..."}
            onDone={() => markTypingDone("decision")}
          />
          {typingDone.decision && (
            <div className="reasoning-box">{order.agent_reasoning}</div>
          )}
          {typingDone.decision && (
            <div className="selected-badge">
              ✓ Fleet Selected: {order.selected_fleet} at ₹{order.selected_price}
            </div>
          )}
        </StepCard>
      )}

      {/* Step 3: Payment hold */}
      {visibleSteps >= 2 && (
        <StepCard icon="🔒" title="Creating payment hold..." delay={0} complete={typingDone.hold}>
          <Typewriter
            text={`Holding ₹${order.selected_price} via Razorpay Orders API...`}
            onDone={() => markTypingDone("hold")}
          />
          {typingDone.hold && holdTxn && (
            <p style={{ marginTop: "10px", fontSize: "0.85rem", color: "var(--muted)" }}>
              Hold ref: <code>{holdTxn.razorpay_ref}</code> · Status: {holdTxn.status}
            </p>
          )}
        </StepCard>
      )}

      {/* Step 4: Payment collection / proceed */}
      {visibleSteps >= 3 && (
        <StepCard icon="💳" title="Payment collection" delay={0} complete={isPaid || !canCheckout}>
          {canCheckout ? (
            <>
              <p style={{ fontSize: "0.88rem", color: "var(--muted)", marginBottom: "12px" }}>
                Complete a test checkout so refunds are real. {TEST_CARD_HINT}
              </p>
              <button className="btn btn-primary" onClick={handleCheckout}>Open Razorpay Checkout</button>
              {payMsg && <p className="quick-hint" style={{ marginTop: "10px" }}>{payMsg}</p>}
            </>
          ) : isPaid ? (
            <p style={{ fontSize: "0.88rem", color: "var(--accent)", fontWeight: 600 }}>
              ✓ Payment captured · {order.razorpay_payment_id}
            </p>
          ) : (
            <p style={{ fontSize: "0.88rem", color: "var(--muted)" }}>
              Hold is mocked (no Razorpay keys configured). Refunds will mock. Proceed to delivery.
            </p>
          )}
        </StepCard>
      )}

      {/* Proceed to delivery */}
      {visibleSteps >= 3 && (isPaid || !canCheckout) && (
        <div className="agent-actions">
          <button className="btn btn-primary btn-lg" onClick={() => navigate(`/payout/${order.id}`)}>
            Proceed to Delivery →
          </button>
        </div>
      )}
    </div>
  );
}
