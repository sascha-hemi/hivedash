# Changelog

All notable changes to HiveDash are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Search bar on the dashboard for external search engines (Google, Bing, DuckDuckGo, Startpage,
  Brave, Ecosia, Kagi, Perplexity) - default configurable via `SEARCH_ENGINE`, per-user override
  saved to the account.
- Self-service account page (`/account`): language choice and password change, available to
  every user, not just admins.
- Multi-language UI (English, German, Dutch, Spanish, French) with automatic browser detection
  and a manual per-user override.
- Toast notifications (Tabler-styled) for every error/success message, replacing the old inline
  alert banners across the admin pages, login, and the dashboard's NPM/Proxmox connectivity
  status.
- Version number and update-check against GitHub Releases, shown on the account page.
- This changelog, rendered on its own page from the account page.
- CI: automated backend test suite + frontend production build on every push/PR, plus building
  and publishing the container image to `ghcr.io/sascha-hemi/hivedash`.

### Fixed

- The dashboard's NPM/Proxmox error banner could silently show nothing at all for certain
  connection failures (e.g. a timeout) whose error message stringifies to an empty string.

## [1.0.0] - 2026-08-24

### Added

- Initial release: auto-discovers services from Nginx Proxy Manager (proxy hosts) and Proxmox VE
  (VMs/LXCs), matching a guest to its proxy host by IP or hostname and merging them into one
  tile with live CPU/RAM stats.
- Multi-user, multi-dashboard support: an admin curates per-dashboard visibility, order,
  category, and display name for each service, and assigns users to a dashboard.
- Logo library with automatic matching against the
  [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) catalog.
- Local email/password login and optional generic OIDC/SSO login.
- Live updates over WebSocket, with an HTTP polling fallback.
- Proxmox VE LXC installer, both as a community-scripts-style script and a standalone
  self-contained install script.
