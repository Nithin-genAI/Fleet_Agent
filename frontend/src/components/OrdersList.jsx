export default function OrdersList({ orders, selectedId, onSelect }) {
  if (!orders.length) return null;
  return (
    <div className="orders-list">
      <h3>Orders</h3>
      <ul>
        {orders.map((o) => (
          <li key={o.id} className={o.id === selectedId ? "active" : ""} onClick={() => onSelect(o.id)}>
            #{o.id} · {o.selected_fleet || "…"} · {o.status}
          </li>
        ))}
      </ul>
    </div>
  );
}
