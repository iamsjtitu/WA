import { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../lib/api";
import {
  ArrowLeft,
  ArrowRight,
  Phone,
  QrCode,
  Check,
  CheckCircle,
  Warning,
  Spinner,
  Copy,
  House,
  Folders,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const COUNTRY_CODES = [
  { code: "91", name: "India", flag: "IN" },
  { code: "1", name: "United States", flag: "US" },
  { code: "44", name: "United Kingdom", flag: "GB" },
  { code: "971", name: "United Arab Emirates", flag: "AE" },
  { code: "61", name: "Australia", flag: "AU" },
  { code: "65", name: "Singapore", flag: "SG" },
  { code: "966", name: "Saudi Arabia", flag: "SA" },
  { code: "92", name: "Pakistan", flag: "PK" },
  { code: "880", name: "Bangladesh", flag: "BD" },
  { code: "94", name: "Sri Lanka", flag: "LK" },
  { code: "60", name: "Malaysia", flag: "MY" },
  { code: "62", name: "Indonesia", flag: "ID" },
  { code: "63", name: "Philippines", flag: "PH" },
  { code: "234", name: "Nigeria", flag: "NG" },
  { code: "27", name: "South Africa", flag: "ZA" },
  { code: "49", name: "Germany", flag: "DE" },
  { code: "33", name: "France", flag: "FR" },
  { code: "55", name: "Brazil", flag: "BR" },
  { code: "52", name: "Mexico", flag: "MX" },
  { code: "81", name: "Japan", flag: "JP" },
];

const PREP_STEPS = [
  "Creating Service Instance",
  "Assigning API Key",
  "Configuring Service",
  "Generating Connection",
];

export default function ServiceCreate() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [method, setMethod] = useState(null); // "phone" | "qr"
  const [serviceName, setServiceName] = useState("");
  const [country, setCountry] = useState(COUNTRY_CODES[0]);
  const [phoneLocal, setPhoneLocal] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [prepDone, setPrepDone] = useState(0);
  const [busy, setBusy] = useState(false);

  const [sessionId, setSessionId] = useState(null);
  const [pairingCode, setPairingCode] = useState("");
  const [qrData, setQrData] = useState(null);
  const [status, setStatus] = useState("starting");
  const [secondsLeft, setSecondsLeft] = useState(15 * 60); // 15 min
  const pollRef = useRef(null);

  useEffect(() => {
    if (step !== 5) return;
    if (!sessionId) return;
    if (pollRef.current) clearInterval(pollRef.current);

    const poll = async () => {
      try {
        const { data } = await api.get(`/sessions/${sessionId}/status`);
        setStatus(data.status);
        if (data.qr) setQrData(data.qr);
        if (data.status === "connected") {
          clearInterval(pollRef.current);
          toast.success("Connected to WhatsApp");
          setTimeout(() => navigate(`/app/sessions/${sessionId}`), 800);
        }
      } catch {}
    };
    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => clearInterval(pollRef.current);
  }, [step, sessionId, navigate]);

  useEffect(() => {
    if (step !== 5) return;
    const t = setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(t);
  }, [step]);

  // step 4 — preparing animation
  useEffect(() => {
    if (step !== 4) return;
    let cancelled = false;
    (async () => {
      try {
        // 1. Create service
        setPrepDone(0);
        await new Promise((r) => setTimeout(r, 600));
        if (cancelled) return;
        const { data: created } = await api.post("/sessions", {
          name: serviceName.trim() || `Service ${Date.now().toString().slice(-5)}`,
        });
        setSessionId(created.id);
        setPrepDone(1);

        // 2. Assigning API Key (already done at register, just visual)
        await new Promise((r) => setTimeout(r, 500));
        if (cancelled) return;
        setPrepDone(2);

        // 3. Configuring service (apply default country code)
        await api.patch(`/sessions/${created.id}/settings`, {
          default_country_code: country.code,
          auto_prefix: true,
        });
        if (cancelled) return;
        setPrepDone(3);

        // 4. Generating connection
        if (method === "phone") {
          const fullPhone = (country.code + phoneLocal).replace(/[^0-9]/g, "");
          try {
            const { data } = await api.post(`/sessions/${created.id}/pair`, {
              phone: fullPhone,
            });
            if (data.pairing_code) setPairingCode(data.pairing_code);
          } catch (e) {
            toast.error(
              e?.response?.data?.detail || "Pairing code failed — falling back to QR"
            );
          }
        }
        if (cancelled) return;
        setPrepDone(4);
        await new Promise((r) => setTimeout(r, 500));
        if (cancelled) return;
        setStep(5);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Service creation failed");
        setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  const fmtTime = (s) => {
    const m = Math.floor(s / 60).toString().padStart(2, "0");
    const ss = (s % 60).toString().padStart(2, "0");
    return `${m}:${ss}`;
  };

  return (
    <div className="p-10 fade-in" data-testid="service-create-page">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-xs text-neutral-500 font-mono">
        <Link to="/" className="hover:text-neutral-900 inline-flex items-center gap-1">
          <House size={12} /> Portal Home
        </Link>
        <span>/</span>
        <Link to="/app" className="hover:text-neutral-900">Client Area</Link>
        <span>/</span>
        <Link to="/app/sessions" className="hover:text-neutral-900 inline-flex items-center gap-1">
          <Folders size={12} /> My Services
        </Link>
        <span>/</span>
        <span className="text-neutral-900">Service Connection</span>
      </nav>

      <div className="flex items-center justify-between mt-3 flex-wrap gap-3">
        <h1 className="font-display text-4xl tracking-tight">Service Connection</h1>
        {step === 5 && (
          <div className="flex gap-2">
            <span className="status-pill !bg-yellow-50 !border-yellow-200 !text-yellow-800">
              <span className="dot qr" /> Awaiting Connection
            </span>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="mt-6 flex items-center gap-2 max-w-2xl">
        {[1, 2, 3, 4, 5].map((n) => (
          <div key={n} className="flex-1 flex items-center gap-2">
            <div
              className={`h-7 w-7 rounded-full border-2 flex items-center justify-center text-xs font-mono ${
                step > n
                  ? "bg-[#1FA855] border-[#1FA855] text-white"
                  : step === n
                    ? "border-[#1FA855] text-[#1FA855]"
                    : "border-neutral-300 text-neutral-400"
              }`}
              data-testid={`step-indicator-${n}`}
            >
              {step > n ? <Check size={14} weight="bold" /> : n}
            </div>
            {n < 5 && <div className={`h-0.5 flex-1 ${step > n ? "bg-[#1FA855]" : "bg-neutral-200"}`} />}
          </div>
        ))}
      </div>

      <div className="mt-8 max-w-3xl">
        {step === 1 && (
          <Step1ChooseMethod
            method={method}
            setMethod={setMethod}
            serviceName={serviceName}
            setServiceName={setServiceName}
            onNext={() => setStep(method === "phone" ? 2 : 3)}
            onBack={() => navigate("/app/sessions")}
          />
        )}
        {step === 2 && (
          <Step2Phone
            country={country}
            setCountry={setCountry}
            phoneLocal={phoneLocal}
            setPhoneLocal={setPhoneLocal}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Guidelines
            agreed={agreed}
            setAgreed={setAgreed}
            onBack={() => setStep(method === "phone" ? 2 : 1)}
            onNext={() => {
              if (!agreed) return toast.error("Please confirm you've read the guidelines");
              setBusy(true);
              setStep(4);
            }}
          />
        )}
        {step === 4 && <Step4Preparing prepDone={prepDone} method={method} />}
        {step === 5 && (
          <Step5Connect
            method={method}
            qrData={qrData}
            pairingCode={pairingCode}
            phoneFull={country.code + phoneLocal}
            status={status}
            secondsLeft={secondsLeft}
            timeStr={fmtTime(secondsLeft)}
          />
        )}
      </div>
    </div>
  );
}

// ============ Step 1 ============
function Step1ChooseMethod({ method, setMethod, serviceName, setServiceName, onNext, onBack }) {
  return (
    <div data-testid="step1">
      <div className="border border-neutral-200 sharp p-6 mb-6">
        <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          Service Name
        </label>
        <input
          data-testid="service-name-input"
          value={serviceName}
          onChange={(e) => setServiceName(e.target.value)}
          placeholder="e.g. Sales Line, Support Desk"
          className="w-full mt-1.5 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855]"
        />
        <p className="text-xs text-neutral-500 mt-1">
          A label to identify this WhatsApp number in your dashboard.
        </p>
      </div>

      <h2 className="font-display text-2xl tracking-tight">Choose Connection Method</h2>
      <p className="text-sm text-neutral-600 mt-1">
        Pick how you want to link your WhatsApp account.
      </p>

      <div className="mt-6 grid md:grid-cols-2 gap-4">
        <MethodCard
          selected={method === "phone"}
          onClick={() => setMethod("phone")}
          icon={<Phone size={32} weight="fill" />}
          title="Connect via Phone Number"
          body="Enter your WhatsApp number to receive an 8-character code. Easier on a phone-only setup."
          testId="method-phone"
        />
        <MethodCard
          selected={method === "qr"}
          onClick={() => setMethod("qr")}
          icon={<QrCode size={32} weight="fill" />}
          title="Scan QR Code"
          body="Scan a QR with WhatsApp to instantly link a device. Fastest if you have your phone handy."
          testId="method-qr"
        />
      </div>

      <div className="mt-8 flex justify-between">
        <button onClick={onBack} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="step1-back">
          <ArrowLeft size={14} /> Cancel
        </button>
        <button
          onClick={onNext}
          disabled={!method}
          className="btn-brand text-sm inline-flex items-center gap-2 disabled:opacity-50"
          data-testid="step1-next"
        >
          Continue <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

function MethodCard({ selected, onClick, icon, title, body, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`text-left border-2 sharp p-6 transition-all ${
        selected
          ? "border-[#1FA855] bg-emerald-50/50"
          : "border-neutral-200 hover:border-neutral-400"
      }`}
    >
      <div
        className={`w-14 h-14 sharp flex items-center justify-center ${
          selected ? "bg-[#1FA855] text-white" : "bg-neutral-100 text-neutral-700"
        }`}
      >
        {icon}
      </div>
      <h3 className="font-display font-semibold text-lg mt-4 tracking-tight">{title}</h3>
      <p className="text-sm text-neutral-600 mt-1.5 leading-relaxed">{body}</p>
      {selected && (
        <div className="mt-3 inline-flex items-center gap-1.5 text-[#1FA855] text-xs font-mono uppercase tracking-widest">
          <CheckCircle size={14} weight="fill" /> selected
        </div>
      )}
    </button>
  );
}

// ============ Step 2 ============
function Step2Phone({ country, setCountry, phoneLocal, setPhoneLocal, onBack, onNext }) {
  return (
    <div data-testid="step2">
      <h2 className="font-display text-2xl tracking-tight">Connect via Phone Number</h2>
      <p className="text-sm text-neutral-600 mt-1">
        Enter the WhatsApp number you want to link. We'll generate an 8-character pairing code.
      </p>

      <div className="mt-6 border border-neutral-200 sharp p-6">
        <label className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          WhatsApp Number
        </label>
        <div className="flex gap-2 mt-1.5">
          <select
            data-testid="phone-country"
            value={country.code}
            onChange={(e) => setCountry(COUNTRY_CODES.find((c) => c.code === e.target.value))}
            className="border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] bg-white font-mono text-sm w-32"
          >
            {COUNTRY_CODES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.flag} +{c.code}
              </option>
            ))}
          </select>
          <input
            data-testid="phone-input"
            value={phoneLocal}
            onChange={(e) => setPhoneLocal(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="9876543210"
            inputMode="numeric"
            className="flex-1 border border-neutral-300 sharp px-3 py-2.5 outline-none focus:border-[#1FA855] focus:ring-1 focus:ring-[#1FA855] font-mono"
          />
        </div>
        <p className="text-xs text-neutral-500 mt-2">
          {country.name} · Full number: <span className="font-mono">+{country.code}{phoneLocal || "•••"}</span>
        </p>
      </div>

      <div className="mt-8 flex justify-between">
        <button onClick={onBack} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="step2-back">
          <ArrowLeft size={14} /> Back
        </button>
        <button
          onClick={onNext}
          disabled={phoneLocal.length < 6}
          className="btn-brand text-sm inline-flex items-center gap-2 disabled:opacity-50"
          data-testid="step2-next"
        >
          Continue <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

// ============ Step 3 ============
function Step3Guidelines({ agreed, setAgreed, onBack, onNext }) {
  const guidelines = [
    "Do not initiate conversations with strangers — wait for them to message you first.",
    "Avoid sending bulk messages to numbers you have no relationship with.",
    "Add random delays between messages — don't blast 50 in a row.",
    "Don't send repetitive promotional content; vary your wording.",
    "Avoid prohibited content, spam, scams, or anything that violates WhatsApp's Terms of Service.",
  ];
  return (
    <div data-testid="step3">
      <h2 className="font-display text-2xl tracking-tight">Service Usage Guidelines</h2>
      <p className="text-sm text-neutral-600 mt-1">
        Please review these guidelines before connecting. They reduce the risk of WhatsApp banning your number.
      </p>

      <div className="mt-6 border border-neutral-200 sharp">
        <ul className="divide-y divide-neutral-100">
          {guidelines.map((g, i) => (
            <li key={i} className="px-5 py-4 flex items-start gap-3">
              <div className="w-7 h-7 sharp bg-[#1FA855]/10 text-[#1FA855] flex items-center justify-center flex-shrink-0 font-mono text-xs">
                {i + 1}
              </div>
              <p className="text-sm text-neutral-700">{g}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-5 border border-yellow-200 sharp p-4 bg-yellow-50 flex gap-3">
        <Warning size={18} weight="fill" className="text-yellow-700 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-yellow-900">
          Unofficial WhatsApp Web automation can result in your number being temporarily or permanently
          banned by WhatsApp. Use responsibly. We don't take responsibility for bans caused by misuse.
        </p>
      </div>

      <label className="mt-5 flex items-start gap-3 cursor-pointer" data-testid="step3-checkbox-label">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1"
          data-testid="step3-checkbox"
        />
        <span className="text-sm">
          I have read all of the above and understand the risks of unofficial WhatsApp automation.
        </span>
      </label>

      <div className="mt-8 flex justify-between">
        <button onClick={onBack} className="btn-ghost text-sm inline-flex items-center gap-2" data-testid="step3-back">
          <ArrowLeft size={14} /> Back
        </button>
        <button
          onClick={onNext}
          disabled={!agreed}
          className="btn-brand text-sm inline-flex items-center gap-2 disabled:opacity-50"
          data-testid="step3-next"
        >
          Confirm & Connect <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

// ============ Step 4 ============
function Step4Preparing({ prepDone, method }) {
  const labels = [...PREP_STEPS];
  if (method === "phone") labels[3] = "Generating Pairing Code";
  else labels[3] = "Generating QR Code";

  return (
    <div data-testid="step4" className="text-center py-8">
      <Spinner
        size={48}
        weight="bold"
        className="mx-auto text-[#1FA855] animate-spin"
      />
      <h2 className="font-display text-2xl tracking-tight mt-6">Preparing Your Service</h2>
      <p className="text-sm text-neutral-600 mt-1">Hang tight — this takes just a few seconds.</p>

      <div className="mt-8 mx-auto max-w-md text-left border border-neutral-200 sharp">
        {labels.map((label, i) => (
          <div
            key={i}
            className={`px-5 py-3.5 flex items-center gap-3 ${
              i < labels.length - 1 ? "border-b border-neutral-100" : ""
            }`}
            data-testid={`prep-step-${i}`}
          >
            <div
              className={`w-6 h-6 sharp flex items-center justify-center ${
                prepDone > i
                  ? "bg-[#1FA855] text-white"
                  : prepDone === i
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-neutral-100 text-neutral-400"
              }`}
            >
              {prepDone > i ? (
                <Check size={14} weight="bold" />
              ) : prepDone === i ? (
                <Spinner size={12} className="animate-spin" />
              ) : (
                <span className="text-xs">{i + 1}</span>
              )}
            </div>
            <span
              className={`text-sm ${prepDone > i ? "text-neutral-900" : "text-neutral-600"}`}
            >
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ Step 5 ============
function Step5Connect({ method, qrData, pairingCode, phoneFull, status, timeStr }) {
  const copy = (txt) => {
    navigator.clipboard.writeText(txt);
    toast.success("Copied");
  };
  const expired = timeStr === "00:00";

  if (method === "phone") {
    return (
      <div data-testid="step5-phone">
        <h2 className="font-display text-2xl tracking-tight">Enter the Pairing Code in WhatsApp</h2>
        <p className="text-sm text-neutral-600 mt-1">
          Open WhatsApp on +{phoneFull} → Linked Devices → Link with phone number.
        </p>

        <div className="mt-6 grid lg:grid-cols-2 gap-6">
          <div className="border-2 border-[#1FA855] sharp p-8 bg-emerald-50/40 flex flex-col items-center">
            <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-600">
              your pairing code
            </p>
            <div className="mt-4 font-display text-5xl tracking-[0.4em] text-[#1FA855]" data-testid="pairing-code">
              {pairingCode || "————————"}
            </div>
            <button
              onClick={() => pairingCode && copy(pairingCode)}
              disabled={!pairingCode}
              className="btn-ghost text-sm mt-5 inline-flex items-center gap-2 disabled:opacity-50"
              data-testid="copy-pairing-code"
            >
              <Copy size={14} /> Copy
            </button>
            <p className="font-mono text-xs text-neutral-500 mt-4">
              Expires in {timeStr}
            </p>
          </div>

          <div className="border border-neutral-200 sharp p-6">
            <h3 className="font-display font-semibold">How to enter</h3>
            <ol className="mt-3 space-y-2 text-sm text-neutral-700 list-decimal pl-5">
              <li>Open WhatsApp on your phone</li>
              <li>Tap <span className="kbd">Settings</span> → <span className="kbd">Linked Devices</span></li>
              <li>Tap <span className="kbd">Link a Device</span></li>
              <li>Tap <span className="kbd">Link with phone number instead</span></li>
              <li>Enter the 8-character code shown</li>
            </ol>
            <div className="mt-5 border-t border-neutral-200 pt-4 flex items-center gap-2">
              {status === "connected" ? (
                <>
                  <CheckCircle size={18} weight="fill" className="text-emerald-600" />
                  <span className="text-sm">Connected — redirecting…</span>
                </>
              ) : (
                <>
                  <Spinner size={16} className="animate-spin text-[#1FA855]" />
                  <span className="text-sm text-neutral-600">
                    Auto-checking · Waiting for connection from WhatsApp
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // QR mode
  return (
    <div data-testid="step5-qr">
      <h2 className="font-display text-2xl tracking-tight">Scan the QR Code</h2>
      <p className="text-sm text-neutral-600 mt-1">
        Open WhatsApp → Linked Devices → Link a device → Scan the QR.
      </p>

      <div className="mt-6 grid lg:grid-cols-2 gap-6">
        <div className="border-2 border-[#1FA855] sharp p-6 bg-emerald-50/40 flex flex-col items-center">
          <div className="w-72 h-72 bg-white border border-neutral-200 sharp flex items-center justify-center" data-testid="qr-box">
            {qrData ? (
              <img src={qrData} alt="QR" className="w-full h-full" />
            ) : status === "connected" ? (
              <div className="text-center">
                <CheckCircle size={48} weight="fill" className="text-emerald-600 mx-auto" />
                <p className="font-display font-semibold mt-3">Connected</p>
              </div>
            ) : expired ? (
              <p className="text-sm text-red-600">QR expired — refresh page</p>
            ) : (
              <div className="text-center">
                <Spinner size={32} className="animate-spin text-[#1FA855] mx-auto" />
                <p className="font-mono text-xs text-neutral-500 mt-3">{status}</p>
              </div>
            )}
          </div>
          <p className="font-mono text-xs text-neutral-500 mt-4">Expires in {timeStr}</p>
        </div>

        <div className="border border-neutral-200 sharp p-6">
          <h3 className="font-display font-semibold">How to scan</h3>
          <ol className="mt-3 space-y-2 text-sm text-neutral-700 list-decimal pl-5">
            <li>Open WhatsApp on your phone</li>
            <li>Tap <span className="kbd">Settings</span> → <span className="kbd">Linked Devices</span></li>
            <li>Tap <span className="kbd">Link a Device</span> and scan the QR</li>
          </ol>
          <div className="mt-5 border-t border-neutral-200 pt-4 flex items-center gap-2">
            {status === "connected" ? (
              <>
                <CheckCircle size={18} weight="fill" className="text-emerald-600" />
                <span className="text-sm">Connected — redirecting…</span>
              </>
            ) : (
              <>
                <Spinner size={16} className="animate-spin text-[#1FA855]" />
                <span className="text-sm text-neutral-600">
                  Auto-checking · Waiting for connection from WhatsApp
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
