# WapiHub — Product Requirements Document

## Original Problem Statement
"kya hum 360messenger.com jaisa khud ka bana sakte hai?" — Build own WhatsApp messaging API platform for personal/reseller use, give API access to customers.

## Architecture
- **Node.js Baileys microservice** (`/app/wa-service/`, port 3001) — auto-spawned, watchdog respawn, configurable WA_AUTH_DIR.
- **FastAPI backend** (`/app/backend/`, port 8001):
  - `server.py` — auth, sessions, messages, webhooks, plugins, scheduler dispatcher
  - `billing.py` — plans + Stripe/Razorpay/PayPal subscriptions
  - `v2_compat.py` — 360messenger-compatible v2 API
  - `auth.py` — JWT helpers
  - `wa_client.py` / `wa_supervisor.py` — Node service control
- **React frontend** — Landing, Auth, Dashboard (Overview, Sessions, **SessionDetail**, Send, BulkSend, Logs, ApiDocs, Customers, Plans, Billing, Settings)

## Implementation History

### Iteration 1 — MVP (29/29 tests)
JWT auth, sessions CRUD, send/bulk text, message logs, public v1 API, landing page.

### Iteration 2 — Webhooks + Media + Resilience (46/46 tests)
HMAC inbound webhooks, Node→FastAPI internal endpoint, dashboard media upload, public API media_url, Node watchdog, port-conflict check.

### Iteration 3 — Billing + CSV + Retries + Inbound Media Download (72/72 tests)
Webhook retry [2s, 6s, 18s] + auto-disable after 10 failures, inbound media auto-download served at `/api/media/{id}`, CSV bulk with `{{var}}` templates, admin Plans CRUD, full Stripe + Razorpay + PayPal subscription billing (gracefully degraded when keys missing).

### Iteration 4 — 360messenger Parity (94/94 tests)
- ✅ **v2 API compatibility layer** (`v2_compat.py`):
  - `POST /api/v2/sendMessage` — multipart phonenumber/text/url/delay, Bearer auth, returns 201 with 360-style response shape
  - `POST /api/v2/sendGroup` — group jid `{groupId}@g.us` send via Baileys
  - `GET /api/v2/message/status?id=`, `/sentMessages`, `/receivedMessages`, `/account`
  - Bearer (Authorization), X-API-Key, or `?token=` auth all accepted
  - Delay format: `MM-DD-YYYY HH:MM` GMT (per 360messenger spec); past/invalid delays return 400
- ✅ **Schedule/delay**: `db.scheduled_messages` collection + async dispatcher loop (60s) that claims pending docs (status: pending → running → sent/failed), increments quota only on success
- ✅ **Per-session settings**: `default_country_code`, `auto_prefix`, `receive_messages`, `mark_as_seen` on `wa_sessions`. PATCH `/api/sessions/{id}/settings`
- ✅ **Service Detail page** (`/app/sessions/{id}`) matches 360messenger layout exactly:
  - Top stat cards (Service ID, Connected Number, Status, Quota)
  - API Key card with copy + Bearer hint
  - Connection Status card with Show QR / Restart / Disconnect actions
  - 3-column inline: Received / Sent / Send Message form (with link + schedule)
  - Account Settings (3 toggles) + Webhook URL + Service Management (Cancel/Renew/Upgrade)
  - Live polling every 5s
- ✅ **WHMCS plugin** (`/api/plugins/whmcs.zip`) — PHP module with curl helper for invoice/ticket hooks
- ✅ **WooCommerce plugin** (`/api/plugins/woocommerce.zip`) — auto-WhatsApp on order paid/processing with `{{name}}` `{{order_id}}` `{{total}}` template variables, settings page in WP admin
- ✅ **Group send via Node** — `/sessions/:id/send-group` endpoint with text or url/media

## Configuration (env vars)
```
WA_AUTH_DIR=/app/wa-service/auth
INTERNAL_SECRET=<long-random>
BACKEND_PUBLIC_URL=https://...
FRONTEND_URL=https://...
JWT_SECRET=<long-random>
ADMIN_EMAIL / ADMIN_PASSWORD

# Payment gateways (admin fills in production)
STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
PAYPAL_MODE=sandbox|live, PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_WEBHOOK_ID
```

## v2 API endpoints (360messenger-compatible)
| Method | Path | Auth | Body |
|---|---|---|---|
| POST | `/api/v2/sendMessage` | Bearer | multipart: phonenumber, text, url?, delay? |
| POST | `/api/v2/sendGroup` | Bearer | multipart: groupId, text, url?, delay? |
| GET | `/api/v2/message/status` | Bearer | ?id= |
| GET | `/api/v2/message/sentMessages` | Bearer | ?page=&phonenumber= |
| GET | `/api/v2/message/receivedMessages` | Bearer | ?page=&phonenumber= |
| GET | `/api/v2/account` | Bearer | — |

## Backlog / Known Improvements
- **P1**: SSRF guard + content-length cap on v2/sendMessage `url=` fetch (currently no max-size)
- **P1**: Phone country-code heuristic (`len <= 11`) is fragile — make deterministic
- **P1**: Bulk CSV with 500+ rows hits ingress timeout — needs background job queue
- **P1**: Rate limiting + brute-force lockout on `/auth/login`
- **P2**: Stuck-job recovery for scheduled_messages stuck in `running` (TTL >5min)
- **P2**: Stripe Customer Portal, PayPal webhook signature verification, Razorpay webhook secret enforcement
- **P2**: `?token=` query auth leaks into nginx logs — drop or rate-limit
- **P2**: Pagination cursor on `/sessions/{id}/messages` (currently capped 200)
- **P2**: server.py is 1346 lines — split into routers/ subpackage
- **P3**: Move inbound media to S3 for multi-pod scale, group chat features beyond send, password reset, 2FA, whitelabel domains, sub-customers (reseller of resellers)

## Next Tasks (User)
1. **Real WhatsApp QR scan** — link a number, scan, send/receive on real WhatsApp.
2. **Add payment gateway keys** to `/app/backend/.env`, restart backend, register webhook URLs:
   - Stripe → `{BACKEND_URL}/api/webhooks/stripe`
   - Razorpay → `{BACKEND_URL}/api/webhooks/razorpay`
   - PayPal → `{BACKEND_URL}/api/webhooks/paypal`
3. **Test plugin downloads** — install WHMCS module / WooCommerce plugin in your dev sites.
