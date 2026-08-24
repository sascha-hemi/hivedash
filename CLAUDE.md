# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted, multi-user dashboard that auto-discovers services from two sources — no manual
YAML per service:

- **Nginx Proxy Manager**: all configured proxy hosts, shown as clickable tiles with domain and
  online/offline status.
- **Proxmox VE**: all VMs and LXC containers, with live CPU/RAM stats.
- **Matching**: a Proxmox guest is matched to an NPM proxy host by comparing the host's
  `forward_host` against the guest's known IP addresses (QEMU IPs come from the
  `qemu-guest-agent`; LXC IPs come from the Proxmox interfaces endpoint) OR, case-insensitively,
  against the guest's own `name` (covers an NPM host configured with a hostname instead of a raw
  IP — Proxmox's "name" field doubles as the actual hostname for the common case of an LXC/VM set
  up that way); an IP match wins if both would otherwise apply. A match merges them into one tile,
  preferring the guest's own name as the tile's default display name over the NPM subdomain
  (overridable via the "Dienste" admin page's per-service `custom_name`). Anything that can't be
  matched is still shown — as a plain link (unmatched proxy host) or a bare infrastructure tile
  (unmatched guest). Nothing is ever silently dropped.

A FastAPI backend polls both APIs on a timer and persists the result into SQLite (not just an
in-memory cache — a restart or a transient NPM/Proxmox outage doesn't blank the dashboard). Users
log in (local email/password, or OIDC against e.g. an Authentik instance) and see a dashboard;
an admin can create additional dashboards and curate visibility/order/display-name per service,
per dashboard, and assign users to one. The frontend is an Angular SPA styled with
[Tabler](https://github.com/tabler/tabler).

Read `README.md` for full setup/credentials instructions.

## Commands

### Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # lifespan auto-creates tables via init_models()
```

Tests are plain `assert`-based scripts (no pytest), run directly with the interpreter — each is
self-contained (uses a temp-file SQLite via `DATABASE_PATH`, cleans up after itself):

```bash
python tests/test_merge.py            # pure IP-or-hostname matching logic, no DB/network
python tests/test_dashboard_view.py    # pure per-dashboard visibility/order/category/custom-service logic
python tests/test_logo_matching.py     # pure keyword-matching logic (longest-keyword-wins, tie-break)
python tests/test_db_repository.py     # upsert/prune/default-dashboard-population + logo sticky/self-healing, against a temp SQLite DB
python tests/test_auth.py              # drives the real FastAPI app over an in-process ASGI transport: login/logout/CSRF/roles
python tests/test_admin_dashboards.py  # dashboard tile_size/category CRUD + category_id round-trip through bulk items PATCH
python tests/test_admin_services.py    # "Dienste" page: global logo/name/url on a proxy_host/guest + custom-service CRUD
python tests/test_admin_logos.py       # logo upload/list/delete + dangling-reference cleanup + image serving auth
python tests/test_clients_live.py      # NpmClient/ProxmoxClient against a local fake HTTP server
```

`tests/fake_backend.py` is not a test — a standalone fake NPM+Proxmox server for manual smoke
testing. There is no lint/format tooling configured for the backend.

### Frontend

```bash
cd frontend
npm install
npm start            # ng serve; proxy.conf.json forwards /api/* to http://localhost:8090
npm run build         # production build -> dist/frontend/browser
```

For local end-to-end testing without `ng serve`, build once and copy the output where FastAPI's
static mount expects it: `cp -r frontend/dist/frontend/browser/* app/static/`.

### Docker (primary supported way to run the whole thing)

```bash
cp .env.example .env   # fill in NPM/Proxmox/COOKIE_SECRET/BOOTSTRAP_ADMIN_*
docker compose up -d --build
docker compose logs -f
```

The image is a multi-stage build (Node stage compiles the Angular app, Python stage serves it);
the container's `CMD` runs `alembic upgrade head` before starting uvicorn. The SQLite DB lives on
a named volume (`dashboard-data:/srv/data`) so it survives rebuilds.

### Migrations

Schema changes go through Alembic, not ad-hoc `create_all()` (which is still used for local
dev/tests via `init_models()` — see `app/db/engine.py`):

```bash
alembic revision --autogenerate -m "..."   # DATABASE_PATH env var controls which DB it targets
alembic upgrade head
```

## Architecture

### Backend (`app/`)

- `app/config.py` — single `Settings` object reading everything from env vars (`os.environ.get`).
  Several `*_enabled` properties (`npm_enabled`, `proxmox_enabled`, `oidc_enabled`) are derived —
  true only if all required values for that feature are non-empty — and are how "not configured"
  is distinguished from "configured but failing" throughout the app.
- `app/clients/npm.py`, `app/clients/proxmox.py` — one async httpx client per external API, each
  independent of FastAPI and of each other. Return plain dataclasses (`ProxyHost`, `Guest`). Guest
  IP lookup is best-effort (missing guest-agent, stopped LXC, etc. all just yield `[]`).
- `app/merge.py` — pure function `build_dashboard(hosts, guests, npm_error, proxmox_error)`, the
  IP-*or*-hostname matching logic (a host's `forward_host` against each guest's IPs, falling back
  to a case-insensitive match against the guest's own `name`), no I/O, no DB. **Never modified for
  DB/auth/multi-dashboard work** — the DB layer's job is only to get `ProxyHost`/`Guest`
  dataclasses into and back out of storage, so this function keeps operating on the exact same
  shapes it always has. Reused as-is (not reimplemented) by `admin_repository.list_discovered_services`
  for the "Dienste" page, so the two can never disagree on what counts as matched.
- `app/db/` — the persistence layer:
  - `models.py` — `User`, `OidcIdentity`, `Session` (identity/auth) and `ProxyHost`, `Guest`,
    `CustomService`, `Dashboard`, `DashboardItem`, `Category`, `Logo` (persisted poll results +
    per-dashboard curation + the logo library). `CustomService` is a wholly admin-created "Dienst"
    with no NPM/Proxmox counterpart at all (e.g. a device that's neither) — discovery never
    touches it, only the "Dienste" admin page's CRUD does. `DashboardItem` is the join table
    making the same service visible/hidden/reordered/categorized differently per dashboard
    (exactly one of `proxy_host_id`/`guest_id`/`custom_service_id` set, enforced by a
    `CheckConstraint` summing which of the three is non-null). **Identity (logo/name/link) is
    global, not per-dashboard**: `ProxyHost`/`Guest` each carry nullable `logo_id`/`custom_name`/
    `custom_url` columns (same idiom for all three — "what this service is"), and `CustomService`
    carries `name`/`url`/`logo_id` as its actual (not override) fields — a service is called and
    links to the same thing everywhere it's shown, configured once on the "Dienste" admin page.
    `DashboardItem` itself only ever holds curation (`visible`/`sort_order`/`category_id`) — it
    used to also carry `display_name_override`/`custom_url` per-dashboard, but that was
    superseded (see the `32a2dadd26d2` migration, which also folds any values already set there
    onto the corresponding service's new global column). `Logo` stores the image itself as a
    `LargeBinary` blob (no second volume needed) plus lowercased `keywords` used for
    auto-matching. **SQLite never enforces `ondelete=` here** (no `PRAGMA foreign_keys=ON` is ever
    set) — the FK annotations are documentation-only, so anything that deletes a `Logo` must
    explicitly null out referencing rows itself (see `admin_repository.delete_logo`, which nulls
    `logo_id` on all three of `ProxyHost`/`Guest`/`CustomService`), and any join reading `logo_id`
    back out must stay an outer join and tolerate a dangling id gracefully. Similarly, deleting a
    `CustomService` deletes its `DashboardItem` rows outright (not null-out) since the check
    constraint requires exactly one target.
  - `engine.py` — **lazily** creates the async engine/sessionmaker from `settings.database_path`
    (not at import time, unlike `npm_client`/`proxmox_client` in `main.py`) so tests can point it
    at a temp file first. `init_models()` (dev/tests) vs. Alembic (production) — see Commands.
  - `repository.py` — the hot path used by the poll loop and `GET /api/dashboard`:
    `upsert_proxy_hosts`/`upsert_guests` (natural-key upsert + prune, **only called when that
    source's poll succeeded** — a transient failure leaves existing rows untouched, so the
    dashboard shows last-known-good data through the error banner rather than going blank).
    These same two functions also auto-assign `logo_id` via `app/logo_matching.py`, using a
    `func.coalesce(existing_column, stmt.excluded.column)` SQL expression in the upsert's `set_`
    clause — **"sticky but self-healing"**: a manual assignment or prior auto-match is never
    overwritten (non-null stays non-null), but a still-`NULL` `logo_id` is re-evaluated on every
    poll, so a logo uploaded after a service was already discovered still gets picked up later.
    This is a genuinely different idiom than `first_seen_at`'s stickiness (achieved by *omitting*
    the column from `set_` entirely) — don't conflate the two patterns. `ProxyHost`/`Guest.logo_locked`
    gates this: it exists because "self-healing" alone can't tell "never evaluated yet" apart from
    "the admin explicitly cleared this to **kein Logo**" — both look like `logo_id IS NULL`.
    `admin_repository.set_service_details` sets `logo_locked = True` on *any* explicit `logo_id`
    write from the "Dienste" page (a specific logo, or `None`); both upsert functions then load
    each row's current `logo_locked` up front and skip `_match_or_fetch_logo()` entirely for a
    locked row (feeding `None` into the same COALESCE, which then just preserves whatever's
    already there — including a deliberately-`NULL` "kein Logo").
    `load_proxy_hosts`/`load_guests` (DB rows back out *as the original dataclasses*, straight into
    `build_dashboard()`), `ensure_default_dashboard_items` (keeps the one `is_default` dashboard
    auto-populated with every known service, including `CustomService` rows — custom dashboards
    are **not** auto-populated; an admin attaches services to those explicitly, and a freshly
    created custom service is also attached to the default dashboard immediately at creation time
    rather than waiting for the next poll cycle), `load_resolved_dashboard_items` (resolves
    `DashboardItem` rows to the natural key `build_dashboard()`'s output uses, joining out to
    whichever of `ProxyHost`/`Guest`/`CustomService` is the item's target for its global
    `custom_name`/`custom_url`/`logo_url`, so `dashboard_view.py` stays DB-free).
  - `admin_repository.py` — everything backing `routers/admin.py` (user CRUD, dashboard CRUD,
    per-item visibility/order/category, the "available services" picker, `list_discovered_services`
    for the "Dienste" page's full identity listing regardless of dashboard attachment,
    `set_service_details` for a proxy_host/guest's global logo/name/url, and full CRUD for
    `CustomService`). `list_discovered_services` reuses `app.merge.build_dashboard()` (not its own
    reimplementation) to fold a matched proxy_host+guest pair into one row instead of listing it
    twice — editing that row always targets the proxy_host side, matching the exact precedence
    `dashboard_view.py` already applies on the live tile. Kept separate from `repository.py` since
    nothing here runs outside an explicit admin action.
  - `timeutil.py` — **always** use `utcnow()` from here for anything stored in or compared against
    the DB. SQLite has no tz-aware storage — a value written tz-aware comes back naive on read, so
    every timestamp in this app is naive-but-implicitly-UTC. Mixing `datetime.now(timezone.utc)`
    back in will raise `TypeError: can't compare offset-naive and offset-aware datetimes`.
- `app/logo_matching.py` — pure function `match_logo(candidates, logos: list[LogoCandidate])`, no
  DB/ORM import (mirrors `merge.py`'s testability). Case-insensitive substring match; the longest
  matching keyword wins (a specific "plex" beats a generic "web"), ties broken by lowest logo id.
  Match candidates are a `ProxyHost`'s `domain_names` or a `Guest`'s `name` — deliberately never
  `forward_host`, which is frequently a bare IP.
- `app/clients/dashboard_icons.py` — optional convenience client for
  [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) (Apache-2.0): lets an admin
  search/import a ready-made icon instead of sourcing and uploading one manually. Only ever called
  from an explicit admin action (`/api/admin/logos/catalog/*`) — normal operation (polling, serving
  the dashboard) never depends on it or needs internet access.
- `app/dashboard_view.py` — pure function `apply_dashboard_overrides(merged, items, categories)`,
  applies one dashboard's visibility/order/category curation (plus each item's global
  name/url/logo) on top of `build_dashboard()`'s output, and synthesizes a tile (`type: "custom"`)
  for every `custom_service` item directly from its `ResolvedDashboardItem` — `build_dashboard()`
  never sees custom services at all, discovery stays solely NPM/Proxmox's job. A service/guest
  with no matching item on the given dashboard is treated as hidden (this is what makes custom
  dashboards "opt-in" for new discoveries while the default dashboard stays fully auto-populated).
  Output groups tiles into sections: any admin-defined `Category` first, then the two permanent
  built-in sections "Dienste" (services + custom services with no category) and "Infrastruktur".
- `app/auth/` — `security.py` (argon2 hashing — always does the hashing work even for a missing
  user/password, to avoid a timing oracle), `oidc.py` (Authlib OIDC client, generic/config-driven;
  `provision_user_from_oidc_claims` is deliberately DB-only/no-HTTP so it's unit-testable without
  mocking Authlib), `dependencies.py` (`get_current_user`, `require_admin`, `require_csrf`),
  `bootstrap.py` (first-admin creation), `routes.py` (`/api/auth/*`).
  - Sessions are DB-backed (`Session` model), not JWT — the cookie holds a random token, only its
    sha256 lives in the DB, so a DB dump can't be replayed as a live session. Logout = row delete.
  - CSRF is double-submit-cookie based and applied **only to mutating routes** (`Depends(require_csrf)`
    added per-route, not router-wide) — GETs, including admin-only GETs, don't need it.
  - Starlette's `SessionMiddleware` (added in `main.py`) holds only the transient OIDC
    state/nonce during the login redirect — it is unrelated to the app's own login session.
- `app/routers/admin.py` — everything under `/api/admin`, gated by `require_admin` at the router
  level and `require_csrf` per mutating route. Never creates `ProxyHost`/`Guest` rows — discovery
  stays solely the pollers' job; this manages users, dashboard curation, the logo library, and
  the "Dienste" surface: `PATCH /services/{kind}/{id}` (global logo/name/url on a proxy_host/guest)
  and `/custom-services` CRUD (services with no NPM/Proxmox counterpart at all).
- `app/main.py` — wiring: NPM and Proxmox are polled by two **independent** loops
  (`npm_poll_loop()`/`proxmox_poll_loop()`, each just `poll_*_once()` + `asyncio.sleep(settings.*_poll_interval_seconds)`)
  rather than one combined cycle — Proxmox (CPU/RAM/status) polls much faster by default
  (`PROXMOX_POLL_INTERVAL_SECONDS`, default 5s) than NPM (`NPM_POLL_INTERVAL_SECONDS`, default
  60s, since the proxy host list/online-flag rarely changes and there's no reason to hit NPM's
  login+list endpoints every few seconds). Each persists via `app/db/repository.py`
  (conditionally, per the "only on success" rule above), calls `ensure_default_dashboard_items`,
  then `await ws_manager.broadcast()`. `_build_dashboard_payload(session, user)` is the one place
  that assembles a `GET /api/dashboard` response (`resolve_dashboard_for_user` → `load_proxy_hosts`/
  `load_guests` → `build_dashboard()` → `apply_dashboard_overrides()`) — shared by the HTTP route,
  the websocket's initial snapshot, and every broadcast push, so there is exactly one code path
  that decides what a user's dashboard looks like. `GET /api/dashboard` itself is
  `Depends(get_current_user)`. The module-level `state` dict is purely diagnostic
  (`npm_error`/`proxmox_error`/`generated_at`) — dashboard *content* is fully DB-backed.
  `GET /api/logos/{id}/image` is gated by `get_current_user` only (**not** `require_admin`/
  `admin_router`) — any logged-in user needs to load tile images. `/api/*` routes are included
  before the SPA static mount (ordering matters).
  - `WS /api/ws/dashboard` — live push counterpart to `GET /api/dashboard`. Auth reuses the same
    session cookie via `get_current_user_ws()` (`app/auth/dependencies.py`) — a WebSocket
    handshake has no `Request` to hang a normal `Depends()` off of, so that function opens its
    own short-lived DB session just for the cookie check instead of depending on
    `get_db_session` (which would otherwise stay open for the connection's entire lifetime).
    `DashboardConnectionManager` (in `main.py`) tracks `{websocket: user_id}` and, on
    `broadcast()`, recomputes and sends **each** connected user's own resolved dashboard
    individually (different users can be on different dashboards/tile_size/categories — this can
    never be one shared payload). A dead/erroring socket is dropped from the manager, never
    allowed to break the loop over the others.
- `app/spa_static.py` — `SPAStaticFiles`, falls back to `index.html` for a 404 on a path with no
  file extension in its last segment (i.e. an Angular client route like `/admin/users`) so direct
  loads of those URLs work; a genuinely missing asset (`/foo.js`) still 404s.
- `migrations/` — Alembic, `env.py` overrides `sqlalchemy.url` from `settings.database_path` at
  runtime (not `alembic.ini`'s static value) so `alembic upgrade head` always targets the same DB
  file the app itself uses.

### Frontend (`frontend/`)

Angular (standalone components, `@angular/cdk` for drag-drop), styled via the `@tabler/core` npm
package (its prebuilt CSS/JS bundle, wired into `angular.json`'s `styles`/`scripts` arrays — not a
dedicated Angular wrapper; `tabler-angular` is archived/outdated) plus `@tabler/icons-webfont`.

- `src/app/core/` — `auth.service.ts` (signals for current user; `fetchMe()` on bootstrap),
  `auth.guard.ts`/`admin.guard.ts` (functional `CanActivateFn`s), `auth.interceptor.ts` (attaches
  `X-CSRF-Token` from the `csrf_token` cookie on mutating requests; on a 401, clears the user and
  redirects to `/login`), `dashboard.service.ts` (one-shot `GET /api/dashboard`, used for first
  paint and as the fallback poll), `dashboard-ws.service.ts` (the live-update path: opens
  `/api/ws/dashboard`, exposes the latest push as a `data` signal plus a `connected` signal;
  reconnects with exponential backoff, capped at 30s, on an unexpected close - the browser attaches
  the session cookie to the same-origin websocket handshake automatically, no extra auth wiring
  needed), `admin.service.ts` (thin API wrapper), `models.ts`, `format.ts` (shared tile-formatting
  helpers: byte sizes, status-dot color/title, and the fallback-avatar color/initial for a service
  with no logo assigned).
- `src/app/app.ts`/`app.html` — the shell: renders the Tabler navbar (brand mark + an
  "Einstellungen" link for admins + logout) only when a user is present; otherwise just
  `<router-outlet>` (so `/login` fills the screen).
- `src/app/pages/admin/admin-shell.ts` — the `/admin` parent route's component: a Tabler tab bar
  ("Nutzer" | "Dashboards" | "Dienste" | "Logos") + `<router-outlet>` for the child admin pages
  (`users/`, `dashboards/`, `dashboards/:id`, `services/`, `logos/`) — this tab bar, not a second
  nav layer, is what makes Einstellungen "ein ordentliches Menü". `adminGuard` sits on the parent
  route only; children inherit it.
- `src/app/pages/dashboard/dashboard.ts` — on init, fetches once over plain HTTP for first paint
  (the websocket needs a round-trip to connect+authenticate first), then calls
  `DashboardWsService.connect()` and from then on just applies whatever it pushes (via an
  `effect()` reading its `data` signal) straight onto its own `data` signal — unless `editMode()`
  is true, so a live push mid-drag/rename can never clobber an in-progress local edit (the same
  rule the old polling loop used). A `scheduleFallbackCheck()` timer (cadence = the server's
  `poll_interval_seconds`, i.e. the Proxmox interval) is a safety net only: it does a plain HTTP
  refresh, but *only* when `DashboardWsService.connected()` is currently false - e.g. a proxy that
  strips websocket upgrades, or a connection still reconnecting.
  `service-card`/`infra-card`/`custom-card` render the three tile `type`s
  (`service`/`infrastructure`/`custom`); `service-card`/`infra-card` are a direct port of the old
  vanilla-JS tile templates (same status-dot semantics, same CPU/RAM stat line) — **the tile
  UX/information content is not meant to be redesigned**, only reskinned/prettied in Tabler's
  card + `avatar` classes (logo image if `logo_url` is set, otherwise a deterministic color +
  initial letter via `core/format.ts`); `custom-card` is the same shape minus VM stats, for a
  `CustomService` tile.
- `src/app/pages/admin/services/admin-services.ts` — the "Dienste" page: a table of every
  auto-discovered service (`GET /api/admin/services/discovered`) with editable logo/name/url per
  row (`PATCH /api/admin/services/{kind}/{id}`, global — not per-dashboard), plus full CRUD for
  admin-created custom services (`/api/admin/custom-services`) including a create form. This is
  the one place identity (logo/name/link) is edited; dashboard curation pages don't touch it.
- `src/app/pages/admin/dashboards/admin-dashboard-edit.ts` — the per-dashboard curation UI:
  CDK drag-drop reorder (persists `sort_order` on drop), a visibility switch, and a category
  `<select>` per item, plus an attach-service picker backed by `GET /api/admin/services` (kind
  `proxy_host`/`guest`/`custom_service`) — deliberately has **no** logo/name/url editing of its
  own (see "Dienste" above); a service is called and links to the same thing on every dashboard.
- `src/app/pages/admin/logos/admin-logos.ts` — the logo library page: manual upload (multipart
  `FormData`, no explicit `Content-Type` — the browser sets the multipart boundary) and a
  dashboard-icons catalog search/import (preview images are loaded directly from
  `raw.githubusercontent.com` by the admin's own browser, not proxied through the backend).
- `proxy.conf.json` — used by `ng serve` (`npm start`) so local dev stays same-origin against the
  backend (needed for the session/CSRF cookies to work without CORS complications); `"ws": true`
  on the `/api` entry so the `/api/ws/dashboard` websocket upgrade also proxies correctly.

### Data flow

`npm_poll_loop()`/`proxmox_poll_loop()` (main.py, independent intervals) →
`NpmClient.list_proxy_hosts()`/`ProxmoxClient.list_guests()` (clients) → `app/db/repository.py`
upserts (conditional on success) → `ws_manager.broadcast()` pushes each connected client its own
freshly recomputed dashboard over `/api/ws/dashboard`. Both that push and a plain
`GET /api/dashboard` request go through the same `_build_dashboard_payload()`: resolve the
caller's dashboard → `load_proxy_hosts`/`load_guests` → `build_dashboard()` (merge.py, unchanged)
→ `apply_dashboard_overrides()` (dashboard_view.py, per the caller's resolved dashboard) → JSON →
rendered by the Angular dashboard page, which applies a websocket push immediately or falls back
to polling `GET /api/dashboard` if the websocket isn't currently connected.

### Conventions worth knowing before editing

- Errors from each source are tracked separately (`errors.npm`, `errors.proxmox`) and surfaced via
  the dashboard's error banner — never let one source's failure hide or crash the other's data,
  and never let a failure delete already-persisted rows for that source.
- `build_dashboard` strips `ip_addresses` from the `vm` object embedded in a *matched* service tile
  but keeps it on *unmatched* infrastructure tiles — deliberate: the IP is only useful context when
  there's no domain name already attached to the tile.
- A guest embedded as `vm` inside a matched service tile is controlled solely by that service's own
  `DashboardItem` — the guest's own item (if any) is irrelevant while matched, since there's only
  one combined tile to show or hide.
- New local user accounts are admin-created only (`POST /api/admin/users`) — there is no
  self-registration endpoint, by design.
