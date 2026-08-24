export interface CurrentUser {
  id: number;
  email: string;
  display_name: string | null;
  role: 'admin' | 'user';
  locale: string | null;
  // false for an OIDC-provisioned account - it has no local password to change at all.
  has_password: boolean;
}

export interface VmStats {
  vmid: number;
  name: string;
  node: string;
  kind: 'qemu' | 'lxc';
  status: string;
  cpu: number | null;
  mem: number | null;
  maxmem: number | null;
}

export type TileSize = 'small' | 'medium' | 'large';

export interface ServiceTileBase {
  id: number;
  name: string;
  domain_names: string[];
  href: string | null;
  forward_host: string;
  forward_port: number;
  enabled: boolean;
  online: boolean | null;
  vm: VmStats | null;
  logo_url: string | null;
}

export interface InfrastructureTileBase extends VmStats {
  ip_addresses: string[];
  logo_url: string | null;
  href: string | null;
}

/** Every tile in a DashboardSection carries these regardless of underlying kind, so edit mode
 * can drag/PATCH it without caring whether it's a service or a guest. `type` is redeclared with
 * its own literal on each concrete type below (not inherited as the union here) so `Tile` stays a
 * proper discriminated union - narrowing on `tile.type === 'service'` needs each branch to have a
 * distinct literal, not the same `'service' | 'infrastructure'` on both. */
export interface TileMeta {
  item_id: number;
  category_id: number | null;
}

export interface CustomTileBase {
  id: number;
  name: string;
  href: string | null;
  logo_url: string | null;
}

export type ServiceTile = ServiceTileBase & TileMeta & { type: 'service' };
export type InfrastructureTile = InfrastructureTileBase & TileMeta & { type: 'infrastructure' };
export type CustomTile = CustomTileBase & TileMeta & { type: 'custom' };
export type Tile = ServiceTile | InfrastructureTile | CustomTile;

export interface DashboardSection {
  id: number | null;
  name: string;
  tiles: Tile[];
}

export interface DashboardResponse {
  generated_at: string | null;
  poll_interval_seconds: number;
  dashboard: { id: number; name: string; tile_size: TileSize };
  sections: DashboardSection[];
  errors: { npm: string | null; proxmox: string | null };
}

export interface AdminUser {
  id: number;
  email: string;
  display_name: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  dashboard_id: number | null;
}

export interface AdminDashboard {
  id: number;
  name: string;
  is_default: boolean;
  tile_size: TileSize;
}

export interface AdminDashboardItem {
  item_id: number;
  kind: 'proxy_host' | 'guest' | 'custom_service';
  label: string;
  visible: boolean;
  sort_order: number;
  category_id: number | null;
  service_kind: 'proxy_host' | 'guest' | 'custom_service';
  service_id: number;
  logo_id: number | null;
}

export interface Category {
  id: number;
  name: string;
  sort_order: number;
}

export interface AvailableService {
  kind: 'proxy_host' | 'guest' | 'custom_service';
  id: number;
  label: string;
}

/** A service the admin created directly (no NPM/Proxmox counterpart) - configured on the
 * "Dienste" admin page alongside identity overrides for auto-discovered services. */
export interface CustomService {
  id: number;
  name: string;
  url: string | null;
  logo_id: number | null;
}

/** An auto-discovered proxy_host/guest with its current global identity override, for the
 * "Dienste" admin page - independent of any dashboard attachment. A proxy_host matched to a
 * guest (see app.merge's IP-matching) is folded into one row here: `label` prefers the guest's
 * own name over the NPM subdomain (the same default the live tile itself uses), with
 * `secondary_label` carrying the subdomain for context - the guest never appears as its own row. */
export interface DiscoveredService {
  kind: 'proxy_host' | 'guest';
  id: number;
  label: string;
  secondary_label: string | null;
  custom_name: string | null;
  custom_url: string | null;
  logo_id: number | null;
}

export interface Logo {
  id: number;
  name: string;
  keywords: string[];
  content_type: string;
}

export interface CatalogIconResult {
  slug: string;
  aliases: string[];
  preview_url: string;
}
