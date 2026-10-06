import { Routes, Route, Navigate } from "react-router-dom";

// 1. Customer-facing web app (public, no login, anonymous)
import CustomerChat from "./pages/CustomerChat";

// 2. Staff portal (Employee & Compliance, behind login)
import StaffLogin from "./pages/StaffLogin";
import StaffChat from "./pages/StaffChat";

// 3. Admin console (Administrator only, zero query interface)
import Login from "./pages/Login";
import AdminLayout from "./components/AdminLayout";
import Dashboard from "./pages/Dashboard";
import Employees from "./pages/Employees";
import Documents from "./pages/Documents";
import AuditLog from "./pages/AuditLog";

function AdminProtectedRoute({ children }) {
  const session = localStorage.getItem("bankkms_session");
  const role = localStorage.getItem("bankkms_role");
  return session && role === "admin" ? children : <Navigate to="/admin/login" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Surface 1: Customer web app (Public, no login, anonymous session) */}
      <Route path="/" element={<CustomerChat />} />
      <Route path="/chat" element={<Navigate to="/" replace />} />
      <Route path="/customer" element={<Navigate to="/" replace />} />

      {/* Surface 2: Staff portal (Employee + Compliance, behind login) */}
      <Route path="/staff" element={<StaffLogin />} />
      <Route path="/staff/chat" element={<StaffChat />} />

      {/* Surface 3: Admin console (Administrator only, ZERO query interface) */}
      <Route path="/admin/login" element={<Login />} />
      <Route
        path="/admin"
        element={
          <AdminProtectedRoute>
            <AdminLayout />
          </AdminProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="employees" element={<Employees />} />
        <Route path="documents" element={<Documents />} />
        <Route path="audit" element={<AuditLog />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}