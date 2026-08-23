import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AdminService } from '../../../core/admin.service';
import { AdminDashboard, AdminUser } from '../../../core/models';

@Component({
  selector: 'app-admin-users',
  imports: [FormsModule],
  templateUrl: './admin-users.html',
})
export class AdminUsersPage implements OnInit {
  private readonly admin = inject(AdminService);

  readonly users = signal<AdminUser[]>([]);
  readonly dashboards = signal<AdminDashboard[]>([]);
  readonly error = signal<string | null>(null);
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
    this.error.set(null);
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
      this.error.set(this.extractError(err, 'Anlegen fehlgeschlagen.'));
    } finally {
      this.creating.set(false);
    }
  }

  async toggleActive(user: AdminUser): Promise<void> {
    try {
      await this.admin.updateUser(user.id, { is_active: !user.is_active });
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, 'Aktion fehlgeschlagen.'));
    }
  }

  async setRole(user: AdminUser, role: string): Promise<void> {
    try {
      await this.admin.updateUser(user.id, { role });
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, 'Aktion fehlgeschlagen.'));
    }
  }

  async setDashboard(user: AdminUser, dashboardId: string): Promise<void> {
    try {
      await this.admin.updateUser(user.id, {
        dashboard_id: dashboardId ? Number(dashboardId) : null,
      });
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, 'Aktion fehlgeschlagen.'));
    }
  }

  async deleteUser(user: AdminUser): Promise<void> {
    if (!confirm(`${user.email} wirklich löschen?`)) return;
    try {
      await this.admin.deleteUser(user.id);
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, 'Löschen fehlgeschlagen.'));
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
