/**
 * Animated step card — fades/slides in from the left after `delay` ms.
 * Shows an icon, title, and children content. A green check appears when
 * `complete` is true.
 */
export default function StepCard({ icon, title, delay = 0, complete = false, children }) {
  return (
    <div
      className={`step-card ${complete ? "done" : ""}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="step-card-header">
        <span className="step-card-icon">{icon}</span>
        <span className="step-card-title">{title}</span>
        {complete && <span className="step-card-check">✓</span>}
      </div>
      <div className="step-card-body">{children}</div>
    </div>
  );
}
