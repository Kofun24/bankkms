import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [auditLog, setAuditLog] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [statsData, docsData] = await Promise.all([
          api.getDashboardStats(),
          api.listDocuments(false),
        ]);
        setStats(statsData);
        setDocuments(docsData.slice(0, 4));
      } catch (err) {
        setError(err.message);
      }

      try {
        const logData = await api.getAuditLog(4);
        setAuditLog(logData);
      } catch {
        setAuditLog([]);
      }
    }
    load();
  }, []);

  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  const [weekday, ...rest] = today.split(" ");

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">OVERVIEW</span>
          <h1>Operations overview</h1>
          <p>Monitor your institutional knowledge environment.</p>
        </div>
        <div className="date-display">
          <span>{weekday.toUpperCase().replace(",", "")}</span>
          <strong>{rest.join(" ").toUpperCase()}</strong>
        </div>
      </div>

      {error && <div className="login-error"><span>!</span>{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-top">
            <span>USERS</span>
            <span className="stat-symbol">♙</span>
          </div>
          <div className="stat-number">{stats ? stats.total_employees : "—"}</div>
          <div className="stat-description">Employee, compliance & admin accounts</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>ACTIVE</span>
            <span className="stat-symbol">✓</span>
          </div>
          <div className="stat-number">{stats ? stats.active_employees : "—"}</div>
          <div className="stat-description">
            {stats && stats.total_employees > 0
              ? `${Math.round((stats.active_employees / stats.total_employees) * 100)}% of all users`
              : "of all users"}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>DOCUMENTS</span>
            <span className="stat-symbol">▤</span>
          </div>
          <div className="stat-number">{stats ? stats.total_documents : "—"}</div>
          <div className="stat-description">Approved knowledge sources</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>RESTRICTED</span>
            <span className="stat-symbol">◈</span>
          </div>
          <div className="stat-number">{stats ? stats.restricted_documents : "—"}</div>
          <div className="stat-description">Compliance documents</div>
        </div>
      </div>

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">KNOWLEDGE BASE</span>
              <h2>Document registry</h2>
            </div>
            <Link to="/admin/documents" className="text-link">View all →</Link>
          </div>

          <div className="document-list">
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                name={doc.title}
                version={doc.version}
                access={doc.access_level.toUpperCase()}
                status={doc.is_current ? "CURRENT" : "RETIRED"}
              />
            ))}
            {documents.length === 0 && (
              <p style={{ padding: 20, color: "var(--muted)", fontSize: 12 }}>
                No documents yet.
              </p>
            )}
          </div>
        </section>

        <section className="panel activity-panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">SYSTEM ACTIVITY</span>
              <h2>Recent events</h2>
            </div>
            <Link to="/admin/audit" className="text-link">Audit log →</Link>
          </div>

          <div className="activity-list">
            {auditLog.map((entry) => (
              <Activity
                key={entry.id}
                title={entry.stage.replace("_", " ")}
                detail={entry.decision_summary}
                time={new Date(entry.timestamp).toLocaleString()}
              />
            ))}
            {auditLog.length === 0 && (
              <p style={{ padding: 20, color: "var(--muted)", fontSize: 12 }}>
                No activity recorded yet.
              </p>
            )}
          </div>
        </section>
      </div>

      <section className="principle-section">
        <div className="principle-number">01</div>
        <div>
          <span className="eyebrow">BANKKMS PRINCIPLE</span>
          <h2>
            Every answer begins with
            <em> approved knowledge.</em>
          </h2>
          <p>
            Documents determine what the system knows. Access levels
            determine who can see it. Administrators control both.
          </p>
        </div>
      </section>
    </div>
  );
}

function DocumentRow({ name, version, access, status }) {
  return (
    <div className="document-row">
      <div className="document-icon">▤</div>
      <div className="document-main">
        <strong>{name}</strong>
        <span>{version}</span>
      </div>
      <span className={`access-badge ${access.toLowerCase()}`}>{access}</span>
      <span className={`status ${status.toLowerCase()}`}>
        {status === "CURRENT" ? "●" : "○"} {status}
      </span>
    </div>
  );
}

function Activity({ title, detail, time }) {
  return (
    <div className="activity-item">
      <div className="activity-dot"></div>
      <div className="activity-content">
        <strong style={{ textTransform: "capitalize" }}>{title}</strong>
        <span>{detail.length > 60 ? detail.slice(0, 60) + "…" : detail}</span>
      </div>
      <time>{time}</time>
    </div>
  );
}