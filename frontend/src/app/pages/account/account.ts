import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AuthService } from '../../core/auth.service';
import { VersionInfo } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { VersionService } from '../../core/version.service';
import { LanguageSwitcher } from '../../i18n/language-switcher';

/** Accessible to every logged-in user (authGuard, not adminGuard) - language choice and password
 * change are self-service, independent of role. This is deliberately separate from the admin
 * "Einstellungen" area, which only admins can reach. */
@Component({
  selector: 'app-account',
  imports: [FormsModule, TranslatePipe, LanguageSwitcher, RouterLink],
  templateUrl: './account.html',
})
export class AccountPage implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly translate = inject(TranslateService);
  private readonly toast = inject(ToastService);
  private readonly versionService = inject(VersionService);

  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  readonly saving = signal(false);
  readonly version = signal<VersionInfo | null>(null);

  async ngOnInit(): Promise<void> {
    this.version.set(await this.versionService.fetch().catch(() => null));
  }

  async changePassword(): Promise<void> {
    if (!this.newPassword) {
      this.toast.show(this.translate.instant('account.passwordEmpty'));
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      this.toast.show(this.translate.instant('account.passwordMismatch'));
      return;
    }

    this.saving.set(true);
    try {
      await this.auth.changePassword(this.currentPassword, this.newPassword);
      this.currentPassword = '';
      this.newPassword = '';
      this.confirmPassword = '';
      this.toast.show(this.translate.instant('account.passwordChanged'), 'success');
    } catch (err) {
      this.toast.show(this.extractError(err, this.translate.instant('account.changeFailed')));
    } finally {
      this.saving.set(false);
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
