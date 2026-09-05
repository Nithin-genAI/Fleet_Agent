import { sendDeliveryEvent } from "../api";

const STATUS_LABELS = {
  created: "Created",
  quoted: "Quotes received",
  fleet_selected: "Fleet selected",
  booked: "Booked — awaiting delivery",
  completed: "Delivered — payment released",
  failed: "Failed (retry limit reached)",
};

export default function OrderTimeline({ order, onUpdated }) {
  if (!order) return <p className="empty">Create an order to see the agent work.</p>;

  async function fire(outcome) {
    const updated = await sendDeliveryEvent(order.id, outcome);
    onUpdated(updated);
  }

  const canSimulate = order.status === "booked";

  return (
    <div className="timeline">
      <h2>Order #{order.id}</h2>
      <p className="status-badge" data-status={order.status}>
        {STATUS_LABELS[order.status] || order.status}
      </p>

      <section>
        <h3>1. Quotes fetched</h3>
        <ul className="quote-list">
          {order.quotes.map((q, i) => (
            <li key={i} className={q.fleet_name === order.selected_fleet ? "chosen" : ""}>
              <strong>{q.fleet_name}</strong> — ₹{q.price} · ETA {q.eta_hours}h
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

      {canSimulate && (
        <section>
          <h3>4. Simulate delivery outcome</h3>
          <div className="sim-buttons">
            <button className="delivered" onClick={() => fire("delivered")}>Simulate Delivered</button>
            <button className="rto" onClick={() => fire("rto")}>Simulate RTO</button>
          </div>
        </section>
      )}
    </div>
  );
}
