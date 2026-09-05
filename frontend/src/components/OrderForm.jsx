import { useState } from "react";
import { createOrder } from "../api";

const DEFAULTS = { origin_pincode: "560001", destination_pincode: "400001", weight_kg: 2, package_value: 500 };

export default function OrderForm({ onCreated }) {
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const order = await createOrder({
        ...form,
        weight_kg: Number(form.weight_kg),
        package_value: Number(form.package_value),
      });
      onCreated(order);
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
      <button type="submit" disabled={loading}>
        {loading ? "Dispatching agent…" : "Create Order"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
