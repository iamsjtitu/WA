import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { PageHeader } from "./Overview";
import api from "../lib/api";
import { Copy, ArrowsClockwise, LinkSimple, Trash, PaperPlaneTilt } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Settings() {
  const { user, refresh } = useAuth();
  const [webhookUrl, setWebhookUrl] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setWebhookUrl(user?.webhook_url || "");
  }, [user?.webhook_url]);

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

  const saveWebhook = async (e) => {
    e?.preventDefault?.();
    if (!webhookUrl.startsWith("http://") && !webhookUrl.startsWith("https://")) {
      toast.error("URL must start with http:// or https://");
      return;
    }
    setBusy(true);
    try {
      await api.patch("/me/webhook", { url: webhookUrl });
      await refresh();
      toast.success("Webhook saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  const clearWebhook = async () => {
    if (!confirm("Remove webhook URL? Inbound events will no longer be delivered.")) return;
    setBusy(true);
    try {
      await api.delete("/me/webhook");
      setWebhookUrl("");
      await refresh();
      toast.success("Webhook cleared");
    } catch {
      toast.error("Failed");
    }
    setBusy(false);
  };

  const testWebhook = async () => {
    setBusy(true);
    try {
      await api.post("/me/webhook/test");
      toast.success("Test event dispatched — check your endpoint logs");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  return (
    <div className="p-10 fade-in max-w-3xl">
      <PageHeader title="Settings" sub="Account, API key & inbound webhook." />

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

      {/* Webhook section */}
      <div className="mt-6 border border-neutral-200 sharp p-6" data-testid="webhook-section">
        <div className="flex items-center gap-2">
          <LinkSimple size={18} weight="fill" color="#1FA855" />
          <h3 className="font-display font-semibold text-lg tracking-tight">Inbound Webhook</h3>
        </div>
        <p className="text-sm text-neutral-600 mt-2">
          When a connected WhatsApp number receives a message, we'll POST it to your endpoint signed
          with HMAC-SHA256.
        </p>

        {user?.webhook_disabled && (
          <div className="mt-4 border border-red-300 sharp p-4 bg-red-50" data-testid="webhook-disabled-banner">
            <p className="font-mono text-[11px] uppercase tracking-widest text-red-700">webhook auto-disabled</p>
            <p className="text-sm text-red-700 mt-1">
              We tried to deliver to your endpoint 10 times in a row without success. Fix your endpoint, then click <strong>Re-enable</strong>.
            </p>
            <button
              onClick={async () => {
                await api.post("/me/webhook/enable");
                await refresh();
                toast.success("Webhook re-enabled");
              }}
              className="btn-brand text-sm mt-3"
              data-testid="webhook-enable-btn"
            >
              Re-enable
            </button>
          </div>
        )}

        {!user?.webhook_disabled && user?.webhook_consecutive_failures > 0 && (
          <div className="mt-4 border border-yellow-300 sharp p-3 bg-yellow-50">
            <p className="font-mono text-[11px] text-yellow-800">
              {user.webhook_consecutive_failures} recent delivery failure(s). After 10 in a row we'll auto-disable.
            </p>
          </div>
        )}

        <form onSubmit={saveWebhook} className="mt-4 space-y-3">
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              Webhook URL
            </label>
            <input
              data-testid="webhook-url-input"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://your-app.com/whatsapp/webhook"
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855] font-mono text-sm"
            />
          </div>

          <div className="flex gap-2 flex-wrap">
            <button
              type="submit"
              disabled={busy}
              className="btn-brand text-sm disabled:opacity-50"
              data-testid="webhook-save-btn"
            >
              {user?.webhook_url ? "Update" : "Save webhook"}
            </button>
            {user?.webhook_url && (
              <>
                <button
                  type="button"
                  onClick={testWebhook}
                  disabled={busy}
                  className="btn-ghost text-sm inline-flex items-center gap-2 disabled:opacity-50"
                  data-testid="webhook-test-btn"
                >
                  <PaperPlaneTilt size={14} /> Send test
                </button>
                <button
                  type="button"
                  onClick={clearWebhook}
                  disabled={busy}
                  className="btn-ghost text-sm inline-flex items-center gap-2 disabled:opacity-50 hover:!border-red-500 hover:!text-red-600"
                  data-testid="webhook-clear-btn"
                >
                  <Trash size={14} /> Remove
                </button>
              </>
            )}
          </div>
        </form>

        {user?.webhook_secret && (
          <div className="mt-5 border-t border-neutral-200 pt-5">
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              webhook signing secret
            </p>
            <code className="block mt-2 font-mono text-xs bg-neutral-100 border border-neutral-200 sharp p-3 break-all" data-testid="webhook-secret">
              {user.webhook_secret}
            </code>
            <button onClick={() => copy(user.webhook_secret)} className="btn-ghost text-xs mt-2 inline-flex items-center gap-1" data-testid="copy-webhook-secret">
              <Copy size={12} /> Copy
            </button>
            <p className="text-xs text-neutral-600 mt-3 leading-relaxed">
              We sign each request with this secret using HMAC-SHA256, and send it in the{" "}
              <span className="kbd">X-Wapihub-Signature</span> header (format:{" "}
              <span className="kbd">sha256=&lt;hex&gt;</span>). Verify it on your end before
              processing.
            </p>
          </div>
        )}
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
