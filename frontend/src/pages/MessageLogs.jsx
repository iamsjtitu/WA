import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { ArrowsClockwise } from "@phosphor-icons/react";

const STATUSES = ["", "sent", "failed", "received", "queued"];
const DIRECTIONS = ["", "outbound", "inbound"];

export default function MessageLogs() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [direction, setDirection] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (filter) params.status = filter;
      if (direction) params.direction = direction;
      const { data } = await api.get("/messages", { params });
      setItems(data);
    } catch {}
    setLoading(false);
  }, [filter, direction]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = items.filter(
    (m) =>
      !q ||
      m.to?.includes(q) ||
      m.from?.includes(q) ||
      m.text?.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="p-10 fade-in">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Message Logs" sub="Search, filter, and audit every message — outbound &amp; inbound." />
        <button onClick={load} className="btn-ghost inline-flex items-center gap-2 text-sm" data-testid="logs-refresh-btn">
          <ArrowsClockwise size={14} /> Refresh
        </button>
      </div>

      <div className="mt-8 flex flex-wrap gap-2 items-center">
        <input
          data-testid="logs-search-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search recipient, sender, or text…"
          className="border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#1FA855] text-sm w-72"
        />
        <div className="flex gap-1">
          {DIRECTIONS.map((d) => (
            <button
              key={d || "any"}
              onClick={() => setDirection(d)}
              className={`px-3 py-2 sharp text-xs font-mono uppercase tracking-widest border ${
                direction === d
                  ? "border-[#1FA855] text-[#1FA855] bg-[#1FA855]/5"
                  : "border-neutral-200 text-neutral-600 hover:border-neutral-400"
              }`}
              data-testid={`logs-direction-${d || "any"}`}
            >
              {d || "any"}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {STATUSES.map((s) => (
            <button
              key={s || "all"}
              onClick={() => setFilter(s)}
              className={`px-3 py-2 sharp text-xs font-mono uppercase tracking-widest border ${
                filter === s
                  ? "border-[#1FA855] text-[#1FA855] bg-[#1FA855]/5"
                  : "border-neutral-200 text-neutral-600 hover:border-neutral-400"
              }`}
              data-testid={`logs-filter-${s || "all"}`}
            >
              {s || "all status"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 border border-neutral-200 sharp overflow-hidden">
        <table className="tbl">
          <thead>
            <tr>
              <th>Dir</th>
              <th>Status</th>
              <th>Peer</th>
              <th>Text</th>
              <th>Type</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="text-center text-neutral-500 font-mono text-xs">Loading…</td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center text-neutral-500 py-12">
                  No messages yet.
                </td>
              </tr>
            )}
            {filtered.map((m) => {
              const isInbound = m.direction === "inbound";
              const peer = isInbound ? m.from : m.to;
              return (
                <tr key={m.id} data-testid={`log-row-${m.id}`}>
                  <td>
                    <span
                      className={`status-pill ${
                        isInbound ? "!bg-blue-50 !border-blue-200 !text-blue-700" : ""
                      }`}
                    >
                      {isInbound ? "↓ in" : "↑ out"}
                    </span>
                  </td>
                  <td>
                    <span className="status-pill">
                      <span className={`dot ${m.status === "sent" || m.status === "received" ? "connected" : m.status}`} /> {m.status}
                    </span>
                  </td>
                  <td className="font-mono text-xs">{peer || "—"}</td>
                  <td className="max-w-md truncate text-sm">
                    {m.has_media && (
                      <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2 border border-neutral-200 px-1.5 py-0.5">
                        {m.type || "media"}
                      </span>
                    )}
                    {m.text || (m.has_media ? "(media)" : "")}
                  </td>
                  <td>
                    <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                      {m.source}
                    </span>
                  </td>
                  <td className="font-mono text-xs text-neutral-500 whitespace-nowrap">
                    {new Date(m.sent_at).toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
