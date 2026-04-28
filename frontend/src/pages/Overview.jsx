import { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import api from "../lib/api";
import { Link } from "react-router-dom";
import { ArrowRight, Plugs, PaperPlaneTilt, Code, ChartLineUp } from "@phosphor-icons/react";

export default function Overview() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api
      .get(isAdmin ? "/admin/stats" : "/me/stats")
      .then((r) => setStats(r.data))
      .catch(() => setStats({}));
  }, [isAdmin]);

  return (
    <div className="p-10 fade-in">
      <PageHeader
        title={`Hello, ${user?.name?.split(" ")[0] || "there"}.`}
        sub={isAdmin ? "Platform overview." : "Your account at a glance."}
      />

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-0 mt-8 border border-neutral-200">
        {isAdmin ? (
          <>
            <Stat label="customers" value={stats?.customers ?? "—"} />
            <Stat label="active sessions" value={stats?.sessions ?? "—"} border />
            <Stat label="msgs today" value={stats?.messages_today ?? "—"} border />
            <Stat label="msgs total" value={stats?.messages_total ?? "—"} border />
          </>
        ) : (
          <>
            <Stat label="sessions" value={stats?.sessions ?? "—"} />
            <Stat label="msgs today" value={stats?.messages_today ?? "—"} border />
            <Stat label="msgs total" value={stats?.messages_total ?? "—"} border />
            <Stat
              label="quota used"
              value={`${stats?.quota_used ?? 0}/${stats?.quota_monthly ?? 0}`}
              border
            />
          </>
        )}
      </div>

      {!isAdmin && stats?.quota_monthly ? (
        <div className="mt-8 border border-neutral-200 sharp p-6">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              monthly quota
            </span>
            <span className="font-mono text-xs">
              {stats.quota_used} / {stats.quota_monthly}
            </span>
          </div>
          <div className="h-2 bg-neutral-100 sharp overflow-hidden">
            <div
              className="h-full bg-[#1FA855]"
              style={{
                width: `${Math.min(100, ((stats.quota_used / stats.quota_monthly) * 100) || 0)}%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <h2 className="font-display text-2xl mt-12 tracking-tight">Quick actions</h2>
      <div className="grid md:grid-cols-3 gap-0 mt-4 border border-neutral-200">
        <ActionCard
          to="/app/sessions/new"
          icon={<Plugs size={22} weight="fill" />}
          title="Connect a WhatsApp number"
          body="Scan a QR or pair via phone number to link a new service."
        />
        <ActionCard
          to="/app/send"
          icon={<PaperPlaneTilt size={22} weight="fill" />}
          title="Send a message"
          body="Compose & send to a single recipient."
          border
        />
        <ActionCard
          to="/app/docs"
          icon={<Code size={22} weight="fill" />}
          title="Read API docs"
          body="Integrate via REST in 5 minutes."
          border
        />
      </div>

      {isAdmin && (
        <div className="mt-12 border border-neutral-200 sharp p-6 flex items-start gap-4">
          <ChartLineUp size={24} weight="fill" color="#1FA855" />
          <div>
            <h3 className="font-display font-semibold text-lg tracking-tight">Reseller mode</h3>
            <p className="text-sm text-neutral-600 mt-1">
              Add customers from the Customers page. Each gets their own API key, quota, and dashboard view.
            </p>
            <Link
              to="/app/customers"
              className="btn-ghost text-sm inline-flex items-center gap-2 mt-3"
              data-testid="overview-go-customers"
            >
              Manage customers <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export function PageHeader({ title, sub }) {
  return (
    <div>
      <h1 className="font-display text-4xl tracking-tight" data-testid="page-title">{title}</h1>
      {sub && <p className="text-neutral-600 mt-2">{sub}</p>}
    </div>
  );
}

function Stat({ label, value, border }) {
  return (
    <div className={`p-6 ${border ? "md:border-l border-neutral-200" : ""}`}>
      <div className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className="font-display font-bold text-3xl mt-2 tracking-tight">{value}</div>
    </div>
  );
}

function ActionCard({ to, icon, title, body, border }) {
  return (
    <Link
      to={to}
      className={`p-6 hover:bg-neutral-50 transition-colors flex flex-col gap-3 ${
        border ? "md:border-l border-neutral-200" : ""
      }`}
    >
      <div className="w-10 h-10 bg-[#1FA855]/10 text-[#1FA855] flex items-center justify-center sharp">
        {icon}
      </div>
      <h3 className="font-display font-semibold text-lg tracking-tight">{title}</h3>
      <p className="text-sm text-neutral-600">{body}</p>
      <span className="text-sm text-[#1FA855] inline-flex items-center gap-1 mt-1">
        Go <ArrowRight size={14} />
      </span>
    </Link>
  );
}
