import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AuthService } from '../../core/auth.service';
import { LanguageSwitcher } from '../../i18n/language-switcher';

/** Accessible to every logged-in user (authGuard, not adminGuard) - language choice and password
 * change are self-service, independent of role. This is deliberately separate from the admin
 * "Einstellungen" area, which only admins can reach. */
@Component({
  selector: 'app-account',
  imports: [FormsModule, TranslatePipe, LanguageSwitcher],
  templateUrl: './account.html',
})
export class AccountPage {
  protected readonly auth = inject(AuthService);
  private readonly translate = inject(TranslateService);

  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal(false);

  async changePassword(): Promise<void> {
    this.error.set(null);
    this.success.set(false);

    if (!this.newPassword) {
      this.error.set(this.translate.instant('account.passwordEmpty'));
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      this.error.set(this.translate.instant('account.passwordMismatch'));
      return;
    }

    this.saving.set(true);
    try {
      await this.auth.changePassword(this.currentPassword, this.newPassword);
      this.currentPassword = '';
      this.newPassword = '';
      this.confirmPassword = '';
      this.success.set(true);
    } catch (err) {
      this.error.set(this.extractError(err, this.translate.instant('account.changeFailed')));
    } finally {
      this.saving.set(false);
    }
  }

  private extractError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
