#!/usr/bin/env bash

# Copyright (c) 2021-2026 community-scripts ORG
# Author: sascha-hemi
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://github.com/sascha-hemi/hivedash

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing build dependencies"
# argon2-cffi (password hashing) may need to compile its C extension from source if the
# venv's Python is too new for a prebuilt wheel yet.
$STD apt install -y build-essential libffi-dev python3-dev
msg_ok "Installed build dependencies"

NODE_VERSION="22" setup_nodejs
setup_uv

fetch_and_deploy_gh_release "hivedash" "sascha-hemi/hivedash" "tarball" "latest" "/opt/hivedash"

msg_info "Setting up persistent data directory"
mkdir -p /opt/hivedash_data
msg_ok "Set up persistent data directory"

msg_info "Building frontend"
cd /opt/hivedash/frontend
$STD npm install --no-fund --no-audit
$STD npm run build
mkdir -p /opt/hivedash/app/static
cp -r dist/frontend/browser/. /opt/hivedash/app/static/
msg_ok "Built frontend"

msg_info "Setting up Python environment"
cd /opt/hivedash
$STD /usr/local/bin/uv venv .venv
$STD /usr/local/bin/uv pip install -r requirements.txt --python .venv/bin/python
msg_ok "Set up Python environment"

msg_info "Generating configuration"
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
msg_ok "Generated configuration"

msg_info "Running database migrations"
cd /opt/hivedash
set -a
. /opt/hivedash_data/hivedash.env
set +a
$STD .venv/bin/python -m alembic upgrade head
msg_ok "Ran database migrations"

msg_info "Creating service"
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
systemctl enable -q --now hivedash
msg_ok "Created service"

echo -e "${INFO}${YW}Bootstrap admin: admin@hivedash.local / ${ADMIN_PASS}${CL}"
echo -e "${INFO}${YW}(also saved in /opt/hivedash_data/hivedash.env)${CL}"

motd_ssh
customize
cleanup_lxc
