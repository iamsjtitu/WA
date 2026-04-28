import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChatCircle,
  Copy,
  MagnifyingGlass,
  Code,
  Terminal,
  ArrowSquareOut,
  Check,
  Lightning,
  Lock,
} from "@phosphor-icons/react";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "https://wa.9x.design";
const API_BASE = `${BACKEND}/api`;

// ---------------- Endpoint catalogue ----------------
const SECTIONS = [
  {
    id: "introduction",
    title: "Introduction",
    items: [{ id: "intro", label: "Overview" }],
  },
  {
    id: "auth",
    title: "Authentication",
    items: [
      { id: "auth-bearer", label: "Bearer (v2)" },
      { id: "auth-apikey", label: "API key (v1)" },
    ],
  },
  {
    id: "v2",
    title: "WhatsApp API v2.0",
    items: [
      { id: "v2-send", label: "Send Message", method: "POST" },
      { id: "v2-group", label: "Send Group Message", method: "POST" },
      { id: "v2-status", label: "Get Message Status", method: "GET" },
      { id: "v2-sent", label: "List Sent Messages", method: "GET" },
      { id: "v2-recv", label: "List Received Messages", method: "GET" },
      { id: "v2-account", label: "Account Info", method: "GET" },
    ],
  },
  {
    id: "v1",
    title: "Modern API v1.0",
    items: [
      { id: "v1-messages", label: "Send (text or media)", method: "POST" },
      { id: "v1-sessions", label: "List Sessions", method: "GET" },
    ],
  },
  {
    id: "webhooks",
    title: "Webhooks",
    items: [
      { id: "wh-inbound", label: "Inbound Messages" },
      { id: "wh-verify", label: "HMAC Verification" },
    ],
  },
];

// ---------------- Helpers ----------------
const Method = ({ m }) => {
  const colors = {
    GET: "bg-blue-100 text-blue-800 border-blue-200",
    POST: "bg-emerald-100 text-emerald-800 border-emerald-200",
    PATCH: "bg-amber-100 text-amber-800 border-amber-200",
    DELETE: "bg-red-100 text-red-800 border-red-200",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 font-mono text-[11px] font-bold tracking-wider uppercase border sharp ${
        colors[m] || colors.GET
      }`}
      data-testid={`method-${m.toLowerCase()}`}
    >
      {m}
    </span>
  );
};

function CopyBtn({ text, testid }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="absolute top-2.5 right-2.5 p-1.5 bg-white/10 hover:bg-white/20 text-white sharp transition"
      title="Copy"
      data-testid={testid}
    >
      {done ? <Check size={14} weight="bold" /> : <Copy size={14} />}
    </button>
  );
}

function CodeTabs({ samples, testid }) {
  const langs = Object.keys(samples);
  const [active, setActive] = useState(langs[0]);
  return (
    <div className="border border-neutral-800 sharp overflow-hidden" data-testid={testid}>
      <div className="flex bg-neutral-900 border-b border-neutral-800">
        {langs.map((l) => (
          <button
            key={l}
            onClick={() => setActive(l)}
            className={`px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider transition ${
              active === l
                ? "bg-neutral-950 text-emerald-300 border-b-2 border-emerald-400"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
            data-testid={`${testid}-tab-${l}`}
          >
            {l}
          </button>
        ))}
      </div>
      <div className="relative">
        <pre
          className="bg-neutral-950 text-neutral-100 font-mono text-[12.5px] leading-relaxed p-4 overflow-auto whitespace-pre"
          data-testid={`${testid}-code`}
        >
          {samples[active]}
        </pre>
        <CopyBtn text={samples[active]} testid={`${testid}-copy`} />
      </div>
    </div>
  );
}

function ResponseBlock({ status, body, testid }) {
  const ok = status >= 200 && status < 300;
  return (
    <div className="mt-4 border border-neutral-200 sharp" data-testid={testid}>
      <div className="px-3 py-1.5 border-b border-neutral-200 bg-neutral-50 flex items-center gap-2">
        <span
          className={`inline-block px-2 py-0.5 font-mono text-[10px] font-bold sharp border ${
            ok
              ? "bg-emerald-100 text-emerald-800 border-emerald-200"
              : "bg-red-100 text-red-800 border-red-200"
          }`}
        >
          {status} {ok ? "OK" : "ERROR"}
        </span>
        <span className="text-xs text-neutral-500 font-mono">Example response</span>
      </div>
      <pre className="bg-neutral-950 text-emerald-300 font-mono text-[12.5px] leading-relaxed p-4 overflow-auto whitespace-pre">
        {body}
      </pre>
    </div>
  );
}

