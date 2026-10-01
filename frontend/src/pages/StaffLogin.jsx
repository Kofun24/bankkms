import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const STAFF_SESSION_KEY = "bankkms_staff_session";
const STAFF_USER_KEY = "bankkms_staff_user";

export default function StaffLogin() {
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.staffLogin(username, password);
      localStorage.setItem(STAFF_SESSION_KEY, res.session_id);
      localStorage.setItem(
        STAFF_USER_KEY,
        JSON.stringify({
          username: res.username,
          role: res.role,
          access_level: res.access_level,
        })
      );
      navigate("/staff/chat");
    } catch (err) {
      setError(err.message || "Invalid credentials or unauthorized role.");
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (u, p) => {
    setUsername(u);
    setPassword(p);
  };

  return (
    <div className="bk-staff-login-surface">
      <div className="bk-staff-login-card">
        <header className="bk-staff-login-header">
          <div className="bk-staff-badge-institution">BankKMS Internal Portal</div>
          <h1>Staff &amp; Regulatory Portal</h1>
          <p>
            Authorized access for Bank Employees and Compliance Officers. Knowledge boundaries are
            strictly enforced based on your verified role.
          </p>
        </header>

        <form onSubmit={handleLogin} className="bk-form">
          <div className="bk-field-group">
            <label htmlFor="staff-username" className="bk-label">
              Staff Username
            </label>
            <input
              id="staff-username"
              className="bk-input"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. demo_employee or demo_compliance"
              autoFocus
              required
            />
          </div>

          <div className="bk-field-group">
            <label htmlFor="staff-password" className="bk-label">
              Account Password
            </label>
            <input
              id="staff-password"
              className="bk-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
            />
          </div>

          {error && (
            <div className="bk-alert-banner" role="alert">
              <span>{error}</span>
            </div>
          )}

          <button type="submit" className="bk-btn-primary full-width" disabled={loading}>
            {loading ? "Authenticating Session…" : "Sign In to Staff Portal"}
          </button>
        </form>

        <section className="bk-demo-credentials-box">
          <h2 className="bk-demo-title">Evaluation Test Accounts</h2>
          <div className="bk-demo-buttons">
            <button
              type="button"
              className="bk-demo-btn"
              onClick={() => fillDemo("demo_employee", "DemoEmp123!")}
            >
              <span className="bk-demo-role employee">Employee</span>
              <span className="bk-demo-u">demo_employee</span>
              <span className="bk-demo-tier">Tier: Internal</span>
            </button>
            <button
              type="button"
              className="bk-demo-btn"
              onClick={() => fillDemo("demo_compliance", "DemoComp123!")}
            >
              <span className="bk-demo-role compliance">Compliance</span>
              <span className="bk-demo-u">demo_compliance</span>
              <span className="bk-demo-tier">Tier: Restricted</span>
            </button>
          </div>
        </section>

        <footer className="bk-staff-login-footer">
          <span>All query activity is written to a tamper-evident, hash-chained audit log.</span>
          <div className="bk-cross-links">
            <a href="/">Customer Web App</a>
            <span>·</span>
            <a href="/admin/login">Admin Console</a>
          </div>
        </footer>
      </div>
    </div>
  );
}