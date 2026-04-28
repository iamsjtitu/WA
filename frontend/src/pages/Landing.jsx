import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  CheckCircle,
  Code,
  ChatCircle,
  Lightning,
  ShieldCheck,
  Globe,
  ChartLineUp,
} from "@phosphor-icons/react";

export default function Landing() {
  return (
    <div className="min-h-screen bg-white text-neutral-950">
      {/* Header */}
      <header
        className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-neutral-200"
        data-testid="landing-header"
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-link">
            <div className="w-8 h-8 bg-[#1FA855] flex items-center justify-center sharp">
              <ChatCircle weight="fill" size={18} color="#fff" />
            </div>
            <span className="font-display font-bold text-lg tracking-tight">wa.9x.design</span>
            <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 ml-1 border border-neutral-200 px-1.5 py-0.5">
              api
            </span>
          </Link>
          <nav className="hidden md:flex items-center gap-8 text-sm text-neutral-600">
            <a href="#features" className="hover:text-neutral-950">Features</a>
            <a href="#how" className="hover:text-neutral-950">How it works</a>
            <a href="#pricing" className="hover:text-neutral-950">Pricing</a>
            <Link to="/developer" className="hover:text-neutral-950" data-testid="nav-docs-link">Docs</Link>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/login" className="btn-ghost text-sm" data-testid="nav-login-btn">
              Sign in
            </Link>
            <Link to="/register" className="btn-brand text-sm" data-testid="nav-signup-btn">
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-neutral-200">
        <div className="absolute inset-0 grid-bg opacity-60 pointer-events-none" />
        <div className="max-w-7xl mx-auto px-6 pt-20 pb-24 grid lg:grid-cols-12 gap-10 relative">
          <div className="lg:col-span-7">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 border border-neutral-200 bg-white px-3 py-1 text-xs font-mono uppercase tracking-wider text-neutral-600 sharp"
            >
              <span className="dot connected" /> Built for developers · Resell-ready API
            </motion.div>
            <motion.h1
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.05 }}
              className="font-display tracking-tight text-5xl sm:text-6xl lg:text-7xl mt-6 leading-[1.02]"
            >
              The <span className="bg-[#EDFF00] px-2">WhatsApp API</span>
              <br /> you ship to your customers.
            </motion.h1>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.15 }}
              className="text-lg text-neutral-600 mt-6 max-w-xl"
            >
              Link any WhatsApp number, get an API key, and start sending. wa.9x.design gives
              you a multi-tenant dashboard, quotas, message logs, and a clean REST endpoint —
              all under your own brand.
            </motion.p>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.25 }}
              className="mt-8 flex flex-wrap items-center gap-3"
            >
              <Link to="/register" className="btn-brand inline-flex items-center gap-2" data-testid="hero-cta-signup">
                Start free <ArrowRight size={16} />
              </Link>
              <a href="#api" className="btn-ghost inline-flex items-center gap-2" data-testid="hero-cta-docs">
                <Code size={16} /> Read the docs
              </a>
              <span className="font-mono text-xs text-neutral-500">
                no credit card · 1,000 msgs/mo free
              </span>
            </motion.div>

            <div className="mt-10 grid grid-cols-3 max-w-md border border-neutral-200 sharp divide-x divide-neutral-200">
              <Stat label="latency" value="<2s" />
              <Stat label="uptime" value="99.9%" />
              <Stat label="msgs/sec" value="20" />
            </div>
          </div>

          <div className="lg:col-span-5 relative">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="bg-[#0A0A0A] sharp border border-neutral-800 overflow-hidden shadow-2xl"
            >
              <div className="px-4 py-2 flex items-center gap-2 border-b border-neutral-800 text-xs text-neutral-500 font-mono">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
                <span className="ml-3">terminal — wa9x</span>
              </div>
              <pre className="p-5 text-[12.5px] leading-relaxed text-neutral-200 font-mono whitespace-pre-wrap">
{`$ curl -X POST https://your.wa9x.app/api/v1/messages \\
   -H "X-API-Key: wa9x_•••" \\
   -H "Content-Type: application/json" \\
   -d '{
     "to": "919876543210",
     "text": "Hi {{name}}, your OTP is 4421"
   }'

`}<span className="text-emerald-400">{`{
  "status": "sent",
  "message_id": "3EB0...A91",
  "to": "919876543210"
}`}</span>
              </pre>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="absolute -bottom-6 -left-6 bg-white border border-neutral-200 p-4 sharp shadow-lg hidden md:flex items-center gap-3"
            >
              <Lightning size={20} weight="fill" color="#1FA855" />
              <div>
                <div className="font-display font-semibold text-sm">Sub-2s delivery</div>
                <div className="text-xs text-neutral-500 font-mono">queued → sent</div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Logos / Trust */}
      <section className="border-b border-neutral-200 bg-neutral-50">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-wrap items-center justify-between gap-6">
          <p className="font-mono text-xs uppercase tracking-widest text-neutral-500">
            Trusted by indie SaaS, agencies, and growth teams
          </p>
          <div className="flex flex-wrap items-center gap-8 text-neutral-400 font-display font-semibold tracking-tight">
            <span>NorthStack</span>
            <span>Plinth.io</span>
            <span>RootGrid</span>
            <span>Kiln Labs</span>
            <span>Loop&Co.</span>
          </div>
        </div>
      </section>

      {/* Features bento */}
      <section id="features" className="border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-widest text-[#1FA855]">
              · Features
            </p>
            <h2 className="font-display text-4xl sm:text-5xl mt-3 tracking-tight">
              Everything to run a WhatsApp API business.
            </h2>
            <p className="text-neutral-600 mt-4">
              Built like the dev tools you actually want to use — not another reseller panel.
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-0 mt-12 border border-neutral-200">
            <Feature
              icon={<ChatCircle size={22} weight="fill" />}
              title="Multi-session WhatsApp"
              body="Each customer links their own number via QR. Sessions auto-reconnect and persist across restarts."
            />
            <Feature
              icon={<Code size={22} weight="fill" />}
              title="REST API + per-user keys"
              body="One clean endpoint. Each customer gets their own X-API-Key with quota enforcement."
              border
            />
            <Feature
              icon={<ChartLineUp size={22} weight="fill" />}
              title="Live logs & analytics"
              body="Searchable, queryable message logs with status, errors, and source tracking."
            />
            <Feature
              icon={<ShieldCheck size={22} weight="fill" />}
              title="Quota & access control"
              body="Set monthly limits per customer. Lock or rotate API keys instantly from the admin panel."
              border
              top
            />
            <Feature
              icon={<Globe size={22} weight="fill" />}
              title="Bulk campaigns"
              body="Paste a list, write your message, hit send. Throttled delivery built-in to stay safe."
              top
            />
            <Feature
              icon={<Lightning size={22} weight="fill" />}
              title="Self-hosted control"
              body="Your data, your numbers, your billing. We don't touch the conversations — ever."
              border
              top
            />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-b border-neutral-200 bg-neutral-50">
        <div className="max-w-7xl mx-auto px-6 py-20 grid lg:grid-cols-2 gap-12 items-start">
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-[#1FA855]">
              · 3 steps
            </p>
            <h2 className="font-display text-4xl sm:text-5xl mt-3 tracking-tight">
              From signup to first message in 90 seconds.
            </h2>
            <p className="text-neutral-600 mt-4">
              No business verification. No template approvals. Just scan a QR and send.
            </p>
          </div>
          <div className="space-y-0 border border-neutral-200 bg-white">
            <Step n="01" title="Register & link a number">
              Create your wa.9x.design account and scan the QR with WhatsApp on your phone to link any number.
            </Step>
            <Step n="02" title="Grab your API key">
              Visit the dashboard, copy your <code className="font-mono text-xs px-1.5 py-0.5 bg-neutral-100 border border-neutral-200">X-API-Key</code>, and start integrating.
            </Step>
            <Step n="03" title="Send via REST or dashboard">
              Send messages programmatically, or from the in-app composer. Logs and quotas update in real time.
            </Step>
          </div>
        </div>
      </section>

      {/* API preview */}
      <section id="api" className="bg-[#0A0A0A] text-white border-b border-neutral-800 relative">
        <div className="absolute inset-0 grid-bg-dark opacity-50 pointer-events-none" />
        <div className="max-w-7xl mx-auto px-6 py-20 relative">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <p className="font-mono text-xs uppercase tracking-widest text-[#EDFF00]">
                · API
              </p>
              <h2 className="font-display text-4xl sm:text-5xl mt-3 tracking-tight">
                One endpoint. Zero ceremony.
              </h2>
              <p className="text-neutral-400 mt-4 max-w-md">
                Authenticate with a header, send a message, get a delivery status. That's it.
              </p>
              <ul className="mt-8 space-y-3 text-sm">
                {["Bearer-style header auth", "JSON in, JSON out", "Idempotent sends", "Per-account quotas"].map((t) => (
                  <li key={t} className="flex items-center gap-2 text-neutral-300">
                    <CheckCircle size={16} weight="fill" color="#EDFF00" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="codeblk text-[12.5px]">
{`POST /api/v1/messages
Host: your.wa9x.app
X-API-Key: wa9x_••••••••••••••••••
Content-Type: application/json

{
  "to": "919876543210",
  "text": "Your code is 4421",
  "session_id": "optional-session-uuid"
}

→ 200 OK
{
  "status": "sent",
  "message_id": "3EB0...A91",
  "to": "919876543210"
}`}
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-widest text-[#1FA855]">
              · Pricing
            </p>
            <h2 className="font-display text-4xl sm:text-5xl mt-3 tracking-tight">
              Pay-as-you-grow, indie-friendly.
            </h2>
          </div>
          <div className="mt-12 grid md:grid-cols-3 gap-0 border border-neutral-200">
            <Plan
              name="Free"
              price="₹0"
              period="forever"
              features={["1 WhatsApp number", "1,000 msgs / month", "API + dashboard", "Basic logs"]}
              cta="Start free"
            />
            <Plan
              name="Starter"
              price="₹999"
              period="/ month"
              features={["3 numbers", "20,000 msgs / month", "Bulk campaigns", "Priority retries"]}
              highlight
              cta="Choose Starter"
            />
            <Plan
              name="Pro"
              price="Custom"
              period="reseller"
              features={["Unlimited numbers", "Per-customer quotas", "Whitelabel API URL", "Dedicated support"]}
              cta="Contact sales"
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-6 py-16 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <h3 className="font-display text-3xl sm:text-4xl tracking-tight">
            Stop renting. Start <span className="bg-[#EDFF00] px-2">reselling.</span>
          </h3>
          <Link to="/register" className="btn-brand inline-flex items-center gap-2 self-start md:self-auto" data-testid="bottom-cta-signup">
            Create your account <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#0A0A0A] text-neutral-400">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[#1FA855] flex items-center justify-center sharp">
              <ChatCircle weight="fill" size={14} color="#fff" />
            </div>
            <span className="font-display font-semibold text-white">wa.9x.design</span>
            <span className="font-mono text-xs ml-2">© {new Date().getFullYear()}</span>
          </div>
          <p className="font-mono text-xs">
            Unofficial WhatsApp Web automation. Use responsibly.
          </p>
        </div>
      </footer>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="px-4 py-3">
      <div className="font-display font-bold text-2xl tracking-tight">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
    </div>
  );
}

function Feature({ icon, title, body, border, top }) {
  return (
    <div
      className={`p-8 ${border ? "lg:border-l border-neutral-200" : ""} ${
        top ? "border-t border-neutral-200" : ""
      } hover:bg-neutral-50 transition-colors`}
    >
      <div className="w-10 h-10 bg-[#1FA855]/10 text-[#1FA855] flex items-center justify-center sharp">
        {icon}
      </div>
      <h3 className="font-display font-semibold text-xl mt-5 tracking-tight">{title}</h3>
      <p className="text-neutral-600 mt-2 text-sm leading-relaxed">{body}</p>
    </div>
  );
}

function Step({ n, title, children }) {
  return (
    <div className="p-8 border-b border-neutral-200 last:border-b-0 flex gap-6">
      <div className="font-mono text-sm text-[#1FA855]">{n}</div>
      <div>
        <h4 className="font-display font-semibold text-lg tracking-tight">{title}</h4>
        <p className="text-neutral-600 mt-1 text-sm">{children}</p>
      </div>
    </div>
  );
}

function Plan({ name, price, period, features, highlight, cta }) {
  return (
    <div className={`p-8 ${highlight ? "bg-[#0A0A0A] text-white" : "bg-white"} relative`}>
      {highlight && (
        <span className="absolute top-4 right-4 font-mono text-[10px] uppercase tracking-widest bg-[#EDFF00] text-black px-2 py-1 sharp">
          most popular
        </span>
      )}
      <h3 className="font-display font-semibold text-xl">{name}</h3>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="font-display text-4xl tracking-tight">{price}</span>
        <span className={`font-mono text-xs ${highlight ? "text-neutral-400" : "text-neutral-500"}`}>
          {period}
        </span>
      </div>
      <ul className={`mt-6 space-y-2 text-sm ${highlight ? "text-neutral-300" : "text-neutral-600"}`}>
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2">
            <CheckCircle size={16} weight="fill" color={highlight ? "#EDFF00" : "#1FA855"} className="mt-0.5 shrink-0" />
            {f}
          </li>
        ))}
      </ul>
      <Link
        to="/register"
        className={`mt-8 inline-flex items-center gap-2 ${highlight ? "btn-accent" : "btn-brand"} text-sm`}
        data-testid={`pricing-${name.toLowerCase()}-cta`}
      >
        {cta} <ArrowRight size={14} />
      </Link>
    </div>
  );
}
