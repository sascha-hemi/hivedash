"""Configuration loaded from environment variables (see .env.example)."""
import os


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Nginx Proxy Manager
    npm_url: str = os.environ.get("NPM_URL", "").rstrip("/")
    npm_email: str = os.environ.get("NPM_EMAIL", "")
    npm_password: str = os.environ.get("NPM_PASSWORD", "")
    npm_verify_ssl: bool = _bool("NPM_VERIFY_SSL", True)

    # Proxmox VE
    proxmox_url: str = os.environ.get("PROXMOX_URL", "").rstrip("/")
    proxmox_token_id: str = os.environ.get("PROXMOX_TOKEN_ID", "")  # e.g. root@pam!dashboard
    proxmox_token_secret: str = os.environ.get("PROXMOX_TOKEN_SECRET", "")
    proxmox_verify_ssl: bool = _bool("PROXMOX_VERIFY_SSL", False)

    # General
    # Split so Proxmox (CPU/RAM/status - the stats that actually change second to second) can be
    # polled much more often than NPM (proxy host list/online-flag - rarely changes, and hitting
    # NPM's login+list endpoints every few seconds would be pointless load for no benefit).
    npm_poll_interval_seconds: int = int(os.environ.get("NPM_POLL_INTERVAL_SECONDS", "60"))
    proxmox_poll_interval_seconds: int = int(os.environ.get("PROXMOX_POLL_INTERVAL_SECONDS", "5"))
    request_timeout_seconds: float = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10"))

    # Database
    database_path: str = os.environ.get("DATABASE_PATH", "data/dashboard.db")

    # Auth / sessions
    cookie_secret: str = os.environ.get("COOKIE_SECRET", "")
    cookie_secure: bool = _bool("COOKIE_SECURE", True)
    session_lifetime_days: int = int(os.environ.get("SESSION_LIFETIME_DAYS", "30"))
    public_base_url: str = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    bootstrap_admin_email: str = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "")
    bootstrap_admin_password: str = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")

    # OIDC (generic, e.g. Authentik)
    oidc_issuer: str = os.environ.get("OIDC_ISSUER", "").rstrip("/")
    oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "")
    oidc_client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "")

    # Logo library: auto-download a matching icon from the dashboard-icons catalog for any
    # service with no local logo match yet. Set to false for fully offline polling.
    logo_catalog_auto_import: bool = _bool("LOGO_CATALOG_AUTO_IMPORT", True)

    @property
    def npm_enabled(self) -> bool:
        return bool(self.npm_url and self.npm_email and self.npm_password)

    @property
    def proxmox_enabled(self) -> bool:
        return bool(self.proxmox_url and self.proxmox_token_id and self.proxmox_token_secret)

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret and self.public_base_url)


settings = Settings()
