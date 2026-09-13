import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="landing">
      {/* Hero */}
      <section className="hero">
        <h1><span className="hero-accent">FleetAgent</span></h1>
        <p className="hero-sub">
          An AI agent that takes a delivery order, compares live fleet pricing,
          books the best option, holds payment through Razorpay, and
          self-recovers on RTO — with no human in the loop.
        </p>
        <div className="hero-cta">
          <Link to="/order" className="btn btn-primary btn-lg">Create Order →</Link>
          <Link to="/orders" className="btn btn-outline btn-lg">View Orders</Link>
        </div>
      </section>

      {/* Problem / Solution */}
      <h2 className="section-title">The Problem → The Solution</h2>
      <div className="problem-solution">
        <div className="ps-card problem">
          <h3>✗ Without FleetAgent</h3>
          <ul>
            <li>Check prices across multiple courier apps by hand</li>
            <li>Book one fleet manually, reconcile payment separately</li>
            <li>When delivery fails (RTO), the entire cycle repeats manually</li>
            <li>RTO accounts for significant margin loss during peak periods</li>
          </ul>
        </div>
        <div className="ps-card solution">
          <h3>✓ With FleetAgent</h3>
          <ul>
            <li>Agent fetches live quotes from WareIQ, NimbusPost, Borzo, Porter</li>
            <li>AI picks best fleet by cost + time efficiency, holds payment instantly</li>
            <li>Delivered → payment released to fleet automatically</li>
            <li>RTO → payment refunded, agent reroutes and retries — no human needed</li>
          </ul>
        </div>
      </div>

      {/* 3-step flow */}
      <h2 className="section-title">How It Works</h2>
      <div className="flow-diagram">
        <div className="flow-step">
          <div className="flow-icon">🔍</div>
          <h4>Fetch Quotes</h4>
          <p>Agent scrapes live fleet pricing across multiple aggregators in parallel</p>
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-step">
          <div className="flow-icon">🤖</div>
          <h4>Select &amp; Book</h4>
          <p>AI picks the best cost+time balance, holds payment via Razorpay Orders API</p>
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-step">
          <div className="flow-icon">📦</div>
          <h4>Deliver or Recover</h4>
          <p>Payment released on delivery, refunded + rerouted on RTO — autonomously</p>
        </div>
      </div>

      {/* What's real */}
      <h2 className="section-title">What's Real vs Simulated</h2>
      <table className="real-table">
        <thead>
          <tr><th>Component</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr><td>Fleet quote fetching (WareIQ, NimbusPost, Borzo)</td><td><span className="badge-real">Real — live scraping</span></td></tr>
          <tr><td>AI fleet selection (Groq gpt-oss-20b)</td><td><span className="badge-real">Real — with composite-score fallback</span></td></tr>
          <tr><td>Payment hold &amp; refund (Razorpay)</td><td><span className="badge-real">Real — verifiable in dashboard</span></td></tr>
          <tr><td>Payout to fleet on delivery</td><td><span className="badge-dormant">Wired but dormant — needs RazorpayX</span></td></tr>
        </tbody>
      </table>

      {/* Fleet grid */}
      <h2 className="section-title">Fleet Partners</h2>
      <div className="fleet-grid">
        <div className="fleet-card"><div className="fleet-name">WareIQ</div><div className="fleet-desc">Multi-courier aggregator (long-haul)</div></div>
        <div className="fleet-card"><div className="fleet-name">NimbusPost</div><div className="fleet-desc">Multi-courier aggregator (long-haul)</div></div>
        <div className="fleet-card"><div className="fleet-name">Borzo</div><div className="fleet-desc">Intra-city 2-wheeler (same-day)</div></div>
        <div className="fleet-card"><div className="fleet-name">Porter</div><div className="fleet-desc">Intra-city 2-wheeler (same-day)</div></div>
        <div className="fleet-card"><div className="fleet-name">Delhivery</div><div className="fleet-desc">Long-haul (attempted integration)</div></div>
        <div className="fleet-card"><div className="fleet-name">Shiprocket</div><div className="fleet-desc">Long-haul (login-gated, documented gap)</div></div>
      </div>

      <div style={{ textAlign: "center", marginTop: "40px" }}>
        <Link to="/order" className="btn btn-primary btn-lg">Start Demo →</Link>
      </div>
    </div>
  );
}
