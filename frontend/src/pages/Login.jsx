import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { formatErr } from "../lib/api";
import { ChatCircle, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await login(email, password);
      toast.success("Welcome back");
      navigate("/app", { replace: true });
    } catch (e) {
      const msg = formatErr(e?.response?.data?.detail) || e.message;
      setErr(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-white">
      <div className="hidden lg:flex relative bg-[#0A0A0A] text-white p-12 flex-col justify-between overflow-hidden">
        <div className="absolute inset-0 grid-bg-dark opacity-60 pointer-events-none" />
        <Link to="/" className="flex items-center gap-2 relative" data-testid="login-brand">
          <div className="w-8 h-8 bg-[#1FA855] flex items-center justify-center sharp">
            <ChatCircle weight="fill" size={18} color="#fff" />
          </div>
          <span className="font-display font-bold text-lg">wa.9x.design</span>
        </Link>
        <div className="relative">
          <p className="font-mono text-xs uppercase tracking-widest text-[#EDFF00]">— signed in</p>
          <h2 className="font-display text-5xl tracking-tight mt-3 leading-tight">
            Welcome back. <br /> Your queue is ready.
          </h2>
          <p className="text-neutral-400 mt-4 max-w-md">
            Pick up where you left off — sessions, logs, and API keys all in one place.
          </p>
        </div>
        <p className="font-mono text-xs text-neutral-500 relative">© {new Date().getFullYear()} wa.9x.design</p>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-3xl tracking-tight">Sign in</h1>
          <p className="text-neutral-600 text-sm mt-2">
            Don't have an account?{" "}
            <Link to="/register" className="text-[#1FA855] underline" data-testid="link-to-register">
              Create one
            </Link>
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4" data-testid="login-form">
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Email
              </label>
              <input
                data-testid="login-email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
                placeholder="you@company.com"
                autoComplete="email"
              />
            </div>
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Password
              </label>
              <input
                data-testid="login-password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>

            {err && (
              <div className="text-sm text-red-600 font-mono" data-testid="login-error">
                {err}
              </div>
            )}

            <button
              data-testid="login-submit-button"
              type="submit"
              disabled={busy}
              className="btn-brand w-full inline-flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {busy ? "Signing in…" : "Sign in"} <ArrowRight size={14} />
            </button>
          </form>

          <p className="mt-6 text-xs text-neutral-500 font-mono">
            Default admin · admin@wa9x.com / admin123
          </p>
        </div>
      </div>
    </div>
  );
}
