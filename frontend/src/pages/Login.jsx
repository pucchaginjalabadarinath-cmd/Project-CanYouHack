// Login page. Uses Supabase Auth's JS client DIRECTLY (per
// FILE_WORKING_GUIDE.md - "use their JS client directly here rather than
// routing through your own backend for login/signup"). After a successful
// login, calls our own backend's /auth/me to find the user's role, then
// redirects accordingly.
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { supabase } from "../api/supabaseClient";
import { getMe } from "../api/client";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const { error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }

    try {
      const profile = await getMe();
      if (profile.role === "professor" || profile.role === "ta") {
        navigate("/professor/dashboard");
      } else {
        navigate("/student/dashboard");
      }
    } catch (err) {
      // Logged into Supabase but no profile row yet - signup flow was
      // interrupted. Send them back to finish signup rather than a dead end.
      setError("Account exists but profile is incomplete. Please sign up again.");
      navigate("/signup");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <form
        onSubmit={handleSubmit}
        className="bg-slate-800 p-8 rounded-xl w-80 text-slate-100"
      >
        <h1 className="text-lg font-semibold mb-4">DSA Portal - Login</h1>

        <label className="block text-sm text-slate-400 mt-3 mb-1">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full p-2 rounded bg-slate-900 border border-slate-700"
        />

        <label className="block text-sm text-slate-400 mt-3 mb-1">Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 rounded bg-slate-900 border border-slate-700"
        />

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-5 py-2 rounded bg-indigo-600 hover:bg-indigo-500 font-semibold disabled:opacity-50"
        >
          {loading ? "Logging in..." : "Log in"}
        </button>

        {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

        <p className="text-sm text-center mt-4">
          No account? <Link to="/signup" className="text-indigo-400">Sign up</Link>
        </p>
      </form>
    </div>
  );
}
