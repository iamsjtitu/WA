# WapiHub — Product Requirements Document

## Original Problem Statement
"kya hum 360messenger.com jaisa khud ka bana sakte hai?" — Build own WhatsApp messaging API platform for personal/reseller use, give API access to customers.

## Architecture
- **Node.js Baileys microservice** (`/app/wa-service/`, port 3001 internal) — auto-spawned by FastAPI on startup with watchdog auto-respawn. AUTH dir configurable via `WA_AUTH_DIR` env.
- **FastAPI backend** (`/app/backend/`, port 8001) — auth, customer mgmt, message logs, webhooks, public API. Proxies WA ops to Node service.
- **React frontend** (`/app/frontend/`) — Landing + Auth + Admin/Customer dashboards.

## User Personas
1. **Admin (Reseller / Owner)** — manages customer accounts, quotas, API keys, platform stats.
2. **Customer** — links own WhatsApp via QR, gets API key, sends + receives messages programmatically with webhook.

## What's Been Implemented

### 2026-04-28 — MVP (Iteration 1)
- ✅ JWT auth with httpOnly cookies (admin + customer roles), bcrypt password hashing
- ✅ Admin endpoints: customer CRUD, key regeneration, platform stats, RBAC
- ✅ Customer endpoints: profile, key rotation, stats
- ✅ WhatsApp sessions: create/list/status/delete via Baileys multi-session
- ✅ Outbound messaging: dashboard send (single + bulk with 0.6s throttle), message logs
- ✅ Public API: `POST /api/v1/messages` and `GET /api/v1/sessions` via X-API-Key header
- ✅ Frontend: Landing (Swiss high-contrast), Login/Register, Dashboard layout
- ✅ Pages: Overview, Sessions (QR modal), Send, Bulk, Logs, API Docs, Customers (admin), Settings
- ✅ 29/29 backend tests pass

### 2026-04-28 — Iteration 2 (Webhooks + Media + Resilience)
- ✅ **Inbound webhooks** with HMAC-SHA256 signature: `PATCH /api/me/webhook`, `DELETE /api/me/webhook`, `POST /api/me/webhook/test`
- ✅ **Internal inbound endpoint** `POST /api/internal/inbound` (X-Internal-Secret auth) — Node forwards every received WhatsApp msg here, FastAPI stores it (direction='inbound') and fires the per-user webhook
- ✅ **Media attachments**: 
  - Dashboard: `POST /api/messages/send-media` (multipart, 25MB cap, image/video/audio/pdf/doc)
  - Public API: `POST /api/v1/messages` accepts `media_url` field (we download server-side and forward)
- ✅ **Persistence**: AUTH dir configurable via `WA_AUTH_DIR` env; uploads land in `/app/wa-service/uploads/` (deleted after send)
- ✅ **Resilience**: watchdog thread auto-respawns Node if it dies; port-conflict check prevents double-spawn (compatible with future supervisor takeover)
- ✅ Frontend: Settings → Webhook URL form + signing secret display, SendMessage → Text/Media tabs with file picker, ApiDocs → media + webhook payload + verify signature snippets (Node + Python), MessageLogs → direction column + filter
- ✅ 46/46 backend tests pass (17 new + 29 carryover)

## Known Minor Items (Non-Blocking)
- `server.py` is ~940 lines — should be split into routers when adding more endpoints
- `/messages/send-media` buffers full file before 25MB check (acceptable at this size)
- `media_url` download doesn't enforce a max-size limit on response body (consider streaming guard)
- Webhook delivery failures are silently logged — no auto-disable after N consecutive failures (yet)

## Prioritized Backlog
- **P1**: Production deployment — point `WA_AUTH_DIR` to a persistent volume so QR linkings survive redeploys
- **P1**: Rate limiting & brute-force lockout on `/auth/login`
- **P2**: CSV upload for bulk + `{{name}}` template variables
- **P2**: Stripe/Razorpay subscription billing for plan upgrades
- **P2**: Webhook retry with exponential backoff + auto-disable after N consecutive failures
- **P2**: Inbound media download — currently we only flag `has_media:true`; download & store would let customers receive images via webhook payload
- **P3**: Password reset flow
- **P3**: Whitelabel custom domain per customer
- **P3**: Group chat support (currently filtered out)
- **P3**: Two-factor authentication

## Next Tasks
1. Manual end-to-end QR scan + real send/receive verification by user with their own WhatsApp number.
2. Deploy + configure persistent volume for `WA_AUTH_DIR`.
3. Decide on the first paid tier feature: webhook retry policy, or CSV+template variables.
