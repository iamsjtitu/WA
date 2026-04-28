#!/usr/bin/env bash
# wa.9x.design — One-shot VPS installer
#
# Tested on Ubuntu 22.04 / 24.04 LTS (fresh server, root user).
#
# Prereqs you provide:
#   - A clean Ubuntu VPS with public IP + a domain pointing to it (A record).
#   - Source archive uploaded to /root/wa9x.tar.gz  OR  pass --git <repo-url>.
#
# Usage:
#   1. Upload your code:  scp wa9x.tar.gz root@YOUR_VPS:/root/
#   2. Upload this script:  scp deploy/setup-vps.sh root@YOUR_VPS:/root/
#   3. SSH in: ssh root@YOUR_VPS
#   4. Run:    bash setup-vps.sh
#
# It will prompt for: domain name, admin email, admin password.
# Everything else is auto-configured.

set -euo pipefail

# ---------------- Helpers ----------------
log()  { echo -e "\033[1;32m▶\033[0m $*"; }
warn() { echo -e "\033[1;33m!\033[0m $*"; }
err()  { echo -e "\033[1;31m✖\033[0m $*" >&2; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    err "Run as root (use sudo)."
    exit 1
  fi
}

random_secret() {
  head -c 48 /dev/urandom | base64 | tr -d '\n=/+' | head -c 48
}

prompt() {
  local var=$1 msg=$2 default=${3:-}
  if [[ -n "$default" ]]; then
    read -rp "$msg [$default]: " input
    eval "$var=\"\${input:-$default}\""
  else
    read -rp "$msg: " input
    eval "$var=\"\$input\""
  fi
}

# ---------------- Args ----------------
GIT_URL=""
SRC_ARCHIVE="/root/wa9x.tar.gz"
APP_DIR="/opt/wa9x"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --git)     GIT_URL="$2"; shift 2 ;;
    --archive) SRC_ARCHIVE="$2"; shift 2 ;;
    --dir)     APP_DIR="$2"; shift 2 ;;
    *)         err "Unknown arg: $1"; exit 1 ;;
  esac
done

# ---------------- 0. Sanity ----------------
require_root

log "wa.9x.design — VPS setup starting"

prompt DOMAIN     "Your domain (e.g. wa.9x.design or yourapp.com)"
prompt ADMIN_EMAIL "Admin email (for login + Let's Encrypt)" "admin@${DOMAIN}"
prompt ADMIN_PASS  "Admin password (min 8 chars)"

