export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

/** Tabler's status-dot component takes a bg-{color} utility class. */
export function statusDotClass(status: string | boolean | null | undefined): string {
  if (status === 'running' || status === true) return 'bg-green';
  if (status === 'stopped' || status === false) return 'bg-red';
  return 'bg-secondary';
}

export function statusDotTitle(status: boolean | null | undefined): string {
  if (status === null || status === undefined) return 'Status unbekannt';
  return status ? 'online' : 'offline';
}

/** Fallback avatar for a service/guest with no logo assigned - deterministic per name so a tile
 * doesn't change color on every poll refresh. */
const AVATAR_COLOR_CLASSES = [
  'bg-blue-lt', 'bg-azure-lt', 'bg-purple-lt', 'bg-pink-lt', 'bg-red-lt',
  'bg-orange-lt', 'bg-yellow-lt', 'bg-lime-lt', 'bg-green-lt', 'bg-teal-lt', 'bg-cyan-lt',
];

export function avatarColorClass(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLOR_CLASSES[hash % AVATAR_COLOR_CLASSES.length];
}

export function initials(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?';
}

/** "qemu" is the Proxmox API's internal guest type name - "VM" is what a user actually means. */
export function kindLabel(kind: string): string {
  return kind === 'qemu' ? 'VM' : kind.toUpperCase();
}
