import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { Modal } from "./Sessions";
import { Plus, Trash, Copy, Key, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Customers() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showKey, setShowKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/customers");
      setList(data);
    } catch (e) {
      toast.error("Failed to load customers");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (c) => {
    if (!confirm(`Delete customer ${c.email}? All their data will be gone.`)) return;
    try {
      await api.delete(`/admin/customers/${c.id}`);
      toast.success("Customer deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const regen = async (c) => {
    if (!confirm(`Rotate API key for ${c.email}?`)) return;
    try {
      const { data } = await api.post(`/admin/customers/${c.id}/regenerate-key`);
      toast.success("API key rotated");
      setShowKey({ email: c.email, key: data.api_key });
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  const updateQuota = async (c) => {
    const v = prompt(`New monthly quota for ${c.email}`, c.quota_monthly);
    if (!v) return;
    try {
      await api.patch(`/admin/customers/${c.id}`, { quota_monthly: Number(v) });
      toast.success("Quota updated");
      load();
    } catch {
      toast.error("Failed");
    }
  };

  const copy = (k) => {
    navigator.clipboard.writeText(k);
    toast.success("Copied");
  };

  return (
    <div className="p-10 fade-in">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Customers" sub="Manage customer accounts, API keys, and quotas." />
        <button onClick={() => setShowCreate(true)} className="btn-brand inline-flex items-center gap-2" data-testid="new-customer-btn">
          <Plus size={16} /> New customer
        </button>
      </div>

      <div className="mt-8 border border-neutral-200 sharp overflow-hidden">
        <table className="tbl">
          <thead>
            <tr>
              <th>Customer</th>
              <th>API Key</th>
              <th>Quota</th>
              <th>Created</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 font-mono text-xs">Loading…</td>
              </tr>
            )}
            {!loading && list.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-neutral-500 py-12">No customers yet.</td>
              </tr>
            )}
            {list.map((c) => (
              <tr key={c.id} data-testid={`customer-row-${c.id}`}>
                <td>
                  <div className="font-medium">{c.name}</div>
                  <div className="font-mono text-xs text-neutral-500">{c.email}</div>
                </td>
                <td>
                  <button
                    onClick={() => copy(c.api_key)}
                    className="font-mono text-xs hover:underline inline-flex items-center gap-1"
                    title="Copy"
                    data-testid={`customer-copykey-${c.id}`}
                  >
                    {c.api_key.slice(0, 16)}… <Copy size={12} />
                  </button>
                </td>
                <td className="font-mono text-xs">
                  {c.quota_used}/{c.quota_monthly}
                </td>
                <td className="font-mono text-xs text-neutral-500 whitespace-nowrap">
                  {new Date(c.created_at).toLocaleDateString()}
                </td>
                <td className="text-right">
                  <div className="inline-flex gap-2">
                    <button onClick={() => updateQuota(c)} className="btn-ghost text-xs" data-testid={`customer-quota-${c.id}`}>
                      Quota
                    </button>
                    <button onClick={() => regen(c)} className="btn-ghost text-xs inline-flex items-center gap-1" data-testid={`customer-regen-${c.id}`}>
                      <ArrowsClockwise size={12} />
                    </button>
                    <button onClick={() => remove(c)} className="btn-ghost text-xs hover:!border-red-500 hover:!text-red-600" data-testid={`customer-delete-${c.id}`}>
                      <Trash size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateCustomerModal
          onClose={() => setShowCreate(false)}
          onCreated={(newKey) => {
            setShowCreate(false);
            load();
            setShowKey(newKey);
          }}
        />
      )}

      {showKey && (
        <Modal title="API key" onClose={() => setShowKey(null)}>
          <p className="text-sm text-neutral-600">Share this key with <strong>{showKey.email}</strong>. They'll need it to call the API.</p>
          <code className="block mt-3 font-mono text-xs bg-neutral-100 border border-neutral-200 sharp p-3 break-all">
            {showKey.key}
          </code>
          <div className="flex justify-end mt-4">
            <button onClick={() => copy(showKey.key)} className="btn-brand text-sm inline-flex items-center gap-2">
              <Copy size={14} /> Copy
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function CreateCustomerModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [quota, setQuota] = useState(1000);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/admin/customers", {
        name,
        email,
        password,
        quota_monthly: Number(quota),
      });
      toast.success("Customer created");
      onCreated({ email: data.email, key: data.api_key });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  return (
    <Modal title="New customer" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" data-testid="customer-create-form">
        <Input label="Name" value={name} onChange={setName} testId="customer-name-input" />
        <Input label="Email" type="email" value={email} onChange={setEmail} testId="customer-email-input" />
        <Input label="Initial password" type="text" value={password} onChange={setPassword} testId="customer-password-input" />
        <Input label="Monthly quota" type="number" value={quota} onChange={setQuota} testId="customer-quota-input" />
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy} className="btn-brand text-sm disabled:opacity-50" data-testid="customer-create-submit">
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Input({ label, value, onChange, type = "text", testId }) {
  return (
    <div>
      <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</label>
      <input
        data-testid={testId}
        required
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7]"
      />
    </div>
  );
}
