// One base URL, one place to change it (e.g. if you deploy the backend
// somewhere for the live demo instead of localhost).
const BASE_URL = "http://127.0.0.1:8000";

export async function createOrder(order) {
  const res = await fetch(`${BASE_URL}/orders/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });
  if (!res.ok) throw new Error("Failed to create order");
  return res.json();
}

export async function listOrders() {
  const res = await fetch(`${BASE_URL}/orders/`);
  if (!res.ok) throw new Error("Failed to fetch orders");
  return res.json();
}

export async function getOrder(id) {
  const res = await fetch(`${BASE_URL}/orders/${id}`);
  if (!res.ok) throw new Error("Failed to fetch order");
  return res.json();
}

export async function sendDeliveryEvent(id, outcome) {
  const res = await fetch(`${BASE_URL}/orders/${id}/delivery-event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outcome }),
  });
  if (!res.ok) throw new Error("Failed to send delivery event");
  return res.json();
}
