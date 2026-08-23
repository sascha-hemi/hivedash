#!/usr/bin/env bash
# Standalone HiveDash installer - for running directly inside a fresh Debian 12/13 LXC or
# VM, right now, without going through community-scripts (their tooling can only fetch an
# install script from community-scripts/ProxmoxVE itself, not yet from this project's own
# repo - see contrib/proxmoxve/README.md for the eventual PR-based path). No dependency on
# any community-scripts helper function; this is plain bash you can read top to bottom.
#
# Run this as root INSIDE the container/VM you want HiveDash on (e.g. via the Proxmox
# console/shell for that container), not on the Proxmox host itself.
set -euo pipefail

HIVEDASH_VERSION="v1.0.0"

echo "==> Updating system"
apt update && apt -y upgrade

echo "==> Installing Python and build tools"
# build-essential/libffi-dev/python3-dev: argon2-cffi (password hashing) may need to compile
# its C extension from source if Debian's Python is too new for a prebuilt wheel yet.
apt install -y curl ca-certificates gnupg python3 python3-venv python3-pip \
  build-essential libffi-dev python3-dev

echo "==> Installing Node.js 22 (build-time only - not needed once the frontend is built)"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs

echo "==> Fetching HiveDash ${HIVEDASH_VERSION}"
mkdir -p /opt/hivedash_data
mkdir -p /opt/hivedash
curl -fsSL -o /tmp/hivedash.tar.gz \
  "https://github.com/sascha-hemi/hivedash/archive/refs/tags/${HIVEDASH_VERSION}.tar.gz"
tar -xzf /tmp/hivedash.tar.gz -C /opt/hivedash --strip-components=1
rm /tmp/hivedash.tar.gz

echo "==> Building frontend"
cd /opt/hivedash/frontend
npm install --no-fund --no-audit
npm run build
mkdir -p /opt/hivedash/app/static
cp -r dist/frontend/browser/. /opt/hivedash/app/static/

echo "==> Setting up Python environment"
cd /opt/hivedash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo "==> Generating configuration"
COOKIE_SECRET="$(openssl rand -base64 32)"
ADMIN_PASS="$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | cut -c1-16)"
cat <<EOF >/opt/hivedash_data/hivedash.env
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
DATABASE_PATH=/opt/hivedash_data/hivedash.db

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

echo "==> Running database migrations"
cd /opt/hivedash
set -a
. /opt/hivedash_data/hivedash.env
set +a
.venv/bin/python -m alembic upgrade head

echo "==> Creating systemd service"
cat <<EOF >/etc/systemd/system/hivedash.service
[Unit]
Description=HiveDash Backend Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/hivedash
EnvironmentFile=/opt/hivedash_data/hivedash.env
ExecStart=/opt/hivedash/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now hivedash

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "==================================================================="
echo " HiveDash is running: http://${IP}:8000"
echo ""
echo " Bootstrap admin: admin@hivedash.local / ${ADMIN_PASS}"
echo " (also saved in /opt/hivedash_data/hivedash.env)"
echo ""
echo " Nothing will be discovered yet - edit:"
echo "   /opt/hivedash_data/hivedash.env"
echo " with your Nginx Proxy Manager and Proxmox VE credentials, then:"
echo "   systemctl restart hivedash"
echo "==================================================================="
