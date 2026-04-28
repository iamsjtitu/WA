# WapiHub — Product Requirements Document

## Original Problem Statement
"kya hum 360messenger.com jaisa khud ka bana sakte hai?" — User wants their own WhatsApp messaging API platform (like 360messenger.com) for personal/reseller use, where they can give API access to their customers.

## Architecture
- **Node.js Baileys microservice** at `/app/wa-service/` — handles WhatsApp Web multi-session connections (port 3001, internal). Spawned by FastAPI on startup.
- **FastAPI backend** at `/app/backend/` (port 8001) — auth, customer mgmt, message logs, public API. Proxies WA ops to Node service.
- **React frontend** at `/app/frontend/` — Landing + Auth + Admin/Customer dashboards.

## User Personas
1. **Admin (Reseller / Owner)** — Can create customer accounts, set quotas, rotate API keys, view platform stats.
2. **Customer** — Links WhatsApp via QR, gets API key, sends messages from dashboard or programmatically.

## Core Requirements (Static)
- Multi-session WhatsApp Web automation via Baileys (`@whiskeysockets/baileys` v7)
- JWT auth with httpOnly cookies (admin + customer roles)
- Per-customer API keys for the public REST API
- Monthly message quotas (enforced)
- Real-time session status polling + QR display
- Single + bulk message sending with throttling

## What's Been Implemented (2026-04-28)
- ✅ Backend: JWT auth (register/login/logout/me/refresh), bcrypt password hashing, secure cookies
- ✅ Admin endpoints: customer CRUD, key regeneration, platform stats, RBAC enforcement
- ✅ Customer endpoints: profile, key rotation, stats
- ✅ WhatsApp sessions: create/list/status/delete via Baileys (multi-session)
- ✅ Messaging: dashboard send (single + bulk with 0.6s throttle), message logs
- ✅ Public API: `POST /api/v1/messages` and `GET /api/v1/sessions` via X-API-Key header
- ✅ Frontend: Landing page (Swiss high-contrast design — Outfit + IBM Plex Sans + JetBrains Mono fonts, blue/black/yellow palette)
- ✅ Auth screens (Login + Register), Dashboard layout with sidebar
- ✅ Pages: Overview, Sessions (with QR modal), Send Message, Bulk Campaign, Message Logs, API Docs (curl/Node/Python/PHP examples), Customers (admin), Settings
- ✅ Node Baileys service auto-spawned by FastAPI; sessions persist across reboots; auto-reconnect
- ✅ 29/29 backend tests pass

## Prioritized Backlog
- **P1**: Manual end-to-end QR scan + real WhatsApp message send (out-of-scope for automated tests — user must verify with their own number)
- **P1**: Webhook for inbound messages from Baileys → backend
- **P1**: Media (image/video/document) attachments in send + API
- **P2**: CSV upload for bulk campaigns + template variables ({{name}})
- **P2**: Stripe/Razorpay subscription billing for plan upgrades
- **P2**: Password reset flow (forgot password)
- **P2**: Rate limiting & brute-force lockout on /auth/login
- **P3**: Webhook delivery callbacks per-message status updates
- **P3**: Whitelabel custom domain per customer
- **P3**: Two-factor authentication

## Next Tasks
1. User does a manual QR scan with their own WhatsApp number to verify end-to-end send.
2. Decide on production deployment: persistent storage for `/app/wa-service/auth/` (auth state) + run Node service via supervisor instead of subprocess for resiliency.
3. Add inbound webhook so customers can receive replies via API.
