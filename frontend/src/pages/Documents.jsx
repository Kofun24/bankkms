import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function Documents() {
  const [documents, setDocuments] = useState([]);
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [showAddModal, setShowAddModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Retiring confirmation state
  const [retireConfirmDoc, setRetireConfirmDoc] = useState(null);
  const [retireLoading, setRetireLoading] = useState(false);
  const [retireError, setRetireError] = useState("");

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
    const term = search.toLowerCase();
    const matchesSearch =
      doc.title.toLowerCase().includes(term) ||
      (doc.doc_id && doc.doc_id.toLowerCase().includes(term));
    const matchesTier =
      tierFilter === "ALL" ||
      doc.access_level.toUpperCase() === tierFilter.toUpperCase();
    const matchesStatus =
      statusFilter === "ALL" ||
      (statusFilter === "CURRENT" && doc.is_current) ||
      (statusFilter === "RETIRED" && !doc.is_current);
    return matchesSearch && matchesTier && matchesStatus;
  });

  const promptRetire = (doc) => {
    setRetireError("");
    setRetireConfirmDoc(doc);
  };

  const handleConfirmRetire = async () => {
    if (!retireConfirmDoc) return;
    setRetireLoading(true);
    setRetireError("");
    try {
      await api.retireDocument(retireConfirmDoc.doc_id);
      setRetireConfirmDoc(null);
      loadDocuments();
    } catch (err) {
      setRetireError(err.message || "Failed to retire document.");
    } finally {
      setRetireLoading(false);
    }
  };

  return (
    <div className="bk-admin-page">
      {/* Header bar */}
      <div className="bk-page-header">
        <div>
          <span className="bk-section-tag">Knowledge Governance</span>
          <h1 className="bk-page-title">Document Registry</h1>
          <p className="bk-page-desc">
            Authorized repository of approved policies, regulatory charters, and operational guides.
          </p>
        </div>
        <button
          type="button"
          className="bk-btn-primary"
          onClick={() => setShowAddModal(true)}
        >
          Add Document
        </button>
      </div>

      {error && (
        <div className="bk-alert-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {/* Toolbar: Search and Filter Groups */}
      <div className="bk-toolbar">
        <div className="bk-search-box">
          <input
            className="bk-search-input"
            type="text"
            placeholder="Search documents by title or ID…"
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
                {t === "ALL"
                  ? "All Tiers"
                  : t === "PUBLIC"
                  ? "Public"
                  : t === "INTERNAL"
                  ? "Internal"
                  : "Restricted"}
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
                {s === "ALL" ? "All Statuses" : s === "CURRENT" ? "Current" : "Retired"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Document Ledger Table */}
      <section className="bk-table-card">
        <div className="bk-table-container">
          <table className="bk-data-table">
            <thead>
              <tr>
                <th scope="col">Document Policy &amp; ID</th>
                <th scope="col">Version</th>
                <th scope="col">Effective Date</th>
                <th scope="col">Access Tier</th>
                <th scope="col">Status</th>
                <th scope="col" className="text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                filtered.map((doc) => (
                  <tr key={doc.id || doc.doc_id}>
                    <td>
                      <div className="bk-doc-cell">
                        <strong className="bk-doc-cell-title">{doc.title}</strong>
                        <span className="bk-doc-cell-id tabular-nums">{doc.doc_id}</span>
                      </div>
                    </td>
                    <td>
                      <span className="bk-version-badge tabular-nums">{doc.version}</span>
                    </td>
                    <td>
                      <span className="bk-date-text tabular-nums">
                        {doc.effective_date || "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`bk-tier-pill ${doc.access_level.toLowerCase()}`}>
                        {doc.access_level === "public"
                          ? "Public"
                          : doc.access_level === "internal"
                          ? "Internal"
                          : doc.access_level === "restricted"
                          ? "Restricted"
                          : doc.access_level}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`bk-account-status ${
                          doc.is_current ? "active" : "inactive"
                        }`}
                      >
                        {doc.is_current ? "Current" : "Retired"}
                      </span>
                    </td>
                    <td className="text-right">
                      <div className="bk-action-btn-group">
                        {doc.is_current ? (
                          <button
                            type="button"
                            className="bk-btn-table destructive"
                            onClick={() => promptRetire(doc)}
                            title="Retire document from active pipeline retrieval"
                          >
                            Retire Policy
                          </button>
                        ) : (
                          <span className="bk-retired-label">Superseded</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {loading && (
            <div className="bk-table-loading">
              <span>Loading document repository…</span>
            </div>
          )}

          {!loading && filtered.length === 0 && (
            <div className="bk-empty-table-state">
              <h3>No Documents Found</h3>
              <p>
                No documents match your query ({search ? `search: "${search}", ` : ""}
                tier: {tierFilter.toLowerCase()}, status: {statusFilter.toLowerCase()}).
              </p>
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => {
                  setSearch("");
                  setTierFilter("ALL");
                  setStatusFilter("ALL");
                }}
              >
                Reset Filters
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Governance Explanation Card */}
      <section className="bk-governance-summary-banner">
        <div className="bk-gov-banner-badge">Knowledge Governance Axiom</div>
        <div className="bk-gov-banner-body">
          <h3>Only active documents are referenced in verified pipeline answers.</h3>
          <p>
            When policies are updated, superseded versions are flagged as retired. Retired
            documents remain preserved for cryptographic audit chain verification but are strictly
            excluded from customer and staff query retrieval.
          </p>
        </div>
      </section>

      {/* Retire Confirmation Modal */}
      {retireConfirmDoc && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card">
            <header className="bk-modal-header">
              <h2>Retire Knowledge Document</h2>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setRetireConfirmDoc(null)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <div className="bk-modal-body">
              <p>
                Are you sure you want to retire <strong>{retireConfirmDoc.title}</strong> (
                <code className="bk-code-inline tabular-nums">{retireConfirmDoc.doc_id}</code>)?
              </p>
              <p className="bk-field-help" style={{ marginTop: 8 }}>
                Once retired, this document will be excluded from all vector retrieval steps.
                Historical citations in the immutable audit ledger will remain intact.
              </p>

              {retireError && (
                <div className="bk-alert-banner" role="alert" style={{ marginTop: 12 }}>
                  <span>{retireError}</span>
                </div>
              )}
            </div>

            <footer className="bk-modal-footer">
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => setRetireConfirmDoc(null)}
                disabled={retireLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="bk-btn-primary destructive"
                onClick={handleConfirmRetire}
                disabled={retireLoading}
              >
                {retireLoading ? "Retiring Policy…" : "Confirm Retire"}
              </button>
            </footer>
          </div>
        </div>
      )}

      {/* Add Document Modal */}
      {showAddModal && (
        <AddDocumentModal
          close={() => setShowAddModal(false)}
          onAdded={() => {
            setShowAddModal(false);
            loadDocuments();
          }}
        />
      )}
    </div>
  );
}

function AddDocumentModal({ close, onAdded }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  function handleFile(file) {
    if (!file) return;
    if (!file.name.endsWith(".md") && !file.name.endsWith(".txt")) {
      setError("Please select a Markdown (.md) or Text (.txt) file.");
      return;
    }
    setSelectedFile(file);
    setError("");
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    handleFile(file);
  }

  const submit = async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Please select or drop a Markdown file to upload.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await api.addDocument(selectedFile);
      if (result.status === "created_metadata_only") {
        setError(
          `Document registered but indexing had warnings: ${result.warning || "Check vector service"}`
        );
        return;
      }
      onAdded();
    } catch (err) {
      setError(err.message || "Failed to upload and ingest document.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
      <div className="bk-modal-card bk-modal-card-lg">
        <header className="bk-modal-header">
          <div>
            <span className="bk-section-tag">Knowledge Ingestion</span>
            <h2>Register New Document</h2>
          </div>
          <button type="button" className="bk-modal-close" onClick={close} aria-label="Close dialog">
            ×
          </button>
        </header>

        <form onSubmit={submit}>
          <div className="bk-modal-body">
            {/* Dropzone area */}
            <div
              className={`bk-dropzone ${isDragging ? "active" : ""} ${
                selectedFile ? "has-file" : ""
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  fileInputRef.current?.click();
                }
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt"
                style={{ display: "none" }}
                onChange={(e) => handleFile(e.target.files?.[0])}
              />

              {selectedFile ? (
                <div className="bk-file-selected-box">
                  <div className="bk-file-icon">MD</div>
                  <div className="bk-file-info">
                    <strong className="bk-file-name">{selectedFile.name}</strong>
                    <span className="bk-file-size tabular-nums">
                      {(selectedFile.size / 1024).toFixed(1)} KB · Click to replace file
                    </span>
                  </div>
                  <button
                    type="button"
                    className="bk-file-remove-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                    }}
                    title="Remove file"
                  >
                    ×
                  </button>
                </div>
              ) : (
                <div className="bk-dropzone-content">
                  <div className="bk-dropzone-icon">
                    <span className="bk-upload-arrow">↑</span>
                  </div>
                  <strong className="bk-dropzone-title">
                    Drop Markdown document here, or browse files
                  </strong>
                  <span className="bk-dropzone-sub">
                    Accepts Markdown (.md) documents with YAML frontmatter
                  </span>
                </div>
              )}
            </div>

            {/* Frontmatter Guidance Callout */}
            <div className="bk-frontmatter-guidance">
              <strong className="bk-guidance-title">Frontmatter Specifications</strong>
              <p>
                Document ID, Title, Access Tier (<code className="bk-code-inline">public</code>,{" "}
                <code className="bk-code-inline">internal</code>, or{" "}
                <code className="bk-code-inline">restricted</code>), Version, and Effective Date are
                extracted automatically from the YAML frontmatter.
              </p>
              <pre className="bk-code-block">
{`---
doc_id: "doc_010"
title: "Retail Account Wire Transfer Procedures"
access_level: "internal"
version: "v1.0"
effective_date: "2026-10-01"
---`}
              </pre>
            </div>

            {error && (
              <div className="bk-alert-banner" role="alert" style={{ marginTop: 14 }}>
                <span>{error}</span>
              </div>
            )}
          </div>

          <footer className="bk-modal-footer">
            <button
              type="button"
              className="bk-btn-secondary"
              onClick={close}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bk-btn-primary"
              disabled={submitting || !selectedFile}
            >
              {submitting ? "Parsing & Ingesting…" : "Upload & Ingest Document"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}