import { useState } from "react";
import { createOrder } from "../api";
import { openCheckout, checkoutAvailable, TEST_CARD_HINT } from "../checkout";

const DEFAULTS = {
  origin_pincode: "560001",
  destination_pincode: "400001",
  weight_kg: 2,
  package_value: 500,
  pickup_area: "",
  pickup_city: "",
  drop_area: "",
  drop_city: "",
};

export default function OrderPage({ onCreated }) {
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showQuick, setShowQuick] = useState(false);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload = {
        ...form,
        weight_kg: Number(form.weight_kg),
        package_value: Number(form.package_value),
      };
      if (!form.pickup_city.trim()) {
        delete payload.pickup_area;
        delete payload.pickup_city;
        delete payload.drop_area;
        delete payload.drop_city;
      }
      const order = await createOrder(payload);
      if (checkoutAvailable(order)) {
        const result = await openCheckout(order);
        if (result.status === "captured") onCreated(result.order);
        else onCreated(order);
      } else {
        onCreated(order);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h2>Create New Order</h2>
        <p>Fill in the shipment details. The agent will fetch live quotes, select the best fleet, and hold payment.</p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="order-blocks">
          <div className="order-block">
            <h3>Shipment Details</h3>
            <label>Origin pincode<input value={form.origin_pincode} onChange={(e) => update("origin_pincode", e.target.value)} required /></label>
            <label>Destination pincode<input value={form.destination_pincode} onChange={(e) => update("destination_pincode", e.target.value)} required /></label>
            <label>Weight (kg)<input type="number" step="0.1" value={form.weight_kg} onChange={(e) => update("weight_kg", e.target.value)} required /></label>
            <label>Package value (₹)<input type="number" value={form.package_value} onChange={(e) => update("package_value", e.target.value)} required /></label>
          </div>

          <div className="order-block">
            <h3>Quick Fleets <span style={{ fontSize: "0.78rem", fontWeight: 400, color: "var(--muted)" }}>(optional)</span></h3>
            <p className="quick-hint">Add intra-city same-day quotes (Borzo, Porter). Enter city and areas, or leave empty for long-haul only.</p>
            <button type="button" className="quick-toggle" onClick={() => setShowQuick((s) => !s)}>
              {showQuick ? "\u2212 Hide Quick Fleets" : "+ Show Quick Fleets (same-day intra-city)"}
            </button>
            {showQuick && (
              <div className="quick-fields">
                <label>Pickup area<input value={form.pickup_area} onChange={(e) => update("pickup_area", e.target.value)} /></label>
                <label>Pickup city<input value={form.pickup_city} onChange={(e) => update("pickup_city", e.target.value)} placeholder="e.g. Bengaluru" /></label>
                <label>Drop area<input value={form.drop_area} onChange={(e) => update("drop_area", e.target.value)} /></label>
                <label>Drop city<input value={form.drop_city} onChange={(e) => update("drop_city", e.target.value)} placeholder="e.g. Bengaluru" /></label>
              </div>
            )}
          </div>
        </div>

        <div className="order-submit-bar">
          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            {loading ? (<><span className="spinner" /> Dispatching agent...</>) : "Dispatch Agent \u2192"}
          </button>
        </div>
        <p className="quick-hint" style={{ marginTop: "12px" }}>
          On submit, the agent fetches quotes, picks a fleet, and opens Razorpay test checkout ({TEST_CARD_HINT}).
        </p>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
