import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { PaperPlane, FileCsv, ListBullets } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function BulkSend() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode] = useState("paste"); // paste | csv
  const [recipientsRaw, setRecipientsRaw] = useState("");
  const [text, setText] = useState("");
  const [csvFile, setCsvFile] = useState(null);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvPreview, setCsvPreview] = useState([]);
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

  const onCsvChange = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setCsvFile(f);
    // preview first 3 rows
    const text = await f.text();
    const lines = text.split(/\r?\n/).filter(Boolean);
    if (lines.length === 0) return;
    const headers = lines[0].split(",").map((h) => h.trim());
    const previewRows = lines.slice(1, 4).map((l) => {
      const cols = l.split(",");
      const o = {};
      headers.forEach((h, i) => (o[h] = (cols[i] || "").trim()));
      return o;
    });
    setCsvHeaders(headers);
    setCsvPreview(previewRows);
  };

  const send = async (e) => {
    e.preventDefault();
    if (!sessionId) return toast.error("Pick a connected session");

    setBusy(true);
    setResult(null);
    try {
      if (mode === "paste") {
        const recipients = parseRecipients();
        if (recipients.length === 0) return toast.error("Add at least one phone number");
        const { data } = await api.post("/messages/bulk", {
          session_id: sessionId,
          recipients,
          text,
        });
        setResult(data);
        toast.success(`Sent ${data.sent}/${data.total}`);
      } else {
        if (!csvFile) {
          toast.error("Select a CSV file");
          setBusy(false);
          return;
        }
        if (!text.trim()) {
          toast.error("Enter a message template");
          setBusy(false);
          return;
        }
        const fd = new FormData();
        fd.append("session_id", sessionId);
        fd.append("template", text);
        fd.append("file", csvFile);
        const { data } = await api.post("/messages/bulk-csv", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setResult(data);
        toast.success(`Sent ${data.sent}/${data.total}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Bulk failed");
    }
    setBusy(false);
  };

  const recipients = parseRecipients();
  const sampleRendered =
    mode === "csv" && csvPreview[0]
      ? Object.entries(csvPreview[0]).reduce(
          (acc, [k, v]) => acc.replaceAll("{{" + k + "}}", v || ""),
          text
        )
      : "";

  return (
    <div className="p-10 fade-in">
      <PageHeader title="Bulk Campaign" sub="Send to many. Paste a list, or upload a CSV with template variables." />

      {/* Mode tabs */}
      <div className="mt-6 flex gap-1 border-b border-neutral-200">
        <Tab active={mode === "paste"} onClick={() => setMode("paste")} testId="mode-paste" icon={<ListBullets size={14} />}>
          Paste numbers
        </Tab>
        <Tab active={mode === "csv"} onClick={() => setMode("csv")} testId="mode-csv" icon={<FileCsv size={14} />}>
          CSV + template
        </Tab>
      </div>

      <form onSubmit={send} className="mt-6 grid lg:grid-cols-3 gap-6" data-testid="bulk-form">
        <div className="lg:col-span-2 space-y-4 border border-neutral-200 sharp p-6">
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              From session
            </label>
            <select
              data-testid="bulk-session-select"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855] bg-white"
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

          {mode === "paste" ? (
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Recipients (one per line, comma, or space)
              </label>
              <textarea
                data-testid="bulk-recipients-input"
                rows={8}
                value={recipientsRaw}
                onChange={(e) => setRecipientsRaw(e.target.value)}
                placeholder={"919876543210\n919812345678\n919998877665"}
                className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855] font-mono text-sm"
              />
              <p className="text-xs font-mono text-neutral-500 mt-1">
                {recipients.length} valid numbers detected
              </p>
            </div>
          ) : (
            <>
              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                  CSV file (must include header row, first column = phone)
                </label>
                <div className="mt-1.5">
                  <label
                    className="border border-dashed border-neutral-300 sharp px-4 py-6 flex flex-col items-center justify-center cursor-pointer hover:border-[#1FA855] hover:bg-blue-50/30 transition-colors"
                    data-testid="csv-drop-area"
                  >
                    <FileCsv size={22} className="text-neutral-400" />
                    <span className="mt-2 text-sm">
                      {csvFile ? csvFile.name : "Click to select a CSV"}
                    </span>
                    <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-400 mt-1">
                      .csv
                    </span>
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={onCsvChange}
                      className="hidden"
                      data-testid="csv-file-input"
                    />
                  </label>
                </div>

                {csvHeaders.length > 0 && (
                  <div className="mt-3 border border-neutral-200 sharp p-3 bg-neutral-50">
                    <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                      Detected variables (use them as <span className="kbd">{"{{name}}"}</span> in the template)
                    </p>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {csvHeaders.map((h) => (
                        <span key={h} className="kbd text-[11px]">{`{{${h}}}`}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              {mode === "csv" ? "Message template" : "Message"}
            </label>
            <textarea
              data-testid="bulk-text-input"
              required
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                mode === "csv"
                  ? "Hi {{name}}, your order {{order_id}} ships tomorrow."
                  : "Your message here"
              }
              className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
            />
          </div>

          <div className="flex justify-end">
            <button
              data-testid="bulk-submit-btn"
              type="submit"
              disabled={busy}
              className="btn-brand inline-flex items-center gap-2 disabled:opacity-50"
            >
              <PaperPlane size={16} />
              {busy
                ? "Sending…"
                : mode === "csv"
                  ? "Send campaign"
                  : `Send to ${recipients.length}`}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          {mode === "csv" && csvPreview.length > 0 && (
            <div className="border border-neutral-200 sharp p-5">
              <h3 className="font-display font-semibold tracking-tight text-sm">CSV preview</h3>
              <div className="mt-2 max-h-48 overflow-auto">
                <table className="w-full text-[11px] font-mono">
                  <thead>
                    <tr className="text-left text-neutral-500">
                      {csvHeaders.map((h) => (
                        <th key={h} className="px-2 py-1.5 border-b border-neutral-200">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {csvPreview.map((row, i) => (
                      <tr key={i}>
                        {csvHeaders.map((h) => (
                          <td key={h} className="px-2 py-1.5 border-b border-neutral-100">
                            {row[h]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {sampleRendered && (
                <div className="mt-3 border-t border-neutral-200 pt-3">
                  <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                    sample rendered
                  </p>
                  <p className="text-sm mt-1 whitespace-pre-wrap">{sampleRendered}</p>
                </div>
              )}
            </div>
          )}

          <div className="border border-neutral-200 sharp p-6 sticky top-6">
            <h3 className="font-display font-semibold tracking-tight">Throughput</h3>
            <p className="text-sm text-neutral-600 mt-2">
              Bulk sends are throttled at ~1 msg / 0.6s to reduce ban risk. Track progress
              in <span className="kbd">Message Logs</span>.
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

function Tab({ active, onClick, children, testId, icon }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors inline-flex items-center gap-2 ${
        active
          ? "border-[#1FA855] text-[#1FA855]"
          : "border-transparent text-neutral-600 hover:text-neutral-900"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}