function ParamTable({ params }) {
  if (!params || params.length === 0) return null;
  return (
    <div className="mt-4 border border-neutral-200 sharp overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-neutral-50 border-b border-neutral-200">
          <tr>
            <th className="text-left px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-neutral-500 w-1/4">Field</th>
            <th className="text-left px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-neutral-500 w-1/6">Type</th>
            <th className="text-left px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-neutral-500">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p, i) => (
            <tr key={p.name} className={i ? "border-t border-neutral-200" : ""}>
              <td className="px-3 py-2 font-mono text-[12.5px] align-top">
                {p.name}
                {p.required && (
                  <span className="ml-1 text-red-600 text-[10px] font-sans">required</span>
                )}
              </td>
              <td className="px-3 py-2 font-mono text-[12px] text-neutral-600 align-top">
                {p.type}
              </td>
              <td className="px-3 py-2 text-neutral-700 align-top">{p.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Endpoint({ id, method, path, title, description, auth, params, samples, response }) {
  const url = `${API_BASE}${path}`;
  return (
    <section id={id} className="scroll-mt-24" data-testid={`endpoint-${id}`}>
      <div className="border-t border-neutral-200 pt-10 mt-12">
        <div className="flex items-baseline gap-3 flex-wrap">
          <Method m={method} />
          <h3 className="font-display font-semibold text-2xl tracking-tight">{title}</h3>
        </div>
        <div className="mt-3 flex items-center gap-2 group">
          <code className="font-mono text-[13px] bg-neutral-100 border border-neutral-200 sharp px-3 py-1.5 break-all flex-1">
            {url}
          </code>
          <CopyButtonInline text={url} testid={`copy-url-${id}`} />
        </div>
        {description && <p className="mt-3 text-neutral-600">{description}</p>}
        {auth && (
          <div className="mt-3 inline-flex items-center gap-2 text-xs font-mono text-neutral-700 bg-neutral-100 border border-neutral-200 sharp px-2.5 py-1">
            <Lock size={12} weight="fill" />
            {auth}
          </div>
        )}
        <ParamTable params={params} />
        <div className="mt-4">
          <CodeTabs samples={samples} testid={`samples-${id}`} />
        </div>
        {response && <ResponseBlock {...response} testid={`response-${id}`} />}
      </div>
    </section>
  );
}

function CopyButtonInline({ text, testid }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="p-2 bg-white border border-neutral-200 hover:border-neutral-900 sharp transition"
      title="Copy URL"
      data-testid={testid}
    >
      {done ? <Check size={14} weight="bold" /> : <Copy size={14} />}
    </button>
  );
}

// ---------------- Endpoint definitions ----------------
function getEndpoints() {
  return [
    {
      id: "v2-send",
      method: "POST",
      path: "/v2/sendMessage",
      title: "Send Message",
      description:
        "Send a text message (and optionally a media file) to a single phone number. The phone must be in international format without +.",
      auth: "Bearer Token (your API key)",
      params: [
        { name: "phonenumber", type: "string", required: true, desc: "Recipient (e.g. 447488888888 — no +, no leading 0)" },
        { name: "text", type: "string", required: true, desc: "Message body. Max 4096 chars." },
        { name: "url", type: "string", required: false, desc: "Public URL of an image / video / document to attach." },
        { name: "delay", type: "string", required: false, desc: "MM-DD-YYYY HH:MM in GMT — schedule for later." },
      ],
      samples: {
        cURL: `curl --location '${API_BASE}/v2/sendMessage' \\
  --header 'Authorization: Bearer YOUR_API_KEY' \\
  --form 'phonenumber="447488888888"' \\
  --form 'text="Hello World!"' \\
  --form 'url="https://example.com/poster.jpg"'`,
        Python: `import requests

resp = requests.post(
    "${API_BASE}/v2/sendMessage",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    data={
        "phonenumber": "447488888888",
        "text": "Hello World!",
        "url": "https://example.com/poster.jpg",  # optional
    },
)
print(resp.json())`,
        Node: `import fetch from "node-fetch";
import FormData from "form-data";

const form = new FormData();
form.append("phonenumber", "447488888888");
form.append("text", "Hello World!");
form.append("url", "https://example.com/poster.jpg"); // optional

const res = await fetch("${API_BASE}/v2/sendMessage", {
  method: "POST",
  headers: { Authorization: "Bearer YOUR_API_KEY" },
  body: form,
});
console.log(await res.json());`,
        PHP: `$ch = curl_init('${API_BASE}/v2/sendMessage');
curl_setopt_array($ch, [
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_POST => true,
  CURLOPT_HTTPHEADER => ['Authorization: Bearer YOUR_API_KEY'],
  CURLOPT_POSTFIELDS => [
    'phonenumber' => '447488888888',
    'text' => 'Hello World!',
    'url' => 'https://example.com/poster.jpg',
  ],
]);
echo curl_exec($ch);`,
      },
      response: {
        status: 201,
        body: `{
  "success": true,
  "statusCode": 201,
  "timestamp": "2026-04-28 09:02:10",
  "data": {
    "phonenumber": "447488888888",
    "id": "bcf2b4f0-73f7-4235-b691-e9b08a5aa0b9"
  }
}`,
      },
    },
    {
      id: "v2-group",
      method: "POST",
      path: "/v2/sendGroup",
      title: "Send Group Message",
      description: "Post a message to a WhatsApp group you're a member of.",
      auth: "Bearer Token (your API key)",
      params: [
        { name: "groupId", type: "string", required: true, desc: "WhatsApp group ID (the long numeric string from group invite metadata)." },
        { name: "text", type: "string", required: true, desc: "Message body. Max 4096 chars." },
        { name: "url", type: "string", required: false, desc: "Public URL of an image / video / document." },
        { name: "delay", type: "string", required: false, desc: "MM-DD-YYYY HH:MM in GMT — schedule for later." },
      ],
      samples: {
        cURL: `curl --location '${API_BASE}/v2/sendGroup' \\
  --header 'Authorization: Bearer YOUR_API_KEY' \\
  --form 'groupId="1203********"' \\
  --form 'text="Hello team!"'`,
        Python: `import requests
resp = requests.post(
    "${API_BASE}/v2/sendGroup",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    data={"groupId": "1203********", "text": "Hello team!"},
)
print(resp.json())`,
        Node: `const form = new FormData();
form.append("groupId", "1203********");
form.append("text", "Hello team!");
const r = await fetch("${API_BASE}/v2/sendGroup", {
  method: "POST",
  headers: { Authorization: "Bearer YOUR_API_KEY" },
  body: form,
});
console.log(await r.json());`,
        PHP: `curl_setopt($ch, CURLOPT_URL, '${API_BASE}/v2/sendGroup');
// see Send Message for full setup`,
      },
      response: {
        status: 201,
        body: `{
  "success": true,
  "statusCode": 201,
  "data": {
    "groupId": "1203********",
    "id": "d8fdf876-d54b-4522-bcf5-fabc8802fcbd"
  }
}`,
      },
    },
    {
      id: "v2-status",
      method: "GET",
      path: "/v2/message/status",
      title: "Get Message Status",
      description: "Look up the delivery status of a previously sent message by its id.",
      auth: "Bearer Token",
      params: [{ name: "id", type: "string", required: true, desc: "Message id returned from sendMessage." }],
      samples: {
        cURL: `curl '${API_BASE}/v2/message/status?id=bcf2b4f0-73f7-4235-b691-e9b08a5aa0b9' \\
  --header 'Authorization: Bearer YOUR_API_KEY'`,
        Python: `requests.get(
    "${API_BASE}/v2/message/status",
    params={"id": "bcf2b4f0-73f7-4235-b691-e9b08a5aa0b9"},
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)`,
      },
      response: {
        status: 200,
        body: `{
  "success": true,
  "result": {
    "status": "OK",
    "statusInfo": "message successfully sent.",
    "delivery": "device",
    "id": "bcf2b4f0-73f7-4235-b691-e9b08a5aa0b9",
    "text": "Hello World!",
    "phonenumber": "447488888888",
    "createdAt": "2026-04-28 08:01:51",
    "executedAt": "2026-04-28 08:01:55"
  },
  "statusCode": 200
}`,
      },
    },
    {
      id: "v2-sent",
      method: "GET",
      path: "/v2/message/sentMessages",
      title: "List Sent Messages",
      description: "Paginated list of all outbound messages on your account.",
      auth: "Bearer Token",
      params: [
        { name: "page", type: "integer", required: false, desc: "Page number (default 1)." },
        { name: "phonenumber", type: "string", required: false, desc: "Filter by recipient prefix." },
      ],
      samples: {
        cURL: `curl '${API_BASE}/v2/message/sentMessages?page=1' \\
  --header 'Authorization: Bearer YOUR_API_KEY'`,
      },
      response: {
        status: 200,
        body: `{
  "success": true,
  "result": {
    "count": 2,
    "pageCount": 1,
    "page": "1 of 1",
    "data": [{ "...": "..." }]
  },
  "statusCode": 200
}`,
      },
    },
    {
      id: "v2-recv",
      method: "GET",
      path: "/v2/message/receivedMessages",
      title: "List Received Messages",
      description: "Paginated list of inbound (received) messages.",
      auth: "Bearer Token",
      params: [
        { name: "page", type: "integer", required: false, desc: "Page number (default 1)." },
        { name: "phonenumber", type: "string", required: false, desc: "Filter by sender prefix." },
      ],
      samples: {
        cURL: `curl '${API_BASE}/v2/message/receivedMessages?page=1' \\
  --header 'Authorization: Bearer YOUR_API_KEY'`,
      },
      response: { status: 200, body: `{ "success": true, "result": { "data": [/* ... */] } }` },
    },
    {
      id: "v2-account",
      method: "GET",
      path: "/v2/account",
      title: "Account Info",
      description: "Returns your account quota, used messages, and connected sessions.",
      auth: "Bearer Token",
      samples: {
        cURL: `curl '${API_BASE}/v2/account' --header 'Authorization: Bearer YOUR_API_KEY'`,
      },
      response: {
        status: 200,
        body: `{
  "success": true,
  "result": {
    "email": "you@example.com",
    "quota": { "monthly": 5000, "used": 137 },
    "sessions": 1
  }
}`,
      },
    },
    {
      id: "v1-messages",
      method: "POST",
      path: "/v1/messages",
      title: "Send (text or media)",
      description:
        "Modern JSON-based send endpoint. Use either text or media_url. Defaults to your only connected session if session_id is omitted.",
      auth: "X-API-Key header",
      params: [
        { name: "to", type: "string", required: true, desc: "Recipient phone (international format, no +)." },
        { name: "text", type: "string", required: false, desc: "Text body. Required if media_url is empty." },
        { name: "media_url", type: "string", required: false, desc: "Public URL of media to attach." },
        { name: "caption", type: "string", required: false, desc: "Caption for media (overrides text for media)." },
        { name: "session_id", type: "string", required: false, desc: "Specific session id to use." },
      ],
      samples: {
        cURL: `curl --location '${API_BASE}/v1/messages' \\
  --header 'X-API-Key: wa9x_YOUR_KEY' \\
  --header 'Content-Type: application/json' \\
  --data '{"to":"447488888888","text":"Hello"}'`,
        Python: `import requests
requests.post(
    "${API_BASE}/v1/messages",
    headers={"X-API-Key": "wa9x_YOUR_KEY"},
    json={"to": "447488888888", "text": "Hello"},
)`,
        Node: `await fetch("${API_BASE}/v1/messages", {
  method: "POST",
  headers: {
    "X-API-Key": "wa9x_YOUR_KEY",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ to: "447488888888", text: "Hello" }),
});`,
      },
      response: {
        status: 200,
        body: `{
  "status": "sent",
  "message_id": "3EB0xxxx",
  "to": "447488888888",
  "error": null
}`,
      },
    },
    {
      id: "v1-sessions",
      method: "GET",
      path: "/v1/sessions",
      title: "List Sessions",
      description: "Lists every WhatsApp session linked to your account with live status.",
      auth: "X-API-Key header",
      samples: {
        cURL: `curl '${API_BASE}/v1/sessions' --header 'X-API-Key: wa9x_YOUR_KEY'`,
      },
      response: {
        status: 200,
        body: `[
  {
    "id": "abc-123",
    "name": "My WhatsApp",
    "status": "connected",
    "phone": "447488888888"
  }
]`,
      },
    },
  ];
}

// ---------------- Page ----------------
export default function DeveloperDocs() {
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState("intro");
  const endpoints = useMemo(getEndpoints, []);

  // Document title + meta for SEO
  useEffect(() => {
    const prevTitle = document.title;
    document.title = "wa.9x.design — Developer API Reference";
    const meta = document.createElement("meta");
    meta.name = "description";
    meta.content =
      "Public API documentation for wa.9x.design — send WhatsApp messages, attach media, manage sessions, receive inbound webhooks. Compatible with 360messenger v2 API.";
    document.head.appendChild(meta);
    return () => {
      document.title = prevTitle;
      try { document.head.removeChild(meta); } catch (e) { void e; }
    };
  }, []);

  // Scroll-spy
  useEffect(() => {
    const ids = SECTIONS.flatMap((s) => s.items.map((i) => i.id));
    const observers = [];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const o = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) setActiveId(id);
        },
        { rootMargin: "-30% 0px -60% 0px", threshold: 0 }
      );
      o.observe(el);
      observers.push(o);
    });
    return () => observers.forEach((o) => o.disconnect());
  }, []);

  const filteredSections = SECTIONS.map((s) => ({
    ...s,
    items: s.items.filter((i) =>
      query
        ? (i.label + " " + (i.method || "")).toLowerCase().includes(query.toLowerCase())
        : true
    ),
  })).filter((s) => s.items.length);

  return (
    <div className="min-h-screen bg-white text-neutral-950" data-testid="developer-docs">
      {/* Top bar */}
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur border-b border-neutral-200">
        <div className="px-6 lg:px-10 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="docs-brand">
            <div className="w-8 h-8 bg-[#1FA855] flex items-center justify-center sharp">
              <ChatCircle weight="fill" size={18} color="#fff" />
            </div>
            <span className="font-display font-bold text-lg tracking-tight">
              wa.9x.design
              <span className="text-neutral-400 font-normal ml-1">/ developers</span>
            </span>
          </Link>
          <nav className="flex items-center gap-3">
            <a
              href="https://github.com/iamsjtitu/WA"
              target="_blank"
              rel="noreferrer"
              className="text-sm text-neutral-600 hover:text-neutral-900 hidden sm:inline-flex items-center gap-1"
              data-testid="docs-github"
            >
              GitHub <ArrowSquareOut size={12} />
            </a>
            <Link
              to="/login"
              className="text-sm px-3 py-1.5 border border-neutral-300 hover:border-neutral-900 sharp"
              data-testid="docs-login"
            >
              Log in
            </Link>
            <Link
              to="/register"
              className="text-sm px-3 py-1.5 bg-[#1FA855] hover:bg-[#178c47] text-white sharp font-medium"
              data-testid="docs-signup"
            >
              Get API key
            </Link>
          </nav>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] max-w-7xl mx-auto">
        {/* Sidebar */}
        <aside className="lg:sticky lg:top-14 lg:self-start lg:h-[calc(100vh-3.5rem)] overflow-y-auto px-4 lg:px-6 py-6 border-b lg:border-b-0 lg:border-r border-neutral-200" data-testid="docs-sidebar">
          <div className="relative mb-5">
            <MagnifyingGlass
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-400"
            />
            <input
              type="text"
              placeholder="Search endpoints…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-sm border border-neutral-300 sharp outline-none focus:border-[#1FA855] font-mono"
              data-testid="docs-search"
            />
          </div>
          {filteredSections.map((s) => (
            <div key={s.id} className="mb-5">
              <p className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5">
                {s.title}
              </p>
              <ul>
                {s.items.map((i) => (
                  <li key={i.id}>
                    <a
                      href={`#${i.id}`}
                      onClick={() => setActiveId(i.id)}
                      className={`flex items-center gap-2 px-2 py-1 text-sm sharp transition ${
                        activeId === i.id
                          ? "bg-emerald-50 text-emerald-900 font-medium"
                          : "text-neutral-700 hover:bg-neutral-100"
                      }`}
                      data-testid={`docs-nav-${i.id}`}
                    >
                      {i.method && (
                        <span className="text-[9px] font-mono font-bold w-9 shrink-0 text-neutral-400">
                          {i.method}
                        </span>
                      )}
                      <span className="truncate">{i.label}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>

        {/* Main content */}
        <main className="px-6 lg:px-10 py-10 lg:py-14 max-w-3xl">
          {/* Intro */}
          <section id="intro" className="scroll-mt-24">
            <p className="font-mono text-[11px] uppercase tracking-widest text-[#1FA855] mb-2">
              Developer reference
            </p>
            <h1 className="font-display text-4xl sm:text-5xl tracking-tight font-bold">
              wa.9x.design API
            </h1>
            <p className="mt-4 text-lg text-neutral-700">
              Send and receive WhatsApp messages from your application using a simple HTTPS API.
              Drop-in compatible with the 360messenger v2 contract — change the base URL, keep your code.
            </p>

            <div className="mt-6 grid sm:grid-cols-3 gap-3">
              <FeatureCard icon={<Lightning size={18} weight="fill" />} title="Fast">
                Messages dispatched within ~600ms of API call (network excluded).
              </FeatureCard>
              <FeatureCard icon={<Code size={18} weight="fill" />} title="Drop-in">
                Compatible with 360messenger v2 — switch by changing the host.
              </FeatureCard>
              <FeatureCard icon={<Lock size={18} weight="fill" />} title="Secure">
                HMAC-signed inbound webhooks, scoped per-account API keys.
              </FeatureCard>
            </div>

            <div className="mt-6 border border-neutral-200 sharp p-4 bg-neutral-50">
              <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">Base URL</p>
              <code className="block font-mono text-[13px] mt-1.5">{API_BASE}</code>
            </div>
          </section>

          {/* Auth */}
          <section id="auth-bearer" className="scroll-mt-24 mt-14">
            <h2 className="font-display text-3xl tracking-tight font-bold">Authentication</h2>
            <p className="mt-3 text-neutral-700">
              Every request must be authenticated. Two schemes are supported:
            </p>

            <h3 className="mt-6 font-display text-xl font-semibold flex items-baseline gap-2">
              <span>Bearer Token</span>
              <span className="text-xs text-neutral-500 font-mono">v2 endpoints</span>
            </h3>
            <p className="mt-2 text-neutral-700">
              Add an <code className="font-mono text-sm bg-neutral-100 px-1.5 py-0.5">Authorization</code> header containing your API key as a Bearer token.
            </p>
            <div className="mt-3">
              <CodeTabs
                samples={{
                  cURL: `curl --header 'Authorization: Bearer YOUR_API_KEY' \\
     '${API_BASE}/v2/account'`,
                  Python: `headers={"Authorization": "Bearer YOUR_API_KEY"}`,
                  Node: `headers: { Authorization: "Bearer YOUR_API_KEY" }`,
                }}
                testid="auth-bearer-sample"
              />
            </div>

            <h3 id="auth-apikey" className="scroll-mt-24 mt-8 font-display text-xl font-semibold flex items-baseline gap-2">
              <span>X-API-Key Header</span>
              <span className="text-xs text-neutral-500 font-mono">v1 endpoints</span>
            </h3>
            <p className="mt-2 text-neutral-700">
              For modern <code>/v1/*</code> endpoints, send the API key in the <code className="font-mono text-sm bg-neutral-100 px-1.5 py-0.5">X-API-Key</code> header. Keys begin with <code className="font-mono">wa9x_</code>.
            </p>
            <div className="mt-3">
              <CodeTabs
                samples={{
                  cURL: `curl --header 'X-API-Key: wa9x_YOUR_KEY' \\
     '${API_BASE}/v1/sessions'`,
                  Python: `headers={"X-API-Key": "wa9x_YOUR_KEY"}`,
                }}
                testid="auth-apikey-sample"
              />
            </div>
          </section>

          {/* v2 Section */}
          <section id="v2" className="mt-16">
            <h2 className="font-display text-3xl tracking-tight font-bold">WhatsApp API v2.0</h2>
            <p className="mt-2 text-neutral-700">
              Form-data endpoints. 100% wire-compatible with 360messenger so you can drop in our base URL
              into existing integrations.
            </p>
          </section>
          {endpoints
            .filter((e) => e.id.startsWith("v2-"))
            .map((e) => (
              <Endpoint key={e.id} {...e} />
            ))}

          {/* v1 Section */}
          <section id="v1" className="mt-20">
            <h2 className="font-display text-3xl tracking-tight font-bold">Modern API v1.0</h2>
            <p className="mt-2 text-neutral-700">
              JSON in, JSON out. Recommended for new integrations.
            </p>
          </section>
          {endpoints
            .filter((e) => e.id.startsWith("v1-"))
            .map((e) => (
              <Endpoint key={e.id} {...e} />
            ))}

          {/* Webhooks */}
          <section id="wh-inbound" className="scroll-mt-24 mt-20">
            <h2 className="font-display text-3xl tracking-tight font-bold">Inbound Webhooks</h2>
            <p className="mt-3 text-neutral-700">
              Configure a webhook URL in <em>Settings → Inbound Webhook</em> and we'll POST every received
              WhatsApp message to your endpoint, signed with HMAC-SHA256.
            </p>

            <h3 className="mt-6 font-display text-xl font-semibold">Payload</h3>
            <ResponseBlock
              status={200}
              body={`{
  "event": "message.received",
  "session_id": "abc-123",
  "from": "447488888888",
  "text": "Hi there!",
  "type": "text",
  "message_id": "3EB0xxxx",
  "timestamp": 1716893012345,
  "has_media": false,
  "media_url": null,
  "mime_type": null,
  "file_name": null
}`}
              testid="webhook-payload"
            />

            <h3 id="wh-verify" className="scroll-mt-24 mt-8 font-display text-xl font-semibold">
              HMAC Verification
            </h3>
            <p className="mt-2 text-neutral-700">
              Each request carries an <code className="font-mono text-sm bg-neutral-100 px-1.5 py-0.5">X-Wapihub-Signature</code> header
              of the form <code className="font-mono">sha256=&lt;hex&gt;</code>. Recompute it with your webhook secret and compare in constant time.
            </p>
            <div className="mt-3">
              <CodeTabs
                samples={{
                  Python: `import hmac, hashlib

def verify(body: bytes, header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)`,
                  Node: `import crypto from "node:crypto";

export function verify(body, header, secret) {
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(body)
    .digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(header));
}`,
                  PHP: `function verify($body, $header, $secret) {
  $expected = 'sha256=' . hash_hmac('sha256', $body, $secret);
  return hash_equals($expected, $header);
}`,
                }}
                testid="hmac-verify-sample"
              />
            </div>
          </section>

          {/* Footer CTA */}
          <section className="mt-20 mb-10 border-t border-neutral-200 pt-10">
            <h2 className="font-display text-2xl tracking-tight font-bold">
              Ready to start?
            </h2>
            <p className="mt-2 text-neutral-700">
              Create a free account, link a WhatsApp number, and you're ready to send.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                to="/register"
                className="px-4 py-2 bg-[#1FA855] hover:bg-[#178c47] text-white sharp font-medium inline-flex items-center gap-2"
                data-testid="docs-cta-signup"
              >
                <Terminal size={16} weight="fill" /> Create account
              </Link>
              <Link
                to="/login"
                className="px-4 py-2 border border-neutral-300 hover:border-neutral-900 sharp inline-flex items-center gap-2"
                data-testid="docs-cta-login"
              >
                Already have one — log in
              </Link>
            </div>
            <p className="mt-8 text-xs text-neutral-500 font-mono">
              wa.9x.design © {new Date().getFullYear()} — built on Baileys
            </p>
          </section>
        </main>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, children }) {
  return (
    <div className="border border-neutral-200 sharp p-4">
      <div className="flex items-center gap-2 text-[#1FA855]">
        {icon}
        <span className="font-display font-semibold text-sm">{title}</span>
      </div>
      <p className="mt-2 text-sm text-neutral-600 leading-relaxed">{children}</p>
    </div>
  );
}
