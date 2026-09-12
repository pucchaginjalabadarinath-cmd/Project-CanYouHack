// Signup page. Two-step flow required by our architecture:
//   1. supabase.auth.signUp() creates the login credentials in Supabase.
//   2. createProfile() (our own backend) writes the name+role row into
//      OUR users table, since Supabase has no concept of "role".
// Per ISSUES.md #14 acceptance criteria: non-college emails are rejected
// client-side, before any network call is made.
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { supabase } from "../api/supabaseClient";
import { createProfile } from "../api/client";

const COLLEGE_EMAIL_DOMAIN = import.meta.env.VITE_COLLEGE_EMAIL_DOMAIN;

export default function Signup() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  function isCollegeEmail(value) {
    return value.toLowerCase().endsWith(`@${COLLEGE_EMAIL_DOMAIN.toLowerCase()}`);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    // Client-side domain check FIRST - no network call for a bad domain.
    if (!isCollegeEmail(email)) {
      setError(`Please use your college email (@${COLLEGE_EMAIL_DOMAIN}).`);
      return;
    }
    if (!role) {
      setError("Please select a role.");
      return;
    }

    setLoading(true);

    const { error: signUpError } = await supabase.auth.signUp({ email, password });
    if (signUpError) {
      setError(signUpError.message);
      setLoading(false);
      return;
    }

    try {
      await createProfile({ name, role });
      navigate("/login");
    } catch (err) {
      setError(
        "Account created but saving your profile failed: " + err.message +
        ". Try logging in - the profile step will retry."
      );
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
        <h1 className="text-lg font-semibold mb-4">DSA Portal - Sign up</h1>

        <label className="block text-sm text-slate-400 mt-3 mb-1">Full name</label>
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full p-2 rounded bg-slate-900 border border-slate-700"
        />

        <label className="block text-sm text-slate-400 mt-3 mb-1">
          College email (@{COLLEGE_EMAIL_DOMAIN})
        </label>
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
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 rounded bg-slate-900 border border-slate-700"
        />

        <label className="block text-sm text-slate-400 mt-3 mb-1">Role</label>
        <select
          required
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="w-full p-2 rounded bg-slate-900 border border-slate-700"
        >
          <option value="" disabled>Select role</option>
          <option value="student">Student</option>
          <option value="ta">Teaching Assistant</option>
          <option value="professor">Professor</option>
        </select>

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-5 py-2 rounded bg-indigo-600 hover:bg-indigo-500 font-semibold disabled:opacity-50"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>

        {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

        <p className="text-sm text-center mt-4">
          Already have an account? <Link to="/login" className="text-indigo-400">Log in</Link>
        </p>
      </form>
    </div>
  );
}
