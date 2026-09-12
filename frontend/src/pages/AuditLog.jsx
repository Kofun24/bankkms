import { useState, useEffect } from "react";
import { api } from "../api";

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [chainStatus, setChainStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [logData, verifyData] = await Promise.all([
        api.getAuditLog(50),
        api.verifyAuditChain(),
      ]);
      setLogs(logData);
      setChainStatus(verifyData);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const stageCounts = logs.reduce((acc, log) => {
    acc[log.stage] = (acc[log.stage] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">SECURITY & GOVERNANCE</span>
          <h1>Audit log</h1>
          <p>A tamper-evident record of activity across BankKMS.</p>
        </div>
        {chainStatus && (
          <div className="audit-status">
            <span>●</span>
            {chainStatus.intact ? "Chain intact" : "Tampering detected"}
          </div>
        )}
      </div>

      {error && (
        <div className="login-error">
          <span>!</span>
          {error}
        </div>
      )}

      <div className="audit-summary">
        <div>
          <span>TOTAL EVENTS</span>
          <strong>{logs.length}</strong>
        </div>
        <div>
          <span>CLASSIFICATIONS</span>
          <strong>{stageCounts.classification || 0}</strong>
        </div>
        <div>
          <span>RETRIEVALS</span>
          <strong>{stageCounts.retrieval || 0}</strong>
        </div>
        <div>
          <span>VERIFICATIONS</span>
          <strong>{stageCounts.verification || 0}</strong>
        </div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>TIMESTAMP</th>
              <th>SESSION</th>
              <th>STAGE</th>
              <th>AGENT</th>
              <th>SUMMARY</th>
            </tr>
          </thead>
          <tbody>
            {!loading &&
              logs.map((log) => (
                <tr key={log.id}>
                  <td className="timestamp">
                    {new Date(log.timestamp).toLocaleString()}
                  </td>
                  <td className="muted-cell">{log.session_id.slice(0, 12)}…</td>
                  <td>
                    <span
                      className="role-badge employee"
                      style={{ textTransform: "capitalize" }}
                    >
                      {log.stage}
                    </span>
                  </td>
                  <td className="muted-cell">{log.agent}</td>
                  <td>{log.decision_summary}</td>
                </tr>
              ))}
          </tbody>
        </table>
        {loading && <p style={{ padding: 20 }}>Loading...</p>}
        {!loading && logs.length === 0 && (
          <p style={{ padding: 20, color: "var(--muted)" }}>
            No audit records yet.
          </p>
        )}
      </div>

      {chainStatus && (
        <div
          className="audit-integrity"
          style={
            !chainStatus.intact
              ? { background: "var(--red-light)", borderColor: "#d9b8b3" }
              : {}
          }
        >
          <div
            className="integrity-icon"
            style={!chainStatus.intact ? { background: "var(--red)" } : {}}
          >
            {chainStatus.intact ? "✓" : "!"}
          </div>
          <div>
            <span className="eyebrow">LOG INTEGRITY</span>
            <h3>
              {chainStatus.intact
                ? "Audit records are protected from modification."
                : "Tampering has been detected in the audit chain."}
            </h3>
            <p>
              {chainStatus.intact
                ? "Every event is hash-chained, timestamped, and recorded for accountability and regulatory review."
                : `${chainStatus.broken_records.length} record(s) show signs of tampering. Review immediately.`}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
