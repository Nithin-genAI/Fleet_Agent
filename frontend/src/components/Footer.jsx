export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-grid">
          <div className="footer-col">
            <h4>Fleet Partners</h4>
            <ul>
              <li className="fleet-item"><strong>WareIQ</strong><span>Multi-courier aggregator</span></li>
              <li className="fleet-item"><strong>NimbusPost</strong><span>Multi-courier aggregator</span></li>
              <li className="fleet-item"><strong>Borzo</strong><span>Intra-city 2-wheeler</span></li>
              <li className="fleet-item"><strong>Porter</strong><span>Intra-city 2-wheeler</span></li>
              <li className="fleet-item"><strong>Delhivery</strong><span>Long-haul (attempted)</span></li>
              <li className="fleet-item"><strong>Shiprocket</strong><span>Long-haul (login-gated)</span></li>
            </ul>
          </div>
          <div className="footer-col">
            <h4>Tech Stack</h4>
            <ul>
              <li>FastAPI + SQLAlchemy</li>
              <li>React + Vite</li>
              <li>Groq (gpt-oss-20b)</li>
              <li>Razorpay SDK</li>
              <li>Playwright (scraping)</li>
              <li>SQLite + Alembic</li>
            </ul>
          </div>
          <div className="footer-col">
            <h4>About</h4>
            <p>Autonomous delivery booking + agentic payments. An AI agent that takes a delivery order, compares live fleet pricing, books the best option, holds payment through Razorpay, and self-recovers on RTO — with no human in the loop.</p>
            <p>Built for the Razorpay Buildathon Open Track.</p>
          </div>
        </div>
        <div className="footer-bottom">
          Built by <strong>Nithin K</strong> &copy; 2026
        </div>
      </div>
    </footer>
  );
}
