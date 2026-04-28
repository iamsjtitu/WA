# wa.9x.design — VPS Deployment Guide

Repo: **https://github.com/iamsjtitu/WA** (private)
Domain example: **wa.9x.design**

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

## 3. GitHub Personal Access Token (PAT) बनाएं

Repo private है, इसलिए VPS को clone करने के लिए token चाहिए:

1. GitHub → top-right avatar → **Settings**
2. **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. **Generate new token**
4. Settings:
   - **Token name:** `wa9x-vps`
   - **Expiration:** 90 days (या जो ठीक लगे)
   - **Repository access:** Only select repositories → `iamsjtitu/WA`
   - **Permissions** → **Repository permissions** → **Contents: Read-only**
5. **Generate token** click → token (`github_pat_xxx...`) copy करके safely रखें (दोबारा नहीं दिखेगा)

---

## 4. SSH से VPS पर login करें

अपने laptop के terminal में:
```bash
ssh root@<YOUR_VPS_IP>
```

---

## 5. Setup script को VPS पर लाएं

VPS के terminal में:
```bash
cd /root

# Private repo से raw script download (token के साथ):
curl -H "Authorization: token github_pat_YOUR_TOKEN_HERE" \
     -o setup-vps.sh \
     https://raw.githubusercontent.com/iamsjtitu/WA/main/deploy/setup-vps.sh

chmod +x setup-vps.sh
```

> Tip: अगर आपकी default branch `main` नहीं है तो URL में `main` की जगह उसका नाम डालें।

---

## 6. Setup script चलाएं

```bash
bash setup-vps.sh --git https://iamsjtitu:github_pat_YOUR_TOKEN_HERE@github.com/iamsjtitu/WA.git
```

(Username `iamsjtitu` + token URL में embed है — script कोई password prompt नहीं करेगी।)

Script आपसे पूछेगी:
| Prompt | जवाब |
|---|---|
| Your domain | `wa.9x.design` |
| Admin email | `admin@wa.9x.design` |
| Admin password | strong password (≥8 chars) |

⏱️ ~10–15 मिनट लगेंगे। Script auto करेगी:
- apt update + Node.js 20 + MongoDB 7 + Python 3.11 + Nginx + Supervisor
- `git clone` → `pip install` → `yarn build`
- `/opt/wa9x` पर deploy → persistent dirs `/var/lib/wa9x/auth`
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

## 7. ✅ Login करें

Browser → `https://wa.9x.design` → login → Services → Add new → WhatsApp link करें (Phone Number या QR Code)।

---

## 8. 🚀 Auto-Update (Emergent → GitHub → VPS, one click)

अब जब भी आप Emergent में changes करें:

**Emergent पर:**
1. Top-right में **Save to GitHub** button click करें → Emergent commit करेगा

**VPS पर (browser से, NO SSH):**
2. `https://wa.9x.design/login` → admin login
3. Sidebar में **System** ⚙️
4. **Check for updates** → "X new commits" दिखेगा
5. **Update Now** click → live log on screen
6. ~30 sec में app नया code पर restart हो जाएगा

बस! कोई SSH नहीं, कोई command नहीं।

---

## 9. Useful SSH Commands (rarely needed)

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

# SSL renew test
certbot renew --dry-run

# MongoDB shell
mongosh wa9x_db

# Disk usage of WA auth (अगर बहुत बड़ा हो जाए)
du -sh /var/lib/wa9x/auth
df -h
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `certbot failed` | DNS abhi propagate नहीं → 10 min wait → `certbot --nginx -d wa.9x.design` re-run |
| `502 Bad Gateway` | `supervisorctl status wa9x-backend` → `tail /var/log/wa9x-backend.err.log` |
| `git clone` asks for password | Token URL में नहीं है — Step 6 की URL दोबारा check करें |
| Auto-update "Cannot reach origin" | `cd /opt/wa9x && git remote -v` → URL check; अगर PAT expire हो गया तो `git remote set-url origin <new-url-with-new-token>` |
| WhatsApp disconnect | Admin → Services → restart session या phone के Linked Devices से re-link |
| Out of memory | `free -h` → MongoDB का limit kam karें या VPS upgrade करें |

---

## 11. Security Checklist (post-deploy)

- [ ] Admin password strong है (script ने ज़बरदस्ती ≥8 chars लिया है)
- [ ] Stripe/Razorpay/PayPal keys `/opt/wa9x/backend/.env` में डालें (default empty हैं)
- [ ] Restart करें: `supervisorctl restart wa9x-backend`
- [ ] PAT expiry calendar में note करें — expire हो जाए तो auto-update fail होगा
- [ ] `ufw status` से confirm करें — सिर्फ SSH + HTTPS open हों
- [ ] MongoDB को **localhost-only** रखें (script default ऐसा ही रखती है — `mongo --eval "db.serverStatus()"` से check)
