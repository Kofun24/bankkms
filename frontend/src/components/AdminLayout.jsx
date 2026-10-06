import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function AdminLayout() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // Clear client session regardless
    }
    localStorage.removeItem("bankkms_session");
    localStorage.removeItem("bankkms_role");
    navigate("/admin/login");
  };

  return (
    <div className="bk-admin-shell">
      {/* Back-office Administrative Sidebar */}
      <aside className="bk-admin-sidebar">
        <div className="bk-sidebar-header">
          <div className="bk-admin-brand">
            <span className="bk-brand-title">BankKMS</span>
            <span className="bk-brand-sub">Administration Console</span>
          </div>
        </div>

        <div className="bk-sidebar-section-label">Management Modules</div>
        <nav className="bk-admin-nav" aria-label="Admin Navigation">
          <NavLink
            to="/admin"
            end
            className={({ isActive }) => `bk-nav-item ${isActive ? "active" : ""}`}
          >
            <span className="bk-nav-tag">01</span>
            <span className="bk-nav-title">Operations Overview</span>
          </NavLink>

          <NavLink
            to="/admin/employees"
            className={({ isActive }) => `bk-nav-item ${isActive ? "active" : ""}`}
          >
            <span className="bk-nav-tag">02</span>
            <span className="bk-nav-title">Account Governance</span>
          </NavLink>

          <NavLink
            to="/admin/documents"
            className={({ isActive }) => `bk-nav-item ${isActive ? "active" : ""}`}
          >
            <span className="bk-nav-tag">03</span>
            <span className="bk-nav-title">Document Registry</span>
          </NavLink>

          <NavLink
            to="/admin/audit"
            className={({ isActive }) => `bk-nav-item ${isActive ? "active" : ""}`}
          >
            <span className="bk-nav-tag">04</span>
            <span className="bk-nav-title">Audit Chain Integrity</span>
          </NavLink>
        </nav>

        {/* Structural Reminder: Zero Chat Policy */}
        <div className="bk-sidebar-guardrail">
          <div className="bk-guardrail-title">Governance Constraint</div>
          <p className="bk-guardrail-text">
            Admin sessions have zero knowledge-base query access. Administrative permissions are
            restricted exclusively to account and document metadata management.
          </p>
        </div>

        <div className="bk-sidebar-footer">
          <div className="bk-admin-user-card">
            <div className="bk-admin-badge">Admin</div>
            <div className="bk-admin-details">
              <span className="bk-admin-name">System Administrator</span>
              <span className="bk-admin-role">Full Governance Access</span>
            </div>
          </div>
          <button type="button" className="bk-btn-secondary full-width" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Administrative Workplace */}
      <main className="bk-admin-workspace">
        <header className="bk-admin-topbar">
          <div className="bk-topbar-breadcrumb">
            <span className="bk-topbar-root">Administration</span>
            <span className="bk-topbar-sep">/</span>
            <span className="bk-topbar-env">Production Environment (Single Node)</span>
          </div>

          <div className="bk-topbar-actions">
            <a href="/" className="bk-topbar-link">
              Customer Portal
            </a>
            <span className="bk-topbar-sep">·</span>
            <a href="/staff" className="bk-topbar-link">
              Staff Portal
            </a>
          </div>
        </header>

        <div className="bk-admin-content-area">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
