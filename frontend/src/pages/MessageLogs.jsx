import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { ArrowsClockwise } from "@phosphor-icons/react";

const STATUSES = ["", "sent", "failed", "queued"];

export default function MessageLogs() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/messages", {
        params: filter ? { status: filter, limit: 200 } : { limit: 200 },
      });
      setItems(data);
    } catch {}
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = items.filter(
    (m) =>
      !q ||
      m.to?.includes(q) ||
      m.text?.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="p-10 fade-in">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Message Logs" sub="Search, filter, and audit every message sent through your account." />
        <button onClick={load} className="btn-ghost inline-flex items-center gap-2 text-sm" data-testid="logs-refresh-btn">
          <ArrowsClockwise size={14} /> Refresh
        </button>
      </div>

      <div className="mt-8 flex flex-wrap gap-2 items-center">
        <input
          data-testid="logs-search-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search recipient or text…"
          className="border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] text-sm w-72"
        />
        <div className="flex gap-1">
          {STATUSES.map((s) => (
            <button
              key={s || "all"}
              onClick={() => setFilter(s)}
              className={`px-3 py-2 sharp text-xs font-mono uppercase tracking-widest border ${
                filter === s
                  ? "border-[#002FA7] text-[#002FA7] bg-[#002FA7]/5"
                  : "border-neutral-200 text-neutral-600 hover:border-neutral-400"
              }`}
              data-testid={`logs-filter-${s || "all"}`}
            >
              {s || "all"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 border border-neutral-200 sharp overflow-hidden">
        <table className="tbl">
          <thead>
            <tr>
              <th>Status</th>
              <th>To</th>
              <th>Text</th>
              <th>Source</th>
              <th>Sent</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 font-mono text-xs">Loading…</td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 py-12">
                  No messages yet.
                </td>
              </tr>
            )}
            {filtered.map((m) => (
              <tr key={m.id} data-testid={`log-row-${m.id}`}>
                <td>
                  <span className="status-pill">
                    <span className={`dot ${m.status === "sent" ? "connected" : m.status}`} /> {m.status}
                  </span>
                </td>
                <td className="font-mono text-xs">{m.to}</td>
                <td className="max-w-md truncate text-sm">{m.text}</td>
                <td>
                  <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                    {m.source}
                  </span>
                </td>
                <td className="font-mono text-xs text-neutral-500 whitespace-nowrap">
                  {new Date(m.sent_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
