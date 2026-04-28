import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { PaperPlaneTilt } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function SendMessage() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  useEffect(() => {
    api.get("/sessions").then((r) => {
      setSessions(r.data);
      const connected = r.data.find((s) => s.status === "connected");
      if (connected) setSessionId(connected.id);
    });
  }, []);

  const send = async (e) => {
    e.preventDefault();
    if (!sessionId) return toast.error("Pick a connected session");
    setBusy(true);
    setLast(null);
    try {
      const { data } = await api.post("/messages/send", { session_id: sessionId, to, text });
      setLast(data);
      if (data.status === "sent") toast.success("Message sent");
      else toast.error(data.error || "Failed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  return (
    <div className="p-10 fade-in">
      <PageHeader title="Send Message" sub="Send a single WhatsApp message from a connected session." />

      <form onSubmit={send} className="mt-8 grid lg:grid-cols-3 gap-6" data-testid="send-form">
        <div className="lg:col-span-2 space-y-4 border border-neutral-200 sharp p-6">
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              From session
            </label>
            <select
              data-testid="send-session-select"
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
              To (phone with country code)
            </label>
            <input
              data-testid="send-to-input"
              required
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="919876543210"
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7] font-mono"
            />
            <p className="text-xs text-neutral-500 mt-1 font-mono">No + or spaces. Example: 919876543210</p>
          </div>

          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              Message
            </label>
            <textarea
              data-testid="send-text-input"
              required
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Hello, this is a test message from WapiHub"
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7]"
            />
          </div>

          <div className="flex justify-end">
            <button
              data-testid="send-submit-btn"
              type="submit"
              disabled={busy}
              className="btn-brand inline-flex items-center gap-2 disabled:opacity-50"
            >
              <PaperPlaneTilt size={16} /> {busy ? "Sending…" : "Send message"}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="border border-neutral-200 sharp p-6">
            <h3 className="font-display font-semibold tracking-tight">Tips</h3>
            <ul className="mt-3 text-sm text-neutral-600 space-y-2 list-disc pl-4">
              <li>Use country code (no + sign).</li>
              <li>Avoid sending to numbers that haven't messaged you in 24h with promotional content.</li>
              <li>Throttle bulk sends to stay clear of WhatsApp limits.</li>
            </ul>
          </div>

          {last && (
            <div className={`border sharp p-5 ${last.status === "sent" ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <div className="font-mono text-[11px] uppercase tracking-widest">{last.status}</div>
              <div className="text-sm mt-1">→ {last.to}</div>
              {last.error && <div className="text-xs text-red-600 mt-2 font-mono">{last.error}</div>}
            </div>
          )}
        </div>
      </form>
    </div>
  );
}
