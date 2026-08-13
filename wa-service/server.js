import express from "express";
import cors from "cors";
import qrcode from "qrcode";
import pino from "pino";
import { Boom } from "@hapi/boom";
import path from "path";
import fs from "fs";
import crypto from "node:crypto";
import { fileURLToPath } from "url";
import * as baileysPkg from "@whiskeysockets/baileys";

const {
  makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  Browsers,
  fetchLatestBaileysVersion,
  downloadMediaMessage,
} = baileysPkg;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const AUTH_ROOT = process.env.WA_AUTH_DIR || path.join(__dirname, "auth");
const FASTAPI_URL = process.env.FASTAPI_URL || "http://127.0.0.1:8001";
const INTERNAL_SECRET = process.env.INTERNAL_SECRET || "";
const INBOUND_MEDIA_DIR = path.join(__dirname, "uploads", "inbound");

if (!fs.existsSync(AUTH_ROOT)) fs.mkdirSync(AUTH_ROOT, { recursive: true });
if (!fs.existsSync(INBOUND_MEDIA_DIR)) fs.mkdirSync(INBOUND_MEDIA_DIR, { recursive: true });

function extForMime(mime) {
  const m = (mime || "").toLowerCase();
  if (m.includes("jpeg") || m.includes("jpg")) return ".jpg";
  if (m.includes("png")) return ".png";
  if (m.includes("gif")) return ".gif";
  if (m.includes("webp")) return ".webp";
  if (m.includes("mp4")) return ".mp4";
  if (m.includes("3gp")) return ".3gp";
  if (m.includes("ogg")) return ".ogg";
  if (m.includes("mpeg") || m.includes("mp3")) return ".mp3";
  if (m.includes("wav")) return ".wav";
  if (m.includes("pdf")) return ".pdf";
  if (m.includes("msword")) return ".doc";
  if (m.includes("officedocument.wordprocessingml")) return ".docx";
  if (m.includes("officedocument.spreadsheetml")) return ".xlsx";
  if (m.includes("plain")) return ".txt";
  if (m.includes("csv")) return ".csv";
  return ".bin";
}

const logger = pino({ level: "warn" });

// session_id -> { sock, status, qrDataUrl, phone, lastError, retryCount, keepAliveTimer, reconnectTimer }
const sessions = new Map();

// Retry limits — after ~5 minutes of failed reconnects we stop and mark
// disconnected. Users can then click "Reconnect" from the UI which resets
// the counter.
const MAX_RECONNECT_ATTEMPTS = 20;
const KEEPALIVE_INTERVAL_MS = 4 * 60 * 1000; // 4 minutes

function computeBackoff(attempt) {
  // Exponential backoff with ±20% jitter, capped at 60s
  const base = Math.min(60_000, 3_000 * Math.pow(2, Math.max(0, attempt - 1)));
  const jitter = base * (0.8 + Math.random() * 0.4);
  return Math.round(jitter);
}

function clearTimers(meta) {
  if (meta.keepAliveTimer) {
    clearInterval(meta.keepAliveTimer);
    meta.keepAliveTimer = null;
  }
  if (meta.reconnectTimer) {
    clearTimeout(meta.reconnectTimer);
    meta.reconnectTimer = null;
  }
}

function scheduleReconnect(sessionId, delayMs, reason) {
  const meta = sessions.get(sessionId) || {};
  if (meta.reconnectTimer) clearTimeout(meta.reconnectTimer);
  meta.retryCount = (meta.retryCount || 0) + 1;
  if (meta.retryCount > MAX_RECONNECT_ATTEMPTS) {
    console.error(
      `[wa] session ${sessionId} giving up after ${MAX_RECONNECT_ATTEMPTS} attempts (last: ${reason})`
    );
    meta.status = "disconnected";
    meta.lastError = `Auto-reconnect gave up after ${MAX_RECONNECT_ATTEMPTS} attempts. Reason: ${reason}`;
    sessions.set(sessionId, meta);
    return;
  }
  console.log(
    `[wa] session ${sessionId} reconnect in ${delayMs}ms (attempt ${meta.retryCount}, reason=${reason})`
  );
  meta.reconnectTimer = setTimeout(() => {
    startSession(sessionId).catch((e) =>
      console.error(`[wa] reconnect failed session=${sessionId}: ${e.message}`)
    );
  }, delayMs);
  sessions.set(sessionId, meta);
}

