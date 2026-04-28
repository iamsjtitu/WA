# WapiHub — Product Requirements Document

## Original Problem Statement
"kya hum 360messenger.com jaisa khud ka bana sakte hai?" — Build own WhatsApp messaging API platform for personal/reseller use, give API access to customers.

## Architecture
- **Node.js Baileys microservice** (`/app/wa-service/`, port 3001 internal) — auto-spawned by FastAPI, watchdog auto-respawn, configurable AUTH dir via WA_AUTH_DIR. Inbound msgs auto-downloaded for media.
- **FastAPI backend** (`/app/backend/`, port 8001) — auth, customer mgmt, message logs, webhooks, public API, plans, billing.
  - `server.py` — core (auth, sessions, messages, webhooks)
  - `billing.py` — plans CRUD + Stripe/Razorpay/PayPal subscription billing
  - `auth.py` — JWT helpers
  - `wa_client.py` / `wa_supervisor.py` — Node service control
- **React frontend** — Landing + Auth + Admin/Customer dashboards.

## What's Been Implemented

### 2026-04-28 — Iteration 1 (MVP)
JWT auth, admin+customer roles, sessions CRUD, send/bulk text, message logs, public API (X-API-Key), landing page. **29/29 tests**.

### 2026-04-28 — Iteration 2 (Webhooks + Media + Resilience)
Inbound webhooks (HMAC), internal Node→FastAPI inbound endpoint, dashboard media upload (multipart, 25MB), public API media_url, watchdog respawn, port-conflict check. **+17 tests, 46/46 total**.

### 2026-04-28 — Iteration 3 (Billing + CSV + Retries + Inbound Media)
- ✅ **Webhook retry**: exp backoff [2s, 6s, 18s] + auto-disable after 10 consecutive failures + per-user counter + `/api/me/webhook/enable` to re-arm. `/test` endpoint now fires async (non-blocking).
- ✅ **Inbound media download**: Node downloads media via `downloadMediaMessage`, stores at `/app/wa-service/uploads/inbound/<msg_id>.<ext>`. FastAPI serves at `/api/media/{message_id}` (auth via cookie or X-API-Key). Webhook payload includes `media_url`, `mime_type`, `file_name`.
- ✅ **CSV bulk send**: `POST /api/messages/bulk-csv` (multipart) — auto-detects phone column, renders `{{var}}` template per row, throttled.
- ✅ **Admin Plans CRUD**: `/api/admin/plans` (POST/GET/PATCH/DELETE) + public `/api/plans` for active plans. Plan model: name, price, currency, quota_monthly, max_sessions, features[], active, sort.
- ✅ **3-gateway billing**:
  - **Stripe**: Checkout Session via `POST /billing/stripe/checkout`, webhook on `/webhooks/stripe`, cancel on `/billing/stripe/cancel`. Auto-creates Product+Price in Stripe on first checkout.
  - **Razorpay**: Subscription via `POST /billing/razorpay/create-subscription`, webhook on `/webhooks/razorpay`, cancel on `/billing/razorpay/cancel`. Auto-creates RP Plan on first subscription.
  - **PayPal**: Subscription via `POST /billing/paypal/create-subscription`, return handler at `/billing/paypal/return`, webhook on `/webhooks/paypal`, cancel on `/billing/paypal/cancel`. Auto-creates Product+Plan.
  - All gateways return 400 "not configured" if env keys missing — graceful degradation.
- ✅ **Subscription state**: `subscriptions` collection with active/cancelled/past_due/superseded states. Activates → user.quota_monthly = plan.quota_monthly. Cancelled → reset to 1000 free tier.
- ✅ **Frontend**: AdminPlans (CRUD), Billing (customer view with 3 gateway buttons + cancel), Settings webhook auto-disable banner with re-enable button, BulkSend CSV tab + variable preview.
- ✅ **72/72 tests pass**.

## Configuration (env vars)
```
# WhatsApp
WA_AUTH_DIR=/app/wa-service/auth   (production: point to persistent volume)
INTERNAL_SECRET=<long-random>
BACKEND_PUBLIC_URL=<https url>
FRONTEND_URL=<https url>

# Payment gateways (admin fills)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
PAYPAL_MODE=sandbox|live
PAYPAL_CLIENT_ID=
PAYPAL_SECRET=
PAYPAL_WEBHOOK_ID=
```

## Webhook URLs to register at gateways
- Stripe → `{BACKEND_PUBLIC_URL}/api/webhooks/stripe`
- Razorpay → `{BACKEND_PUBLIC_URL}/api/webhooks/razorpay`
- PayPal → `{BACKEND_PUBLIC_URL}/api/webhooks/paypal`

## Backlog / Known Improvements (Non-Blocking)
- **P1**: Bulk CSV with 500+ rows hits ingress timeout — push to background job/queue with status polling
- **P1**: Rate limiting & brute-force lockout on `/auth/login`
- **P2**: Stripe Customer Portal for self-service billing management
- **P2**: PayPal webhook signature verification via `/v1/notifications/verify-webhook-signature`
- **P2**: Razorpay webhook secret enforcement (warn-log when missing in production)
- **P2**: Plan price stored as float — should be Decimal/cents for accuracy
- **P2**: Currency allowlist on plan creation
- **P2**: Add jitter to webhook retry backoff
- **P2**: Make `WEBHOOK_AUTO_DISABLE_AFTER` configurable per-user/env
- **P3**: Move inbound media to S3-style storage for horizontal scale
- **P3**: Refactor server.py (1140 lines) into routers
- **P3**: Group chat support, password reset, 2FA, whitelabel domains

## Next Tasks
1. **User**: Manual end-to-end QR scan + real send/receive on a real WhatsApp number.
2. **User**: Add Stripe / Razorpay / PayPal API keys to `/app/backend/.env`, restart backend, test live checkout.
3. **User**: Configure webhook URLs at each gateway dashboard (URLs above).
4. Add background job system (Celery/RQ) for bulk CSV sends.
