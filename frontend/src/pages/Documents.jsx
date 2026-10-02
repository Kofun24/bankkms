import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function Documents() {
  const [documents, setDocuments] = useState([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDocuments() {
    setLoading(true);
    try {
      const data = await api.listDocuments(false);
      setDocuments(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, []);

  const filtered = documents.filter((doc) => {
    const matchesSearch = doc.title.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = filter === "ALL" || doc.access_level.toUpperCase() === filter;
    return matchesSearch && matchesFilter;
  });

  const retire = async (docId) => {
    try {
      await api.retireDocument(docId);
      loadDocuments();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">KNOWLEDGE GOVERNANCE</span>
          <h1>Document registry</h1>
          <p>Control the approved knowledge available to BankKMS.</p>
        </div>
        <button className="primary-button" onClick={() => setShowModal(true)}>
          + Add document
        </button>
      </div>

      {error && <div className="login-error"><span>!</span>{error}</div>}

      <div className="toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="filter-group">
          {["ALL", "PUBLIC", "INTERNAL", "RESTRICTED"].map((item) => (
            <button
              key={item}
              className={filter === item ? "filter-button selected" : "filter-button"}
              onClick={() => setFilter(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>DOCUMENT</th>
              <th>VERSION</th>
              <th>ACCESS LEVEL</th>
              <th>STATUS</th>
              <th>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {!loading &&
              filtered.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div className="document-cell">
                      <div className="document-table-icon">▤</div>
                      <div>
                        <strong>{doc.title}</strong>
                        <span>{doc.doc_id}</span>
                      </div>
                    </div>
                  </td>
                  <td className="version-cell">{doc.version}</td>
                  <td>
                    <span className={`access-badge large ${doc.access_level}`}>
                      {doc.access_level.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    <span className={`status ${doc.is_current ? "current" : "retired"}`}>
                      {doc.is_current ? "● CURRENT" : "○ RETIRED"}
                    </span>
                  </td>
                  <td>
                    {doc.is_current && (
                      <button className="table-action danger" onClick={() => retire(doc.doc_id)}>
                        Retire
                      </button>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {loading && <p style={{ padding: 20 }}>Loading...</p>}
        {!loading && filtered.length === 0 && (
          <p style={{ padding: 20, color: "var(--muted)" }}>No documents found.</p>
        )}
      </div>

      <div className="document-note">
        <div className="note-symbol">i</div>
        <div>
          <strong>Knowledge governance matters.</strong>
          <p>
            Only current documents are used as approved knowledge sources.
            Retired versions remain available for audit purposes but are
            excluded from answers.
          </p>
        </div>
      </div>

      {showModal && (
        <AddDocumentModal
          close={() => setShowModal(false)}
          onAdded={() => {
            setShowModal(false);
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
      setError("Select or drop a document file.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await api.addDocument(selectedFile);
      if (result.status === "created_metadata_only") {
        setError(
          `Document registered but not yet searchable: ${result.warning || "indexing failed"}`
        );
        return;
      }
      onAdded();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <div>
            <span className="eyebrow">KNOWLEDGE SOURCE</span>
            <h2>Add document</h2>
          </div>
          <button className="close-button" onClick={close}>×</button>
        </div>

        <form onSubmit={submit}>
          <div
            className={`dropzone ${isDragging ? "dragging" : ""} ${selectedFile ? "has-file" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.txt"
              style={{ display: "none" }}
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            {selectedFile ? (
              <>
                <div className="dropzone-file-icon">▤</div>
                <strong>{selectedFile.name}</strong>
                <span>Click to choose a different file</span>
              </>
            ) : (
              <>
                <div className="upload-icon">↑</div>
                <strong>Drop a document here, or click to browse</strong>
                <span>Markdown (.md) with YAML frontmatter</span>
              </>
            )}
          </div>

          <p className="dropzone-path-note">
            Document ID, title, access level, version, and effective date
            are all read automatically from the file's own frontmatter —
            the file is routed to the correct knowledge_base folder and
            indexed for search immediately after upload.
          </p>

          {error && <div className="login-error"><span>!</span>{error}</div>}

          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={close} disabled={submitting}>
              Cancel
            </button>
            <button className="primary-button" disabled={submitting}>
              {submitting ? "Uploading..." : "Add document"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}