import { useState, useEffect } from "react";
import { api } from "../api";

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [chainStatus, setChainStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    Promise.all([api.getAuditLog(60), api.verifyAuditChain()])
      .then(([logData, verifyData]) => {
        if (!ignore) {
          setLogs(logData);
          setChainStatus(verifyData);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Failed to load audit records.");
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  async function handleVerifyChain() {
    setVerifying(true);
    try {
      const verifyData = await api.verifyAuditChain();
      setChainStatus(verifyData);
    } catch (err) {
      setError(err.message || "Cryptographic verification check failed.");
    } finally {
      setVerifying(false);
    }
  }

  const stageCounts = logs.reduce((acc, log) => {
    acc[log.stage] = (acc[log.stage] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="bk-admin-page">
      <div className="bk-page-header">
        <div>
          <span className="bk-section-tag">Regulatory Compliance</span>
          <h1 className="bk-page-title">Tamper-Evident Audit Ledger</h1>
          <p className="bk-page-desc">
            Immutable, SHA-256 hash-chained log recording every pipeline classification, retrieval,
            synthesis, and verification event.
          </p>
        </div>

        <div className="bk-chain-control-group">
          {chainStatus && (
            <div
              className={`bk-chain-status-indicator ${
                chainStatus.intact ? "intact" : "compromised"
              }`}
            >
              <span className="bk-chain-status-dot"></span>
              <span className="bk-chain-status-label">
                {chainStatus.intact ? "Hash Chain Intact" : "Chain Integrity Breach"}
              </span>
            </div>
          )}
          <button
            type="button"
            className="bk-btn-secondary"
            onClick={handleVerifyChain}
            disabled={verifying}
          >
            {verifying ? "Verifying SHA-256 Chain…" : "Verify Chain Now"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bk-alert-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {/* Stage Distribution Counters */}
      <section className="bk-audit-stats-grid" aria-label="Event Distribution">
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Total Logged Records</span>
          <span className="bk-audit-stat-val tabular-nums">{logs.length}</span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Agent 1: Classification</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.classification || 0}
          </span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Agent 2: Retrieval</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.retrieval || 0}
          </span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Agent 3: Synthesis</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.generation || 0}
          </span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Agent 4: Verification</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.verification || 0}
          </span>
        </div>
      </section>

      {/* Audit Chain Table */}
      <section className="bk-table-card">
        <div className="bk-table-container">
          <table className="bk-data-table">
            <thead>
              <tr>
                <th scope="col">Timestamp</th>
                <th scope="col">Pipeline Stage</th>
                <th scope="col">Agent Responsible</th>
                <th scope="col">Decision Summary</th>
                <th scope="col">Session Token</th>
                <th scope="col">Cryptographic Hash</th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                logs.map((log) => (
                  <tr key={log.id}>
                    <td>
                      <span className="bk-date-text tabular-nums">
                        {new Date(log.timestamp).toLocaleString("en-GB", {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                          day: "2-digit",
                          month: "short",
                        })}
                      </span>
                    </td>
                    <td>
                      <span className="bk-stage-pill">{log.stage.replace("_", " ")}</span>
                    </td>
                    <td>
                      <span className="bk-agent-name">{log.agent}</span>
                    </td>
                    <td>
                      <div className="bk-log-summary">{log.decision_summary}</div>
                    </td>
                    <td>
                      <code className="bk-token-mono tabular-nums">
                        {log.session_id ? log.session_id.slice(0, 8) + "…" : "—"}
                      </code>
                    </td>
                    <td>
                      <code className="bk-hash-mono tabular-nums" title={log.immutable_hash}>
                        {log.immutable_hash ? log.immutable_hash.slice(0, 14) + "…" : "—"}
                      </code>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {loading && (
            <div className="bk-table-loading">
              <span>Reading cryptographic ledger blocks…</span>
            </div>
          )}

          {!loading && logs.length === 0 && (
            <div className="bk-empty-table-state">
              <h3>Audit Ledger Empty</h3>
              <p>No transactions have been recorded in the persistent audit database yet.</p>
            </div>
          )}
        </div>
      </section>

      {/* Integrity Assessment Callout */}
      {chainStatus && (
        <section
          className={`bk-chain-integrity-panel ${
            chainStatus.intact ? "intact" : "compromised"
          }`}
        >
          <div className="bk-integrity-header">
            <h3>
              {chainStatus.intact
                ? "Cryptographic Verification Confirmed: Ledger Unmodified"
                : "Cryptographic Verification Alert: Chain Modification Detected"}
            </h3>
          </div>
          <p className="bk-integrity-desc">
            {chainStatus.intact
              ? "Every pipeline record contains a SHA-256 payload digest combined with the previous record's hash. The entire chain validates without any missing or re-ordered blocks."
              : `Integrity check failed: ${
                  chainStatus.broken_records?.length || "One or more"
                } record(s) violate sequential hash continuity. Immediate security audit required.`}
          </p>
        </section>
      )}
    </div>
  );
}
