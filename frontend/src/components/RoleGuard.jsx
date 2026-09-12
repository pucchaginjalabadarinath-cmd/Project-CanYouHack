// Wraps a route element. Redirects to /login if not authenticated, or
// shows a 403 page if the logged-in role isn't in `allow`. Per ISSUES.md
// #15 acceptance criteria: a student typing /professor/flags directly into
// the URL bar must be redirected, not just hidden from the nav menu - this
// component is what makes that true, since it runs on every render of the
// protected page, independent of how the user navigated there.
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { getMe } from "../api/client";

export default function RoleGuard({ allow, children }) {
  const [status, setStatus] = useState("loading"); // loading | ok | unauthenticated | forbidden

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((profile) => {
        if (cancelled) return;
        setStatus(allow.includes(profile.role) ? "ok" : "forbidden");
      })
      .catch(() => {
        if (!cancelled) setStatus("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, [allow]);

  if (status === "loading") {
    return <div className="min-h-screen bg-slate-900" />; // avoid a flash of wrong content
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }
  if (status === "forbidden") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-100">
        <p>403 - you don't have access to this page.</p>
      </div>
    );
  }
  return children;
}
