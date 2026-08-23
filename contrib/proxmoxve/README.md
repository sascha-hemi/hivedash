# community-scripts/ProxmoxVE contribution

These three files are a ready-to-submit LXC install script for HiveDash, written to match
the current conventions of [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE)
(the project formerly maintained by tteck) - native install, no Docker, matching their
`AGENTS.md` style guide and the `mediamanager`/`homarr` scripts as reference.

- `ct/hivedash.sh` - runs on the Proxmox host: creates the LXC, sets default
  resources/OS, then calls the install script inside it. Also contains `update_script()`,
  used when this same script is re-run against an existing HiveDash container.
- `install/hivedash-install.sh` - runs inside the freshly created LXC: installs Node.js
  (build-time only) and Python/uv, fetches the HiveDash release tarball, builds the
  Angular frontend, sets up the Python venv, runs the Alembic migrations, generates
  `/opt/hivedash_data/hivedash.env` with a fresh cookie secret and bootstrap admin
  password, and creates the systemd service.
- `json/hivedash.json` - metadata for the community-scripts website (description,
  category, default resources, notes shown to the admin after install).
