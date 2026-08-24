# community-scripts/ProxmoxVE contribution

**Want to install HiveDash on your Proxmox right now, before this is anywhere near merged?**
Use `standalone-install.sh` instead - a plain, self-contained bash script with no
community-scripts dependency at all. `ct/hivedash.sh` can't be run standalone yet: it
sources the *official* `community-scripts/ProxmoxVE`'s `build.func`, which fetches the
install script from a hardcoded `community-scripts/ProxmoxVE` URL - not from this repo -
so it 404s until the PR below is actually merged.

```bash
# Inside a fresh Debian 12/13 LXC or VM (create it yourself via the Proxmox UI first),
# run as root. A minimal Debian LXC template ships with neither curl nor wget, and this
# one-liner needs curl just to fetch itself, so install that first:
apt update && apt install -y curl

bash -c "$(curl -fsSL https://raw.githubusercontent.com/sascha-hemi/hivedash/main/contrib/proxmoxve/standalone-install.sh)"
```

Verified end to end against a real, fresh Debian 13 container: release fetch, Angular
build, Python venv + pip install (incl. argon2-cffi), and the Alembic migration all run
clean; the app starts and answers `/api/health`. The only part that can't be verified
outside a real LXC is the final `systemctl enable --now hivedash` (Docker has no init
system to test against) - on a real Proxmox LXC this just works.

---

The three files below are a ready-to-submit LXC install script for HiveDash, written to match
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

Submission to community-scripts/ProxmoxVE is planned but not yet public - not everything
about that process is documented in this repo.
