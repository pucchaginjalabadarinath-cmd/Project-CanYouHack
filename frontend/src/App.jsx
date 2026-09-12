// Router setup. Professor/TA-only and Student-only pages get added inside
// their respective RoleGuard as they're built - do not add a route without
// wrapping it in RoleGuard if it's not Login/Signup.
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import RoleGuard from "./components/RoleGuard";

// Placeholder dashboards until ProfessorDashboard.jsx / StudentDashboard.jsx
// are built for real (see ISSUES.md #16, #17) - kept here so routing and
// auth can be tested end-to-end before those pages exist.
function ProfessorDashboardPlaceholder() {
  return <div className="p-6 text-slate-100">Professor/TA dashboard - coming soon.</div>;
}
function StudentDashboardPlaceholder() {
  return <div className="p-6 text-slate-100">Student dashboard - coming soon.</div>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />

        <Route
          path="/professor/dashboard"
          element={
            <RoleGuard allow={["professor", "ta"]}>
              <ProfessorDashboardPlaceholder />
            </RoleGuard>
          }
        />
        <Route
          path="/student/dashboard"
          element={
            <RoleGuard allow={["student"]}>
              <StudentDashboardPlaceholder />
            </RoleGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
