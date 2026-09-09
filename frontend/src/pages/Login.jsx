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

  return (
    <div className="login-page">
      <div className="login-left">
        <div className="login-brand">
          <div className="brand-mark large">K</div>
          <div>
            <div className="brand-name">BANKKMS</div>
            <div className="brand-subtitle">KNOWLEDGE MANAGEMENT SYSTEM</div>
          </div>
        </div>

        <div className="login-message">
          <span className="eyebrow">CONTROLLED KNOWLEDGE</span>
          <h1>
            Trusted knowledge.
            <br />
            <em>Precisely governed.</em>
          </h1>
          <p>
            BankKMS gives financial institutions control over the knowledge
            their people access, while ensuring every answer remains grounded
            in approved documentation.
          </p>
          <div className="login-line"></div>
          <div className="login-footer-text">
            <span>01</span>
            <p>Institutional knowledge, securely managed.</p>
          </div>
        </div>

        <div className="login-copyright">BANKKMS · INTERNAL OPERATIONS</div>
      </div>

      <div className="login-right">
        <div className="login-form-container">
          <div className="mobile-brand">BANKKMS</div>

          <div className="form-heading">
            <span className="eyebrow">ADMINISTRATOR ACCESS</span>
            <h2>Welcome back.</h2>
            <p>Sign in to manage your BankKMS environment.</p>
          </div>

          <form onSubmit={handleLogin}>
            <div className="input-group">
              <label>USERNAME</label>
              <div className="input-wrapper">
                <input
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
            </div>

            <div className="input-group">
              <label>PASSWORD</label>
              <div className="input-wrapper">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {error && (
              <div className="login-error">
                <span>!</span>
                {error}
              </div>
            )}

            <button className="login-button" type="submit" disabled={loading}>
              <span>{loading ? "Signing in..." : "Sign in to BankKMS"}</span>
              <span>→</span>
            </button>
          </form>

          <div className="secure-note">
            <span className="secure-check">✓</span>
            <div>
              <strong>Authorized personnel only</strong>
              <p>This console is restricted to BankKMS administrators.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}