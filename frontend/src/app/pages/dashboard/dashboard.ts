import {
  CdkDrag,
  CdkDragDrop,
  CdkDragHandle,
  CdkDropList,
  CdkDropListGroup,
  moveItemInArray,
  transferArrayItem,
} from '@angular/cdk/drag-drop';
import { Component, OnDestroy, OnInit, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { DashboardService } from '../../core/dashboard.service';
import { DashboardWsService } from '../../core/dashboard-ws.service';
import { DashboardResponse, DashboardSection, Tile, TileSize } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { SearchBar } from '../../search/search-bar';
import { CustomCard } from './custom-card';
import { InfraCard } from './infra-card';
import { ServiceCard } from './service-card';

const TILE_COLUMN_CLASSES: Record<TileSize, string> = {
  small: 'col-6 col-md-3 col-xl-2',
  medium: 'col-sm-6 col-lg-4 col-xl-3',
  large: 'col-sm-12 col-lg-6 col-xl-4',
};

@Component({
  selector: 'app-dashboard-page',
  imports: [
    ServiceCard,
    InfraCard,
    CustomCard,
    FormsModule,
    CdkDropList,
    CdkDropListGroup,
    CdkDrag,
    CdkDragHandle,
    TranslatePipe,
    SearchBar,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit, OnDestroy {
  private readonly dashboardService = inject(DashboardService);
  private readonly adminService = inject(AdminService);
  private readonly translate = inject(TranslateService);
  private readonly toast = inject(ToastService);
  protected readonly ws = inject(DashboardWsService);
  protected readonly auth = inject(AuthService);

  private fallbackTimer: ReturnType<typeof setTimeout> | undefined;
  private destroyed = false;
  // Edge-triggered: a toast fires once when a source's error message first appears or changes,
  // never again for the same still-ongoing failure (every poll would otherwise spam a new toast
  // for as long as e.g. Proxmox stays unreachable). Tracked separately from `hasLoadError` below,
  // which is about the frontend's own request to the backend rather than a data source.
  private lastNpmError: string | null = null;
  private lastProxmoxError: string | null = null;
  private hasLoadError = false;

  readonly data = signal<DashboardResponse | null>(null);
  readonly editMode = signal(false);
  readonly savingEdit = signal(false);

  newCategoryName = '';

  constructor() {
    // live push from the server (see app.main's DashboardConnectionManager) - applied straight
    // onto `data` unless we're mid-edit, same rule the old polling loop used to avoid clobbering
    // an in-progress drag/rename with a stale-relative-to-it server snapshot.
    effect(() => {
      const pushed = this.ws.data();
      if (pushed && !this.editMode()) {
        this.data.set(pushed);
        this.hasLoadError = false;
      }
    });

    effect(() => {
      const d = this.data();
      if (!d) return;
      this.toastOnSourceErrorChange('NPM', d.errors.npm, () => this.lastNpmError, (v) => (this.lastNpmError = v));
      this.toastOnSourceErrorChange(
        'Proxmox', d.errors.proxmox, () => this.lastProxmoxError, (v) => (this.lastProxmoxError = v),
      );
    });
  }

  private toastOnSourceErrorChange(
    label: string,
    message: string | null,
    getLast: () => string | null,
    setLast: (value: string | null) => void,
  ): void {
    if (message && message !== getLast()) {
      this.toast.show(`${label}: ${message}`);
    }
    setLast(message);
  }

  ngOnInit(): void {
    this.refresh(); // first paint over plain HTTP, before the websocket has connected/authenticated
    this.ws.connect();
    this.scheduleFallbackCheck();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    if (this.fallbackTimer) clearTimeout(this.fallbackTimer);
    this.ws.disconnect();
  }

  private async refresh(): Promise<void> {
    try {
      const data = await this.dashboardService.fetch();
      if (this.destroyed) return;
      this.data.set(data);
      this.hasLoadError = false;
    } catch {
      if (this.destroyed) return;
      // Edge-triggered like the NPM/Proxmox toasts above - the fallback timer retries this
      // every poll interval while the websocket is down, and a still-unreachable backend
      // shouldn't spam a new toast on every single retry.
      if (!this.hasLoadError) {
        this.toast.show(this.translate.instant('dashboard.apiUnreachable'));
      }
      this.hasLoadError = true;
    }
  }

  /** Safety net only - the websocket is the primary update path. Periodically checks whether it's
   * actually connected, and only falls back to an HTTP refresh while it isn't (e.g. a proxy that
   * doesn't forward websocket upgrades, or a dropped connection still reconnecting). */
  private scheduleFallbackCheck(): void {
    const interval = Math.max((this.data()?.poll_interval_seconds || 5) * 1000, 5000);
    this.fallbackTimer = setTimeout(async () => {
      if (this.destroyed) return;
      if (!this.ws.connected() && !this.editMode()) {
        await this.refresh();
      }
      this.scheduleFallbackCheck();
    }, interval);
  }

  get generatedAtLabel(): string {
    const d = this.data();
    if (!d?.generated_at) return this.translate.instant('dashboard.noDataYet');
    const time = new Date(d.generated_at).toLocaleTimeString(this.translate.currentLang() ?? undefined);
    return `${this.translate.instant('dashboard.updated')}: ${time}`;
  }

  tileColumnClass(): string {
    const size = this.data()?.dashboard.tile_size ?? 'medium';
    return TILE_COLUMN_CLASSES[size];
  }

  hasCategories(): boolean {
    return this.data()?.sections.some((s) => s.id !== null) ?? false;
  }

  /** The two built-in sections arrive from the backend as the fixed strings "Dienste"/
   * "Infrastruktur" (see app.dashboard_view - never localized server-side); a custom category's
   * name is arbitrary admin-authored text and is shown exactly as entered, untranslated. */
  sectionLabel(section: DashboardSection): string {
    if (section.id !== null) return section.name;
    const key = section.name === 'Infrastruktur' ? 'dashboard.infrastructure' : 'dashboard.services';
    return this.translate.instant(key);
  }

  async toggleEditMode(): Promise<void> {
    if (this.editMode()) {
      this.editMode.set(false);
      await this.refresh(); // reconcile with the authoritative server state we've been ignoring
    } else {
      this.editMode.set(true);
    }
  }

  async onTileDrop(event: CdkDragDrop<Tile[]>): Promise<void> {
    const current = this.data();
    if (!current) return;

    // without any custom category, the two sections are the fixed Dienste/Infrastruktur split -
    // a service can't semantically become a guest tile or vice versa, so cross-section moves are
    // only meaningful once the admin has created at least one real category.
    if (event.previousContainer !== event.container && !this.hasCategories()) {
      return;
    }

    const targetSection = current.sections.find((s) => s.tiles === event.container.data);
    const sourceSection = current.sections.find((s) => s.tiles === event.previousContainer.data);
    if (!targetSection || !sourceSection) return;

    if (sourceSection === targetSection) {
      moveItemInArray(targetSection.tiles, event.previousIndex, event.currentIndex);
    } else {
      transferArrayItem(
        sourceSection.tiles,
        targetSection.tiles,
        event.previousIndex,
        event.currentIndex,
      );
    }
    this.data.set({ ...current, sections: [...current.sections] });

    const updates = targetSection.tiles.map((tile, index) => ({
      item_id: tile.item_id,
      sort_order: index,
      ...(sourceSection !== targetSection ? { category_id: targetSection.id } : {}),
    }));
    if (sourceSection !== targetSection) {
      updates.push(
        ...sourceSection.tiles.map((tile, index) => ({ item_id: tile.item_id, sort_order: index })),
      );
    }

    this.savingEdit.set(true);
    try {
      await this.adminService.updateDashboardItems(current.dashboard.id, updates);
    } catch {
      this.toast.show(this.translate.instant('dashboard.saveFailedReload'), 'warning');
    } finally {
      this.savingEdit.set(false);
    }
  }

  async addCategory(): Promise<void> {
    const name = this.newCategoryName.trim();
    const dashboardId = this.data()?.dashboard.id;
    if (!name || !dashboardId) return;
    this.newCategoryName = '';
    try {
      await this.adminService.createCategory(dashboardId, name);
      await this.refresh();
    } catch {
      this.toast.show(this.translate.instant('dashboard.createFailed'), 'warning');
    }
  }

  async renameCategory(section: DashboardSection, name: string): Promise<void> {
    const dashboardId = this.data()?.dashboard.id;
    if (section.id === null || !dashboardId || !name.trim()) return;
    try {
      await this.adminService.updateCategory(dashboardId, section.id, { name: name.trim() });
      section.name = name.trim();
    } catch {
      this.toast.show(this.translate.instant('dashboard.renameFailed'), 'warning');
    }
  }

  async deleteCategory(section: DashboardSection): Promise<void> {
    const dashboardId = this.data()?.dashboard.id;
    if (section.id === null || !dashboardId) return;
    if (!confirm(this.translate.instant('dashboard.deleteCategoryConfirm', { name: section.name }))) return;
    try {
      await this.adminService.deleteCategory(dashboardId, section.id);
      await this.refresh();
    } catch {
      this.toast.show(this.translate.instant('dashboard.deleteFailed'), 'warning');
    }
  }

  async moveCategory(section: DashboardSection, direction: -1 | 1): Promise<void> {
    const dashboardId = this.data()?.dashboard.id;
    if (section.id === null || !dashboardId) return;
    try {
      const categories = await this.adminService.listCategories(dashboardId);
      const index = categories.findIndex((c) => c.id === section.id);
      const neighborIndex = index + direction;
      if (index === -1 || neighborIndex < 0 || neighborIndex >= categories.length) return;

      const current = categories[index];
      const neighbor = categories[neighborIndex];
      await this.adminService.updateCategory(dashboardId, current.id, { sort_order: neighbor.sort_order });
      await this.adminService.updateCategory(dashboardId, neighbor.id, { sort_order: current.sort_order });
      await this.refresh();
    } catch {
      this.toast.show(this.translate.instant('dashboard.moveFailed'), 'warning');
    }
  }
}
