#!/usr/bin/env bash
# Standalone HiveDash installer/updater - for running directly inside a fresh (or existing)
# Debian 12/13 LXC or VM, right now, without going through community-scripts (their tooling
# can only fetch an install script from community-scripts/ProxmoxVE itself, not yet from this
# project's own repo - see contrib/proxmoxve/README.md for the eventual PR-based path). No
# dependency on any community-scripts helper function; this is plain bash you can read top to
# bottom.
#
# Run this as root INSIDE the container/VM you want HiveDash on (e.g. via the Proxmox
# console/shell for that container), not on the Proxmox host itself.
#
# Re-running the same command later updates an existing install in place: detected by the
# presence of ENV_FILE below, which only a prior run of this script creates. Update mode
# leaves ENV_FILE (NPM/Proxmox config, cookie secret, DB path) and the systemd unit alone,
# and never touches DATA_DIR (holds the SQLite DB) - only INSTALL_DIR (the app source) is
# replaced.
set -euo pipefail

INSTALL_DIR=/opt/hivedash
DATA_DIR=/opt/hivedash_data
ENV_FILE="$DATA_DIR/hivedash.env"

if [[ -f "$ENV_FILE" ]]; then
  MODE="update"
else
  MODE="install"
fi

echo "==> Resolving HiveDash version"
if [[ -z "${HIVEDASH_VERSION:-}" ]]; then
  HIVEDASH_VERSION="$(curl -fsSL https://api.github.com/repos/sascha-hemi/hivedash/releases/latest \
    | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')"
fi
if [[ -z "${HIVEDASH_VERSION:-}" ]]; then
  echo "Could not resolve the latest release from the GitHub API - pass a version explicitly," \
    "e.g. HIVEDASH_VERSION=v1.0.0 bash -c \"\$(curl ...)\"" >&2
  exit 1
fi
echo "==> HiveDash ${HIVEDASH_VERSION} (${MODE})"

echo "==> Installing/updating base packages"
apt update && apt -y upgrade
# build-essential/libffi-dev/python3-dev: argon2-cffi (password hashing) may need to compile
# its C extension from source if Debian's Python is too new for a prebuilt wheel yet.
apt install -y curl ca-certificates gnupg python3 python3-venv python3-pip \
  build-essential libffi-dev python3-dev

if ! command -v node >/dev/null 2>&1; then
  echo "==> Installing Node.js 22 (build-time only - not needed once the frontend is built)"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt install -y nodejs
fi

if [[ "$MODE" == "update" ]] && systemctl is-active --quiet hivedash 2>/dev/null; then
  echo "==> Stopping service"
  systemctl stop hivedash
fi

echo "==> Fetching HiveDash ${HIVEDASH_VERSION}"
mkdir -p "$DATA_DIR"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
curl -fsSL -o /tmp/hivedash.tar.gz \
  "https://github.com/sascha-hemi/hivedash/archive/refs/tags/${HIVEDASH_VERSION}.tar.gz"
tar -xzf /tmp/hivedash.tar.gz -C "$INSTALL_DIR" --strip-components=1
rm /tmp/hivedash.tar.gz

echo "==> Building frontend"
cd "$INSTALL_DIR/frontend"
npm install --no-fund --no-audit
npm run build
mkdir -p "$INSTALL_DIR/app/static"
cp -r dist/frontend/browser/. "$INSTALL_DIR/app/static/"

echo "==> Setting up Python environment"
cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

if [[ "$MODE" == "install" ]]; then
  echo "==> Generating configuration"
  COOKIE_SECRET="$(openssl rand -base64 32)"
  ADMIN_PASS="$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | cut -c1-16)"
  cat <<EOF >"$ENV_FILE"
# --- Nginx Proxy Manager --- (required - fill in, then: systemctl restart hivedash)
NPM_URL=
NPM_EMAIL=
NPM_PASSWORD=
NPM_VERIFY_SSL=true

# --- Proxmox VE --- (required - fill in, then: systemctl restart hivedash)
PROXMOX_URL=
PROXMOX_TOKEN_ID=
PROXMOX_TOKEN_SECRET=
PROXMOX_VERIFY_SSL=false

# --- General ---
NPM_POLL_INTERVAL_SECONDS=60
PROXMOX_POLL_INTERVAL_SECONDS=5
REQUEST_TIMEOUT_SECONDS=10
DASHBOARD_TITLE=HiveDash

# --- Database ---
DATABASE_PATH=$DATA_DIR/hivedash.db

# --- Auth / sessions ---
COOKIE_SECRET=$COOKIE_SECRET
COOKIE_SECURE=false
SESSION_LIFETIME_DAYS=30
PUBLIC_BASE_URL=
BOOTSTRAP_ADMIN_EMAIL=admin@hivedash.local
BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASS

# --- OIDC (optional - leave blank to disable) ---
OIDC_ISSUER=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=

# --- Logo library ---
LOGO_CATALOG_AUTO_IMPORT=true
EOF
fi

echo "==> Running database migrations"
cd "$INSTALL_DIR"
set -a
. "$ENV_FILE"
set +a
.venv/bin/python -m alembic upgrade head

if [[ "$MODE" == "install" ]]; then
  echo "==> Creating systemd service"
  cat <<EOF >/etc/systemd/system/hivedash.service
[Unit]
Description=HiveDash Backend Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now hivedash
else
  echo "==> Starting service"
  systemctl daemon-reload
  systemctl start hivedash
fi

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "==================================================================="
if [[ "$MODE" == "install" ]]; then
  echo " HiveDash is running: http://${IP}:8000"
  echo ""
  echo " Bootstrap admin: admin@hivedash.local / ${ADMIN_PASS}"
  echo " (also saved in $ENV_FILE)"
  echo ""
  echo " Nothing will be discovered yet - edit:"
  echo "   $ENV_FILE"
  echo " with your Nginx Proxy Manager and Proxmox VE credentials, then:"
  echo "   systemctl restart hivedash"
else
  echo " HiveDash updated to ${HIVEDASH_VERSION}: http://${IP}:8000"
  echo " Config and database in $DATA_DIR were left untouched."
fi
echo "==================================================================="