async function startSession(sessionId) {
  const sessionDir = path.join(AUTH_ROOT, sessionId);
  if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

  // If a previous socket exists, close & clear it before starting a new one
  const existing = sessions.get(sessionId);
  if (existing?.sock) {
    try {
      // end() aborts any WS reconnect logic inside Baileys and releases handles
      existing.sock.end?.(undefined);
      existing.sock.ev.removeAllListeners?.();
    } catch (e) {
      /* ignore */ void e;
    }
    clearTimers(existing);
    // Give the WS a moment to actually close before spawning the replacement
    // so we don't briefly have two live sockets fighting over the same creds.
    await new Promise((r) => setTimeout(r, 100));
  }

  const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    browser: Browsers.macOS("Chrome"),
    printQRInTerminal: false,
    syncFullHistory: false,
    // Baileys internal WS keep-alive; complements our own presence pings
    keepAliveIntervalMs: 30_000,
    // Reject connection if server takes too long; forces a fresh retry
    connectTimeoutMs: 60_000,
    // Retry the initial handshake on transient network errors
    retryRequestDelayMs: 500,
  });

  const meta = sessions.get(sessionId) || {};
  meta.sock = sock;
  meta.status = meta.status || "connecting";
  meta.qrDataUrl = null;
  meta.lastError = null;
  meta.retryCount = meta.retryCount || 0;
  sessions.set(sessionId, meta);

  sock.ev.on("creds.update", saveCreds);

  // Inbound message listener — forward to FastAPI
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      try {
        if (!m.key || m.key.fromMe) continue;
        const remote = m.key.remoteJid || "";
        if (
          remote.endsWith("@broadcast") ||
          remote.endsWith("@g.us") ||
          remote === "status@broadcast"
        )
          continue;
        const c = m.message;
        if (!c) continue;
        let text = "";
        let msgType = "text";
        let hasMedia = false;
        let mimeType = null;
        let fileName = null;
        if (c.conversation) text = c.conversation;
        else if (c.extendedTextMessage?.text) text = c.extendedTextMessage.text;
        else if (c.imageMessage) {
          text = c.imageMessage.caption || "";
          msgType = "image";
          hasMedia = true;
          mimeType = c.imageMessage.mimetype || "image/jpeg";
        } else if (c.videoMessage) {
          text = c.videoMessage.caption || "";
          msgType = "video";
          hasMedia = true;
          mimeType = c.videoMessage.mimetype || "video/mp4";
        } else if (c.documentMessage) {
          text = c.documentMessage.caption || c.documentMessage.fileName || "";
          msgType = "document";
          hasMedia = true;
          mimeType = c.documentMessage.mimetype || "application/octet-stream";
          fileName = c.documentMessage.fileName || null;
        } else if (c.audioMessage) {
          msgType = "audio";
          hasMedia = true;
          mimeType = c.audioMessage.mimetype || "audio/ogg";
        } else continue;

        // Download media to local file
        let mediaPath = null;
        if (hasMedia) {
          try {
            const buffer = await downloadMediaMessage(
              m,
              "buffer",
              {},
              { logger, reuploadRequest: sock.updateMediaMessage }
            );
            const ext = fileName
              ? path.extname(fileName) || extForMime(mimeType)
              : extForMime(mimeType);
            const finalName = `${m.key.id}${ext}`;
            mediaPath = path.join(INBOUND_MEDIA_DIR, finalName);
            fs.writeFileSync(mediaPath, buffer);
            if (!fileName) fileName = finalName;
          } catch (e) {
            console.error("[wa] media download failed:", e.message);
          }
        }

        const fromPhone = remote.split("@")[0];
        const payload = {
          session_id: sessionId,
          from: fromPhone,
          text,
          type: msgType,
          message_id: m.key.id,
          timestamp: Number(m.messageTimestamp || 0) * 1000,
          has_media: hasMedia,
          media_path: mediaPath,
          mime_type: mimeType,
          file_name: fileName,
        };
        fetch(`${FASTAPI_URL}/api/internal/inbound`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Internal-Secret": INTERNAL_SECRET,
          },
          body: JSON.stringify(payload),
        }).catch((e) => console.error("[wa] inbound forward failed:", e.message));
      } catch (e) {
        console.error("[wa] inbound parse error:", e.message);
      }
    }
  });

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;
    const m = sessions.get(sessionId) || {};

    if (qr) {
      try {
        m.qrDataUrl = await qrcode.toDataURL(qr);
      } catch (e) {
        m.qrDataUrl = null;
      }
      m.status = "qr";
      sessions.set(sessionId, m);
    }

    if (connection === "open") {
      m.status = "connected";
      m.qrDataUrl = null;
      m.phone = sock.user?.id?.split(":")[0]?.split("@")[0] || null;
      m.lastError = null;
      m.retryCount = 0; // reset on successful connect
      // Keep-alive: send a presence update every 4 min so WhatsApp doesn't
      // silently drop the session as "idle". This is the #1 cause of daily
      // "1-3 day disconnects".
      if (m.keepAliveTimer) clearInterval(m.keepAliveTimer);
      m.keepAliveTimer = setInterval(() => {
        const s = sessions.get(sessionId);
        if (!s?.sock || s.status !== "connected") return;
        s.sock.sendPresenceUpdate?.("available").catch((e) =>
          console.error(`[wa] presence keep-alive failed ${sessionId}: ${e.message}`)
        );
      }, KEEPALIVE_INTERVAL_MS);
      sessions.set(sessionId, m);
      console.log(`[wa] session ${sessionId} connected as ${m.phone}`);
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const reason = lastDisconnect?.error?.message || `code=${code}`;

      // Stop keep-alive on any close — will restart on reconnect
      if (m.keepAliveTimer) {
        clearInterval(m.keepAliveTimer);
        m.keepAliveTimer = null;
      }

      // Categorise the disconnect
      const CODES = DisconnectReason;
      const TERMINAL = new Set([
        CODES.loggedOut,        // 401 — user logged out from phone
        CODES.connectionReplaced, // 440 — another device paired
        CODES.forbidden,        // 403 — banned / blocked
        CODES.multideviceMismatch, // 411 — MD not enabled
        CODES.badSession,       // 500 — corrupted creds
      ]);
      const IMMEDIATE_RECONNECT = new Set([
        CODES.restartRequired,  // 515 — the ~daily forced restart
      ]);

      if (TERMINAL.has(code)) {
        m.status = "logged_out";
        m.lastError = `Session terminated (${reason}). Please re-scan QR.`;
        m.sock = null;
        m.qrDataUrl = null;
        m.retryCount = 0;
        sessions.set(sessionId, m);
        // Wipe credentials so a fresh QR is issued on next start
        try {
          fs.rmSync(sessionDir, { recursive: true, force: true });
        } catch (e) {
          void e;
        }
        console.log(
          `[wa] session ${sessionId} TERMINAL close code=${code} reason=${reason}`
        );
        return;
      }

      m.status = "disconnected";
      m.lastError = reason;
      sessions.set(sessionId, m);
      console.log(
        `[wa] session ${sessionId} transient close code=${code} reason=${reason}`
      );

      if (IMMEDIATE_RECONNECT.has(code)) {
        // WhatsApp asked us to reconnect immediately (restart required).
        // Skip the backoff so users don't see even a second of downtime.
        m.retryCount = 0;
        sessions.set(sessionId, m);
        scheduleReconnect(sessionId, 500, `restartRequired(${code})`);
      } else {
        // Transient network / unknown — exponential backoff with jitter
        const nextAttempt = (m.retryCount || 0) + 1;
        scheduleReconnect(sessionId, computeBackoff(nextAttempt), `code=${code}`);
      }
    }
  });

  return sock;
}

