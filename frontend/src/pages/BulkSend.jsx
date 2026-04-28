import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { PaperPlane } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function BulkSend() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [recipientsRaw, setRecipientsRaw] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get("/sessions").then((r) => {
      setSessions(r.data);
      const c = r.data.find((s) => s.status === "connected");
      if (c) setSessionId(c.id);
    });
  }, []);

  const parseRecipients = () =>
    recipientsRaw
      .split(/[\s,;\n]+/)
      .map((s) => s.replace(/[^0-9]/g, ""))
      .filter(Boolean);

  const send = async (e) => {
    e.preventDefault();
    const recipients = parseRecipients();
    if (!sessionId) return toast.error("Pick a connected session");
    if (recipients.length === 0) return toast.error("Add at least one phone number");

    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post("/messages/bulk", {
        session_id: sessionId,
        recipients,
        text,
      });
      setResult(data);
      toast.success(`Sent ${data.sent}/${data.total}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bulk failed");
    }
    setBusy(false);
  };

  const recipients = parseRecipients();

  return (
    <div className="p-10 fade-in">
      <PageHeader title="Bulk Campaign" sub="Paste a list of numbers and a message. We'll send them with built-in throttling." />

      <form onSubmit={send} className="mt-8 grid lg:grid-cols-3 gap-6" data-testid="bulk-form">
        <div className="lg:col-span-2 space-y-4 border border-neutral-200 sharp p-6">
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              From session
            </label>
            <select
              data-testid="bulk-session-select"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7] bg-white"
              required
            >
              <option value="">Select session…</option>
              {sessions.map((s) => (
                <option key={s.id} value={s.id} disabled={s.status !== "connected"}>
                  {s.name} {s.phone ? `(${s.phone})` : ""} — {s.status}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              Recipients (one per line, comma, or space)
            </label>
            <textarea
              data-testid="bulk-recipients-input"
              required
              rows={8}
              value={recipientsRaw}
              onChange={(e) => setRecipientsRaw(e.target.value)}
              placeholder={"919876543210\n919812345678\n919998877665"}
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7] font-mono text-sm"
            />
            <p className="text-xs font-mono text-neutral-500 mt-1">
              {recipients.length} valid numbers detected
            </p>
          </div>

          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              Message
            </label>
            <textarea
              data-testid="bulk-text-input"
              required
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Your message here"
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7]"
            />
          </div>

          <div className="flex justify-end">
            <button
              data-testid="bulk-submit-btn"
              type="submit"
              disabled={busy}
              className="btn-brand inline-flex items-center gap-2 disabled:opacity-50"
            >
              <PaperPlane size={16} /> {busy ? "Sending…" : `Send to ${recipients.length}`}
            </button>
          </div>
        </div>

        <div>
          <div className="border border-neutral-200 sharp p-6 sticky top-6">
            <h3 className="font-display font-semibold tracking-tight">Throughput</h3>
            <p className="text-sm text-neutral-600 mt-2">
              Bulk sends are throttled at ~1 msg / 0.6s to reduce ban risk. You can close this tab —
              progress will appear in <span className="kbd">Message Logs</span>.
            </p>
            {result && (
              <div className="mt-4 border-t border-neutral-200 pt-4 space-y-1 text-sm font-mono">
                <div>Total: {result.total}</div>
                <div className="text-emerald-600">Sent: {result.sent}</div>
                <div className="text-red-600">Failed: {result.failed}</div>
              </div>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
