# wa.9x.design — Product Requirements Document

## Original Problem Statement
"kya hum 360messenger.com jaisa khud ka bana sakte hai?" — Build own WhatsApp messaging API platform under brand **wa.9x.design** for personal/reseller use.

## Architecture
- **Node.js Baileys microservice** (`/app/wa-service/`, port 3001) — auto-spawned, watchdog respawn, configurable WA_AUTH_DIR, **pairing-code support** via `requestPairingCode()`.
- **FastAPI backend** (`/app/backend/`, port 8001):
  - `server.py` — auth, sessions, messages, webhooks, plugins, scheduler
  - `billing.py` — plans + Stripe/Razorpay/PayPal subscriptions
  - `v2_compat.py` — legacy v2 API (Bearer auth, multipart, drop-in compatible)
  - `auth.py` / `wa_client.py` / `wa_supervisor.py`
- **React frontend** — Landing, Auth, Dashboard (Overview, Services, ServiceCreate, ServiceDetail, Send, Bulk, Logs, ApiDocs, Customers, Plans, Billing, Settings)

## Brand & Theme
- Display name: **wa.9x.design**
- Primary color: WhatsApp green `#1FA855`
- API key prefix: `wa9x_`
- Admin email: `admin@wa.9x.design` / `admin123`
- All references to "WapiHub" / "360messenger" purged from code & assets

## Implementation History

| Iter | Tests | Highlights |
|---|---|---|
| 1 | 29/29 | MVP — JWT auth, sessions, send/bulk text, public v1 API, landing |
| 2 | 46/46 | Inbound webhooks (HMAC), media upload + media_url, watchdog respawn |
| 3 | 72/72 | Webhook retry/auto-disable, inbound media download, CSV+templates, admin Plans CRUD, Stripe + Razorpay + PayPal billing |
| 4 | 94/94 | v2 API compat layer (sendMessage/sendGroup/status/sentMessages/receivedMessages/account), schedule/delay dispatcher (60s loop), per-session settings, ServiceDetail page, WHMCS+WooCommerce plugins |
| 5 | 110+1/111 | **Full rebrand to wa.9x.design** + **5-step ServiceCreate wizard** with Baileys phone-number pairing-code support, green theme, terminology refresh |
| 6 | — | Customer impersonation flow + admin credential change + Made-with-Emergent badge removal + VPS setup script |
| 7 | — | (Save to GitHub + handoff) |
| 8 | 18/18 + 72/72 reg | **Admin Auto-Update from GitHub**: `/api/admin/system/{status,log,update}` + `AdminSystem.jsx` page with live log tail, behind-count, defensive fetch, concurrent-update lock, fd leak fix |

### Iteration 5 — wa.9x.design Rebrand & Pairing Code (110/111 + 1 fix = 111/111)
- ✅ Mass rebrand: WapiHub→wa.9x.design, 360messenger refs purged, color blue→green, api key prefix wapi_→wa9x_
- ✅ Admin email seamlessly migrated; old admin@wapihub.com correctly returns 401
- ✅ **Baileys pairing code via phone**: new `POST /api/sessions/{id}/pair {phone}` proxies to `sock.requestPairingCode()`, returns 8-char code displayed in step 5 of wizard (verified live: real "4DTV6BW1" code generated)
- ✅ Session status endpoint now surfaces `pairing_code` and `pairing_phone` (post-fix)
- ✅ **5-step ServiceCreate wizard** at `/app/sessions/new`:
  1. Choose Method (Phone Number / Scan QR Code) + Service Name
  2. Phone input with 20 country codes
  3. Service Usage Guidelines (5 numbered points + warning + agreement checkbox)
  4. Preparing animation (4 sub-steps with green checkmarks)
  5. Pairing Code OR QR display with 15-min expiry + auto-check polling
- ✅ Plugin filenames renamed to `wa9x.php` / `wa9x-woocommerce.php`
- ✅ Webhook UA: `wa.9x.design-Webhook/1.0`

## v2 API endpoints (drop-in legacy compat)
| Method | Path | Auth | Body |
|---|---|---|---|
| POST | `/api/v2/sendMessage` | Bearer | multipart: phonenumber, text, url?, delay? |
| POST | `/api/v2/sendGroup` | Bearer | multipart: groupId, text, url?, delay? |
| GET | `/api/v2/message/status` | Bearer | ?id= |
| GET | `/api/v2/message/sentMessages` | Bearer | ?page=&phonenumber= |
| GET | `/api/v2/message/receivedMessages` | Bearer | ?page=&phonenumber= |
| GET | `/api/v2/account` | Bearer | — |

Delay format: `MM-DD-YYYY HH:MM` (GMT). Past/invalid delays return 400.

## Configuration (env vars)
```
WA_AUTH_DIR=/app/wa-service/auth
INTERNAL_SECRET=<long-random>
BACKEND_PUBLIC_URL=https://...
FRONTEND_URL=https://...
JWT_SECRET=<long-random>
ADMIN_EMAIL=admin@wa.9x.design / ADMIN_PASSWORD=admin123

STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
PAYPAL_MODE=sandbox|live, PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_WEBHOOK_ID
```

## Backlog / Known Improvements
- **P1**: SSRF / size-cap guards on `media_url` and `v2/sendMessage url=` server-side fetch
- **P1**: Phone country-code heuristic (currently `len <= 11`) is fragile — replace with deterministic
- **P1**: Bulk CSV with 500+ rows → background job (Celery/RQ)
- **P1**: Rate limiting + brute-force lockout on `/auth/login`
- **P1**: PairIn validation: digits-only + plausible E.164 length
- **P2**: HTTP status 201 vs body statusCode mismatch on v2 schedule path
- **P2**: scheduled_messages stuck-in-`running` recovery (>5min TTL)
- **P2**: Pair endpoint error mapping (already-registered → 409)
- **P2**: Drop `?token=` query auth (leaks into nginx logs)
- **P2**: server.py 1364 lines — split into routers/ subpackage
- **P2**: PayPal webhook signature verification + Razorpay webhook secret enforcement
- **P3**: Inbound media → S3 for multi-pod scale, group features, password reset, 2FA, whitelabel domains, sub-customers (reseller-of-resellers)

## Next Tasks (User)
1. **Production**: Point `WA_AUTH_DIR` to a persistent volume so QR/pair links survive redeploys.
2. **Real WhatsApp link** — admin@wa.9x.design → /app/sessions/new → choose method → live test send/receive.
3. **Add gateway keys** to `/app/backend/.env`, restart, register webhook URLs at each provider.
4. **Plugins** — install WHMCS / WooCommerce plugins on dev sites and verify event firing.
5. **Auto-Update on VPS** — after first push to GitHub, re-deploy with
   `bash setup-vps.sh --git <your-repo-url>`. Then any future “Save to GitHub” can be pulled
   one-click via Admin → System → **Update Now**. The log tails live at
   `/var/log/wa9x-update.log`.

## Auto-Update endpoints (admin only)
| Method | Path | Returns |
|---|---|---|
| GET | `/api/admin/system/status` | install_dir, git_available, commit, short_commit, branch, last_commit, behind_count, fetch_ok, fetch_error, incoming_commits, last_update_at |
| GET | `/api/admin/system/log?lines=N` | `{log, exists}` — tails `/var/log/wa9x-update.log` |
| POST | `/api/admin/system/update` | spawns detached `deploy/auto-update.sh`; 30 s cooldown between calls; 400 if not a git checkout |
