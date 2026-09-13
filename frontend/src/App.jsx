import { useEffect, useState, useCallback } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { listOrders } from "./api";
import Header from "./components/Header";
import Footer from "./components/Footer";
import Landing from "./pages/Landing";
import OrderPage from "./pages/OrderPage";
import AgentPage from "./pages/AgentPage";
import PayoutPage from "./pages/PayoutPage";
import OrdersPage from "./pages/OrdersPage";

export default function App() {
  const [orders, setOrders] = useState([]);
  const navigate = useNavigate();
  const location = useLocation();

  const refreshOrders = useCallback(async () => {
    try {
      const data = await listOrders();
      setOrders(data);
    } catch {
      // backend not running — orders stay empty
    }
  }, []);

  useEffect(() => {
    refreshOrders();
  }, [refreshOrders]);

  function handleCreated(order) {
    refreshOrders();
    navigate(`/agent/${order.id}`);
  }

  function handleUpdated() {
    refreshOrders();
  }

  return (
    <div className="app-shell">
      <Header orderCount={orders.length} currentPath={location.pathname} />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/order" element={<OrderPage onCreated={handleCreated} />} />
          <Route path="/agent/:orderId" element={<AgentPage onUpdated={handleUpdated} />} />
          <Route path="/payout/:orderId" element={<PayoutPage onUpdated={handleUpdated} />} />
          <Route path="/orders" element={<OrdersPage orders={orders} onRefresh={refreshOrders} />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
