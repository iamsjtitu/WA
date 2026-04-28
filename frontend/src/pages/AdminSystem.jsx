import { useCallback, useEffect, useRef, useState } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import {
  ArrowsClockwise,
  CloudArrowDown,
  GitBranch,
  Terminal,
  Warning,
  CheckCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

export default function AdminSystem() {
  const [status, setStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [log, setLog] = useState("");
  const [tailing, setTailing] = useState(false);
  const tailRef = useRef(null);
  const logBoxRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const { data } = await api.get("/admin/system/status");
      setStatus(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load system status");
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  const fetchLog = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/system/log?lines=300");
      setLog(data.log || "");
      // Auto-scroll to bottom
      setTimeout(() => {
        if (logBoxRef.current) {
          logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
        }
      }, 50);
    } catch (e) {
      // Log may not exist yet — ignore
    }
  }, []);

  const startTailing = useCallback(() => {
    setTailing(true);
    fetchLog();
    tailRef.current = setInterval(fetchLog, 3000);
  }, [fetchLog]);

  const stopTailing = useCallback(() => {
    setTailing(false);
    if (tailRef.current) {
      clearInterval(tailRef.current);
      tailRef.current = null;
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchLog();
    return () => stopTailing();
  }, [fetchStatus, fetchLog, stopTailing]);

  const onCheck = async () => {
    await fetchStatus();
    if (status?.behind_count > 0) {
      toast.success(`${status.behind_count} new commit(s) available`);
    } else if (status?.fetch_ok) {
      toast.success("Already up to date");
    }
  };

  const onUpdate = async () => {
    if (!confirm("Pull latest code from GitHub and restart services?")) return;
    setUpdating(true);
    try {
      const { data } = await api.post("/admin/system/update");
      toast.success(data.message || "Update started");
      startTailing();
      // After a few seconds, refresh status (which will show new commit)
      setTimeout(fetchStatus, 20000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed to start");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="p-8 space-y-8" data-testid="admin-system-page">
      <PageHeader
        title="System"
        sub="Pull the latest code from GitHub and restart your wa.9x.design services."
      />

      {/* Status card */}
      <div className="border border-neutral-200 sharp" data-testid="system-status-card">
        <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between">
          <h2 className="font-display font-semibold text-lg flex items-center gap-2">
            <GitBranch size={18} weight="duotone" />
            Git status
          </h2>
          <button
            onClick={onCheck}
            disabled={loadingStatus}
            className="px-3 py-1.5 text-sm border border-neutral-300 hover:border-neutral-900 sharp inline-flex items-center gap-2 disabled:opacity-50"
            data-testid="check-updates-btn"
          >
            <ArrowsClockwise size={14} className={loadingStatus ? "animate-spin" : ""} />
            Check for updates
          </button>
        </div>

        {loadingStatus && !status ? (
          <div className="px-6 py-8 text-sm text-neutral-500 font-mono">Loading…</div>
        ) : !status?.git_available ? (
          <div className="px-6 py-6 space-y-3" data-testid="not-git-banner">
            <div className="flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 px-4 py-3 sharp">
              <Warning size={18} weight="fill" className="text-amber-600 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Auto-update unavailable</div>
                <div className="text-amber-700 mt-1 font-mono text-xs">
                  {status?.reason ||
                    "This installation is not a Git checkout. Re-deploy your VPS using setup-vps.sh with --git <repo-url> to enable one-click updates."}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="px-6 py-5 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
            <Field label="Branch" value={status.branch || "—"} mono />
            <Field
              label="Current commit"
              value={status.short_commit || "—"}
              mono
              testid="current-commit"
            />
            <Field
              label="Last commit"
              value={(status.last_commit || "").split("|")[0] || "—"}
            />
            <Field
              label="Install dir"
              value={status.install_dir}
              mono
            />
            <div className="md:col-span-2 mt-1">
              {status.fetch_ok ? (
                status.behind_count > 0 ? (
                  <div
                    className="flex items-start gap-3 text-sm text-emerald-900 bg-emerald-50 border border-emerald-200 px-4 py-3 sharp"
                    data-testid="behind-banner"
                  >
                    <CloudArrowDown size={18} weight="fill" className="text-[#1FA855] shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <div className="font-medium">
                        {status.behind_count} new commit{status.behind_count > 1 ? "s" : ""} on origin/{status.branch}
                      </div>
                      {status.incoming_commits && (
                        <pre className="mt-2 font-mono text-[11px] text-emerald-800 whitespace-pre-wrap">
                          {status.incoming_commits}
                        </pre>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-sm text-emerald-800" data-testid="up-to-date-banner">
                    <CheckCircle size={16} weight="fill" className="text-[#1FA855]" />
                    Up to date with origin/{status.branch}
                  </div>
                )
              ) : (
                <div className="flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 px-4 py-3 sharp">
                  <Warning size={18} weight="fill" className="text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <div className="font-medium">Cannot reach origin</div>
                    <div className="font-mono text-xs mt-1 whitespace-pre-wrap">
                      {status.fetch_error || "Configure a remote: git remote add origin <repo-url>"}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {status?.git_available && (
          <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex items-center justify-between">
            <div className="text-xs text-neutral-500 font-mono">
              {status.last_update_at
                ? `Last update: ${new Date(status.last_update_at * 1000).toLocaleString()}`
                : "No previous updates recorded"}
            </div>
            <button
              onClick={onUpdate}
              disabled={updating || !status?.fetch_ok}
              className="px-4 py-2 text-sm bg-[#1FA855] text-white hover:bg-[#178c47] sharp inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              data-testid="update-now-btn"
            >
              <CloudArrowDown size={16} weight="fill" />
              {updating ? "Starting…" : "Update Now"}
            </button>
          </div>
        )}
      </div>

      {/* Log tail */}
      <div className="border border-neutral-200 sharp" data-testid="system-log-card">
        <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between">
          <h2 className="font-display font-semibold text-lg flex items-center gap-2">
            <Terminal size={18} weight="duotone" />
            Update log
            <span className="text-xs font-mono text-neutral-500">/var/log/wa9x-update.log</span>
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchLog}
              className="px-3 py-1.5 text-sm border border-neutral-300 hover:border-neutral-900 sharp inline-flex items-center gap-2"
              data-testid="refresh-log-btn"
            >
              <ArrowsClockwise size={14} />
              Refresh
            </button>
            {tailing ? (
              <button
                onClick={stopTailing}
                className="px-3 py-1.5 text-sm border border-red-300 text-red-700 hover:bg-red-50 sharp"
                data-testid="stop-tail-btn"
              >
                Stop tail
              </button>
            ) : (
              <button
                onClick={startTailing}
                className="px-3 py-1.5 text-sm border border-neutral-900 bg-neutral-900 text-white sharp hover:bg-neutral-800"
                data-testid="start-tail-btn"
              >
                Live tail
              </button>
            )}
          </div>
        </div>

        <div
          ref={logBoxRef}
          className="bg-neutral-950 text-emerald-300 font-mono text-xs p-4 overflow-auto max-h-[420px] min-h-[200px] whitespace-pre-wrap"
          data-testid="system-log-output"
        >
          {log || (
            <span className="text-neutral-600">
              No log output yet. Click <span className="text-neutral-300">Update Now</span> or{" "}
              <span className="text-neutral-300">Live tail</span> to begin.
            </span>
          )}
        </div>
      </div>

      <div className="text-xs text-neutral-500 font-mono leading-relaxed border-t border-neutral-200 pt-4">
        Tip: Auto-update runs <code>git pull</code> in <code>{status?.install_dir || "$INSTALL_DIR"}</code>,
        re-installs deps if package files changed, rebuilds the frontend, and restarts the backend
        via <code>{`supervisorctl restart wa9x-backend`}</code>. The backend will be unavailable for
        ~10–30 seconds during the restart.
      </div>
    </div>
  );
}

function Field({ label, value, mono, testid }) {
  return (
    <div>
      <div className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div
        className={`mt-1 ${mono ? "font-mono" : ""} text-neutral-900 break-all`}
        data-testid={testid}
      >
        {value}
      </div>
    </div>
  );
}
