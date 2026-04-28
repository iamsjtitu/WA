import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { Plus, Trash, ArrowsClockwise, X } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

export default function Sessions() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [qrModal, setQrModal] = useState(null); // {session, qr, status, phone}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/sessions");
      setSessions(data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const create = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/sessions", { name: newName.trim() });
      toast.success("Session starting — open QR to scan");
      setShowCreate(false);
      setNewName("");
      await load();
      openQr(data.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create session");
    }
    setBusy(false);
  };

  const remove = async (s) => {
    if (!confirm(`Delete session "${s.name}"? This will logout WhatsApp.`)) return;
    try {
      await api.delete(`/sessions/${s.id}`);
      toast.success("Session removed");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  const restart = async (s) => {
    try {
      await api.post(`/sessions/${s.id}/restart`);
      toast.success("Session restarted");
      openQr(s.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restart failed");
    }
  };

  const openQr = async (sessionId) => {
    setQrModal({ id: sessionId, qr: null, status: "starting", phone: null });
    let cancel = false;
    const tick = async () => {
      if (cancel) return;
      try {
        const { data } = await api.get(`/sessions/${sessionId}/status`);
        setQrModal((m) => (m && m.id === sessionId ? { ...m, qr: data.qr, status: data.status, phone: data.phone } : m));
        if (data.status === "connected") {
          toast.success("WhatsApp linked");
          await load();
          return;
        }
      } catch {}
      setTimeout(tick, 2000);
    };
    tick();
    return () => {
      cancel = true;
    };
  };

  return (
    <div className="p-10 fade-in">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="WhatsApp Services" sub="Each linked WhatsApp number runs as its own service. Click a row to manage." />
        <Link
          to="/app/sessions/new"
          className="btn-brand inline-flex items-center gap-2"
          data-testid="new-session-btn"
        >
          <Plus size={16} /> New Service
        </Link>
      </div>

      <div className="mt-8 border border-neutral-200 sharp overflow-hidden">
        <table className="tbl">
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Created</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 font-mono text-xs">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && sessions.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 py-12">
                  <div className="font-mono text-xs uppercase tracking-widest">no sessions yet</div>
                  <div className="text-sm mt-2">Click <span className="kbd">New session</span> to link your first WhatsApp number.</div>
                </td>
              </tr>
            )}
            {sessions.map((s) => (
              <tr key={s.id} data-testid={`session-row-${s.id}`} className="hover:bg-neutral-50 cursor-pointer" onClick={() => window.location.assign(`/app/sessions/${s.id}`)}>
                <td className="font-medium">
                  <span className="hover:underline">{s.name}</span>
                </td>
                <td className="font-mono text-xs">{s.phone || "—"}</td>
                <td>
                  <span className="status-pill">
                    <span className={`dot ${s.status}`} /> {s.status}
                  </span>
                </td>
                <td className="font-mono text-xs text-neutral-500">
                  {new Date(s.created_at).toLocaleString()}
                </td>
                <td className="text-right">
                  <div className="inline-flex gap-2" onClick={(e) => e.stopPropagation()}>
                    {s.status !== "connected" && (
                      <button
                        onClick={() => openQr(s.id)}
                        className="btn-ghost text-xs"
                        data-testid={`session-qr-${s.id}`}
                      >
                        Show QR
                      </button>
                    )}
                    <button
                      onClick={() => restart(s)}
                      className="btn-ghost text-xs inline-flex items-center gap-1"
                      data-testid={`session-restart-${s.id}`}
                      title="Restart"
                    >
                      <ArrowsClockwise size={14} />
                    </button>
                    <button
                      onClick={() => remove(s)}
                      className="btn-ghost text-xs inline-flex items-center gap-1 hover:!border-red-500 hover:!text-red-600"
                      data-testid={`session-delete-${s.id}`}
                    >
                      <Trash size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <Modal onClose={() => setShowCreate(false)} title="Link a new WhatsApp number">
          <form onSubmit={create} data-testid="session-create-form" className="space-y-4">
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Name (label)
              </label>
              <input
                data-testid="session-name-input"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
                placeholder="e.g. Sales line"
                className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn-ghost text-sm" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
              <button type="submit" disabled={busy} className="btn-brand text-sm disabled:opacity-50" data-testid="session-create-submit">
                {busy ? "Starting…" : "Start session"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {qrModal && (
        <Modal onClose={() => setQrModal(null)} title="Scan with WhatsApp">
          <div className="flex flex-col items-center" data-testid="qr-modal">
            <ol className="font-mono text-xs text-neutral-600 list-decimal pl-5 space-y-1 self-start">
              <li>Open WhatsApp on your phone</li>
              <li>Tap <span className="kbd">Settings</span> → <span className="kbd">Linked Devices</span></li>
              <li>Scan the QR below</li>
            </ol>

            <div className="mt-6 w-64 h-64 border border-neutral-200 sharp flex items-center justify-center bg-white">
              {qrModal.status === "connected" ? (
                <div className="text-center">
                  <div className="dot connected mx-auto" />
                  <p className="font-display font-semibold mt-3">Connected</p>
                  <p className="font-mono text-xs text-neutral-500 mt-1">{qrModal.phone}</p>
                </div>
              ) : qrModal.qr ? (
                <img src={qrModal.qr} alt="QR" className="w-full h-full" />
              ) : (
                <div className="text-center">
                  <div className="dot connecting mx-auto" />
                  <p className="font-mono text-xs text-neutral-500 mt-3">
                    {qrModal.status === "starting" ? "starting…" : qrModal.status}
                  </p>
                </div>
              )}
            </div>

            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 mt-4">
              status: <span className="text-neutral-900">{qrModal.status}</span>
            </p>
            <button onClick={() => setQrModal(null)} className="btn-ghost text-sm mt-6" data-testid="qr-close-btn">
              Close
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

import { createPortal } from "react-dom";

export function Modal({ children, title, onClose }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" data-testid="modal-backdrop">
      <div className="bg-white sharp w-full max-w-md border border-neutral-200 shadow-xl flex flex-col max-h-[calc(100vh-2rem)]">
        <div className="flex items-center justify-between px-5 h-12 border-b border-neutral-200 shrink-0">
          <h3 className="font-display font-semibold tracking-tight">{title}</h3>
          <button onClick={onClose} className="p-1 hover:bg-neutral-100 sharp" data-testid="modal-close">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body
  );
}
