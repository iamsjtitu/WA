import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import api from "../lib/api";
import { PageHeader } from "./Overview";
import { Copy, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ApiDocs() {
  const { user, refresh } = useAuth();
  const apiBase = `${process.env.REACT_APP_BACKEND_URL}/api`;

  const copy = (txt) => {
    navigator.clipboard.writeText(txt);
    toast.success("Copied");
  };

  const regen = async () => {
    if (!confirm("Rotate your API key? Existing integrations will stop working.")) return;
    await api.post("/me/regenerate-key");
    await refresh();
    toast.success("API key rotated");
  };

  const code = (lang, body) => (
    <div className="codeblk relative group">
      <button
        onClick={() => copy(body)}
        className="absolute top-2 right-2 p-1.5 bg-white/10 hover:bg-white/20 sharp text-white opacity-0 group-hover:opacity-100 transition"
        data-testid={`copy-code-${lang}`}
      >
        <Copy size={14} />
      </button>
      <pre className="whitespace-pre-wrap">{body}</pre>
    </div>
  );

  return (
    <div className="p-10 fade-in">
      <PageHeader title="API Documentation" sub="Send WhatsApp messages programmatically using your X-API-Key." />

      <section className="mt-8 border border-neutral-200 sharp p-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
              your api key
            </p>
            <code className="font-mono text-sm bg-neutral-100 border border-neutral-200 sharp px-3 py-2 mt-2 inline-block break-all" data-testid="api-key-display">
              {user?.api_key}
            </code>
          </div>
          <div className="flex gap-2">
            <button onClick={() => copy(user?.api_key)} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="copy-api-key">
              <Copy size={14} /> Copy
            </button>
            <button onClick={regen} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="rotate-api-key">
              <ArrowsClockwise size={14} /> Rotate
            </button>
          </div>
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-2xl tracking-tight">Base URL</h2>
        <div className="mt-3">{code("base", apiBase)}</div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-2xl tracking-tight">Authentication</h2>
        <p className="text-sm text-neutral-600 mt-2">Send your API key in the <span className="kbd">X-API-Key</span> header.</p>
        <div className="mt-3">{code("auth", `X-API-Key: ${user?.api_key || "wapi_•••"}`)}</div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-2xl tracking-tight">Send a message</h2>
        <p className="font-mono text-xs uppercase tracking-widest text-[#002FA7] mt-2">
          POST /api/v1/messages
        </p>

        <h3 className="font-display font-semibold mt-6">cURL</h3>
        {code(
          "curl",
          `curl -X POST ${apiBase}/v1/messages \\
  -H "X-API-Key: ${user?.api_key || "wapi_•••"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "to": "919876543210",
    "text": "Hello from WapiHub!"
  }'`
        )}

        <h3 className="font-display font-semibold mt-6">Node.js</h3>
        {code(
          "node",
          `const res = await fetch("${apiBase}/v1/messages", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "${user?.api_key || "wapi_•••"}"
  },
  body: JSON.stringify({ to: "919876543210", text: "Hi!" })
});
console.log(await res.json());`
        )}

        <h3 className="font-display font-semibold mt-6">Python</h3>
        {code(
          "python",
          `import requests
r = requests.post(
    "${apiBase}/v1/messages",
    headers={"X-API-Key": "${user?.api_key || "wapi_•••"}"},
    json={"to": "919876543210", "text": "Hi!"},
)
print(r.json())`
        )}

        <h3 className="font-display font-semibold mt-6">PHP</h3>
        {code(
          "php",
          `<?php
$ch = curl_init("${apiBase}/v1/messages");
curl_setopt_array($ch, [
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_POST => true,
  CURLOPT_HTTPHEADER => [
    "Content-Type: application/json",
    "X-API-Key: ${user?.api_key || "wapi_•••"}"
  ],
  CURLOPT_POSTFIELDS => json_encode([
    "to" => "919876543210",
    "text" => "Hi!"
  ])
]);
echo curl_exec($ch);`
        )}
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl tracking-tight">List sessions</h2>
        <p className="font-mono text-xs uppercase tracking-widest text-[#002FA7] mt-2">
          GET /api/v1/sessions
        </p>
        {code(
          "list-sessions",
          `curl -H "X-API-Key: ${user?.api_key || "wapi_•••"}" ${apiBase}/v1/sessions`
        )}
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl tracking-tight">Send media (image · pdf · video)</h2>
        <p className="font-mono text-xs uppercase tracking-widest text-[#002FA7] mt-2">
          POST /api/v1/messages — with media_url
        </p>
        <p className="text-sm text-neutral-600 mt-3">
          Pass a publicly-accessible <span className="kbd">media_url</span>. We download it server-side and forward via WhatsApp.
        </p>

        <h3 className="font-display font-semibold mt-5">Send an image</h3>
        {code(
          "media-image",
          `curl -X POST ${apiBase}/v1/messages \\
  -H "X-API-Key: ${user?.api_key || "wapi_•••"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "to": "919876543210",
    "media_url": "https://example.com/photo.jpg",
    "caption": "Check this out!"
  }'`
        )}

        <h3 className="font-display font-semibold mt-5">Send a PDF</h3>
        {code(
          "media-pdf",
          `curl -X POST ${apiBase}/v1/messages \\
  -H "X-API-Key: ${user?.api_key || "wapi_•••"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "to": "919876543210",
    "media_url": "https://example.com/invoice.pdf",
    "file_name": "invoice-2026.pdf",
    "caption": "Your invoice"
  }'`
        )}
      </section>

      <section className="mt-10 border-t border-neutral-200 pt-10">
        <h2 className="font-display text-2xl tracking-tight">v2 (360messenger-compatible)</h2>
        <p className="text-sm text-neutral-600 mt-2 max-w-3xl">
          Drop-in compatible with{" "}
          <code className="kbd">api.360messenger.com/v2/*</code>. Bearer auth, multipart bodies, identical
          response shapes — switch from 360messenger by just changing the host.
        </p>

        <h3 className="font-display font-semibold mt-5">POST /api/v2/sendMessage</h3>
        {code(
          "v2-send",
          `curl -X POST ${apiBase}/v2/sendMessage \\
  -H "Authorization: Bearer ${user?.api_key || "wapi_•••"}" \\
  --form 'phonenumber="447488888888"' \\
  --form 'text="Hello World!"' \\
  --form 'url="https://example.com/photo.jpg"' \\
  --form 'delay="01-31-2026 09:30"'   # optional GMT schedule`
        )}

        <h3 className="font-display font-semibold mt-5">POST /api/v2/sendGroup</h3>
        {code(
          "v2-group",
          `curl -X POST ${apiBase}/v2/sendGroup \\
  -H "Authorization: Bearer ${user?.api_key || "wapi_•••"}" \\
  --form 'groupId="120363012345678901"' \\
  --form 'text="Hello group!"'`
        )}

        <h3 className="font-display font-semibold mt-5">GET /api/v2/message/status?id=...</h3>
        {code(
          "v2-status",
          `curl "${apiBase}/v2/message/status?id=<msg-uuid>" \\
  -H "Authorization: Bearer ${user?.api_key || "wapi_•••"}"`
        )}

        <h3 className="font-display font-semibold mt-5">GET /api/v2/message/sentMessages</h3>
        {code(
          "v2-sent",
          `curl "${apiBase}/v2/message/sentMessages?page=1" \\
  -H "Authorization: Bearer ${user?.api_key || "wapi_•••"}"`
        )}

        <h3 className="font-display font-semibold mt-5">GET /api/v2/message/receivedMessages</h3>
        {code(
          "v2-received",
          `curl "${apiBase}/v2/message/receivedMessages?page=1" \\
  -H "Authorization: Bearer ${user?.api_key || "wapi_•••"}"`
        )}
      </section>

      <section className="mt-10 border-t border-neutral-200 pt-10">
        <h2 className="font-display text-2xl tracking-tight">Inbound webhook</h2>
        <p className="text-sm text-neutral-600 mt-3 max-w-3xl">
          Set a webhook URL in <a href="/app/settings" className="text-[#002FA7] underline">Settings</a>.
          When a connected number receives a message, we'll POST a signed JSON payload to your endpoint.
          Verify the <span className="kbd">X-Wapihub-Signature</span> header before trusting the body.
        </p>

        <h3 className="font-display font-semibold mt-5">Payload</h3>
        {code(
          "webhook-payload",
          `POST {your-webhook-url}
Content-Type: application/json
X-Wapihub-Signature: sha256=<hex-hmac>
X-Wapihub-Event: message.received

{
  "event": "message.received",
  "session_id": "uuid",
  "from": "919876543210",
  "text": "Hi, what are your hours?",
  "type": "text",
  "message_id": "3EB0...",
  "timestamp": 1714234567000,
  "has_media": false
}`
        )}

        <h3 className="font-display font-semibold mt-5">Verify the signature (Node.js)</h3>
        {code(
          "webhook-verify-node",
          `import crypto from "node:crypto";

app.post("/whatsapp/webhook", express.json(), (req, res) => {
  const sig = req.header("X-Wapihub-Signature") || "";
  const expected =
    "sha256=" +
    crypto
      .createHmac("sha256", process.env.WAPIHUB_WEBHOOK_SECRET)
      .update(JSON.stringify(req.body))
      .digest("hex");

  if (sig !== expected) return res.status(401).send("bad signature");

  console.log("inbound from", req.body.from, ":", req.body.text);
  res.json({ ok: true });
});`
        )}

        <h3 className="font-display font-semibold mt-5">Verify the signature (Python)</h3>
        {code(
          "webhook-verify-py",
          `import hmac, hashlib, json
from fastapi import FastAPI, Request, HTTPException

SECRET = "your-webhook-secret"
app = FastAPI()

@app.post("/whatsapp/webhook")
async def webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("x-wapihub-signature", "")
    expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "bad signature")
    data = json.loads(body)
    print("inbound from", data["from"], ":", data["text"])
    return {"ok": True}`
        )}
      </section>

      <section className="mt-10 border-t border-neutral-200 pt-10">
        <h2 className="font-display text-2xl tracking-tight">Integrations & plugins</h2>
        <p className="text-sm text-neutral-600 mt-2 max-w-3xl">
          Drop-in plugins so non-developer customers can ship WhatsApp notifications without writing code.
        </p>
        <div className="mt-6 grid sm:grid-cols-2 gap-4">
          <a
            href={`${apiBase}/plugins/whmcs.zip`}
            className="border border-neutral-200 sharp p-5 hover:bg-neutral-50 transition-colors flex items-start gap-3"
            data-testid="download-whmcs"
          >
            <div className="w-10 h-10 bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center sharp font-display font-bold">W</div>
            <div>
              <h3 className="font-display font-semibold">WHMCS Module</h3>
              <p className="text-xs text-neutral-600 mt-1">
                Send WhatsApp from invoice events, ticket replies, signups. PHP curl helper included.
              </p>
              <span className="font-mono text-[11px] uppercase tracking-widest text-[#002FA7] mt-2 inline-block">
                ↓ download .zip
              </span>
            </div>
          </a>
          <a
            href={`${apiBase}/plugins/woocommerce.zip`}
            className="border border-neutral-200 sharp p-5 hover:bg-neutral-50 transition-colors flex items-start gap-3"
            data-testid="download-woocommerce"
          >
            <div className="w-10 h-10 bg-[#7B2D8E]/10 text-[#7B2D8E] flex items-center justify-center sharp font-display font-bold">Wo</div>
            <div>
              <h3 className="font-display font-semibold">WooCommerce Plugin</h3>
              <p className="text-xs text-neutral-600 mt-1">
                Auto-WhatsApp on order paid / processing with templates. Settings under WP → Options.
              </p>
              <span className="font-mono text-[11px] uppercase tracking-widest text-[#002FA7] mt-2 inline-block">
                ↓ download .zip
              </span>
            </div>
          </a>
        </div>
      </section>

      <section className="mt-10 border border-neutral-200 sharp p-6 bg-yellow-50">
        <h3 className="font-display font-semibold text-lg tracking-tight">Things to know</h3>
        <ul className="mt-3 text-sm text-neutral-700 space-y-1 list-disc pl-5">
          <li>Numbers must include the country code (no <span className="kbd">+</span> sign).</li>
          <li>If you skip <span className="kbd">session_id</span>, the first connected session is used.</li>
          <li>Quota is enforced per month. Failed sends don't count.</li>
          <li>Media files up to 25 MB. We download &amp; forward — your URL must be public.</li>
          <li>Webhook timeouts: we wait up to 10s for your endpoint to respond. Return 2xx to acknowledge.</li>
        </ul>
      </section>
    </div>
  );
}
