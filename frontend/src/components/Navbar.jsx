// Role-aware nav bar. Per FILE_WORKING_GUIDE.md, this must exist before any
// page needing auth-gating - other pages assume it's already rendering
// correctly for each role.
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { supabase } from "../api/supabaseClient";
import { getMe } from "../api/client";

export default function Navbar() {
  const [role, setRole] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getMe()
      .then((p) => setRole(p.role))
      .catch(() => setRole(null));
  }, []);

  async function handleLogout() {
    await supabase.auth.signOut();
    navigate("/login");
  }

  const isStaff = role === "professor" || role === "ta";

  return (
    <nav className="flex justify-between items-center px-6 py-3 bg-slate-800 text-slate-100">
      <div className="flex gap-4 text-sm">
        <Link to={isStaff ? "/professor/dashboard" : "/student/dashboard"}>Dashboard</Link>
        {isStaff && <Link to="/professor/flags">Flagged Students</Link>}
      </div>
      {role && (
        <button onClick={handleLogout} className="text-sm px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">
          Log out
        </button>
      )}
    </nav>
  );
}
