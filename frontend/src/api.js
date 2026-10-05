const API_BASE = "http://localhost:8000/api";

function getToken() {
  return localStorage.getItem("bankkms_session");
}

async function publicRequest(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

// Separate from request() because file upload needs multipart/form-data,
// and the browser must set that Content-Type header itself (with the
// correct boundary) — setting it manually here would break the upload.
async function uploadRequest(path, formData) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  login: (username, password) =>
    request("/login", { method: "POST", body: JSON.stringify({ username, password }) }),

  logout: () => request("/logout", { method: "POST" }),

  listEmployees: () => request("/employees"),

  addEmployee: (username, password, role) =>
    request("/employees", { method: "POST", body: JSON.stringify({ username, password, role }) }),

  deactivateEmployee: (username) =>
    request(`/employees/${encodeURIComponent(username)}/deactivate`, { method: "POST" }),

  reactivateEmployee: (username) =>
    request(`/employees/${encodeURIComponent(username)}/reactivate`, { method: "POST" }),

  promoteEmployee: (username) =>
    request(`/employees/${encodeURIComponent(username)}/promote`, { method: "POST" }),

  changeRole: (username, newRole) =>
    request(`/employees/${encodeURIComponent(username)}/change-role`, {
      method: "POST",
      body: JSON.stringify({ new_role: newRole }),
    }),

  listDocuments: (currentOnly = false) =>
    request(`/documents?current_only=${currentOnly}`),

  // Takes a raw File object (from <input type="file"> or drag-and-drop).
  // All metadata is read server-side from the file's own frontmatter.
  addDocument: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return uploadRequest("/documents", formData);
  },

  retireDocument: (docId) =>
    request(`/documents/${encodeURIComponent(docId)}/retire`, { method: "POST" }),

  getAuditLog: (limit = 50) => request(`/audit-log?limit=${limit}`),

  verifyAuditChain: () => request("/audit-log/verify"),

  getDashboardStats: () => request("/dashboard-stats"),

  startChatSession: () => publicRequest("/chat/new-session", { method: "POST" }),

  sendChatMessage: (sessionId, message) =>
    publicRequest("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),

  staffLogin: (username, password) =>
    publicRequest("/staff/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  staffLogout: (sessionId) =>
    publicRequest("/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${sessionId}` },
    }),

  sendStaffChatMessage: (sessionId, message) =>
    publicRequest("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),
};