import { useState, useEffect } from "react";
import { api } from "../api";

export default function Employees() {
  const [employees, setEmployees] = useState([]);
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
    employee.username.toLowerCase().includes(search.toLowerCase())
  );

  const toggleStatus = async (employee) => {
    try {
      if (employee.is_active) {
        await api.deactivateEmployee(employee.username);
      } else {
        await api.reactivateEmployee(employee.username);
      }
      loadEmployees();
    } catch (err) {
      setError(err.message);
    }
  };

  const promote = async (employee) => {
    try {
      await api.promoteEmployee(employee.username);
      loadEmployees();
    } catch (err) {
      setError(err.message);
    }
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

      {error && <div className="login-error"><span>!</span>{error}</div>}

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
                    <span className={employee.is_active ? "status current" : "status retired"}>
                      {employee.is_active ? "● ACTIVE" : "○ INACTIVE"}
                    </span>
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        className={employee.is_active ? "table-action danger" : "table-action"}
                        onClick={() => toggleStatus(employee)}
                      >
                        {employee.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                      {employee.role !== "admin" && (
                        <button className="table-action" onClick={() => promote(employee)}>
                          Promote to Admin
                        </button>
                      )}
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
          <button className="close-button" onClick={close}>×</button>
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
            <select className="form-input" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="employee">Employee</option>
              <option value="compliance">Compliance</option>
            </select>
          </div>

          <p style={{ fontSize: 10, color: "var(--muted)", marginTop: -14, marginBottom: 20 }}>
            Admin accounts can't be created directly — promote an existing
            employee or compliance account instead.
          </p>

          {error && <div className="login-error"><span>!</span>{error}</div>}

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