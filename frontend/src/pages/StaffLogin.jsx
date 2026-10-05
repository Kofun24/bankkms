import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import "../staff-portal.css";

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
        JSON.stringify({ username: res.username, role: res.role, access_level: res.access_level })
      );
      navigate("/staff/chat");
    } catch (err) {
      setError(err.message || "Invalid username or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sp-login-page">
      <div className="sp-login-card">
        <div className="sp-login-brand">
          <div className="sp-brand-mark">K</div>
          <div>
            <div className="sp-brand-name">BankKMS Staff Portal</div>
            <div className="sp-brand-subtitle">Employee &amp; Compliance Access</div>
          </div>
        </div>

        <p className="sp-login-intro">
          Sign in with your work account to ask questions against internal
          and role-appropriate knowledge base content.
        </p>

        <form onSubmit={handleLogin}>
          <div className="sp-input-group">
            <label>USERNAME</label>
            <input
              className="sp-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>

          <div className="sp-input-group">
            <label>PASSWORD</label>
            <input
              className="sp-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && <div className="sp-error">{error}</div>}

          <button className="sp-login-button" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="sp-login-footnote">
          Access is limited to what your role is authorized to see. All
          activity is logged for compliance purposes.
        </div>
      </div>
    </div>
  );
}