if [[ ${#ADMIN_PASS} -lt 8 ]]; then
  err "Admin password must be at least 8 characters."
  exit 1
fi

# ---------------- 1. Apt update + base packages ----------------
log "Updating apt + installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y curl wget gnupg ca-certificates lsb-release software-properties-common \
  build-essential git unzip ufw nginx supervisor python3.11 python3.11-venv python3-pip \
  certbot python3-certbot-nginx libffi-dev libssl-dev pkg-config

# ---------------- 2. Node.js 20 ----------------
log "Installing Node.js 20 + Yarn"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
npm install -g yarn

# ---------------- 3. MongoDB 7 ----------------
log "Installing MongoDB 7"
if ! command -v mongod >/dev/null 2>&1; then
  curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-7.gpg --dearmor
  UBUNTU_CODENAME=$(lsb_release -cs)
  if [[ "$UBUNTU_CODENAME" == "noble" ]]; then UBUNTU_CODENAME="jammy"; fi  # MongoDB doesn't have noble repo yet
  echo "deb [signed-by=/usr/share/keyrings/mongodb-7.gpg arch=amd64,arm64] https://repo.mongodb.org/apt/ubuntu $UBUNTU_CODENAME/mongodb-org/7.0 multiverse" \
    > /etc/apt/sources.list.d/mongodb-org-7.0.list
  apt-get update -y
  apt-get install -y mongodb-org
fi
systemctl enable --now mongod

# ---------------- 4. Source code ----------------
log "Setting up application at $APP_DIR"
mkdir -p "$APP_DIR"

if [[ -n "$GIT_URL" ]]; then
  if [[ -d "$APP_DIR/.git" ]]; then
    cd "$APP_DIR" && git pull
  else
    rm -rf "$APP_DIR"
    git clone "$GIT_URL" "$APP_DIR"
  fi
elif [[ -f "$SRC_ARCHIVE" ]]; then
  log "Extracting $SRC_ARCHIVE"
  tar -xzf "$SRC_ARCHIVE" -C "$APP_DIR" --strip-components=1
else
  err "No source. Provide --git <url> OR upload tarball to $SRC_ARCHIVE"
  exit 1
fi

# ---------------- 5. Backend (Python venv) ----------------
log "Installing backend Python dependencies"
cd "$APP_DIR/backend"
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
deactivate

# ---------------- 6. WhatsApp Node service ----------------
log "Installing wa-service (Node + Baileys) dependencies"
cd "$APP_DIR/wa-service"
yarn install --frozen-lockfile

# ---------------- 7. Persistent dirs ----------------
log "Setting up persistent storage"
mkdir -p /var/lib/wa9x/auth /var/lib/wa9x/uploads /var/lib/wa9x/uploads/inbound
ln -sfn /var/lib/wa9x/auth     "$APP_DIR/wa-service/auth"
ln -sfn /var/lib/wa9x/uploads  "$APP_DIR/wa-service/uploads"

# ---------------- 8. Backend .env ----------------
log "Generating backend .env"
JWT_SECRET=$(random_secret)
INTERNAL_SECRET=$(random_secret)

cat > "$APP_DIR/backend/.env" << EOF
MONGO_URL="mongodb://localhost:27017"
DB_NAME="wa9x_db"
CORS_ORIGINS="https://${DOMAIN}"
JWT_SECRET="${JWT_SECRET}"
ADMIN_EMAIL="${ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASS}"
WA_SERVICE_URL="http://127.0.0.1:3001"
WA_SERVICE_DIR="${APP_DIR}/wa-service"
WA_SERVICE_LOG="/var/log/wa9x-wa-service.log"
INTERNAL_SECRET="${INTERNAL_SECRET}"
WA_AUTH_DIR="/var/lib/wa9x/auth"
BACKEND_PUBLIC_URL="https://${DOMAIN}"
FRONTEND_URL="https://${DOMAIN}"
INSTALL_DIR="${APP_DIR}"
AUTO_UPDATE_RESTART_CMD="supervisorctl restart wa9x-backend"
STRIPE_SECRET_KEY=""
STRIPE_WEBHOOK_SECRET=""
RAZORPAY_KEY_ID=""
RAZORPAY_KEY_SECRET=""
RAZORPAY_WEBHOOK_SECRET=""
PAYPAL_MODE="sandbox"
PAYPAL_CLIENT_ID=""
PAYPAL_SECRET=""
PAYPAL_WEBHOOK_ID=""
RESEND_API_KEY=""
EMAIL_FROM="wa.9x.design <noreply@send.9x.design>"
EOF
chmod 600 "$APP_DIR/backend/.env"

# ---------------- 9. Frontend build ----------------
log "Building frontend"
cd "$APP_DIR/frontend"
cat > .env << EOF
REACT_APP_BACKEND_URL=https://${DOMAIN}
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
EOF
yarn install --frozen-lockfile
yarn build

# ---------------- 10. Supervisor ----------------
log "Configuring supervisor"
cat > /etc/supervisor/conf.d/wa9x-backend.conf << EOF
[program:wa9x-backend]
command=$APP_DIR/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
directory=$APP_DIR/backend
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/wa9x-backend.err.log
stdout_logfile=/var/log/wa9x-backend.out.log
environment=PYTHONUNBUFFERED="1"
user=root
EOF

supervisorctl reread
supervisorctl update
supervisorctl restart wa9x-backend || supervisorctl start wa9x-backend

# ---------------- 11. Nginx + Let's Encrypt ----------------
log "Configuring Nginx for ${DOMAIN}"
cat > /etc/nginx/sites-available/wa9x << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 30M;
    access_log /var/log/nginx/wa9x-access.log;
    error_log  /var/log/nginx/wa9x-error.log;

    # Frontend (React build)
    root $APP_DIR/frontend/build;
    index index.html;

    location / {
        try_files \$uri /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 90s;
    }
}
EOF
ln -sfn /etc/nginx/sites-available/wa9x /etc/nginx/sites-enabled/wa9x
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

log "Requesting Let's Encrypt certificate (email: ${ADMIN_EMAIL})"
if ! certbot --nginx --non-interactive --agree-tos -m "${ADMIN_EMAIL}" -d "${DOMAIN}" --redirect; then
  warn "certbot failed — site is reachable on http only. Re-run: certbot --nginx -d ${DOMAIN}"
fi

# ---------------- 12. Firewall ----------------
log "Configuring UFW firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
echo "y" | ufw enable || true

# ---------------- 13. Wait for backend health ----------------
log "Waiting for backend to be healthy…"
for i in {1..30}; do
  if curl -fs http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
    log "Backend is up."
    break
  fi
  sleep 2
done

# ---------------- Done ----------------
echo
echo "═════════════════════════════════════════════════════"
echo "  wa.9x.design is deployed!"
echo "═════════════════════════════════════════════════════"
echo "  URL:           https://${DOMAIN}"
echo "  Admin login:   ${ADMIN_EMAIL}  /  ${ADMIN_PASS}"
echo "  App dir:       ${APP_DIR}"
echo "  Backend logs:  /var/log/wa9x-backend.{out,err}.log"
echo "  WA logs:       /var/log/wa9x-backend.out.log (Node spawned by FastAPI)"
echo "  Auth storage:  /var/lib/wa9x/auth"
echo "  Mongo URL:     mongodb://localhost:27017/wa9x_db"
echo
echo "  Useful commands:"
echo "    supervisorctl restart wa9x-backend"
echo "    tail -f /var/log/wa9x-backend.err.log"
echo "    nginx -t && systemctl reload nginx"
echo "    certbot renew --dry-run"
echo
echo "  Next: log in, link a WhatsApp number, set payment gateway keys."
echo "═════════════════════════════════════════════════════"
