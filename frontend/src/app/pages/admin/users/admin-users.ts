import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../../core/admin.service';
import { AdminDashboard, AdminUser } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-admin-users',
  imports: [FormsModule, TranslatePipe],
  templateUrl: './admin-users.html',
})
export class AdminUsersPage implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly translate = inject(TranslateService);
  private readonly toast = inject(ToastService);

  readonly users = signal<AdminUser[]>([]);
  readonly dashboards = signal<AdminDashboard[]>([]);
  readonly creating = signal(false);

  newEmail = '';
  newPassword = '';
  newDisplayName = '';
  newRole: 'admin' | 'user' = 'user';
  newDashboardId: number | null = null;

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    const [users, dashboards] = await Promise.all([
      this.admin.listUsers(),
      this.admin.listDashboards(),
    ]);
    this.users.set(users);
    this.dashboards.set(dashboards);
  }

  async createUser(): Promise<void> {
    this.creating.set(true);
    try {
      await this.admin.createUser({
        email: this.newEmail,
        password: this.newPassword || null,
        display_name: this.newDisplayName || null,
        role: this.newRole,
        dashboard_id: this.newDashboardId,
      });
      this.newEmail = '';
      this.newPassword = '';
      this.newDisplayName = '';
      this.newRole = 'user';
      this.newDashboardId = null;
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.users.createFailed')));
    } finally {
      this.creating.set(false);
    }
  }

  async toggleActive(user: AdminUser): Promise<void> {
    try {
      await this.admin.updateUser(user.id, { is_active: !user.is_active });
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.users.actionFailed')));
    }
  }

  async setRole(user: AdminUser, role: string): Promise<void> {
    try {
      await this.admin.updateUser(user.id, { role });
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.users.actionFailed')));
    }
  }

  async setDashboard(user: AdminUser, dashboardId: string): Promise<void> {
    try {
      await this.admin.updateUser(user.id, {
        dashboard_id: dashboardId ? Number(dashboardId) : null,
      });
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.users.actionFailed')));
    }
  }

  async deleteUser(user: AdminUser): Promise<void> {
    if (!confirm(this.translate.instant('admin.users.confirmDelete', { email: user.email }))) return;
    try {
      await this.admin.deleteUser(user.id);
      await this.reload();
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('admin.users.deleteFailed')));
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
