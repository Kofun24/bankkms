import { useState, useEffect } from "react";
import { api } from "../api";

export default function Documents() {
  const [documents, setDocuments] = useState([]);
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL"); // ALL, CURRENT, RETIRED
  const [showAddModal, setShowAddModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Add document modal state
  const [newTitle, setNewTitle] = useState("");
  const [newAccess, setNewAccess] = useState("public");
  const [newVersion, setNewVersion] = useState("v1.0");
  const [newEffectiveDate, setNewEffectiveDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState("");

  // Retiring state
  const [retireConfirm, setRetireConfirm] = useState(null);
  const [retireLoading, setRetireLoading] = useState(false);

  async function loadDocuments() {
    setLoading(true);
    try {
      const data = await api.listDocuments(false);
      setDocuments(data);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load document registry.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    api
      .listDocuments(false)
      .then((data) => {
        if (!ignore) {
          setDocuments(data);
          setError("");
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Failed to load document registry.");
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  const filtered = documents.filter((doc) => {
    const matchSearch = doc.title.toLowerCase().includes(search.toLowerCase());
    const matchTier = tierFilter === "ALL" || doc.access_level.toUpperCase() === tierFilter;
    const matchStatus =
      statusFilter === "ALL" ||
      (statusFilter === "CURRENT" && doc.is_current) ||
      (statusFilter === "RETIRED" && !doc.is_current);
    return matchSearch && matchTier && matchStatus;
  });

  async function handleAddDocument(e) {
    e.preventDefault();
    setAddError("");
    setAddLoading(true);

    try {
      await api.addDocument({
        title: newTitle.trim(),
        access_level: newAccess,
        version: newVersion.trim(),
        effective_date: newEffectiveDate,
      });
      setShowAddModal(false);
      setNewTitle("");
      setNewAccess("public");
      setNewVersion("v1.0");
      loadDocuments();
    } catch (err) {
      setAddError(err.message || "Failed to add document metadata.");
    } finally {
      setAddLoading(false);
    }
  }

  async function handleRetire(docId) {
    setRetireLoading(true);
    try {
      await api.retireDocument(docId);
      setRetireConfirm(null);
      loadDocuments();
    } catch (err) {
      setError(err.message || "Failed to retire document.");
    } finally {
      setRetireLoading(false);
    }
  }

  return (
    <div className="bk-admin-page">
      <div className="bk-page-header">
        <div>
          <span className="bk-section-tag">Knowledge Governance</span>
          <h1 className="bk-page-title">Document Metadata Registry</h1>
          <p className="bk-page-desc">
            Define approved documentation metadata, access boundaries, and revision lifecycle.
            Retrieval agents only query active versions.
          </p>
        </div>
        <button
          type="button"
          className="bk-btn-primary"
          onClick={() => setShowAddModal(true)}
        >
          Register Document
        </button>
      </div>

      {error && (
        <div className="bk-alert-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {/* Toolbar with Tier & Status Filter Controls */}
      <div className="bk-toolbar">
        <div className="bk-search-box">
          <input
            className="bk-search-input"
            type="text"
            placeholder="Search by document title (e.g. Savings Guide, AML Procedure)…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="bk-filter-row">
          <div className="bk-filter-group" role="group" aria-label="Access Tier Filters">
            {["ALL", "PUBLIC", "INTERNAL", "RESTRICTED"].map((t) => (
              <button
                key={t}
                type="button"
                className={`bk-filter-btn ${tierFilter === t ? "active" : ""}`}
                onClick={() => setTierFilter(t)}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="bk-filter-group" role="group" aria-label="Status Filters">
            {["ALL", "CURRENT", "RETIRED"].map((s) => (
              <button
                key={s}
                type="button"
                className={`bk-filter-btn ${statusFilter === s ? "active" : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Document Table */}
      <section className="bk-table-card">
        <div className="bk-table-container">
          <table className="bk-data-table">
            <thead>
              <tr>
                <th scope="col">Document Title</th>
                <th scope="col">Version</th>
                <th scope="col">Access Tier</th>
                <th scope="col">Effective Date</th>
                <th scope="col">Lifecycle Status</th>
                <th scope="col" className="text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                filtered.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <div className="bk-doc-cell">
                        <strong className="bk-doc-cell-title">{doc.title}</strong>
                        {doc.id && <span className="bk-doc-cell-id tabular-nums">{doc.id}</span>}
                      </div>
                    </td>
                    <td>
                      <span className="bk-version-badge tabular-nums">{doc.version}</span>
                    </td>
                    <td>
                      <span className={`bk-tier-pill ${doc.access_level.toLowerCase()}`}>
                        {doc.access_level}
                      </span>
                    </td>
                    <td>
                      <span className="bk-date-text tabular-nums">{doc.effective_date}</span>
                    </td>
                    <td>
                      <span
                        className={`bk-lifecycle-badge ${doc.is_current ? "current" : "retired"}`}
                      >
                        {doc.is_current ? "Current" : "Retired"}
                      </span>
                    </td>
                    <td className="text-right">
                      {doc.is_current ? (
                        <button
                          type="button"
                          className="bk-btn-table destructive"
                          onClick={() => setRetireConfirm(doc)}
                        >
                          Retire Document
                        </button>
                      ) : (
                        <span className="bk-retired-label">Superseded</span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {loading && (
            <div className="bk-table-loading">
              <span>Scanning document catalog…</span>
            </div>
          )}

          {/* Deliberate Empty State */}
          {!loading && filtered.length === 0 && (
            <div className="bk-empty-table-state invitation">
              <div className="bk-invitation-badge">Registry Empty</div>
              <h3>
                {documents.length === 0
                  ? "No Knowledge Documents Registered"
                  : "No Documents Match Filter"}
              </h3>
              <p>
                {documents.length === 0
                  ? "The BankKMS knowledge base currently has no active policies. Register approved documents (such as Savings Account Guide, AML Procedure, or KYC Requirements) to enable retrieval."
                  : `No policies match the selected filters (Tier: ${tierFilter}, Status: ${statusFilter}${
                      search ? `, Search: "${search}"` : ""
                    }).`}
              </p>
              <div className="bk-empty-actions">
                <button
                  type="button"
                  className="bk-btn-primary"
                  onClick={() => setShowAddModal(true)}
                >
                  Register New Document
                </button>
                {documents.length > 0 && (
                  <button
                    type="button"
                    className="bk-btn-secondary"
                    onClick={() => {
                      setSearch("");
                      setTierFilter("ALL");
                      setStatusFilter("ALL");
                    }}
                  >
                    Clear Filter Criteria
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Register Document Modal */}
      {showAddModal && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card">
            <header className="bk-modal-header">
              <h2>Register Document Metadata</h2>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setShowAddModal(false)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <form onSubmit={handleAddDocument} className="bk-form">
              <div className="bk-field-group">
                <label htmlFor="doc-title-input" className="bk-label">
                  Document Title
                </label>
                <input
                  id="doc-title-input"
                  className="bk-input"
                  type="text"
                  placeholder="e.g. Savings Account Product Guide, AML Procedure, KYC Requirements"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div className="bk-field-group">
                <label htmlFor="doc-tier-select" className="bk-label">
                  Access Classification Tier
                </label>
                <select
                  id="doc-tier-select"
                  className="bk-select"
                  value={newAccess}
                  onChange={(e) => setNewAccess(e.target.value)}
                >
                  <option value="public">Public (Available to Customers, Staff, Compliance)</option>
                  <option value="internal">Internal (Available to Employees &amp; Compliance)</option>
                  <option value="restricted">Restricted (Strict Compliance &amp; Audit Scope Only)</option>
                </select>
                <span className="bk-field-help">
                  Enforces retrieval boundaries. Queries below this access level cannot retrieve
                  sections from this document.
                </span>
              </div>

              <div className="bk-grid-2">
                <div className="bk-field-group">
                  <label htmlFor="doc-version-input" className="bk-label">
                    Version Number
                  </label>
                  <input
                    id="doc-version-input"
                    className="bk-input"
                    type="text"
                    placeholder="e.g. v1.0 or v2.1"
                    value={newVersion}
                    onChange={(e) => setNewVersion(e.target.value)}
                    required
                  />
                </div>

                <div className="bk-field-group">
                  <label htmlFor="doc-date-input" className="bk-label">
                    Effective Date
                  </label>
                  <input
                    id="doc-date-input"
                    className="bk-input"
                    type="date"
                    value={newEffectiveDate}
                    onChange={(e) => setNewEffectiveDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              {addError && (
                <div className="bk-alert-banner" role="alert">
                  <span>{addError}</span>
                </div>
              )}

              <footer className="bk-modal-footer">
                <button
                  type="button"
                  className="bk-btn-secondary"
                  onClick={() => setShowAddModal(false)}
                  disabled={addLoading}
                >
                  Cancel
                </button>
                <button type="submit" className="bk-btn-primary" disabled={addLoading}>
                  {addLoading ? "Saving Metadata…" : "Register Document"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* Retire Document Confirmation Modal */}
      {retireConfirm && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card">
            <header className="bk-modal-header">
              <h2>Retire Document: {retireConfirm.title}</h2>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setRetireConfirm(null)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <div className="bk-modal-body">
              <p>
                Retiring <strong>{retireConfirm.title}</strong> ({retireConfirm.version}) will flag
                it as superseded in the metadata store.
              </p>
              <p className="bk-modal-warning-text">
                Active retrieval passes will no longer surface sections from this version,
                preventing outdated policy guidance from reaching customers or staff.
              </p>
            </div>

            <footer className="bk-modal-footer">
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => setRetireConfirm(null)}
                disabled={retireLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="bk-btn-primary destructive"
                onClick={() => handleRetire(retireConfirm.id)}
                disabled={retireLoading}
              >
                {retireLoading ? "Retiring…" : "Confirm Retirement"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}