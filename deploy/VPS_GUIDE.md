# wa.9x.design — VPS Deployment Guide

Repo: **https://github.com/iamsjtitu/WA** (public)
Default branch: **main**

---

## 1. VPS खरीदें

| Item | Spec |
|---|---|
| OS | **Ubuntu 22.04 LTS** (recommended) — 24.04 भी चलेगा |
| CPU/RAM | 2 vCPU, 2 GB RAM (minimum) |
| Disk | 30 GB SSD |
| Network | Public IPv4 |
| Provider | Hetzner CX21 / DigitalOcean Basic / Contabo VPS-S / AWS Lightsail |

---

## 2. Domain DNS

अपने domain registrar पर:
```
Type: A     Name: wa     Value: <YOUR_VPS_IP>     TTL: 300
```

5–10 min बाद verify:
```
ping wa.9x.design   # आपका VPS IP दिखना चाहिए
```

---

## 3. SSH से VPS पर login

अपने laptop के terminal में:
```bash
ssh root@<YOUR_VPS_IP>
```
(पहली बार fingerprint accept करें → password VPS provider ने email किया होगा)

---

## 4. Setup script download (VPS terminal में)

```bash
cd /root
wget https://raw.githubusercontent.com/iamsjtitu/WA/main/deploy/setup-vps.sh
chmod +x setup-vps.sh
```

---

## 5. Installer run करें

```bash
bash setup-vps.sh --git https://github.com/iamsjtitu/WA.git
```

Script आपसे ये पूछेगी:

| Prompt | जवाब |
|---|---|
| Your domain | `wa.9x.design` |
| Admin email | `admin@wa.9x.design` |
| Admin password | strong password (≥8 chars) |

⏱️ ~10–15 मिनट लगेंगे। Script auto करेगी:
- apt update + Node.js 20 + MongoDB 7 + Python 3.11 + Nginx + Supervisor
- `git clone` से `/opt/wa9x` पर deploy
- Persistent storage `/var/lib/wa9x/auth` (WhatsApp session save)
- Nginx config + Let's Encrypt SSL (free)
- UFW firewall (only SSH + HTTPS open)
- Backend health check

Last में आपको ये output मिलेगा:
```
═════════════════════════════════════════════════════
  wa.9x.design is deployed!
═════════════════════════════════════════════════════
  URL:           https://wa.9x.design
  Admin login:   admin@wa.9x.design  /  <your-password>
═════════════════════════════════════════════════════
```

---

## 6. ✅ Login करें

Browser → `https://wa.9x.design` → login → Services → Add new → WhatsApp link करें (Phone Number या QR Code)।

---

## 7. 🚀 Auto-Update (NO SSH!)

जब भी आप Emergent में changes करें:

**Emergent पर:**
1. Top-right में **Save to GitHub** button click करें

**VPS पर (browser से, NO SSH):**
2. `https://wa.9x.design/login` → admin login
3. Sidebar → **System** ⚙️
4. **Check for updates** → "X new commits" दिखेगा
5. **Update Now** click → live log on screen
6. ~30 sec में app नया code पर restart हो जाएगा 🎉

---

## 8. Useful SSH Commands (rarely needed)

```bash
# Backend logs
tail -f /var/log/wa9x-backend.err.log
tail -f /var/log/wa9x-backend.out.log

# Auto-update log (UI में भी दिखती है)
tail -f /var/log/wa9x-update.log

# Manual restart
supervisorctl restart wa9x-backend

# Nginx
nginx -t && systemctl reload nginx

# SSL renew test (auto-renew already enabled)
certbot renew --dry-run

# MongoDB shell
mongosh wa9x_db

# Disk usage
du -sh /var/lib/wa9x/auth
df -h
```

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `certbot failed` | DNS abhi propagate नहीं → 10 min wait → `certbot --nginx -d wa.9x.design` re-run |
| `502 Bad Gateway` | `supervisorctl status wa9x-backend` → `tail /var/log/wa9x-backend.err.log` |
| Auto-update "Cannot reach origin" | `cd /opt/wa9x && git remote -v` → URL check; missing हो तो `git remote add origin https://github.com/iamsjtitu/WA.git` |
| Auto-update fails on `git pull` | Repo को private कर दिया? Then `git remote set-url origin https://USER:PAT@github.com/iamsjtitu/WA.git` |
| WhatsApp disconnect | Admin → Services → restart session या phone के Linked Devices से re-link |
| Out of memory | `free -h` → VPS upgrade (4 GB RAM recommended for 5+ active sessions) |

---

## 10. Security Checklist (post-deploy)

- [ ] Admin password strong है (script ने ≥8 chars enforce किया है)
- [ ] Stripe/Razorpay/PayPal keys `/opt/wa9x/backend/.env` में डालें (default empty)
- [ ] After editing `.env`: `supervisorctl restart wa9x-backend`
- [ ] `ufw status` से confirm — सिर्फ SSH + HTTPS open हों
- [ ] MongoDB localhost-only है (script default ऐसा ही रखती है)
- [ ] अगर repo को बाद में private करना हो तो PAT URL set करना (Section 9 देखें)
