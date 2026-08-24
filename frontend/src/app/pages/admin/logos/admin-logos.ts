import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AdminService } from '../../../core/admin.service';
import { CatalogIconResult, Logo } from '../../../core/models';

@Component({
  selector: 'app-admin-logos',
  imports: [FormsModule, TranslatePipe],
  templateUrl: './admin-logos.html',
})
export class AdminLogosPage implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly translate = inject(TranslateService);

  readonly logos = signal<Logo[]>([]);
  readonly error = signal<string | null>(null);

  // manual upload
  uploadName = '';
  uploadKeywords = '';
  uploadFile: File | null = null;
  readonly uploading = signal(false);

  // catalog import
  catalogQuery = '';
  readonly catalogResults = signal<CatalogIconResult[]>([]);
  readonly searching = signal(false);
  readonly importingSlug = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    this.logos.set(await this.admin.listLogos());
  }

  logoImageUrl(logo: Logo): string {
    return `/api/logos/${logo.id}/image`;
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.uploadFile = input.files?.[0] ?? null;
  }

  async upload(): Promise<void> {
    if (!this.uploadFile || !this.uploadName.trim()) return;
    this.uploading.set(true);
    this.error.set(null);
    try {
      await this.admin.uploadLogo(this.uploadName.trim(), this.uploadKeywords, this.uploadFile);
      this.uploadName = '';
      this.uploadKeywords = '';
      this.uploadFile = null;
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.logos.uploadFailed')));
    } finally {
      this.uploading.set(false);
    }
  }

  async deleteLogo(logo: Logo): Promise<void> {
    if (!confirm(this.translate.instant('admin.logos.confirmDelete', { name: logo.name }))) return;
    try {
      await this.admin.deleteLogo(logo.id);
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.logos.deleteFailed')));
    }
  }

  async searchCatalog(): Promise<void> {
    if (!this.catalogQuery.trim()) {
      this.catalogResults.set([]);
      return;
    }
    this.searching.set(true);
    this.error.set(null);
    try {
      this.catalogResults.set(await this.admin.searchLogoCatalog(this.catalogQuery.trim()));
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.logos.searchFailed')));
    } finally {
      this.searching.set(false);
    }
  }

  async importFromCatalog(result: CatalogIconResult): Promise<void> {
    this.importingSlug.set(result.slug);
    this.error.set(null);
    try {
      await this.admin.importLogoFromCatalog(result.slug);
      await this.reload();
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('admin.logos.importFailed')));
    } finally {
      this.importingSlug.set(null);
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
