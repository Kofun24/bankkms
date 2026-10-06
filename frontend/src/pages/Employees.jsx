import { useState, useEffect } from "react";
import { api } from "../api";

export default function Employees() {
  const [employees, setEmployees] = useState([]);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [showAddModal, setShowAddModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Confirmation state
  const [confirmAction, setConfirmAction] = useState(null);
  const [actionError, setActionError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  // New account form state
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("employee");
  const [addError, setAddError] = useState("");
  const [addLoading, setAddLoading] = useState(false);

  async function loadEmployees() {
    setLoading(true);
    try {
      const data = await api.listEmployees();
      setEmployees(data);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load employee directory.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    api
      .listEmployees()
      .then((data) => {
        if (!ignore) {
          setEmployees(data);
          setError("");
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Failed to load employee directory.");
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  const filtered = employees.filter((emp) => {
    const matchSearch = emp.username.toLowerCase().includes(search.toLowerCase());
    const matchRole =
      roleFilter === "ALL" || emp.role.toLowerCase() === roleFilter.toLowerCase();
    return matchSearch && matchRole;
  });

  async function handleAddEmployee(e) {
    e.preventDefault();
    setAddError("");
    setAddLoading(true);

    try {
      await api.addEmployee(newUsername.trim(), newPassword, newRole);
      setShowAddModal(false);
      setNewUsername("");
      setNewPassword("");
      setNewRole("employee");
      loadEmployees();
    } catch (err) {
      setAddError(err.message || "Failed to create user account.");
    } finally {
      setAddLoading(false);
    }
  }

  async function runConfirmedAction() {
    if (!confirmAction) return;
    setActionError("");
    setActionLoading(true);
    try {
      await confirmAction.run();
      setConfirmAction(null);
      loadEmployees();
    } catch (err) {
      setActionError(err.message || "Operation failed.");
    } finally {
      setActionLoading(false);
    }
  }

  const promptToggleActive = (emp) => {
    setActionError("");
    const willDeactivate = emp.is_active;
    setConfirmAction({
      title: willDeactivate ? "Deactivate User Account" : "Reactivate User Account",
      message: willDeactivate
        ? `Are you sure you want to deactivate ${emp.username}? They will immediately lose access to BankKMS sessions.`
        : `Reactivate ${emp.username}? They will regain login access according to their ${emp.role} role.`,
      confirmLabel: willDeactivate ? "Deactivate Account" : "Reactivate Account",
      isDestructive: willDeactivate,
      run: () =>
        willDeactivate
          ? api.deactivateEmployee(emp.username)
          : api.reactivateEmployee(emp.username),
    });
  };

  const promptPromoteAdmin = (emp) => {
    setActionError("");
    setConfirmAction({
      title: "Promote User to System Administrator",
      message: `${emp.username} will be granted full administrative privileges. In accordance with BankKMS separation-of-duties enforcement, they will lose knowledge-base query capabilities.`,
      confirmLabel: "Promote to Admin",
      isDestructive: false,
      run: () => api.promoteEmployee(emp.username),
    });
  };

  const promptChangeRole = (emp, targetRole) => {
    if (emp.role === targetRole) return;
    setActionError("");
    const targetLabel = targetRole === "compliance" ? "Compliance" : "Employee";
    setConfirmAction({
      title: `Change Account Role to ${targetLabel}`,
      message: `Modify ${emp.username}'s access from ${emp.role} to ${targetRole}. This alters their knowledge access tier to ${
        targetRole === "compliance" ? "Restricted" : "Internal"
      }.`,
      confirmLabel: "Apply Role Change",
      isDestructive: false,
      run: () => api.changeRole(emp.username, targetRole),
    });
  };

  const formatRoleName = (role) => {
    if (!role) return "";
    return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
  };

  return (
    <div className="bk-admin-page">
      <div className="bk-page-header">
        <div>
          <span className="bk-section-tag">Identity &amp; Access Management</span>
          <h1 className="bk-page-title">Employee &amp; Staff Accounts</h1>
          <p className="bk-page-desc">
            Manage user authorization, access tier roles, and administrative promotions across the
            institution.
          </p>
        </div>
        <button
          type="button"
          className="bk-btn-primary"
          onClick={() => setShowAddModal(true)}
        >
          Add Staff Account
        </button>
      </div>

      {error && (
        <div className="bk-alert-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bk-toolbar">
        <div className="bk-search-box">
          <input
            className="bk-search-input"
            type="text"
            placeholder="Search by username…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="bk-filter-group" role="group" aria-label="Role Filters">
          {[
            { id: "ALL", label: "All Roles" },
            { id: "employee", label: "Employee" },
            { id: "compliance", label: "Compliance" },
            { id: "admin", label: "Admin" },
          ].map((r) => (
            <button
              key={r.id}
              type="button"
              className={`bk-filter-btn ${roleFilter === r.id ? "active" : ""}`}
              onClick={() => setRoleFilter(r.id)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table Section */}
      <section className="bk-table-card">
        <div className="bk-table-container">
          <table className="bk-data-table">
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Assigned Role</th>
                <th scope="col">Knowledge Access Tier</th>
                <th scope="col">Status</th>
                <th scope="col" className="text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {!loading &&
                filtered.map((emp) => (
                  <tr key={emp.id || emp.username}>
                    <td>
                      <span className="bk-cell-username tabular-nums">{emp.username}</span>
                    </td>
                    <td>
                      <span className={`bk-role-badge ${emp.role}`}>
                        {formatRoleName(emp.role)}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`bk-tier-pill ${
                          emp.role === "compliance"
                            ? "restricted"
                            : emp.role === "employee"
                            ? "internal"
                            : "admin"
                        }`}
                      >
                        {emp.role === "compliance"
                          ? "Restricted"
                          : emp.role === "employee"
                          ? "Internal"
                          : "None (Query Denied)"}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`bk-account-status ${emp.is_active ? "active" : "inactive"}`}
                      >
                        {emp.is_active ? "Active" : "Deactivated"}
                      </span>
                    </td>
                    <td className="text-right">
                      <div className="bk-action-btn-group">
                        {emp.role !== "admin" && (
                          <button
                            type="button"
                            className="bk-btn-table"
                            onClick={() => promptPromoteAdmin(emp)}
                            title="Promote to system administrator"
                          >
                            Promote to Admin
                          </button>
                        )}
                        {emp.role !== "admin" && (
                          <select
                            className="bk-select-inline"
                            value={emp.role}
                            onChange={(e) => promptChangeRole(emp, e.target.value)}
                            aria-label={`Change role for ${emp.username}`}
                          >
                            <option value="employee">Employee</option>
                            <option value="compliance">Compliance</option>
                          </select>
                        )}
                        <button
                          type="button"
                          className={`bk-btn-table ${emp.is_active ? "destructive" : "constructive"}`}
                          onClick={() => promptToggleActive(emp)}
                        >
                          {emp.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {loading && (
            <div className="bk-table-loading">
              <span>Loading employee directory…</span>
            </div>
          )}

          {!loading && filtered.length === 0 && (
            <div className="bk-empty-table-state">
              <h3>No Accounts Found</h3>
              <p>
                No user accounts match the current filter criteria ({search ? `search: "${search}", ` : ""}
                role: {roleFilter}).
              </p>
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => {
                  setSearch("");
                  setRoleFilter("ALL");
                }}
              >
                Reset Filters
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Add User Modal */}
      {showAddModal && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card">
            <header className="bk-modal-header">
              <h2>Register New Staff Account</h2>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setShowAddModal(false)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <form onSubmit={handleAddEmployee} className="bk-form">
              <div className="bk-field-group">
                <label htmlFor="new-emp-username" className="bk-label">
                  Username
                </label>
                <input
                  id="new-emp-username"
                  className="bk-input"
                  type="text"
                  placeholder="e.g. j_smith or compliance_lead"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div className="bk-field-group">
                <label htmlFor="new-emp-password" className="bk-label">
                  Temporary Password
                </label>
                <input
                  id="new-emp-password"
                  className="bk-input"
                  type="password"
                  placeholder="Must contain 8+ characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>

              <div className="bk-field-group">
                <label htmlFor="new-emp-role" className="bk-label">
                  Account Role &amp; Access Tier
                </label>
                <select
                  id="new-emp-role"
                  className="bk-select"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                >
                  <option value="employee">Employee (Access Tier: Internal)</option>
                  <option value="compliance">Compliance (Access Tier: Restricted)</option>
                </select>
                <span className="bk-field-help">
                  Employee accounts access internal procedures; Compliance accounts access
                  restricted AML, KYC directives, and regulatory guidelines.
                </span>
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
                  {addLoading ? "Registering…" : "Register Account"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmAction && (
        <div className="bk-modal-backdrop" role="dialog" aria-modal="true">
          <div className="bk-modal-card">
            <header className="bk-modal-header">
              <h2>{confirmAction.title}</h2>
              <button
                type="button"
                className="bk-modal-close"
                onClick={() => setConfirmAction(null)}
                aria-label="Close dialog"
              >
                ×
              </button>
            </header>

            <div className="bk-modal-body">
              <p>{confirmAction.message}</p>
              {actionError && (
                <div className="bk-alert-banner" role="alert">
                  <span>{actionError}</span>
                </div>
              )}
            </div>

            <footer className="bk-modal-footer">
              <button
                type="button"
                className="bk-btn-secondary"
                onClick={() => setConfirmAction(null)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`bk-btn-primary ${confirmAction.isDestructive ? "destructive" : ""}`}
                onClick={runConfirmedAction}
                disabled={actionLoading}
              >
                {actionLoading ? "Processing…" : confirmAction.confirmLabel}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
