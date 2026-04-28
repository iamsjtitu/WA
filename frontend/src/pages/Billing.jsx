import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { PageHeader } from "./Overview";
import { CheckCircle, X, CreditCard } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Billing() {
  const { user, refresh } = useAuth();
  const [params] = useSearchParams();
  const [plans, setPlans] = useState([]);
  const [current, setCurrent] = useState(null);
  const [gateways, setGateways] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pl, sub, gw] = await Promise.all([
        api.get("/plans"),
        api.get("/me/subscription"),
        api.get("/billing/gateways"),
      ]);
      setPlans(pl.data);
      setCurrent(sub.data);
      setGateways(gw.data);
    } catch (e) {
      toast.error("Failed to load billing");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    if (params.get("ok")) toast.success(`Subscription via ${params.get("ok")} active`);
    if (params.get("cancel")) toast.info("Checkout cancelled");
    if (params.get("error")) toast.error(params.get("error"));
    // refresh user after redirect to pick up new quota
    refresh?.();
  }, [load, params]); // eslint-disable-line react-hooks/exhaustive-deps

  const checkout = async (gateway, plan) => {
    setBusy(true);
    try {
      if (gateway === "stripe") {
        const { data } = await api.post("/billing/stripe/checkout", { plan_id: plan.id });
        if (data.checkout_url) window.location.href = data.checkout_url;
      } else if (gateway === "razorpay") {
        const { data } = await api.post("/billing/razorpay/create-subscription", {
          plan_id: plan.id,
        });
        if (data.short_url) {
          window.location.href = data.short_url;
        } else {
          toast.error("Razorpay subscription created — open hosted page from dashboard");
        }
      } else if (gateway === "paypal") {
        const { data } = await api.post("/billing/paypal/create-subscription", {
          plan_id: plan.id,
        });
        if (data.approval_url) window.location.href = data.approval_url;
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${gateway} checkout failed`);
    }
    setBusy(false);
  };

  const cancelSubscription = async () => {
    if (!current?.subscription) return;
    if (!confirm("Cancel current subscription? Quota will reset to free tier.")) return;
    setBusy(true);
    try {
      await api.post(`/billing/${current.subscription.gateway}/cancel`);
      toast.success("Subscription cancelled");
      await refresh?.();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cancel failed");
    }
    setBusy(false);
  };

  return (
    <div className="p-10 fade-in">
      <PageHeader title="Billing" sub="Manage your plan & payment method." />

      {/* Current subscription */}
      <div className="mt-8 border border-neutral-200 sharp p-6" data-testid="current-subscription">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              current plan
            </p>
            <h3 className="font-display text-2xl tracking-tight mt-1">
              {current?.plan?.name || "Free"}
            </h3>
            <p className="text-sm text-neutral-600 mt-1">
              {user?.quota_used?.toLocaleString()} / {user?.quota_monthly?.toLocaleString()} messages used this period
            </p>
            {current?.subscription && (
              <p className="font-mono text-[11px] text-neutral-500 mt-2">
                via {current.subscription.gateway} · status {current.subscription.status} · until{" "}
                {new Date(current.subscription.current_period_end).toLocaleDateString()}
              </p>
            )}
          </div>
          {current?.subscription && (
            <button
              onClick={cancelSubscription}
              disabled={busy}
              className="btn-ghost text-sm hover:!border-red-500 hover:!text-red-600 disabled:opacity-50"
              data-testid="cancel-subscription-btn"
            >
              Cancel subscription
            </button>
          )}
        </div>
      </div>

      {/* Plans grid */}
      <h2 className="font-display text-2xl tracking-tight mt-12">Available plans</h2>
      {loading ? (
        <p className="text-neutral-500 mt-4 font-mono text-xs">Loading…</p>
      ) : plans.length === 0 ? (
        <p className="text-neutral-500 mt-4">No plans available yet. Check back soon.</p>
      ) : (
        <div className="mt-4 grid md:grid-cols-3 gap-0 border border-neutral-200">
          {plans.map((p, idx) => {
            const isCurrent = current?.plan?.id === p.id;
            return (
              <div
                key={p.id}
                className={`p-6 ${idx > 0 ? "md:border-l border-neutral-200" : ""} ${
                  isCurrent ? "bg-blue-50" : "bg-white"
                }`}
                data-testid={`plan-card-${p.id}`}
              >
                <h3 className="font-display font-semibold text-xl">{p.name}</h3>
                <div className="mt-3 flex items-baseline gap-1.5">
                  <span className="font-display text-3xl tracking-tight">
                    {p.currency} {p.price.toLocaleString()}
                  </span>
                  <span className="font-mono text-xs text-neutral-500">/ mo</span>
                </div>
                <ul className="mt-4 space-y-1.5 text-sm text-neutral-700 min-h-[160px]">
                  <li className="flex items-start gap-2">
                    <CheckCircle size={14} weight="fill" color="#002FA7" className="mt-0.5 shrink-0" />
                    {p.quota_monthly.toLocaleString()} messages / month
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle size={14} weight="fill" color="#002FA7" className="mt-0.5 shrink-0" />
                    {p.max_sessions} WhatsApp number{p.max_sessions > 1 ? "s" : ""}
                  </li>
                  {p.features?.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <CheckCircle size={14} weight="fill" color="#002FA7" className="mt-0.5 shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>

                {isCurrent ? (
                  <div className="mt-5 status-pill !bg-emerald-50 !border-emerald-200 !text-emerald-700">
                    <CheckCircle size={11} weight="fill" /> current plan
                  </div>
                ) : (
                  <div className="mt-5 space-y-2">
                    <button
                      onClick={() => checkout("stripe", p)}
                      disabled={busy || !gateways.stripe}
                      className="btn-brand text-sm w-full inline-flex items-center justify-center gap-2 disabled:opacity-40"
                      data-testid={`checkout-stripe-${p.id}`}
                      title={!gateways.stripe ? "Stripe not configured" : ""}
                    >
                      <CreditCard size={14} /> Pay with Stripe
                    </button>
                    <button
                      onClick={() => checkout("razorpay", p)}
                      disabled={busy || !gateways.razorpay}
                      className="btn-ghost text-sm w-full disabled:opacity-40"
                      data-testid={`checkout-razorpay-${p.id}`}
                      title={!gateways.razorpay ? "Razorpay not configured" : ""}
                    >
                      Pay with Razorpay
                    </button>
                    <button
                      onClick={() => checkout("paypal", p)}
                      disabled={busy || !gateways.paypal}
                      className="btn-ghost text-sm w-full disabled:opacity-40"
                      data-testid={`checkout-paypal-${p.id}`}
                      title={!gateways.paypal ? "PayPal not configured" : ""}
                    >
                      Pay with PayPal
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-8 border border-neutral-200 sharp p-5 bg-neutral-50">
        <h3 className="font-display font-semibold text-sm tracking-tight">Payment gateways</h3>
        <div className="mt-3 grid sm:grid-cols-3 gap-2 text-sm">
          <GatewayChip name="Stripe" enabled={gateways.stripe} />
          <GatewayChip name="Razorpay" enabled={gateways.razorpay} />
          <GatewayChip name="PayPal" enabled={gateways.paypal} />
        </div>
        {(!gateways.stripe || !gateways.razorpay || !gateways.paypal) && (
          <p className="text-xs text-neutral-500 mt-3 font-mono">
            Admin: set keys in <span className="kbd">/app/backend/.env</span> then restart the backend.
          </p>
        )}
      </div>
    </div>
  );
}

function GatewayChip({ name, enabled }) {
  return (
    <div className="border border-neutral-200 sharp px-3 py-2 flex items-center gap-2 bg-white">
      {enabled ? (
        <CheckCircle size={14} weight="fill" color="#10b981" />
      ) : (
        <X size={14} className="text-neutral-400" />
      )}
      <span className={enabled ? "" : "text-neutral-400"}>{name}</span>
      <span className="ml-auto font-mono text-[10px] uppercase tracking-widest">
        {enabled ? "ready" : "off"}
      </span>
    </div>
  );
}
