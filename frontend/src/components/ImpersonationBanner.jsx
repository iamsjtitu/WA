import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Eye, X } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ImpersonationBanner() {
  const { user, exitImpersonation } = useAuth();
  const navigate = useNavigate();

  if (!user?.impersonated_by) return null;

  const onExit = async () => {
    try {
      await exitImpersonation();
      toast.success("Returned to admin");
      navigate("/app/customers", { replace: true });
    } catch {
      toast.error("Could not exit impersonation");
    }
  };

  return (
    <div
      className="bg-yellow-400 text-black px-6 py-2.5 flex items-center justify-between gap-4 border-b-2 border-yellow-500"
      data-testid="impersonation-banner"
    >
      <div className="flex items-center gap-2 text-sm">
        <Eye size={16} weight="fill" />
        <span>
          You are impersonating <strong>{user.name}</strong> ({user.email}) — actions are logged
          to <span className="font-mono text-xs">/api/admin/audit-logs</span>.
        </span>
      </div>
      <button
        onClick={onExit}
        className="bg-black text-yellow-400 hover:bg-neutral-900 sharp px-3 py-1.5 text-xs font-mono uppercase tracking-widest inline-flex items-center gap-1.5 transition-colors"
        data-testid="exit-impersonation-btn"
      >
        <X size={12} /> Exit Impersonation
      </button>
    </div>
  );
}
