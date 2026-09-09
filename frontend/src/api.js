const API_BASE = "http://localhost:8000/api";

function getToken() {
  return localStorage.getItem("bankkms_session");
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

  listDocuments: (currentOnly = false) =>
    request(`/documents?current_only=${currentOnly}`),

  addDocument: (doc) =>
    request("/documents", { method: "POST", body: JSON.stringify(doc) }),

  retireDocument: (docId) =>
    request(`/documents/${encodeURIComponent(docId)}/retire`, { method: "POST" }),

    getAuditLog: (limit = 50) => request(`/audit-log?limit=${limit}`),

  verifyAuditChain: () => request("/audit-log/verify"),

  getDashboardStats: () => request("/dashboard-stats"),
};