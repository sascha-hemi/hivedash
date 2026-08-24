import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../../core/admin.service';
import { AdminDashboard, AdminDashboardItem, AvailableService, Category, TileSize } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-admin-dashboard-edit',
  imports: [FormsModule, CdkDropList, CdkDrag, CdkDragHandle, TranslatePipe],
  templateUrl: './admin-dashboard-edit.html',
})
export class AdminDashboardEditPage implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly admin = inject(AdminService);
  private readonly translate = inject(TranslateService);
  private readonly toast = inject(ToastService);

  dashboardId = 0;
  readonly dashboard = signal<AdminDashboard | null>(null);
  readonly items = signal<AdminDashboardItem[]>([]);
  readonly availableServices = signal<AvailableService[]>([]);
  readonly categories = signal<Category[]>([]);
  readonly saving = signal(false);
  readonly savingSettings = signal(false);

  editedName = '';

  attachKind: 'proxy_host' | 'guest' | 'custom_service' = 'proxy_host';
  attachId: number | null = null;

  async ngOnInit(): Promise<void> {
    this.dashboardId = Number(this.route.snapshot.paramMap.get('id'));
    await this.reload();
  }

  async reload(): Promise<void> {
    const [dashboards, items, services, categories] = await Promise.all([
      this.admin.listDashboards(),
      this.admin.listDashboardItems(this.dashboardId),
      this.admin.listAvailableServices(),
      this.admin.listCategories(this.dashboardId),
    ]);
    const dashboard = dashboards.find((d) => d.id === this.dashboardId) ?? null;
    this.dashboard.set(dashboard);
    this.editedName = dashboard?.name ?? '';
    this.items.set(items);
    this.availableServices.set(services);
    this.categories.set(categories);
  }

  async saveName(): Promise<void> {
    const name = this.editedName.trim();
    if (!name || name === this.dashboard()?.name) return;
    this.savingSettings.set(true);
    try {
      await this.admin.renameDashboard(this.dashboardId, name);
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboardEdit.renameFailed')));
    } finally {
      this.savingSettings.set(false);
    }
  }

  async setTileSize(tileSize: string): Promise<void> {
    this.savingSettings.set(true);
    try {
      const dashboard = await this.admin.setTileSize(this.dashboardId, tileSize as TileSize);
      this.dashboard.set(dashboard);
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboardEdit.tileSizeFailed')));
    } finally {
      this.savingSettings.set(false);
    }
  }

  categoryName(categoryId: number | null): string {
    if (categoryId === null) return '';
    return this.categories().find((c) => c.id === categoryId)?.name ?? '';
  }

  async setCategory(item: AdminDashboardItem, categoryId: string): Promise<void> {
    try {
      this.items.set(
        await this.admin.updateDashboardItems(this.dashboardId, [
          { item_id: item.item_id, category_id: categoryId ? Number(categoryId) : null },
        ]),
      );
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboardEdit.categoryAssignFailed')));
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }

  logoImageUrl(logoId: number): string {
    return `/api/logos/${logoId}/image`;
  }

  async drop(event: CdkDragDrop<AdminDashboardItem[]>): Promise<void> {
    const updated = [...this.items()];
    moveItemInArray(updated, event.previousIndex, event.currentIndex);
    this.items.set(updated);

    const updates = updated.map((item, index) => ({ item_id: item.item_id, sort_order: index }));
    this.saving.set(true);
    try {
      this.items.set(await this.admin.updateDashboardItems(this.dashboardId, updates));
    } finally {
      this.saving.set(false);
    }
  }

  async toggleVisible(item: AdminDashboardItem): Promise<void> {
    this.items.set(
      await this.admin.updateDashboardItems(this.dashboardId, [
        { item_id: item.item_id, visible: !item.visible },
      ]),
    );
  }

  async attach(): Promise<void> {
    if (this.attachId == null) return;
    try {
      await this.admin.attachService(this.dashboardId, this.attachKind, this.attachId);
      this.attachId = null;
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboardEdit.addFailed')));
    }
  }
}
