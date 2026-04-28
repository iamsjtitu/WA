import { useAuth } from "../contexts/AuthContext";
import { PageHeader } from "./Overview";
import api from "../lib/api";
import { Copy, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Settings() {
  const { user, refresh } = useAuth();

  const copy = (k) => {
    navigator.clipboard.writeText(k);
    toast.success("Copied");
  };

  const regen = async () => {
    if (!confirm("Rotate your API key? Existing integrations will stop working.")) return;
    await api.post("/me/regenerate-key");
    await refresh();
    toast.success("API key rotated");
  };

  return (
    <div className="p-10 fade-in max-w-3xl">
      <PageHeader title="Settings" sub="Your account & API key." />

      <div className="mt-8 border border-neutral-200 sharp">
        <Row label="Name" value={user?.name} />
        <Row label="Email" value={user?.email} mono />
        <Row label="Role" value={user?.role} mono />
        <Row label="Member since" value={user?.created_at && new Date(user.created_at).toLocaleString()} mono />
      </div>

      <div className="mt-6 border border-neutral-200 sharp p-6">
        <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">api key</p>
        <code className="block mt-2 font-mono text-sm bg-neutral-100 border border-neutral-200 sharp p-3 break-all" data-testid="settings-api-key">
          {user?.api_key}
        </code>
        <div className="flex gap-2 mt-3">
          <button onClick={() => copy(user?.api_key)} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="settings-copy-key">
            <Copy size={14} /> Copy
          </button>
          <button onClick={regen} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="settings-rotate-key">
            <ArrowsClockwise size={14} /> Rotate
          </button>
        </div>
      </div>

      <div className="mt-6 border border-neutral-200 sharp p-6 bg-neutral-50">
        <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">quota</p>
        <p className="text-sm mt-2">
          {user?.quota_used} of {user?.quota_monthly} messages used this period.
        </p>
      </div>
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="grid grid-cols-[180px_1fr] border-b border-neutral-200 last:border-b-0">
      <div className="px-5 py-4 font-mono text-[11px] uppercase tracking-widest text-neutral-500 bg-neutral-50">
        {label}
      </div>
      <div className={`px-5 py-4 ${mono ? "font-mono text-sm" : ""}`}>{value || "—"}</div>
    </div>
  );
}
