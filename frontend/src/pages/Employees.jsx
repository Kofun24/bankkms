import { useState, useEffect } from "react";
import { api } from "../api";

export default function Employees() {
  const [employees, setEmployees] = useState([]);
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmAction, setConfirmAction] = useState(null);
  const [actionError, setActionError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  async function loadEmployees() {
    setLoading(true);
    try {
      const data = await api.listEmployees();
      setEmployees(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEmployees();
  }, []);

  const filtered = employees.filter((employee) =>
    employee.username.toLowerCase().includes(search.toLowerCase()),
  );

  async function runConfirmedAction() {
    if (!confirmAction) return;
    setActionError("");
    setActionLoading(true);
    try {
      await confirmAction.run();
      setConfirmAction(null);
      loadEmployees();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  const askToggleStatus = (employee) => {
    setActionError("");
    setConfirmAction({
      title: employee.is_active ? "Deactivate account?" : "Reactivate account?",
      message: employee.is_active
        ? `${employee.username} will no longer be able to log in. This can be reversed at any time.`
        : `${employee.username} will be able to log in again.`,
      confirmLabel: employee.is_active ? "Deactivate" : "Reactivate",
      danger: employee.is_active,
      run: () =>
        employee.is_active
          ? api.deactivateEmployee(employee.username)
          : api.reactivateEmployee(employee.username),
    });
  };

  const askChangeRole = (employee, newRole) => {
    setActionError("");
    setConfirmAction({
      title: `Change role to ${newRole}?`,
      message: `${employee.username} will move from ${employee.role} to ${newRole}. ${
        newRole === "admin"
          ? "They will gain full system administration rights and lose knowledge-base query access."
          : employee.role === "admin"
            ? "They will lose administration rights."
            : "This changes what knowledge-base tier they can access."
      }`,
      confirmLabel: `Change to ${newRole}`,
      danger: employee.role === "admin" || newRole === "admin",
      run: () => api.changeRole(employee.username, newRole),
    });
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ACCESS MANAGEMENT</span>
          <h1>Users</h1>
          <p>Manage employee, compliance, and admin access to BankKMS.</p>
        </div>
        <button className="primary-button" onClick={() => setShowModal(true)}>
          + Add user
        </button>
      </div>

      {error && (
        <div className="login-error">
          <span>!</span>
          {error}
        </div>
      )}

      <div className="toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input
            type="text"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="toolbar-info">{filtered.length} users</div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>USERNAME</th>
              <th>ROLE</th>
              <th>STATUS</th>
              <th>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {!loading &&
              filtered.map((employee) => (
                <tr key={employee.id}>
                  <td>
                    <div className="employee-cell">
                      <div className="employee-avatar">
                        {employee.username.charAt(0).toUpperCase()}
                      </div>
                      <strong>{employee.username}</strong>
                    </div>
                  </td>
                  <td>
                    <span className={`role-badge ${employee.role}`}>
                      {employee.role}
                    </span>
                  </td>
                  <td>
                    <span
                      className={
                        employee.is_active ? "status current" : "status retired"
                      }
                    >
                      {employee.is_active ? "● ACTIVE" : "○ INACTIVE"}
                    </span>
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        className={
                          employee.is_active
                            ? "table-action danger"
                            : "table-action"
                        }
                        onClick={() => askToggleStatus(employee)}
                      >
                        {employee.is_active ? "Deactivate" : "Reactivate"}
                      </button>

                      <select
                        className="role-select"
                        value=""
                        onChange={(e) => {
                          if (e.target.value)
                            askChangeRole(employee, e.target.value);
                          e.target.value = "";
                        }}
                      >
                        <option value="" disabled>
                          Change role…
                        </option>
                        {["employee", "compliance", "admin"]
                          .filter((r) => r !== employee.role)
                          .map((r) => (
                            <option key={r} value={r}>
                              {r.charAt(0).toUpperCase() + r.slice(1)}
                            </option>
                          ))}
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {loading && <p style={{ padding: 20 }}>Loading...</p>}
        {!loading && filtered.length === 0 && (
          <p style={{ padding: 20, color: "var(--muted)" }}>No users found.</p>
        )}
      </div>

      {showModal && (
        <AddEmployeeModal
          close={() => setShowModal(false)}
          onAdded={() => {
            setShowModal(false);
            loadEmployees();
          }}
        />
      )}

      {confirmAction && (
        <ConfirmModal
          {...confirmAction}
          error={actionError}
          loading={actionLoading}
          onCancel={() => {
            setConfirmAction(null);
            setActionError("");
          }}
          onConfirm={runConfirmedAction}
        />
      )}
    </div>
  );
}

function ConfirmModal({
  title,
  message,
  confirmLabel,
  danger,
  error,
  loading,
  onCancel,
  onConfirm,
}) {
  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: 420 }}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">CONFIRM ACTION</span>
            <h2>{title}</h2>
          </div>
          <button className="close-button" onClick={onCancel}>
            ×
          </button>
        </div>

        <p
          style={{
            fontSize: 13,
            color: "var(--muted)",
            lineHeight: 1.6,
            marginBottom: error ? 16 : 28,
          }}
        >
          {message}
        </p>

        {error && (
          <div className="login-error" style={{ marginBottom: 20 }}>
            <span>!</span>
            {error}
          </div>
        )}

        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="primary-button"
            style={danger ? { background: "var(--red)" } : {}}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function AddEmployeeModal({ close, onAdded }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("employee");
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.addEmployee(username, password, role);
      onAdded();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <div>
            <span className="eyebrow">NEW ACCOUNT</span>
            <h2>Add user</h2>
          </div>
          <button className="close-button" onClick={close}>
            ×
          </button>
        </div>

        <form onSubmit={submit}>
          <div className="input-group">
            <label>USERNAME</label>
            <input
              className="form-input"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label>TEMPORARY PASSWORD</label>
            <input
              className="form-input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label>ACCESS ROLE</label>
            <select
              className="form-input"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="employee">Employee</option>
              <option value="compliance">Compliance</option>
            </select>
          </div>

          <p
            style={{
              fontSize: 10,
              color: "var(--muted)",
              marginTop: -14,
              marginBottom: 20,
            }}
          >
            Admin accounts can't be created directly — promote an existing
            employee or compliance account instead.
          </p>

          {error && (
            <div className="login-error">
              <span>!</span>
              {error}
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={close}>
              Cancel
            </button>
            <button className="primary-button">Create account</button>
          </div>
        </form>
      </div>
    </div>
  );
}
