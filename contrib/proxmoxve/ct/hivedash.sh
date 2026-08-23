#!/usr/bin/env bash
source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)
# Copyright (c) 2021-2026 community-scripts ORG
# Author: sascha-hemi
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://github.com/sascha-hemi/hivedash

APP="HiveDash"
var_tags="${var_tags:-dashboard}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-8}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/hivedash ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  setup_uv

  if check_for_gh_release "hivedash" "sascha-hemi/hivedash"; then
    msg_info "Stopping Service"
    systemctl stop hivedash
    msg_ok "Stopped Service"

    # /opt/hivedash_data (SQLite DB + generated .env) lives outside the fetch target and is
    # never touched by this - only /opt/hivedash (the app source) gets replaced.
    CLEAN_INSTALL=1 fetch_and_deploy_gh_release "hivedash" "sascha-hemi/hivedash" "tarball" "latest" "/opt/hivedash"

    msg_info "Building frontend"
    cd /opt/hivedash/frontend
    $STD npm install --no-fund --no-audit
    $STD npm run build
    rm -rf /opt/hivedash/app/static
    mkdir -p /opt/hivedash/app/static
    cp -r dist/frontend/browser/. /opt/hivedash/app/static/
    msg_ok "Built frontend"

    msg_info "Updating Python environment"
    cd /opt/hivedash
    $STD /usr/local/bin/uv venv .venv
    $STD /usr/local/bin/uv pip install -r requirements.txt --python .venv/bin/python
    msg_ok "Updated Python environment"

    msg_info "Running database migrations"
    cd /opt/hivedash
    set -a
    . /opt/hivedash_data/hivedash.env
    set +a
    $STD .venv/bin/python -m alembic upgrade head
    msg_ok "Ran database migrations"

    msg_info "Starting Service"
    systemctl start hivedash
    msg_ok "Started Service"
    msg_ok "Updated successfully!"
  fi
  exit
}

start
build_container
description

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:8000${CL}"
echo -e "${INFO}${YW}Nothing will be discovered until you edit /opt/hivedash_data/hivedash.env with your${CL}"
echo -e "${INFO}${YW}Nginx Proxy Manager and Proxmox VE credentials, then run: systemctl restart hivedash${CL}"
