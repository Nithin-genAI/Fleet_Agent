import { useEffect, useState } from "react";
import { listOrders, getOrder } from "./api";
import OrderForm from "./components/OrderForm";
import OrderTimeline from "./components/OrderTimeline";
import OrdersList from "./components/OrdersList";

export default function App() {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(null);

  async function refreshList() {
    const data = await listOrders();
    setOrders(data);
  }

  useEffect(() => {
    refreshList();
  }, []);

  function handleCreated(order) {
    setSelected(order);
    refreshList();
  }

  async function handleSelect(id) {
    const order = await getOrder(id);
    setSelected(order);
  }

  function handleUpdated(order) {
    setSelected(order);
    refreshList();
  }

  return (
    <div className="app">
      <header>
        <h1>FleetAgent</h1>
        <p className="subtitle">AI-orchestrated delivery booking + agentic payments</p>
      </header>
      <div className="layout">
        <aside>
          <OrderForm onCreated={handleCreated} />
          <OrdersList orders={orders} selectedId={selected?.id} onSelect={handleSelect} />
        </aside>
        <main>
          <OrderTimeline order={selected} onUpdated={handleUpdated} />
        </main>
      </div>
    </div>
  );
}
