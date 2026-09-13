import { Link } from "react-router-dom";

export default function Header({ orderCount, currentPath }) {
  const isActive = (path) => {
    if (path === "/") return currentPath === "/";
    return currentPath.startsWith(path);
  };

  return (
    <nav className="nav-bar">
      <div className="nav-inner">
        <Link to="/" className="nav-logo">
          <span className="logo-icon">📦</span>
          FleetAgent
        </Link>
        <div className="nav-links">
          <Link to="/" className={`nav-link ${isActive("/") ? "active" : ""}`}>Home</Link>
          <Link to="/order" className={`nav-link ${isActive("/order") ? "active" : ""}`}>New Order</Link>
          <Link to="/orders" className={`nav-link ${isActive("/orders") ? "active" : ""}`}>
            Orders
            {orderCount > 0 && <span className="nav-badge">{orderCount}</span>}
          </Link>
        </div>
      </div>
    </nav>
  );
}
