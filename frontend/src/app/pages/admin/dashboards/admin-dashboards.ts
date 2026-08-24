import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../../core/admin.service';
import { AdminDashboard } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-admin-dashboards',
  imports: [FormsModule, RouterLink, TranslatePipe],
  templateUrl: './admin-dashboards.html',
})
export class AdminDashboardsPage implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly translate = inject(TranslateService);
  private readonly toast = inject(ToastService);

  readonly dashboards = signal<AdminDashboard[]>([]);
  readonly creating = signal(false);
  newName = '';

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    this.dashboards.set(await this.admin.listDashboards());
  }

  async create(): Promise<void> {
    if (!this.newName.trim()) return;
    this.creating.set(true);
    try {
      await this.admin.createDashboard(this.newName.trim());
      this.newName = '';
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboards.createFailed')));
    } finally {
      this.creating.set(false);
    }
  }

  async setDefault(dashboard: AdminDashboard): Promise<void> {
    await this.admin.setDefaultDashboard(dashboard.id);
    await this.reload();
  }

  async remove(dashboard: AdminDashboard): Promise<void> {
    if (!confirm(this.translate.instant('admin.dashboards.confirmDelete', { name: dashboard.name }))) return;
    try {
      await this.admin.deleteDashboard(dashboard.id);
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.dashboards.deleteFailed')));
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
