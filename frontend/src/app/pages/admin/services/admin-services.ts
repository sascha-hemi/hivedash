import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../../core/admin.service';
import { CustomService, DiscoveredService, Logo } from '../../../core/models';

@Component({
  selector: 'app-admin-services',
  imports: [FormsModule, TranslatePipe],
  templateUrl: './admin-services.html',
})
export class AdminServicesPage implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly translate = inject(TranslateService);

  readonly discovered = signal<DiscoveredService[]>([]);
  readonly customServices = signal<CustomService[]>([]);
  readonly logos = signal<Logo[]>([]);
  readonly error = signal<string | null>(null);
  readonly creating = signal(false);

  newName = '';
  newUrl = '';
  newLogoId: number | null = null;

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    const [discovered, customServices, logos] = await Promise.all([
      this.admin.listDiscoveredServices(),
      this.admin.listCustomServices(),
      this.admin.listLogos(),
    ]);
    this.discovered.set(discovered);
    this.customServices.set(customServices);
    this.logos.set(logos);
  }

  logoImageUrl(logoId: number): string {
    return `/api/logos/${logoId}/image`;
  }

  badgeLabel(service: DiscoveredService): string {
    if (service.kind === 'proxy_host' && service.secondary_label) return this.translate.instant('admin.services.combinedBadge');
    return this.translate.instant(service.kind === 'proxy_host' ? 'admin.services.npmBadge' : 'admin.services.proxmoxBadge');
  }

  async setDiscoveredName(service: DiscoveredService, name: string): Promise<void> {
    try {
      await this.admin.updateService(service.kind, service.id, { custom_name: name || null });
      service.custom_name = name || null;
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.renameFailed')));
    }
  }

  async setDiscoveredUrl(service: DiscoveredService, url: string): Promise<void> {
    try {
      await this.admin.updateService(service.kind, service.id, { custom_url: url || null });
      service.custom_url = url || null;
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.urlSaveFailed')));
    }
  }

  async setDiscoveredLogo(service: DiscoveredService, logoId: string): Promise<void> {
    try {
      const id = logoId ? Number(logoId) : null;
      await this.admin.updateService(service.kind, service.id, { logo_id: id });
      service.logo_id = id;
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.logoAssignFailed')));
    }
  }

  async createCustomService(): Promise<void> {
    const name = this.newName.trim();
    if (!name) return;
    this.creating.set(true);
    this.error.set(null);
    try {
      await this.admin.createCustomService({
        name,
        url: this.newUrl.trim() || null,
        logo_id: this.newLogoId,
      });
      this.newName = '';
      this.newUrl = '';
      this.newLogoId = null;
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.createFailed')));
    } finally {
      this.creating.set(false);
    }
  }

  async setCustomName(service: CustomService, name: string): Promise<void> {
    if (!name.trim()) return;
    try {
      await this.admin.updateCustomService(service.id, { name: name.trim() });
      service.name = name.trim();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.renameFailed')));
    }
  }

  async setCustomUrl(service: CustomService, url: string): Promise<void> {
    try {
      await this.admin.updateCustomService(service.id, { url: url || null });
      service.url = url || null;
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.urlSaveFailed')));
    }
  }

  async setCustomLogo(service: CustomService, logoId: string): Promise<void> {
    try {
      const id = logoId ? Number(logoId) : null;
      await this.admin.updateCustomService(service.id, { logo_id: id });
      service.logo_id = id;
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.logoAssignFailed')));
    }
  }

  async deleteCustomService(service: CustomService): Promise<void> {
    if (!confirm(this.translate.instant('admin.services.confirmDeleteCustom', { name: service.name }))) return;
    try {
      await this.admin.deleteCustomService(service.id);
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.services.deleteFailed')));
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
