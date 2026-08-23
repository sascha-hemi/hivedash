import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AdminService } from '../../../core/admin.service';
import { AdminDashboard } from '../../../core/models';

@Component({
  selector: 'app-admin-dashboards',
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-dashboards.html',
})
export class AdminDashboardsPage implements OnInit {
  private readonly admin = inject(AdminService);

  readonly dashboards = signal<AdminDashboard[]>([]);
  readonly error = signal<string | null>(null);
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
      this.error.set(this.extractError(err, 'Anlegen fehlgeschlagen.'));
    } finally {
      this.creating.set(false);
    }
  }

  async setDefault(dashboard: AdminDashboard): Promise<void> {
    await this.admin.setDefaultDashboard(dashboard.id);
    await this.reload();
  }

  async remove(dashboard: AdminDashboard): Promise<void> {
    if (!confirm(`Dashboard "${dashboard.name}" wirklich löschen?`)) return;
    try {
      await this.admin.deleteDashboard(dashboard.id);
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
