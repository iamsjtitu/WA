import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { PaperPlaneTilt, Paperclip, X, Image, FilePdf } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function SendMessage() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode] = useState("text"); // text | media
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  useEffect(() => {
    api.get("/sessions").then((r) => {
      setSessions(r.data);
      const c = r.data.find((s) => s.status === "connected");
      if (c) setSessionId(c.id);
    });
  }, []);

  const onFileChange = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) {
      toast.error("File too large (max 25MB)");
      return;
    }
    setFile(f);
  };

  const send = async (e) => {
    e.preventDefault();
    if (!sessionId) return toast.error("Pick a connected session");

    setBusy(true);
    setLast(null);
    try {
      if (mode === "text") {
        const { data } = await api.post("/messages/send", {
          session_id: sessionId,
          to,
          text,
        });
        setLast(data);
        if (data.status === "sent") toast.success("Message sent");
        else toast.error(data.error || "Failed");
      } else {
        if (!file) {
          toast.error("Choose a file");
          setBusy(false);
          return;
        }
        const fd = new FormData();
        fd.append("session_id", sessionId);
        fd.append("to", to);
        fd.append("caption", caption);
        fd.append("media", file);
        const { data } = await api.post("/messages/send-media", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setLast(data);
        if (data.status === "sent") toast.success("Media sent");
        else toast.error(data.error || "Failed");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  const fileIcon = () => {
    if (!file) return <Paperclip size={16} />;
    if (file.type.startsWith("image/")) return <Image size={16} weight="fill" />;
    if (file.type === "application/pdf") return <FilePdf size={16} weight="fill" />;
    return <Paperclip size={16} />;
  };

  return (
    <div className="p-10 fade-in">
      <PageHeader title="Send Message" sub="Send a text or media message from a connected session." />

      {/* Mode tabs */}
      <div className="mt-6 flex gap-1 border-b border-neutral-200">
        <Tab active={mode === "text"} onClick={() => setMode("text")} testId="mode-text">
          Text
        </Tab>
        <Tab active={mode === "media"} onClick={() => setMode("media")} testId="mode-media">
          Media (image · video · pdf · doc)
        </Tab>
      </div>

      <form onSubmit={send} className="mt-6 grid lg:grid-cols-3 gap-6" data-testid="send-form">
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
            <p className="text-xs text-neutral-500 mt-1 font-mono">
              No + or spaces. Example: 919876543210
            </p>
          </div>

          {mode === "text" ? (
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
          ) : (
            <>
              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                  File (max 25MB)
                </label>
                <div className="mt-1.5">
                  {!file ? (
                    <label
                      className="border border-dashed border-neutral-300 sharp px-4 py-8 flex flex-col items-center justify-center cursor-pointer hover:border-[#002FA7] hover:bg-blue-50/30 transition-colors"
                      data-testid="file-drop-area"
                    >
                      <Paperclip size={24} className="text-neutral-400" />
                      <span className="mt-2 text-sm text-neutral-600">Click to select a file</span>
                      <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-400 mt-1">
                        image · video · audio · pdf · doc
                      </span>
                      <input
                        type="file"
                        accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.txt,.csv"
                        onChange={onFileChange}
                        className="hidden"
                        data-testid="send-file-input"
                      />
                    </label>
                  ) : (
                    <div className="flex items-center gap-3 border border-neutral-300 sharp px-3 py-2.5">
                      <span className="text-[#002FA7]">{fileIcon()}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{file.name}</div>
                        <div className="font-mono text-[11px] text-neutral-500">
                          {(file.size / 1024).toFixed(1)} KB · {file.type || "unknown"}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setFile(null)}
                        className="p-1 hover:bg-neutral-100 sharp"
                        data-testid="file-clear-btn"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                  Caption (optional)
                </label>
                <textarea
                  data-testid="send-caption-input"
                  rows={3}
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder="Optional caption for image/video/document"
                  className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7]"
                />
              </div>
            </>
          )}

          <div className="flex justify-end">
            <button
              data-testid="send-submit-btn"
              type="submit"
              disabled={busy}
              className="btn-brand inline-flex items-center gap-2 disabled:opacity-50"
            >
              <PaperPlaneTilt size={16} />
              {busy ? "Sending…" : mode === "media" ? "Send media" : "Send message"}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="border border-neutral-200 sharp p-6">
            <h3 className="font-display font-semibold tracking-tight">Tips</h3>
            <ul className="mt-3 text-sm text-neutral-600 space-y-2 list-disc pl-4">
              <li>Use country code (no + sign).</li>
              <li>For images, captions appear under the photo on WhatsApp.</li>
              <li>PDFs &amp; documents appear as files with a tap-to-open.</li>
              <li>Throttle bulk sends to stay clear of WhatsApp limits.</li>
            </ul>
          </div>

          {last && (
            <div
              className={`border sharp p-5 ${
                last.status === "sent" ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"
              }`}
            >
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

function Tab({ active, onClick, children, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? "border-[#002FA7] text-[#002FA7]"
          : "border-transparent text-neutral-600 hover:text-neutral-900"
      }`}
    >
      {children}
    </button>
  );
}
