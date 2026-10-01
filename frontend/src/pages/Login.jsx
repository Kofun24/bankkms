import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Login() {
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { session_id, role } = await api.login(username, password);
      localStorage.setItem("bankkms_session", session_id);
      localStorage.setItem("bankkms_role", role);
      navigate("/admin");
    } catch (err) {
      setError(err.message || "Invalid administrator credentials.");
    } finally {
      setLoading(false);
    }
  };

  const fillDemoAdmin = () => {
    setUsername("demo_admin");
    setPassword("DemoAdmin123!");
  };

  return (
    <div className="bk-admin-login-surface">
      <div className="bk-admin-login-card">
        <header className="bk-admin-login-header">
          <div className="bk-admin-badge-inst">BankKMS Administration</div>
          <h1>System Governance Console</h1>
          <p>
            Administrative console for employee account authorization, role promotions, and document
            metadata management. Query capabilities are structurally disabled on this surface.
          </p>
        </header>

        <form onSubmit={handleLogin} className="bk-form">
          <div className="bk-field-group">
            <label htmlFor="admin-username" className="bk-label">
              Administrator Username
            </label>
            <input
              id="admin-username"
              className="bk-input"
              type="text"
              placeholder="e.g. demo_admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div className="bk-field-group">
            <div className="bk-label-row">
              <label htmlFor="admin-password" className="bk-label">
                Security Password
              </label>
              <button
                type="button"
                className="bk-btn-text"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <input
              id="admin-password"
              className="bk-input"
              type={showPassword ? "text" : "password"}
              placeholder="Enter password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <div className="bk-alert-banner" role="alert">
              <span>{error}</span>
            </div>
          )}

          <button type="submit" className="bk-btn-primary full-width" disabled={loading}>
            {loading ? "Authenticating Session…" : "Sign In to Admin Console"}
          </button>
        </form>

        <section className="bk-demo-credentials-box">
          <div className="bk-demo-header">
            <span className="bk-demo-title">Evaluation Test Credentials</span>
          </div>
          <button type="button" className="bk-demo-btn admin" onClick={fillDemoAdmin}>
            <span className="bk-demo-role admin">Administrator</span>
            <span className="bk-demo-u">demo_admin</span>
            <span className="bk-demo-tier">Full Console Access</span>
          </button>
        </section>

        <footer className="bk-admin-login-footer">
          <p>
            This console is restricted to authorized systems officers. Unauthorized access attempts
            are recorded in the immutable audit log.
          </p>
          <div className="bk-cross-links">
            <a href="/">Customer Web App</a>
            <span>·</span>
            <a href="/staff">Staff Portal</a>
          </div>
        </footer>
      </div>
    </div>
  );
}
