# wa.9x.design — VPS Deployment Guide

## 1. VPS Recommendation

### Minimum (5 – 50 connected WhatsApp numbers)
| Item   | Spec |
|--------|------|
| vCPU   | **2** |
| RAM    | **4 GB** |
| Disk   | **40 GB SSD** |
| OS     | **Ubuntu 22.04 LTS** (or 24.04) |
| BW     | 2 TB / month |

### Recommended (50 – 200 numbers + bulk campaigns)
| Item   | Spec |
|--------|------|
| vCPU   | **4** |
| RAM    | **8 GB** |
| Disk   | **80 GB SSD** |
| OS     | **Ubuntu 22.04 LTS** |

### Cheapest providers (Feb 2026 prices)
- **Hetzner CX22** — 2 vCPU / 4 GB / 40 GB / €4.51 mo (~₹420)
- **DigitalOcean** — 2 vCPU / 4 GB / 80 GB — $24 mo (~₹2,000)
- **Contabo VPS S** — 4 vCPU / 8 GB / 200 GB SSD — €4.50 mo (best ₹/spec, slower CPU)
- **Vultr High-Frequency** — 2 vCPU / 4 GB / 128 GB — $24 mo
- **AWS Lightsail / Linode** — similar pricing

For India-only customers, prefer providers with Mumbai/Bangalore/Singapore regions for lowest latency to WhatsApp servers.

---

## 2. Pre-deploy checklist

1. Buy a domain and point an `A` record to your VPS IPv4 IP. Wait until `dig +short yourapp.com` returns the IP.
2. SSH in as `root` (or a sudo user — script needs root).
3. Have the wa.9x.design source code ready.

---

## 3. One-shot deploy

### Option A — upload tarball (most direct)

On your laptop:
```bash
# Pack the source (run from where /app sits)
tar -czf wa9x.tar.gz --exclude='node_modules' --exclude='wa-service/auth' \
    --exclude='frontend/build' --exclude='frontend/node_modules' \
    --exclude='backend/venv' --exclude='backend/__pycache__' \
    backend frontend wa-service deploy

# Upload to your VPS
scp wa9x.tar.gz root@YOUR_VPS_IP:/root/
scp deploy/setup-vps.sh root@YOUR_VPS_IP:/root/
```

On the VPS:
```bash
ssh root@YOUR_VPS_IP
bash /root/setup-vps.sh
```

You'll be prompted for **domain**, **admin email**, **admin password**. The script does the rest:
- Updates apt, installs Node 20 + Python 3.11 + MongoDB 7 + nginx + certbot
- Builds the React frontend
- Installs Python deps, Yarn (Baileys) deps
- Sets up persistent storage at `/var/lib/wa9x/{auth,uploads}`
- Generates `/opt/wa9x/backend/.env` with random JWT + internal secrets
- Configures supervisor → starts FastAPI (which auto-spawns Node WA service)
- Configures nginx + Let's Encrypt SSL (auto-renews)
- Enables UFW firewall (ports 22, 80, 443)

Total time: **~5 minutes** on a typical VPS.

### Option B — from a Git repo

```bash
ssh root@YOUR_VPS_IP
wget https://raw.githubusercontent.com/YOUR_REPO/main/deploy/setup-vps.sh
bash setup-vps.sh --git https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

---

## 4. After deploy

### Add payment gateway keys
```bash
nano /opt/wa9x/backend/.env
# Fill: STRIPE_SECRET_KEY, RAZORPAY_KEY_ID/SECRET, PAYPAL_CLIENT_ID/SECRET, etc.
supervisorctl restart wa9x-backend
```

### Register webhook URLs at each gateway
- Stripe: `https://yourapp.com/api/webhooks/stripe`
- Razorpay: `https://yourapp.com/api/webhooks/razorpay`
- PayPal: `https://yourapp.com/api/webhooks/paypal`

### Common operations
```bash
# View backend logs
tail -f /var/log/wa9x-backend.err.log

# Restart backend (re-reads .env, restarts Node WA service)
supervisorctl restart wa9x-backend

# Mongo shell
mongosh wa9x_db

# Renew SSL (cron does it automatically, but to test)
certbot renew --dry-run

# Update code (after pushing changes)
cd /opt/wa9x && git pull       # Option B (git)
# OR re-upload tarball + extract
cd /opt/wa9x/frontend && yarn build
supervisorctl restart wa9x-backend
```

### Backup
The two paths that **must** be backed up:
- **MongoDB** — `mongodump --db=wa9x_db --out=/backup`
- **WhatsApp auth state** — `tar -czf wa-auth-backup.tar.gz /var/lib/wa9x/auth`

Without these, all customers will need to re-link their WhatsApp numbers.

---

## 5. Hardening (production)

Recommended after the basic deploy works:

- Move backend into a non-root system user
- Bind MongoDB to localhost (already default) and enable auth
- Add fail2ban for SSH
- Add CloudFlare in front for DDoS + caching
- Set up off-site backups (cron + rclone to S3 or B2)
- Enable rate-limiting in nginx for `/api/auth/login`

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `certbot` fails | DNS not propagated yet — wait 10 min, re-run `certbot --nginx -d yourapp.com` |
| 502 Bad Gateway | Backend not running. `supervisorctl status` and `tail /var/log/wa9x-backend.err.log` |
| Login returns 401 | Wrong admin password (case-sensitive). Check `/opt/wa9x/backend/.env` |
| WhatsApp doesn't connect | Node service not reachable. `curl http://127.0.0.1:3001/health` |
| Sessions disappear after restart | `WA_AUTH_DIR` not set to persistent path. Check `.env` |
| Frontend shows old build | Re-run `cd /opt/wa9x/frontend && yarn build` then refresh browser |
