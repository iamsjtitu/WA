import { useEffect, useState, useMemo } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import {
  ChartLineUp,
  ArrowsClockwise,
  Warning,
  CheckCircle,
} from "@phosphor-icons/react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

const WINDOWS = [
  { key: "5m", label: "Last 5 min", bucket: 1 },
  { key: "1h", label: "Last hour", bucket: 1 },
  { key: "6h", label: "Last 6h", bucket: 5 },
  { key: "24h", label: "Last 24h", bucket: 15 },
  { key: "7d", label: "Last 7 days", bucket: 60 },
];

export default function AdminReliability() {
  const [window, setWindow] = useState("1h");
  const [sessionId, setSessionId] = useState("");
  const [sessions, setSessions] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(true);

  const bucket = useMemo(
    () => WINDOWS.find((w) => w.key === window)?.bucket || 1,
    [window]
  );

  const load = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ window, bucket_minutes: String(bucket) });
      if (sessionId) qs.set("session_id", sessionId);
      const { data: d } = await api.get(`/admin/reliability?${qs.toString()}`);
      setData(d);
    } catch (e) {
      toast.error("Failed to load reliability stats");
    }
    setLoading(false);
  };

  const loadSessions = async () => {
    try {
      const { data: ss } = await api.get("/admin/sessions");
      setSessions(ss || []);
    } catch {
      /* ignore — session filter is optional */
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    load();
  }, [window, sessionId]);

  // Auto-refresh every 15s for 5m/1h windows, 60s for others
  useEffect(() => {
    if (!auto) return;
    const period = window === "5m" || window === "1h" ? 15000 : 60000;
    const t = setInterval(load, period);
    return () => clearInterval(t);
  }, [auto, window, sessionId]);

  return (
    <div className="space-y-6" data-testid="admin-reliability">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display font-semibold tracking-tight text-3xl">
            API Reliability
          </h1>
          <p className="text-sm text-neutral-600 mt-1">
            Live telemetry of every <code className="font-mono text-xs bg-neutral-100 px-1.5">/api/v1/*</code> +
            <code className="font-mono text-xs bg-neutral-100 px-1.5 ml-1">/api/v2/*</code> request. 7-day retention.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={window}
            onChange={(e) => setWindow(e.target.value)}
            className="border border-neutral-300 sharp px-3 py-1.5 text-sm font-mono"
            data-testid="reliability-window"
          >
            {WINDOWS.map((w) => (
              <option key={w.key} value={w.key}>
                {w.label}
              </option>
            ))}
          </select>
          <select
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            className="border border-neutral-300 sharp px-3 py-1.5 text-sm font-mono max-w-[260px]"
            data-testid="reliability-session"
          >
            <option value="">All sessions</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || s.id.slice(0, 8)} · {s.customer}
              </option>
            ))}
          </select>
          <label className="text-xs font-mono text-neutral-600 flex items-center gap-1.5 select-none">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
              data-testid="reliability-autorefresh"
            />
            Auto
          </label>
          <button
            onClick={load}
            disabled={loading}
            className="btn-ghost text-xs inline-flex items-center gap-1 disabled:opacity-50"
            data-testid="reliability-refresh"
          >
            <ArrowsClockwise size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={<ChartLineUp size={20} />}
              label="Total requests"
              value={data.total.toLocaleString()}
              testId="stat-total"
            />
            <StatCard
              icon={
                data.success_rate >= 99 ? (
                  <CheckCircle size={20} weight="fill" color="#10B981" />
                ) : (
                  <Warning size={20} weight="fill" color="#F59E0B" />
                )
              }
              label="Success rate"
              value={`${data.success_rate.toFixed(1)}%`}
              accent={data.success_rate >= 99 ? "emerald" : "amber"}
              testId="stat-success-rate"
            />
            <StatCard
              label="Client errors (4xx)"
              value={data.client_errors.toLocaleString()}
              accent={data.client_errors ? "amber" : "neutral"}
              testId="stat-4xx"
            />
            <StatCard
              label="Server errors (5xx)"
              value={data.server_errors.toLocaleString()}
              accent={data.server_errors ? "red" : "neutral"}
              testId="stat-5xx"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard label="Latency p50" value={`${data.latency.p50} ms`} testId="stat-p50" />
            <StatCard label="Latency p95" value={`${data.latency.p95} ms`} testId="stat-p95" />
            <StatCard label="Latency p99" value={`${data.latency.p99} ms`} testId="stat-p99" />
          </div>

          <div className="border border-neutral-200 sharp p-4" data-testid="reliability-chart">
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 mb-3">
              request volume · {WINDOWS.find((w) => w.key === window)?.label}
            </p>
            {data.series.length === 0 ? (
              <div className="text-sm text-neutral-500 font-mono py-10 text-center">
                No traffic yet in this window.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={data.series}>
                  <defs>
                    <linearGradient id="okGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10B981" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#10B981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="err4Grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#F59E0B" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#F59E0B" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="err5Grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#EF4444" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#EF4444" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis
                    dataKey="t"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(t) =>
                      new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                    }
                  />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 0 }}
                    labelFormatter={(t) => new Date(t).toLocaleString()}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="ok" name="2xx OK" stroke="#10B981" fill="url(#okGrad)" stackId="1" />
                  <Area type="monotone" dataKey="err_4xx" name="4xx Client" stroke="#F59E0B" fill="url(#err4Grad)" stackId="1" />
                  <Area type="monotone" dataKey="err_5xx" name="5xx Server" stroke="#EF4444" fill="url(#err5Grad)" stackId="1" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title="Top failing routes" testId="top-routes">
              {data.top_failing_routes.length === 0 ? (
                <EmptyRow label="No failing routes 🎉" />
              ) : (
                data.top_failing_routes.map((r) => (
                  <div
                    key={r.route}
                    className="py-2 flex items-center justify-between gap-3"
                    data-testid={`route-row-${r.route}`}
                  >
                    <span className="font-mono text-sm truncate">/{r.route}</span>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="font-mono text-xs text-neutral-500">{r.total} req</span>
                      <span
                        className={`font-mono text-xs px-1.5 py-0.5 sharp ${
                          r.fail_rate >= 20
                            ? "bg-red-100 text-red-700"
                            : r.fail_rate >= 5
                            ? "bg-amber-100 text-amber-700"
                            : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {r.fail_rate}% fail
                      </span>
                    </div>
                  </div>
                ))
              )}
            </Panel>

            <Panel title="Status code breakdown" testId="status-breakdown">
              {Object.keys(data.by_status).length === 0 ? (
                <EmptyRow label="No requests in this window" />
              ) : (
                Object.entries(data.by_status)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([code, count]) => (
                    <div
                      key={code}
                      className="py-2 flex items-center justify-between gap-3"
                      data-testid={`status-row-${code}`}
                    >
                      <span
                        className={`font-mono text-sm ${
                          Number(code) < 300
                            ? "text-emerald-700"
                            : Number(code) < 500
                            ? "text-amber-700"
                            : "text-red-700"
                        }`}
                      >
                        HTTP {code}
                      </span>
                      <span className="font-mono text-sm">{count}</span>
                    </div>
                  ))
              )}
            </Panel>
          </div>

          {!sessionId && data.per_session.length > 0 && (
            <Panel title="Per-session activity (top 20)" testId="per-session">
              <div className="grid grid-cols-[1fr,auto,auto,auto] gap-x-4 gap-y-2 items-center">
                <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">Session</span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 text-right">Requests</span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 text-right">Failed</span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 text-right">Rate</span>
                {data.per_session.map((r) => (
                  <PerSessionRow key={r.session_id} row={r} sessions={sessions} />
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function PerSessionRow({ row, sessions }) {
  const s = sessions.find((x) => x.id === row.session_id);
  const label = row.session_id === "master" ? "master key" : (s ? `${s.name} · ${s.customer}` : row.session_id.slice(0, 8));
  return (
    <>
      <span className="font-mono text-xs truncate" title={row.session_id}>{label}</span>
      <span className="font-mono text-xs text-right">{row.total}</span>
      <span className="font-mono text-xs text-right">{row.failed}</span>
      <span className={`font-mono text-xs text-right ${row.fail_rate >= 20 ? "text-red-600" : row.fail_rate >= 5 ? "text-amber-600" : "text-emerald-600"}`}>
        {row.fail_rate}%
      </span>
    </>
  );
}

function StatCard({ icon, label, value, accent = "neutral", testId }) {
  const accents = {
    neutral: "border-neutral-200",
    emerald: "border-emerald-300",
    amber: "border-amber-300",
    red: "border-red-300",
  };
  return (
    <div
      className={`border sharp p-4 bg-white ${accents[accent]}`}
      data-testid={testId}
    >
      <div className="flex items-center gap-2 text-neutral-500">
        {icon}
        <span className="font-mono text-[10px] uppercase tracking-widest">{label}</span>
      </div>
      <p className="font-display font-semibold text-2xl mt-2">{value}</p>
    </div>
  );
}

function Panel({ title, children, testId }) {
  return (
    <div className="border border-neutral-200 sharp p-4" data-testid={testId}>
      <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 mb-3">
        {title}
      </p>
      <div className="divide-y divide-neutral-100">{children}</div>
    </div>
  );
}

function EmptyRow({ label }) {
  return <div className="py-6 text-center text-sm text-neutral-500 font-mono">{label}</div>;
}
