import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { formatErr } from "../lib/api";
import { ChatCircle, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await register({ name, email, password });
      toast.success("Account created");
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
      <div className="flex items-center justify-center p-8 order-2 lg:order-1">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-3xl tracking-tight">Create your account</h1>
          <p className="text-neutral-600 text-sm mt-2">
            Already have one?{" "}
            <Link to="/login" className="text-[#1FA855] underline" data-testid="link-to-login">
              Sign in
            </Link>
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4" data-testid="register-form">
            <Field label="Name" data-testid="register-name-input" value={name} onChange={setName} placeholder="Acme Pvt. Ltd." />
            <Field label="Email" type="email" data-testid="register-email-input" value={email} onChange={setEmail} placeholder="you@company.com" autoComplete="email" />
            <Field label="Password" type="password" data-testid="register-password-input" value={password} onChange={setPassword} placeholder="min 6 characters" autoComplete="new-password" />

            {err && (
              <div className="text-sm text-red-600 font-mono" data-testid="register-error">
                {err}
              </div>
            )}

            <button
              data-testid="register-submit-button"
              type="submit"
              disabled={busy}
              className="btn-brand w-full inline-flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create account"} <ArrowRight size={14} />
            </button>
            <p className="text-xs text-neutral-500 font-mono mt-2">
              Free plan — 1,000 messages / month included.
            </p>
          </form>
        </div>
      </div>

      <div className="hidden lg:flex relative bg-[#0A0A0A] text-white p-12 flex-col justify-between overflow-hidden order-1 lg:order-2">
        <div className="absolute inset-0 grid-bg-dark opacity-60 pointer-events-none" />
        <Link to="/" className="flex items-center gap-2 relative">
          <div className="w-8 h-8 bg-[#1FA855] flex items-center justify-center sharp">
            <ChatCircle weight="fill" size={18} color="#fff" />
          </div>
          <span className="font-display font-bold text-lg">wa.9x.design</span>
        </Link>
        <div className="relative">
          <p className="font-mono text-xs uppercase tracking-widest text-[#EDFF00]">— join the hub</p>
          <h2 className="font-display text-5xl tracking-tight mt-3 leading-tight">
            Ship a WhatsApp API <br /> in <span className="bg-[#EDFF00] text-black px-2">90 seconds.</span>
          </h2>
          <p className="text-neutral-400 mt-4 max-w-md">
            No business verification, no template approvals. Link a number, grab a key, send.
          </p>
        </div>
        <p className="font-mono text-xs text-neutral-500 relative">© {new Date().getFullYear()} wa.9x.design</p>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", placeholder, autoComplete, ...rest }) {
  return (
    <div>
      <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</label>
      <input
        {...rest}
        type={type}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
      />
    </div>
  );
}
