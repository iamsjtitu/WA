import { NavLink, Outlet, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  ChatCircle,
  Gauge,
  Plugs,
  PaperPlaneTilt,
  ListBullets,
  Code,
  Users,
  Gear,
  SignOut,
  PaperPlane,
  Tag,
  CreditCard,
} from "@phosphor-icons/react";

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const isAdmin = user?.role === "admin";

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const items = [
    { to: "/app", label: "Overview", icon: Gauge, end: true, key: "overview" },
    { to: "/app/sessions", label: "Services", icon: Plugs, key: "sessions" },
    { to: "/app/send", label: "Send Message", icon: PaperPlaneTilt, key: "send" },
    { to: "/app/bulk", label: "Bulk Campaign", icon: PaperPlane, key: "bulk" },
    { to: "/app/logs", label: "Message Logs", icon: ListBullets, key: "logs" },
    { to: "/app/docs", label: "API Docs", icon: Code, key: "docs" },
    ...(isAdmin
      ? [
          { to: "/app/customers", label: "Customers", icon: Users, key: "customers" },
          { to: "/app/plans", label: "Plans", icon: Tag, key: "plans" },
        ]
      : [{ to: "/app/billing", label: "Billing", icon: CreditCard, key: "billing" }]),
    { to: "/app/settings", label: "Settings", icon: Gear, key: "settings" },
  ];

  return (
    <div className="min-h-screen bg-white text-neutral-950 grid grid-cols-[260px_1fr]">
      <aside className="border-r border-neutral-200 bg-neutral-50 flex flex-col" data-testid="dashboard-sidebar">
        <Link to="/" className="px-5 h-16 border-b border-neutral-200 flex items-center gap-2" data-testid="sidebar-brand">
          <div className="w-8 h-8 bg-[#1FA855] flex items-center justify-center sharp">
            <ChatCircle weight="fill" size={18} color="#fff" />
          </div>
          <span className="font-display font-bold text-lg tracking-tight">wa.9x.design</span>
        </Link>

        <nav className="px-3 py-4 flex-1 space-y-0.5">
          {items.map(({ to, label, icon: Icon, end, key }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `side-item ${isActive ? "active" : ""}`}
              data-testid={`nav-${key}`}
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-neutral-200 p-3">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-9 h-9 bg-[#1FA855] text-white flex items-center justify-center sharp font-display font-semibold">
              {(user?.name || "U").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate" data-testid="user-name">{user?.name}</div>
              <div className="text-[11px] text-neutral-500 font-mono truncate">{user?.email}</div>
            </div>
            <button
              onClick={onLogout}
              className="p-2 hover:bg-neutral-200 sharp"
              title="Sign out"
              data-testid="logout-button"
            >
              <SignOut size={16} />
            </button>
          </div>
          {isAdmin && (
            <div className="px-2 mt-1">
              <span className="status-pill" data-testid="admin-badge">
                <span className="dot connected" /> admin
              </span>
            </div>
          )}
        </div>
      </aside>

      <main className="min-h-screen overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
