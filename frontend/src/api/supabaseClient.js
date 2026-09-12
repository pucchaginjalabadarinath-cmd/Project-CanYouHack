// Single shared Supabase client. Every page that needs auth (Login, Signup,
// RoleGuard, Navbar) imports THIS instance - never call createClient() a
// second time elsewhere, or you'll get two disconnected auth states.
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
