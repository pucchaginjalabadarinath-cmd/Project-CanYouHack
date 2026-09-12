// Single fetch wrapper - every page imports typed helpers from here, never
// calls fetch() directly (per ISSUES.md #20). Attaches the Supabase auth
// token to every request automatically.
import { supabase } from "./supabaseClient";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function authFetch(path, options = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `request failed with status ${res.status}`);
  }
  return res.json();
}

// --- Auth endpoints ---
export function getMe() {
  return authFetch("/auth/me");
}

export function createProfile({ name, role }) {
  return authFetch("/auth/profile", {
    method: "POST",
    body: JSON.stringify({ name, role }),
  });
}

// TODO: getAssignments(), uploadSubmission(), getFlags(questionId), etc.
// get added here once their backend routers exist - see FILE_WORKING_GUIDE.md
