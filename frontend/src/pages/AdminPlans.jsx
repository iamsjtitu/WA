import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { Modal } from "./Sessions";
import { Plus, Trash, PencilSimple, Check, X } from "@phosphor-icons/react";
import { toast } from "sonner";

const empty = {
  name: "",
  price: 0,
  currency: "INR",
  quota_monthly: 1000,
  max_sessions: 1,
  features: [],
  active: true,
  sort: 0,
};

export default function AdminPlans() {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | "new" | plan object

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/plans");
      setPlans(data);
    } catch (e) {
      toast.error("Failed to load plans");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (p) => {
    if (!confirm(`Delete plan "${p.name}"?`)) return;
    try {
      await api.delete(`/admin/plans/${p.id}`);
      toast.success("Plan deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const toggleActive = async (p) => {
    try {
      await api.patch(`/admin/plans/${p.id}`, { active: !p.active });
      toast.success(p.active ? "Plan disabled" : "Plan enabled");
      load();
    } catch {
      toast.error("Failed");
    }
  };

  return (
    <div className="p-10 fade-in">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Plans" sub="Pricing tiers offered to your customers." />
        <button
          onClick={() => setEditing("new")}
          className="btn-brand inline-flex items-center gap-2"
          data-testid="new-plan-btn"
        >
          <Plus size={16} /> New plan
        </button>
      </div>

      <div className="mt-8 border border-neutral-200 sharp overflow-hidden">
        <table className="tbl">
          <thead>
            <tr>
              <th>Name</th>
              <th>Price</th>
              <th>Quota / mo</th>
              <th>Sessions</th>
              <th>Active</th>
              <th>Sort</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="text-center text-neutral-500 font-mono text-xs">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && plans.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-neutral-500 py-12">
                  No plans yet. Create your first pricing tier.
                </td>
              </tr>
            )}
            {plans.map((p) => (
              <tr key={p.id} data-testid={`plan-row-${p.id}`}>
                <td>
                  <div className="font-medium">{p.name}</div>
                  {p.features?.length > 0 && (
                    <div className="text-xs text-neutral-500 mt-1">
                      {p.features.slice(0, 3).join(" · ")}
                      {p.features.length > 3 && " · +more"}
                    </div>
                  )}
                </td>
                <td className="font-mono text-sm">
                  {p.currency} {p.price.toLocaleString()}
                </td>
                <td className="font-mono text-xs">{p.quota_monthly.toLocaleString()}</td>
                <td className="font-mono text-xs">{p.max_sessions}</td>
                <td>
                  <button
                    onClick={() => toggleActive(p)}
                    className={`status-pill ${p.active ? "!bg-emerald-50 !border-emerald-200 !text-emerald-700" : ""}`}
                    data-testid={`plan-toggle-${p.id}`}
                  >
                    {p.active ? (
                      <>
                        <Check size={10} /> active
                      </>
                    ) : (
                      <>
                        <X size={10} /> off
                      </>
                    )}
                  </button>
                </td>
                <td className="font-mono text-xs">{p.sort}</td>
                <td className="text-right">
                  <div className="inline-flex gap-2">
                    <button
                      onClick={() => setEditing(p)}
                      className="btn-ghost text-xs"
                      data-testid={`plan-edit-${p.id}`}
                    >
                      <PencilSimple size={12} />
                    </button>
                    <button
                      onClick={() => remove(p)}
                      className="btn-ghost text-xs hover:!border-red-500 hover:!text-red-600"
                      data-testid={`plan-delete-${p.id}`}
                    >
                      <Trash size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <PlanFormModal
          initial={editing === "new" ? empty : editing}
          isNew={editing === "new"}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function PlanFormModal({ initial, isNew, onClose, onSaved }) {
  const [form, setForm] = useState({ ...empty, ...initial });
  const [featureInput, setFeatureInput] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const addFeature = () => {
    const v = featureInput.trim();
    if (!v) return;
    setForm((f) => ({ ...f, features: [...f.features, v] }));
    setFeatureInput("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        name: form.name,
        price: Number(form.price),
        currency: form.currency.toUpperCase(),
        quota_monthly: Number(form.quota_monthly),
        max_sessions: Number(form.max_sessions),
        features: form.features,
        active: !!form.active,
        sort: Number(form.sort),
      };
      if (isNew) await api.post("/admin/plans", payload);
      else await api.patch(`/admin/plans/${initial.id}`, payload);
      toast.success(isNew ? "Plan created" : "Plan updated");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setBusy(false);
  };

  return (
    <Modal title={isNew ? "New plan" : "Edit plan"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" data-testid="plan-form">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name" value={form.name} onChange={set("name")} required />
          <Input label="Currency" value={form.currency} onChange={set("currency")} maxLength={3} />
          <Input label="Price" type="number" step="0.01" value={form.price} onChange={set("price")} />
          <Input
            label="Quota / month"
            type="number"
            value={form.quota_monthly}
            onChange={set("quota_monthly")}
          />
          <Input
            label="Max sessions"
            type="number"
            min="1"
            value={form.max_sessions}
            onChange={set("max_sessions")}
          />
          <Input label="Sort" type="number" value={form.sort} onChange={set("sort")} />
        </div>

        <div>
          <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
            Features
          </label>
          <div className="flex gap-2 mt-1.5">
            <input
              value={featureInput}
              onChange={(e) => setFeatureInput(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && (e.preventDefault(), addFeature())
              }
              placeholder="Add a feature and press Enter"
              className="flex-1 border border-neutral-300 sharp px-3 py-2 text-sm outline-none focus:border-[#002FA7]"
            />
            <button type="button" onClick={addFeature} className="btn-ghost text-sm">
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {form.features.map((f, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 text-xs border border-neutral-300 sharp px-2 py-1"
              >
                {f}
                <button
                  type="button"
                  onClick={() =>
                    setForm((s) => ({
                      ...s,
                      features: s.features.filter((_, idx) => idx !== i),
                    }))
                  }
                  className="text-neutral-400 hover:text-red-600"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!form.active}
            onChange={(e) => set("active")(e.target.checked)}
          />
          Active (visible to customers)
        </label>

        <div className="flex justify-end gap-2 pt-3">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={busy} className="btn-brand text-sm disabled:opacity-50" data-testid="plan-save-btn">
            {busy ? "Saving…" : isNew ? "Create" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Input({ label, value, onChange, ...rest }) {
  return (
    <div>
      <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
        {label}
      </label>
      <input
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2 text-sm outline-none focus:border-[#002FA7] focus:ring-1 focus:ring-[#002FA7]"
      />
    </div>
  );
}
