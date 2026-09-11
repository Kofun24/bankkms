import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Layout() {
  const navigate = useNavigate();

  const logout = async () => {
    try {
      await api.logout();
    } catch (e) {
      // ignore — log out client-side regardless of server response
    }
    localStorage.removeItem("bankkms_session");
    localStorage.removeItem("bankkms_role");
    navigate("/");
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">K</div>
          <div>
            <div className="brand-name">BANKKMS</div>
            <div className="brand-subtitle">KNOWLEDGE SYSTEM</div>
          </div>
        </div>

        <div className="sidebar-section">
          <span>OPERATIONS</span>
        </div>

        <nav className="navigation">
          <NavLink to="/admin" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <span className="nav-icon">⌂</span>
            Overview
          </NavLink>
          <NavLink to="/admin/employees" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <span className="nav-icon">♙</span>
            Users
          </NavLink>
          <NavLink to="/admin/documents" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <span className="nav-icon">▤</span>
            Documents
          </NavLink>
          <NavLink to="/admin/audit" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <span className="nav-icon">◷</span>
            Audit Log
          </NavLink>
        </nav>

        <div className="sidebar-bottom">
          <div className="security-box">
            <div className="security-icon">✓</div>
            <div>
              <strong>System Secure</strong>
              <span>Access controls active</span>
            </div>
          </div>

          <button className="logout-button" onClick={logout}>
            <span>↪</span>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="topbar-label">ADMINISTRATOR CONSOLE</span>
          </div>
          <div className="admin-profile">
            <div className="admin-avatar">A</div>
            <div className="admin-info">
              <strong>System Administrator</strong>
              <span>Administrator</span>
            </div>
            <span className="profile-arrow">⌄</span>
          </div>
        </header>

        <div className="page-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}