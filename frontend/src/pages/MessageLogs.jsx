import { Link } from "react-router-dom";
import { PageHeader } from "./Overview";
import { ShieldCheck, ArrowSquareOut } from "@phosphor-icons/react";

// Logs UI removed for end-to-end privacy. Message content is never rendered
// in the dashboard for any user or administrator. To retrieve historical
// messages, applications must call the v2 API with their service API key.
export default function MessageLogs() {
  return (
    <div className="p-10 fade-in" data-testid="message-logs-privacy">
      <PageHeader
        title="Message Logs"
        sub="Logs are intentionally not displayed in the dashboard."
      />

      <div className="mt-8 max-w-2xl border border-neutral-200 sharp p-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#1FA855] flex items-center justify-center sharp">
            <ShieldCheck size={22} weight="fill" color="#fff" />
          </div>
          <div>
            <h2 className="font-display font-bold text-xl tracking-tight">End-to-end privacy</h2>
            <p className="text-sm text-neutral-500">No message content is visible in the dashboard.</p>
          </div>
        </div>

        <div className="mt-6 space-y-3 text-sm text-neutral-700 leading-relaxed">
          <p>
            wa.9x.design intentionally does <strong>not</strong> render sent or received
            message contents to any user — including administrators. Even an authenticated
            customer logged in to their own dashboard cannot read message bodies here.
          </p>
          <p className="text-neutral-600">
            Messages still flow through your <Link to="/app/settings" className="text-[#1FA855] hover:underline">inbound webhook</Link>
            and can be retrieved programmatically using your service API key.
          </p>
        </div>

        <div className="mt-6 border-t border-neutral-200 pt-6">
          <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">retrieve via api</p>
          <ul className="mt-2 space-y-2 text-sm font-mono">
            <li className="flex items-baseline gap-2">
              <span className="inline-block w-12 text-[10px] font-bold tracking-wider text-blue-700 bg-blue-100 border border-blue-200 px-1.5 py-0.5 text-center">GET</span>
              <code className="text-xs">/api/v2/message/sentMessages?page=1</code>
            </li>
            <li className="flex items-baseline gap-2">
              <span className="inline-block w-12 text-[10px] font-bold tracking-wider text-blue-700 bg-blue-100 border border-blue-200 px-1.5 py-0.5 text-center">GET</span>
              <code className="text-xs">/api/v2/message/receivedMessages?page=1</code>
            </li>
            <li className="flex items-baseline gap-2">
              <span className="inline-block w-12 text-[10px] font-bold tracking-wider text-blue-700 bg-blue-100 border border-blue-200 px-1.5 py-0.5 text-center">GET</span>
              <code className="text-xs">/api/v2/message/status?id=&lt;message_id&gt;</code>
            </li>
          </ul>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Link
            to="/developer"
            className="px-3 py-1.5 border border-neutral-300 hover:border-neutral-900 sharp text-sm inline-flex items-center gap-2"
            data-testid="open-public-docs"
          >
            Open public API docs <ArrowSquareOut size={12} />
          </Link>
          <Link
            to="/app/sessions"
            className="px-3 py-1.5 bg-[#1FA855] text-white hover:bg-[#178c47] sharp text-sm inline-flex items-center gap-2"
            data-testid="get-api-keys"
          >
            Get my API keys
          </Link>
        </div>
      </div>
    </div>
  );
}