function ensureSession(sessionId) {
  const m = sessions.get(sessionId);
  if (m && m.sock) return m;
  return null;
}

function jidFromPhone(phone) {
  const digits = String(phone).replace(/[^0-9]/g, "");
  return `${digits}@s.whatsapp.net`;
}

const app = express();
app.use(cors());
app.use(express.json({ limit: "5mb" }));

// SEC-005: gate every /sessions endpoint behind INTERNAL_SECRET so that if the
// Node port ever leaks past the firewall, attackers cannot drive WhatsApp
// sessions. /health stays public for liveness probes.
app.use((req, res, next) => {
  if (req.path === "/health") return next();
  if (!INTERNAL_SECRET) {
    // Refuse to serve if the operator forgot to set the secret.
    return res
      .status(503)
      .json({ error: "wa-service INTERNAL_SECRET is not configured" });
  }
  const provided = req.headers["x-internal-secret"] || "";
  if (
    provided.length !== INTERNAL_SECRET.length ||
    !crypto.timingSafeEqual(Buffer.from(provided), Buffer.from(INTERNAL_SECRET))
  ) {
    return res.status(401).json({ error: "unauthorized" });
  }
  return next();
});

app.get("/health", (_req, res) => res.json({ ok: true }));

app.post("/sessions/:id/start", async (req, res) => {
  const id = req.params.id;
  try {
    const existing = sessions.get(id);
    if (existing && existing.sock && ["connected", "qr", "connecting"].includes(existing.status)) {
      return res.json({ session_id: id, status: existing.status });
    }
    // Manual start resets the retry counter so we get a fresh reconnect budget
    if (existing) {
      existing.retryCount = 0;
      sessions.set(id, existing);
    }
    await startSession(id);
    const m = sessions.get(id);
    res.json({ session_id: id, status: m?.status || "connecting" });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/sessions/:id/pair", async (req, res) => {
  const id = req.params.id;
  const { phone } = req.body || {};
  if (!phone) return res.status(400).json({ error: "phone required" });

  // ensure session is started
  let m = sessions.get(id);
  if (!m || !m.sock) {
    try {
      await startSession(id);
      m = sessions.get(id);
    } catch (e) {
      return res.status(500).json({ error: e.message });
    }
  }
  // wait briefly for socket
  for (let i = 0; i < 30 && (!m?.sock); i++) {
    await new Promise((r) => setTimeout(r, 100));
    m = sessions.get(id);
  }
  if (!m?.sock) return res.status(500).json({ error: "socket init failed" });
  if (m.sock.authState?.creds?.registered) {
    return res.status(400).json({ error: "already registered" });
  }
  const cleanPhone = String(phone).replace(/[^0-9]/g, "");
  try {
    const code = await m.sock.requestPairingCode(cleanPhone);
    m.pairingCode = code;
    m.pairingPhone = cleanPhone;
    sessions.set(id, m);
    res.json({ pairing_code: code, phone: cleanPhone });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/sessions/:id/status", (req, res) => {
  const id = req.params.id;
  const m = sessions.get(id);
  if (!m) {
    return res.json({ session_id: id, status: "not_started", qr: null, phone: null });
  }
  res.json({
    session_id: id,
    status: m.status,
    qr: m.qrDataUrl,
    phone: m.phone || null,
    error: m.lastError || null,
    pairing_code: m.pairingCode || null,
    pairing_phone: m.pairingPhone || null,
  });
});

app.post("/sessions/:id/logout", async (req, res) => {
  const id = req.params.id;
  const m = sessions.get(id);
  try {
    if (m?.sock) {
      try {
        await m.sock.logout();
      } catch {}
      try {
        m.sock.end();
      } catch {}
    }
    sessions.delete(id);
    const sessionDir = path.join(AUTH_ROOT, id);
    try {
      fs.rmSync(sessionDir, { recursive: true, force: true });
    } catch {}
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/sessions/:id/send", async (req, res) => {
  const id = req.params.id;
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "to and text required" });

  const m = ensureSession(id);
  if (!m || m.status !== "connected") {
    return res.status(400).json({ error: `session not connected (status=${m?.status || "not_started"})` });
  }
  try {
    const jid = jidFromPhone(to);
    const result = await m.sock.sendMessage(jid, { text: String(text) });
    res.json({
      ok: true,
      message_id: result?.key?.id || null,
      to,
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/sessions/:id/send-media", async (req, res) => {
  const id = req.params.id;
  const { to, file_path, caption, file_name, mime_type, delete_after } = req.body || {};
  if (!to || !file_path)
    return res.status(400).json({ error: "to and file_path required" });

  const m = ensureSession(id);
  if (!m || m.status !== "connected") {
    return res
      .status(400)
      .json({ error: `session not connected (status=${m?.status || "not_started"})` });
  }
  if (!fs.existsSync(file_path)) {
    return res.status(400).json({ error: "file not found at path" });
  }
  try {
    const toStr = String(to);
    const jid = toStr.includes("@") ? toStr : jidFromPhone(toStr);
    const mt = String(mime_type || "").toLowerCase();
    let payload;
    if (mt.startsWith("image/")) {
      payload = { image: { url: file_path }, caption: caption || undefined };
    } else if (mt.startsWith("video/")) {
      payload = { video: { url: file_path }, caption: caption || undefined };
    } else if (mt.startsWith("audio/")) {
      payload = { audio: { url: file_path }, mimetype: mt, ptt: false };
    } else {
      payload = {
        document: { url: file_path },
        mimetype: mt || "application/octet-stream",
        fileName: file_name || path.basename(file_path),
        caption: caption || undefined,
      };
    }
    const result = await m.sock.sendMessage(jid, payload);
    if (delete_after) {
      try {
        fs.unlinkSync(file_path);
      } catch {}
    }
    res.json({
      ok: true,
      message_id: result?.key?.id || null,
      to,
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/sessions/:id/groups", async (req, res) => {
  const id = req.params.id;
  const m = ensureSession(id);
  if (!m || m.status !== "connected") {
    return res.status(400).json({
      error: `session not connected (status=${m?.status || "not_started"})`,
    });
  }
  try {
    const all = await m.sock.groupFetchAllParticipating();
    const list = Object.values(all).map((g) => ({
      id: g.id?.replace(/@g\.us$/, ""),
      jid: g.id,
      subject: g.subject || "",
      desc: g.desc || "",
      owner: (g.owner || "").replace(/@s\.whatsapp\.net$/, ""),
      creation: g.creation || null,
      size: Array.isArray(g.participants) ? g.participants.length : 0,
      announce: !!g.announce,
      restrict: !!g.restrict,
      is_admin: Array.isArray(g.participants)
        ? g.participants.some(
            (p) => p.id === m.sock.user?.id && ["admin", "superadmin"].includes(p.admin)
          )
        : false,
    }));
    list.sort((a, b) => a.subject.localeCompare(b.subject));
    res.json({ ok: true, count: list.length, groups: list });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/sessions/:id/send-group", async (req, res) => {
  const id = req.params.id;
  const { group_id, text, url } = req.body || {};
  if (!group_id) return res.status(400).json({ error: "group_id required" });

  const m = ensureSession(id);
  if (!m || m.status !== "connected") {
    return res.status(400).json({ error: `session not connected (status=${m?.status || "not_started"})` });
  }

  const cleanGid = String(group_id).replace(/[^0-9A-Za-z\-]/g, "");
  const jid = `${cleanGid}@g.us`;
  try {
    let result;
    if (url) {
      // download to temp + send as image (default)
      const tmpFile = path.join(__dirname, "uploads", `${Date.now()}_grp_${Math.random().toString(36).slice(2)}.bin`);
      const r = await fetch(url);
      if (!r.ok) return res.status(400).json({ error: `failed to fetch url: HTTP ${r.status}` });
      const buf = Buffer.from(await r.arrayBuffer());
      fs.writeFileSync(tmpFile, buf);
      const ct = (r.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
      let payload;
      if (ct.startsWith("image/")) payload = { image: { url: tmpFile }, caption: text || undefined };
      else if (ct.startsWith("video/")) payload = { video: { url: tmpFile }, caption: text || undefined };
      else payload = { document: { url: tmpFile }, mimetype: ct || "application/octet-stream", caption: text || undefined };
      result = await m.sock.sendMessage(jid, payload);
      try { fs.unlinkSync(tmpFile); } catch {}
    } else {
      if (!text) return res.status(400).json({ error: "text or url required" });
      result = await m.sock.sendMessage(jid, { text: String(text) });
    }
    res.json({ ok: true, message_id: result?.key?.id || null, group_id: cleanGid });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Restart any persisted sessions on boot
async function restoreSessions() {
  if (!fs.existsSync(AUTH_ROOT)) return;
  const dirs = fs.readdirSync(AUTH_ROOT, { withFileTypes: true });
  for (const d of dirs) {
    if (!d.isDirectory()) continue;
    const credsFile = path.join(AUTH_ROOT, d.name, "creds.json");
    if (fs.existsSync(credsFile)) {
      console.log(`[wa] restoring session ${d.name}`);
      startSession(d.name).catch((e) =>
        console.error(`restore ${d.name} failed:`, e.message)
      );
    }
  }
}

const PORT = process.env.PORT || 3001;
app.listen(PORT, "127.0.0.1", () => {
  console.log(`[wa] service listening on :${PORT}`);
  restoreSessions();
});
