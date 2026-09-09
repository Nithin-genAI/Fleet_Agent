import { useState } from "react";
import { createOrder } from "../api";
import { openCheckout, checkoutAvailable, TEST_CARD_HINT } from "../checkout";

const DEFAULTS = {
  origin_pincode: "560001",
  destination_pincode: "400001",
  weight_kg: 2,
  package_value: 500,
  // Quick Fleets (optional intra-city same-day). Empty by default — long-haul only.
  pickup_area: "",
  pickup_city: "",
  drop_area: "",
  drop_city: "",
};

export default function OrderForm({ onCreated }) {
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
      // Only send the quick-fleet fields when the user actually filled a city;
      // otherwise the backend fetches long-haul quotes only.
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
      // If a real Razorpay order was created, collect payment now so refunds
      // can be real later. If checkout isn't available (mock/no keys), just
      // hand the order straight to the timeline as before.
      if (checkoutAvailable(order)) {
        const result = await openCheckout(order);
        if (result.status === "captured") onCreated(result.order);
        else onCreated(order); // dismissed/failed — order is still booked, just unpaid
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
    <form className="order-form" onSubmit={handleSubmit}>
      <h2>New Order</h2>
      <label>
        Origin pincode
        <input value={form.origin_pincode} onChange={(e) => update("origin_pincode", e.target.value)} required />
      </label>
      <label>
        Destination pincode
        <input value={form.destination_pincode} onChange={(e) => update("destination_pincode", e.target.value)} required />
      </label>
      <label>
        Weight (kg)
        <input type="number" step="0.1" value={form.weight_kg} onChange={(e) => update("weight_kg", e.target.value)} required />
      </label>
      <label>
        Package value (₹)
        <input type="number" value={form.package_value} onChange={(e) => update("package_value", e.target.value)} required />
      </label>

      <button type="button" className="quick-toggle" onClick={() => setShowQuick((s) => !s)}>
        {showQuick ? "− Hide Quick Fleets" : "+ Quick Fleets (same-day intra-city)"}
      </button>
      {showQuick && (
        <div className="quick-fields">
          <p className="quick-hint">
            Optional — add intra-city same-day quotes (Borzo, Porter). Enter the city and
            areas; leave empty for long-haul-only.
          </p>
          <label>
            Pickup area
            <input value={form.pickup_area} onChange={(e) => update("pickup_area", e.target.value)} />
          </label>
          <label>
            Pickup city
            <input value={form.pickup_city} onChange={(e) => update("pickup_city", e.target.value)} placeholder="e.g. Bengaluru" />
          </label>
          <label>
            Drop area
            <input value={form.drop_area} onChange={(e) => update("drop_area", e.target.value)} />
          </label>
          <label>
            Drop city
            <input value={form.drop_city} onChange={(e) => update("drop_city", e.target.value)} placeholder="e.g. Bengaluru" />
          </label>
        </div>
      )}

      <button type="submit" disabled={loading}>
        {loading ? "Dispatching agent…" : "Create Order"}
      </button>
      <p className="quick-hint">On submit, the agent fetches quotes, picks a fleet, and opens Razorpay test checkout ({TEST_CARD_HINT}).</p>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
