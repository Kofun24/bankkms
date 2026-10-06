import { useState, useEffect } from "react";
import { api } from "../api";

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [chainStatus, setChainStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");

  // Filters & Search
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("ALL");
  const [inspectedEntry, setInspectedEntry] = useState(null);
  const [copiedField, setCopiedField] = useState(null);

  useEffect(() => {
    let ignore = false;
    Promise.all([api.getAuditLog(80), api.verifyAuditChain()])
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
    const s = log.stage?.toLowerCase();
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const filteredLogs = logs.filter((log) => {
    const term = search.toLowerCase();
    const matchesSearch =
      !term ||
      (log.decision_summary && log.decision_summary.toLowerCase().includes(term)) ||
      (log.agent && log.agent.toLowerCase().includes(term)) ||
      (log.session_id && log.session_id.toLowerCase().includes(term)) ||
      (log.immutable_hash && log.immutable_hash.toLowerCase().includes(term));

    const matchesStage =
      stageFilter === "ALL" || log.stage?.toLowerCase() === stageFilter.toLowerCase();

    return matchesSearch && matchesStage;
  });

  const copyToClipboard = (text, fieldName) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const formatStageLabel = (stage) => {
    if (!stage) return "Unknown";
    return stage
      .replace(/_/g, " ")
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(" ");
  };

  return (
    <div className="bk-admin-page">
      {/* Header bar */}
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
          <span className="bk-audit-stat-label">Total Records</span>
          <span className="bk-audit-stat-val tabular-nums">{logs.length}</span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Classification</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.classification || 0}
          </span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Retrieval</span>
          <span className="bk-audit-stat-val tabular-nums">{stageCounts.retrieval || 0}</span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Synthesis</span>
          <span className="bk-audit-stat-val tabular-nums">{stageCounts.generation || 0}</span>
        </div>
        <div className="bk-audit-stat-card">
          <span className="bk-audit-stat-label">Verification</span>
          <span className="bk-audit-stat-val tabular-nums">
            {stageCounts.verification || 0}
          </span>
        </div>
      </section>

      {/* Toolbar */}
      <div className="bk-toolbar">
        <div className="bk-search-box">
          <input
            className="bk-search-input"
            type="text"
            placeholder="Search by decision, agent, session, or hash…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="bk-filter-group" role="group" aria-label="Stage Filters">
          {[
            { id: "ALL", label: "All Events" },
            { id: "classification", label: "Classification" },
            { id: "retrieval", label: "Retrieval" },
            { id: "generation", label: "Synthesis" },
            { id: "verification", label: "Verification" },
          ].map((st) => (
            <button
              key={st.id}
              type="button"
              className={`bk-filter-btn ${stageFilter === st.id ? "active" : ""}`}
              onClick={() => setStageFilter(st.id)}
            >
              {st.label}
            </button>
          ))}
        </div>
      </div>

      {/* Audit Chain Table */}
      <section className="bk-table-card">
        <div className="bk-table-container">
          <table className="bk-data-table bk-audit-table">
            <thead>
              <tr>
                <th scope="col">Timestamp</th>
                <th scope="col">Pipeline Stage</th>
                <th scope="col">Responsible Agent</th>
                <th scope="col">Decision Summary</th>
                <th scope="col">Session Token</th>
                <th scope="col">Cryptographic Hash</th>
                <th scope="col" className="text-right">Details</th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    className="bk-clickable-row"
                    onClick={() => setInspectedEntry(log)}
                    title="Click to inspect complete audit block payload"
                  >
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
                      <span className="bk-stage-pill">{formatStageLabel(log.stage)}</span>
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
                      <code
                        className="bk-hash-mono tabular-nums"
                        title={log.immutable_hash || `Block #${log.id}`}
                      >
                        {log.immutable_hash
                          ? log.immutable_hash.slice(0, 14) + "…"
                          : `Block #${log.id}`}
                      </code>
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="bk-btn-table"
                        onClick={(e) => {
                          e.stopPropagation();
                          setInspectedEntry(log);
                        }}
                      >
                        Inspect
                      </button>
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

          {!loading && filteredLogs.length === 0 && (
            <div className="bk-empty-table-state">
              <h3>No Audit Records Found</h3>
              <p>
                No records match the current filter ({search ? `search: "${search}", ` : ""}
                stage: {stageFilter.toLowerCase()}).
              </p>
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => {
                  setSearch("");
                  setStageFilter("ALL");
                }}
              >
                Reset Filters
              </button>
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

      {/* Audit Block Inspection Modal */}
      {inspectedEntry && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card bk-modal-card-lg">
            <header className="bk-modal-header">
              <div>
                <span className="bk-section-tag">Audit Ledger Inspector</span>
                <h2>Record Block #{inspectedEntry.id}</h2>
              </div>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setInspectedEntry(null)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <div className="bk-modal-body">
              <div className="bk-ledger-detail-grid">
                <div className="bk-detail-field">
                  <span className="bk-detail-label">Timestamp</span>
                  <span className="bk-detail-val tabular-nums">
                    {new Date(inspectedEntry.timestamp).toISOString()}
                  </span>
                </div>

                <div className="bk-detail-field">
                  <span className="bk-detail-label">Pipeline Stage</span>
                  <span className="bk-stage-pill">
                    {formatStageLabel(inspectedEntry.stage)}
                  </span>
                </div>

                <div className="bk-detail-field">
                  <span className="bk-detail-label">Responsible Agent</span>
                  <span className="bk-detail-val">{inspectedEntry.agent}</span>
                </div>

                <div className="bk-detail-field">
                  <span className="bk-detail-label">Session Token</span>
                  <div className="bk-copyable-row">
                    <code className="bk-code-inline tabular-nums">
                      {inspectedEntry.session_id}
                    </code>
                    <button
                      type="button"
                      className="bk-copy-btn"
                      onClick={() => copyToClipboard(inspectedEntry.session_id, "session")}
                    >
                      {copiedField === "session" ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
              </div>

              <div className="bk-field-group" style={{ marginTop: 16 }}>
                <span className="bk-detail-label">Decision Summary</span>
                <div className="bk-callout-panel">
                  {inspectedEntry.decision_summary}
                </div>
              </div>

              <div className="bk-field-group" style={{ marginTop: 16 }}>
                <span className="bk-detail-label">SHA-256 Block Digest</span>
                <div className="bk-copyable-row">
                  <code className="bk-hash-box tabular-nums">
                    {inspectedEntry.immutable_hash || "Calculated sequentially in SQLite ledger"}
                  </code>
                  {inspectedEntry.immutable_hash && (
                    <button
                      type="button"
                      className="bk-copy-btn"
                      onClick={() => copyToClipboard(inspectedEntry.immutable_hash, "hash")}
                    >
                      {copiedField === "hash" ? "Copied" : "Copy"}
                    </button>
                  )}
                </div>
              </div>
            </div>

            <footer className="bk-modal-footer">
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => setInspectedEntry(null)}
              >
                Close Inspector
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
