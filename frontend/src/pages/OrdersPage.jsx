import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

const STATUS_LABELS = {
  created: "Created",
  quoted: "Quotes received",
  fleet_selected: "Fleet selected",
  booked: "Booked",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_COLORS = {
  completed: "var(--accent)",
  failed: "var(--danger)",
  booked: "#8a6a1e",
  created: "var(--muted)",
  quoted: "var(--muted)",
  fleet_selected: "var(--muted)",
};

export default function OrdersPage({ orders, onRefresh }) {
  const navigate = useNavigate();

  useEffect(() => {
    const interval = setInterval(onRefresh, 5000);
    return () => clearInterval(interval);
  }, [onRefresh]);

  function handleRowClick(order) {
    if (["created", "quoted", "fleet_selected", "booked"].includes(order.status)) {
      navigate(`/agent/${order.id}`);
    } else {
      navigate(`/payout/${order.id}`);
    }
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  return (
    <div>
      <div className="orders-toolbar">
        <div className="page-head" style={{ margin: 0 }}>
          <h2>Orders</h2>
          <p>{orders.length} order{orders.length !== 1 ? "s" : ""} total</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate("/order")}>+ New Order</button>
      </div>

      {orders.length === 0 ? (
        <div className="empty">
          <p>No orders yet — create one to see the agent work.</p>
          <button className="btn btn-primary" style={{ marginTop: "16px" }} onClick={() => navigate("/order")}>Create Order \u2192</button>
        </div>
      ) : (
        <div className="orders-table-wrap">
          <table className="orders-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Route</th>
                <th>Fleet</th>
                <th>Price</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} onClick={() => handleRowClick(o)}>
                  <td><strong>#{o.id}</strong></td>
                  <td>{o.origin_pincode} \u2192 {o.destination_pincode}</td>
                  <td>{o.selected_fleet || "..."}</td>
                  <td>\u20b9{o.selected_price || "..."}</td>
                  <td>
                    <span style={{ color: STATUS_COLORS[o.status] || "var(--muted)", fontWeight: 600, fontSize: "0.85rem" }}>
                      {STATUS_LABELS[o.status] || o.status}
                    </span>
                  </td>
                  <td>{formatTime(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
