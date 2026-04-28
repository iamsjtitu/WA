#!/usr/bin/env bash
# wa.9x.design — auto-update from GitHub
#
# Triggered by POST /api/admin/system/update.
# Runs `git pull`, conditionally reinstalls deps, rebuilds frontend, restarts backend.
#
# Required env: INSTALL_DIR (default /opt/wa9x).
#
# Logs to /var/log/wa9x-update.log (tail in admin panel).

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/wa9x}"
RESTART_CMD="${AUTO_UPDATE_RESTART_CMD:-supervisorctl restart wa9x-backend}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

trap 'log "✖ Update FAILED at line $LINENO"' ERR

cd "$INSTALL_DIR"

log "▶ wa.9x.design auto-update starting"
log "▶ Install dir: $INSTALL_DIR"
log "▶ Current HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

# Snapshot dep-file hashes
OLD_REQ=$(md5sum backend/requirements.txt 2>/dev/null | awk '{print $1}' || true)
OLD_FE=$(md5sum frontend/package.json 2>/dev/null | awk '{print $1}' || true)
OLD_WA=$(md5sum wa-service/package.json 2>/dev/null | awk '{print $1}' || true)

# Pull (use reset --hard so any local changes never block the update)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
log "▶ git fetch + reset --hard origin/$BRANCH"
git fetch --quiet origin
git reset --hard "origin/$BRANCH"
git clean -fd --quiet
log "▶ New HEAD: $(git rev-parse --short HEAD)"

# Backend Python deps
NEW_REQ=$(md5sum backend/requirements.txt 2>/dev/null | awk '{print $1}' || true)
if [[ "$OLD_REQ" != "$NEW_REQ" ]]; then
  log "▶ requirements.txt changed → pip install"
  cd backend
  if [[ -d venv ]]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install --quiet -r requirements.txt
    deactivate
  else
    log "  (no venv — skipping; pip-install manually if needed)"
  fi
  cd ..
fi

# wa-service Node deps
NEW_WA=$(md5sum wa-service/package.json 2>/dev/null | awk '{print $1}' || true)
if [[ "$OLD_WA" != "$NEW_WA" ]]; then
  log "▶ wa-service/package.json changed → yarn install"
  cd wa-service
  yarn install --frozen-lockfile --silent
  cd ..
fi

# Frontend deps
NEW_FE=$(md5sum frontend/package.json 2>/dev/null | awk '{print $1}' || true)
if [[ "$OLD_FE" != "$NEW_FE" ]]; then
  log "▶ frontend/package.json changed → yarn install"
  cd frontend
  yarn install --frozen-lockfile --silent
  cd ..
fi

# Frontend build (always, since /src might have changed)
log "▶ Building frontend"
cd frontend
yarn build > /dev/null
cd ..

# Restart backend (this also respawns the wa-service Node child)
log "▶ Restarting backend: $RESTART_CMD"
$RESTART_CMD || log "  (restart command failed — restart manually)"

log "✓ Update complete"
