import { useEffect, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../lib/api";
import { Modal } from "./Sessions";
import {
  ArrowLeft,
  Copy,
  ArrowsClockwise,
  Trash,
  PaperPlaneTilt,
  Plug,
  Plugs,
  Calendar,
  ArrowUp,
  X,
} from "@phosphor-icons/react";
import { toast } from "sonner";

export default function SessionDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [received, setReceived] = useState([]);
  const [sent, setSent] = useState([]);
  const [qrModal, setQrModal] = useState(null);

  // send form
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [link, setLink] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [sRes, recRes, sentRes] = await Promise.all([
        api.get(`/sessions/${id}/status`),
        api.get(`/sessions/${id}/messages`, { params: { direction: "inbound", limit: 20 } }),
        api.get(`/sessions/${id}/messages`, { params: { direction: "outbound", limit: 20 } }),
      ]);
      setSession(sRes.data);
      setReceived(recRes.data);
      setSent(sentRes.data);
    } catch (e) {
      if (e?.response?.status === 404) {
        toast.error("Session not found");
        navigate("/app/sessions", { replace: true });
      }
    }
  }, [id, navigate]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const copy = (txt) => {
    navigator.clipboard.writeText(txt);
    toast.success("Copied");
  };

  const sendMsg = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (link) {
        // use v2 sendMessage with url
        const fd = new FormData();
        fd.append("phonenumber", to);
        fd.append("text", text);
        fd.append("url", link);
        if (scheduleAt) {
          // convert datetime-local to "MM-DD-YYYY HH:MM"
          const d = new Date(scheduleAt);
          const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
          const dd = String(d.getUTCDate()).padStart(2, "0");
          const yyyy = d.getUTCFullYear();
          const hh = String(d.getUTCHours()).padStart(2, "0");
          const mi = String(d.getUTCMinutes()).padStart(2, "0");
          fd.append("delay", `${mm}-${dd}-${yyyy} ${hh}:${mi}`);
        }
        const { data } = await api.post("/v2/sendMessage", fd, {
          headers: {
            Authorization: `Bearer ${user.api_key}`,
            "Content-Type": "multipart/form-data",
          },
        });
        if (data?.success) {
          toast.success(scheduleAt ? "Scheduled" : "Sent");
        } else {
          toast.error(data?.error || "Failed");
        }
      } else if (scheduleAt) {
        const fd = new FormData();
        fd.append("phonenumber", to);
        fd.append("text", text);
        const d = new Date(scheduleAt);
        const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
        const dd = String(d.getUTCDate()).padStart(2, "0");
        const yyyy = d.getUTCFullYear();
        const hh = String(d.getUTCHours()).padStart(2, "0");
        const mi = String(d.getUTCMinutes()).padStart(2, "0");
        fd.append("delay", `${mm}-${dd}-${yyyy} ${hh}:${mi}`);
        await api.post("/v2/sendMessage", fd, {
          headers: {
            Authorization: `Bearer ${user.api_key}`,
            "Content-Type": "multipart/form-data",
          },
        });
        toast.success("Scheduled");
      } else {
        const { data } = await api.post("/messages/send", {
          session_id: id,
          to,
          text,
        });
        if (data.status === "sent") toast.success("Sent");
        else toast.error(data.error || "Failed");
      }
      setText("");
      setLink("");
      setScheduleAt("");
      setShowSchedule(false);
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.response?.data?.error || "Failed");
    }
    setBusy(false);
  };

  const restart = async () => {
    try {
      await api.post(`/sessions/${id}/restart`);
      toast.success("Restarted");
      openQr();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const disconnect = async () => {
    if (!confirm("Disconnect this WhatsApp number?")) return;
    try {
      await api.delete(`/sessions/${id}`);
      toast.success("Disconnected");
      navigate("/app/sessions");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const openQr = async () => {
    setQrModal({ status: "starting", qr: null });
    let cancel = false;
    const tick = async () => {
      if (cancel) return;
      try {
        const { data } = await api.get(`/sessions/${id}/status`);
        setQrModal((m) => (m ? { ...m, qr: data.qr, status: data.status } : m));
        if (data.status === "connected") {
          toast.success("Connected");
          refresh();
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

  const updateSetting = async (patch) => {
    try {
      const { data } = await api.patch(`/sessions/${id}/settings`, patch);
      setSession((s) => ({ ...s, ...data }));
      toast.success("Saved");
    } catch (e) {
      toast.error("Failed");
    }
  };

  if (!session) {
    return <div className="p-10 text-neutral-500 font-mono text-sm">Loading…</div>;
  }

  const isConnected = session.status === "connected";

  return (
    <div className="p-10 fade-in" data-testid="session-detail">
      <Link
        to="/app/sessions"
        className="inline-flex items-center gap-1.5 text-sm text-neutral-600 hover:text-neutral-950"
        data-testid="back-to-sessions"
      >
        <ArrowLeft size={14} /> Sessions
      </Link>
      <h1 className="font-display text-4xl tracking-tight mt-3">{session.name}</h1>

      {/* Top stat cards */}
      <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-4 gap-0 border border-neutral-200">
        <Card label="service id" value={`#${session.id.slice(0, 6)}`} />
        <Card
          label="connected number"
          value={session.phone || "—"}
          mono
          border
        />
        <Card label="status" border>
          <span className="status-pill mt-1.5">
            <span className={`dot ${session.status}`} /> {session.status}
          </span>
        </Card>
        <Card label="quota" value={`${user?.quota_used}/${user?.quota_monthly}`} mono border />
      </div>

      {/* API Key + Connection Status row */}
      <div className="mt-6 grid lg:grid-cols-2 gap-6">
        <div className="border border-neutral-200 sharp p-6" data-testid="api-key-card">
          <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">api key</p>
          <code className="block mt-2 font-mono text-sm bg-neutral-100 border border-neutral-200 sharp p-3 break-all">
            {user?.api_key}
          </code>
          <div className="flex gap-2 mt-3">
            <button onClick={() => copy(user?.api_key)} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="copy-api-key">
              <Copy size={14} /> Copy
            </button>
            <Link
              to="/app/docs"
              className="btn-ghost text-sm inline-flex items-center gap-2"
              data-testid="view-docs"
            >
              View API docs
            </Link>
          </div>
          <p className="text-xs text-neutral-500 mt-3 font-mono">
            Use as <span className="kbd">Authorization: Bearer …</span>
          </p>
        </div>

        <div className="border border-neutral-200 sharp p-6">
          <div className="flex items-center justify-between">
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              connection status
            </p>
            <div className="flex gap-2">
              {!isConnected && (
                <button
                  onClick={openQr}
                  className="btn-ghost text-xs inline-flex items-center gap-1"
                  data-testid="show-qr-btn"
                >
                  <Plug size={12} /> Show QR
                </button>
              )}
              <button
                onClick={restart}
                className="btn-ghost text-xs inline-flex items-center gap-1"
                data-testid="restart-btn"
                title="Restart"
              >
                <ArrowsClockwise size={12} />
              </button>
              <button
                onClick={disconnect}
                className="btn-ghost text-xs hover:!border-red-500 hover:!text-red-600 inline-flex items-center gap-1"
                data-testid="disconnect-btn"
              >
                <Plugs size={12} /> Disconnect
              </button>
            </div>
          </div>
          <div className={`mt-4 border sharp p-3 ${isConnected ? "border-emerald-200 bg-emerald-50" : "border-yellow-200 bg-yellow-50"}`}>
            <div className="flex items-center gap-2">
              <span className={`dot ${session.status}`} />
              <span className="font-display font-semibold text-sm">
                {isConnected ? "Connection is active" : `Status: ${session.status}`}
              </span>
            </div>
            <p className="font-mono text-xs text-neutral-600 mt-1">
              WhatsApp · {session.phone || "—"}
            </p>
          </div>
        </div>
      </div>

      {/* Received / Sent / Send 3-column */}
      <div className="mt-8 grid lg:grid-cols-3 gap-6">
        {/* Received */}
        <div className="border border-neutral-200 sharp">
          <div className="px-4 py-3 border-b border-neutral-200 flex items-center justify-between">
            <h3 className="font-display font-semibold text-sm">Received Messages</h3>
            <button onClick={refresh} className="p-1 hover:bg-neutral-100 sharp" data-testid="refresh-received">
              <ArrowsClockwise size={14} />
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto" data-testid="received-list">
            {received.length === 0 ? (
              <p className="p-4 text-sm text-neutral-500">No received messages yet.</p>
            ) : (
              received.map((m) => (
                <div key={m.id} className="px-4 py-3 border-b border-neutral-100 last:border-b-0">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-neutral-500">
                      {new Date(m.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className="font-mono text-xs">↓ {m.from}</span>
                  </div>
                  <p className="text-sm mt-1 truncate">
                    {m.has_media && (
                      <span className="text-[10px] uppercase tracking-widest text-neutral-500 mr-1 border border-neutral-200 px-1">
                        {m.type}
                      </span>
                    )}
                    {m.text || "(media)"}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Sent */}
        <div className="border border-neutral-200 sharp">
          <div className="px-4 py-3 border-b border-neutral-200 flex items-center justify-between">
            <h3 className="font-display font-semibold text-sm">Sent Messages</h3>
            <button onClick={refresh} className="p-1 hover:bg-neutral-100 sharp" data-testid="refresh-sent">
              <ArrowsClockwise size={14} />
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto" data-testid="sent-list">
            {sent.length === 0 ? (
              <p className="p-4 text-sm text-neutral-500">No sent messages yet.</p>
            ) : (
              sent.map((m) => (
                <div key={m.id} className="px-4 py-3 border-b border-neutral-100 last:border-b-0">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-neutral-500">
                      {new Date(m.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className={`font-mono text-xs ${m.status === "sent" ? "" : "text-red-600"}`}>
                      {m.status === "sent" ? "✓" : "✕"} ↑ {m.to}
                    </span>
                  </div>
                  <p className="text-sm mt-1 truncate">{m.text || "(media)"}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Send form */}
        <div className="border border-neutral-200 sharp">
          <div className="px-4 py-3 border-b border-neutral-200">
            <h3 className="font-display font-semibold text-sm">Send Message</h3>
          </div>
          <form onSubmit={sendMsg} className="p-4 space-y-3" data-testid="quick-send-form">
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Recipient Number
              </label>
              <input
                data-testid="qsend-to"
                required
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="447780000000"
                className="w-full mt-1 border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] font-mono text-sm"
              />
            </div>
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Message Text
              </label>
              <textarea
                data-testid="qsend-text"
                rows={4}
                maxLength={1024}
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="w-full mt-1 border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] text-sm"
              />
              <p className="font-mono text-[10px] text-right text-neutral-400">{text.length}/1024</p>
            </div>
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Link / Media URL (optional)
              </label>
              <input
                data-testid="qsend-link"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="https://…"
                className="w-full mt-1 border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] font-mono text-sm"
              />
            </div>

            {!showSchedule ? (
              <button
                type="button"
                onClick={() => setShowSchedule(true)}
                className="text-xs text-[#002FA7] inline-flex items-center gap-1 font-mono uppercase tracking-widest"
                data-testid="schedule-toggle-btn"
              >
                <Calendar size={12} /> + Schedule
              </button>
            ) : (
              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                  Schedule for (your local time)
                </label>
                <div className="flex gap-2 mt-1">
                  <input
                    type="datetime-local"
                    data-testid="qsend-schedule"
                    value={scheduleAt}
                    onChange={(e) => setScheduleAt(e.target.value)}
                    className="flex-1 border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setScheduleAt("");
                      setShowSchedule(false);
                    }}
                    className="btn-ghost text-xs"
                  >
                    <X size={12} />
                  </button>
                </div>
                <p className="font-mono text-[10px] text-neutral-500 mt-1">
                  Cron runs every 60s. UTC stored on server.
                </p>
              </div>
            )}

            <button
              type="submit"
              disabled={busy || !isConnected}
              className="btn-brand w-full text-sm inline-flex items-center justify-center gap-2 disabled:opacity-50"
              data-testid="qsend-submit"
            >
              <PaperPlaneTilt size={14} />
              {busy ? "Sending…" : scheduleAt ? "Schedule Message" : "Send Message"}
            </button>
            {!isConnected && (
              <p className="text-xs text-yellow-700 text-center">
                Connect WhatsApp first to send.
              </p>
            )}
          </form>
        </div>
      </div>

      {/* Account Settings + Webhook + Service Mgmt */}
      <div className="mt-8 grid lg:grid-cols-3 gap-6">
        {/* Settings */}
        <div className="border border-neutral-200 sharp">
          <div className="px-4 py-3 border-b border-neutral-200">
            <h3 className="font-display font-semibold text-sm">Account Settings</h3>
          </div>
          <div className="p-4 space-y-4">
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                Default Country Code
              </label>
              <input
                data-testid="setting-country-code"
                value={session.default_country_code || ""}
                onChange={(e) => setSession((s) => ({ ...s, default_country_code: e.target.value.replace(/[^0-9]/g, "").slice(0, 4) }))}
                onBlur={() =>
                  updateSetting({ default_country_code: session.default_country_code || "" })
                }
                placeholder="91"
                className="w-full mt-1 border border-neutral-300 sharp px-3 py-2 outline-none focus:border-[#002FA7] font-mono text-sm"
              />
            </div>
            <Toggle
              label="Auto-prefix country code"
              hint="Add country code to short numbers automatically"
              checked={!!session.auto_prefix}
              onChange={(v) => updateSetting({ auto_prefix: v })}
              testId="toggle-auto-prefix"
            />
            <Toggle
              label="Receive Messages"
              hint="Forward inbound messages to your webhook"
              checked={session.receive_messages !== false}
              onChange={(v) => updateSetting({ receive_messages: v })}
              testId="toggle-receive"
            />
            <Toggle
              label="Mark as Seen"
              hint="Send read receipts on inbound messages"
              checked={!!session.mark_as_seen}
              onChange={(v) => updateSetting({ mark_as_seen: v })}
              testId="toggle-seen"
            />
          </div>
        </div>

        {/* Webhook hint */}
        <div className="border border-neutral-200 sharp p-5">
          <h3 className="font-display font-semibold text-sm">Webhook URL</h3>
          <p className="text-xs text-neutral-600 mt-2">
            Webhook is configured globally for your account in{" "}
            <Link to="/app/settings" className="text-[#002FA7] underline">
              Settings
            </Link>
            . When this number receives a message, we POST it there with HMAC signature.
          </p>
          {user?.webhook_url ? (
            <div className="mt-3 border border-neutral-200 sharp p-2 bg-neutral-50 font-mono text-xs break-all">
              {user.webhook_url}
            </div>
          ) : (
            <Link to="/app/settings" className="btn-brand text-xs inline-flex items-center gap-1.5 mt-3">
              Set up webhook
            </Link>
          )}
        </div>

        {/* Service mgmt */}
        <div className="border border-neutral-200 sharp">
          <div className="px-4 py-3 border-b border-neutral-200">
            <h3 className="font-display font-semibold text-sm">Service Management</h3>
          </div>
          <div className="divide-y divide-neutral-100">
            <button
              onClick={disconnect}
              className="w-full px-4 py-3 text-left flex items-center justify-between hover:bg-red-50 transition-colors"
              data-testid="svc-cancel"
            >
              <div>
                <div className="font-medium text-sm text-red-700">Cancel Service</div>
                <div className="text-xs text-neutral-500">Disconnects WhatsApp and removes session</div>
              </div>
              <Trash size={14} className="text-red-600" />
            </button>
            <Link
              to="/app/billing"
              className="w-full px-4 py-3 flex items-center justify-between hover:bg-neutral-50 transition-colors"
              data-testid="svc-renew"
            >
              <div>
                <div className="font-medium text-sm">Renew Service</div>
                <div className="text-xs text-neutral-500">Renew before expiration</div>
              </div>
              <Calendar size={14} />
            </Link>
            <Link
              to="/app/billing"
              className="w-full px-4 py-3 flex items-center justify-between hover:bg-neutral-50 transition-colors"
              data-testid="svc-upgrade"
            >
              <div>
                <div className="font-medium text-sm">Upgrade Service</div>
                <div className="text-xs text-neutral-500">Pick a higher plan</div>
              </div>
              <ArrowUp size={14} />
            </Link>
          </div>
        </div>
      </div>

      {qrModal && (
        <Modal title="Scan with WhatsApp" onClose={() => setQrModal(null)}>
          <div className="flex flex-col items-center" data-testid="qr-modal-detail">
            <ol className="font-mono text-xs text-neutral-600 list-decimal pl-5 space-y-1 self-start">
              <li>Open WhatsApp on your phone</li>
              <li>Tap <span className="kbd">Settings</span> → <span className="kbd">Linked Devices</span></li>
              <li>Scan the QR below</li>
            </ol>
            <div className="mt-6 w-64 h-64 border border-neutral-200 sharp flex items-center justify-center bg-white">
              {qrModal.status === "connected" ? (
                <p className="font-display font-semibold">Connected</p>
              ) : qrModal.qr ? (
                <img src={qrModal.qr} alt="QR" className="w-full h-full" />
              ) : (
                <div className="text-center">
                  <div className="dot connecting mx-auto" />
                  <p className="font-mono text-xs text-neutral-500 mt-3">{qrModal.status}</p>
                </div>
              )}
            </div>
            <button onClick={() => setQrModal(null)} className="btn-ghost text-sm mt-6">
              Close
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Card({ label, value, children, mono, border }) {
  return (
    <div className={`p-5 ${border ? "sm:border-l border-neutral-200" : ""}`}>
      <div className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</div>
      {value !== undefined ? (
        <div className={`font-display font-bold text-2xl mt-1.5 tracking-tight ${mono ? "font-mono text-xl" : ""}`}>
          {value}
        </div>
      ) : (
        children
      )}
    </div>
  );
}

function Toggle({ label, hint, checked, onChange, testId }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-neutral-500 mt-0.5">{hint}</div>
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 sharp transition-colors ${
          checked ? "bg-[#002FA7]" : "bg-neutral-300"
        }`}
        data-testid={testId}
      >
        <span
          className={`inline-block h-5 w-5 transform sharp bg-white shadow transition-transform mt-0.5 ${
            checked ? "translate-x-5" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}
