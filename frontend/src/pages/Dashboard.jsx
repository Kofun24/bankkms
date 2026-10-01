import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [auditLog, setAuditLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    Promise.all([api.getDashboardStats(), api.listDocuments(false)])
      .then(([statsData, docsData]) => {
        if (!ignore) {
          setStats(statsData);
          setDocuments(docsData.slice(0, 5));
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Failed to load dashboard statistics.");
          setLoading(false);
        }
      });

    api
      .getAuditLog(5)
      .then((logData) => {
        if (!ignore) setAuditLog(logData);
      })
      .catch(() => {
        if (!ignore) setAuditLog([]);
      });

    return () => {
      ignore = true;
    };
  }, []);

  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="bk-admin-page">
      {/* Header bar */}
      <div className="bk-page-header">
        <div>
          <span className="bk-section-tag">Governance Overview</span>
          <h1 className="bk-page-title">Operations &amp; System Health</h1>
          <p className="bk-page-desc">
            Operational status of BankKMS accounts, knowledge documents, and verification integrity.
          </p>
        </div>
        <div className="bk-date-badge tabular-nums">
          <span className="bk-date-label">Audit Cycle Date</span>
          <span className="bk-date-value">{today}</span>
        </div>
      </div>

      {error && (
        <div className="bk-alert-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {/* Primary Metrics Grid */}
      <section className="bk-metrics-grid" aria-label="System Metrics">
        <div className="bk-metric-card">
          <div className="bk-metric-meta">
            <span className="bk-metric-label">Registered Accounts</span>
            <span className="bk-metric-tag">Identity</span>
          </div>
          <div className="bk-metric-value tabular-nums">
            {stats ? stats.total_employees : loading ? "…" : "0"}
          </div>
          <p className="bk-metric-sub">Employee, Compliance &amp; Admin accounts</p>
        </div>

        <div className="bk-metric-card">
          <div className="bk-metric-meta">
            <span className="bk-metric-label">Active Users</span>
            <span className="bk-metric-tag">Authorization</span>
          </div>
          <div className="bk-metric-value tabular-nums">
            {stats ? stats.active_employees : loading ? "…" : "0"}
          </div>
          <p className="bk-metric-sub">
            {stats && stats.total_employees > 0
              ? `${Math.round((stats.active_employees / stats.total_employees) * 100)}% active account ratio`
              : "Active session authorization"}
          </p>
        </div>

        <div className="bk-metric-card">
          <div className="bk-metric-meta">
            <span className="bk-metric-label">Approved Documents</span>
            <span className="bk-metric-tag">Knowledge</span>
          </div>
          <div className="bk-metric-value tabular-nums">
            {stats ? stats.total_documents : loading ? "…" : "0"}
          </div>
          <p className="bk-metric-sub">Approved policies in knowledge base</p>
        </div>

        <div className="bk-metric-card">
          <div className="bk-metric-meta">
            <span className="bk-metric-label">Restricted Policies</span>
            <span className="bk-metric-tag">Compliance Tier</span>
          </div>
          <div className="bk-metric-value tabular-nums">
            {stats ? stats.restricted_documents : loading ? "…" : "0"}
          </div>
          <p className="bk-metric-sub">Confidential AML and audit documents</p>
        </div>
      </section>

      {/* Split Activity & Knowledge Panes */}
      <div className="bk-admin-grid-2">
        {/* Document Registry Quick Look */}
        <section className="bk-panel">
          <div className="bk-panel-header">
            <div>
              <h2 className="bk-panel-title">Document Registry Preview</h2>
              <span className="bk-panel-sub">Recent policies active in knowledge retrieval</span>
            </div>
            <Link to="/admin/documents" className="bk-link-subtle">
              Manage All Documents
            </Link>
          </div>

          <div className="bk-panel-body">
            {documents.length > 0 ? (
              <div className="bk-dense-list">
                {documents.map((doc) => (
                  <div key={doc.id} className="bk-dense-row">
                    <div className="bk-dense-col-main">
                      <strong className="bk-doc-title">{doc.title}</strong>
                      <span className="bk-doc-version tabular-nums">Version: {doc.version}</span>
                    </div>
                    <div className="bk-dense-col-badges">
                      <span className={`bk-tier-pill ${doc.access_level.toLowerCase()}`}>
                        {doc.access_level}
                      </span>
                      <span
                        className={`bk-status-indicator-tag ${
                          doc.is_current ? "current" : "retired"
                        }`}
                      >
                        {doc.is_current ? "Current" : "Retired"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bk-empty-state-compact">
                <p>No documents registered yet in the system database.</p>
                <Link to="/admin/documents" className="bk-btn-secondary">
                  Register First Document
                </Link>
              </div>
            )}
          </div>
        </section>

        {/* Audit Chain Event Highlights */}
        <section className="bk-panel">
          <div className="bk-panel-header">
            <div>
              <h2 className="bk-panel-title">Recent Audit Log Transactions</h2>
              <span className="bk-panel-sub">Cryptographically hashed verification events</span>
            </div>
            <Link to="/admin/audit" className="bk-link-subtle">
              Inspect Audit Log
            </Link>
          </div>

          <div className="bk-panel-body">
            {auditLog.length > 0 ? (
              <div className="bk-audit-event-list">
                {auditLog.map((entry) => (
                  <div key={entry.id} className="bk-audit-event-item">
                    <div className="bk-event-header">
                      <span className="bk-stage-tag">{entry.stage.replace("_", " ")}</span>
                      <time className="bk-event-time tabular-nums">
                        {new Date(entry.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </time>
                    </div>
                    <div className="bk-event-summary">{entry.decision_summary}</div>
                    <div className="bk-event-hash-row">
                      <span className="bk-hash-label">Hash:</span>
                      <span className="bk-hash-value tabular-nums">
                        {entry.immutable_hash ? entry.immutable_hash.slice(0, 16) + "…" : "—"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bk-empty-state-compact">
                <p>No audit records recorded in the current session log.</p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Core Architectural Principle Banner */}
      <section className="bk-governance-summary-banner">
        <div className="bk-gov-banner-badge">Core System Axiom</div>
        <div className="bk-gov-banner-body">
          <h3>Every answer is grounded in an approved source document or refused.</h3>
          <p>
            BankKMS does not generate speculative knowledge. Access is verified twice (at initial
            vector retrieval and final response verification), and every system decision is sealed
            in the immutable hash chain.
          </p>
        </div>
      </section>
    </div>
  );
}
